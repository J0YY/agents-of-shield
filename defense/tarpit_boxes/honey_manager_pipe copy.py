import asyncio
import libvirt
import uuid
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# =================CONFIGURATION=================
LISTEN_PORT = 2222          # Port to trap attackers (Redirect Host:22 -> Host:2222 via iptables)
MASTER_VM = "tarpit_vm"   # The defined "Golden Image" VM in Libvirt
POOL_PATH = "/var/lib/libvirt/images/"
MAX_HOT_VMS = 10            # Max simultaneous attacks
PERSISTENCE_MINUTES = 10    # Time to keep VM alive after disconnect
# ===============================================

class VMManager:
    def __init__(self):
        self.conn = libvirt.open("qemu:///system")
        self.warm_vm = None
        self.hot_vms = {}  # {client_ip: {'vm_obj': domain, 'ip': str, 'last_seen': timestamp, 'id': str}}
        self.lock = asyncio.Lock()

    def _create_overlay_disk(self, run_id):
        """Creates a temporary QCOW2 overlay so we don't touch the master image"""
        dom = self.conn.lookupByName(MASTER_VM)
        raw_xml = dom.XMLDesc(0)
        tree = ET.fromstring(raw_xml)
        source_file = tree.find("./devices/disk/source").get("file")

        new_file = os.path.join(POOL_PATH, f"trap_{run_id}.qcow2")

        subprocess.run(
            ["qemu-img", "create", "-f", "qcow2", "-b", source_file, "-F", "qcow2", new_file],
            check=True,
        )
        return new_file

    def _create_transient_vm(self):
        """Creates a throwaway VM based on the Master XML"""
        run_id = str(uuid.uuid4())[:8]
        new_disk = self._create_overlay_disk(run_id)

        dom = self.conn.lookupByName(MASTER_VM)
        xml = dom.XMLDesc(0)
        tree = ET.fromstring(xml)

        name_tag = tree.find("name")
        name_tag.text = f"trap_{run_id}"
        uuid_tag = tree.find("uuid")
        tree.remove(uuid_tag)

        disk_source = tree.find("./devices/disk/source")
        disk_source.set("file", new_disk)

        mac_tag = tree.find("./devices/interface/mac")
        if mac_tag is not None:
            tree.find("./devices/interface").remove(mac_tag)

        new_xml = ET.tostring(tree).decode()
        new_dom = self.conn.createXML(new_xml, 0)

        print(f"[+] Spun up instance: trap_{run_id}")
        return new_dom, run_id, new_disk

    async def get_vm_ip(self, dom):
        """Waits for QEMU Guest Agent to report an IP"""
        await asyncio.sleep(5)
        for _ in range(30):
            try:
                if dom.isActive() == 0:
                    return None
                ifaces = dom.interfaceAddresses(
                    libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT, 0
                )
                for (_name, val) in ifaces.items():
                    for addr in val["addrs"]:
                        if (
                            addr["type"] == libvirt.VIR_IP_ADDR_TYPE_IPV4
                            and addr["addr"] != "127.0.0.1"
                        ):
                            return addr["addr"]
            except libvirt.libvirtError:
                pass
            await asyncio.sleep(1)
        return None

    async def ensure_warm_vm(self):
        """Ensures there is always one Warm VM ready to receive an attacker"""
        async with self.lock:
            if self.warm_vm is None:
                print("[*] Creating new Warm VM...")
                try:
                    dom, run_id, disk_path = await asyncio.to_thread(
                        self._create_transient_vm
                    )
                    ip = await self.get_vm_ip(dom)
                    if ip:
                        self.warm_vm = {
                            "dom": dom,
                            "ip": ip,
                            "id": run_id,
                            "disk": disk_path,
                        }
                        print(f"[✓] Warm VM Ready: {ip}")
                    else:
                        print("[!] Warm VM timed out getting IP. Destroying.")
                        await self.cleanup_vm_entry({"dom": dom, "disk": disk_path})
                except Exception as exc:
                    print(f"[!] Error creating Warm VM: {exc}")

    async def cleanup_vm_entry(self, vm_entry):
        """Destroys VM and deletes disk"""
        try:
            if vm_entry["dom"].isActive():
                vm_entry["dom"].destroy()
            print("[-] Destroyed VM")
        except Exception:
            pass

        if os.path.exists(vm_entry["disk"]):
            os.remove(vm_entry["disk"])

    async def cleanup_expired_sessions(self, force=False):
        """Remove hot VMs whose sessions have exceeded their persistence window."""
        now = datetime.now()
        to_remove = []

        for client_ip, vm in self.hot_vms.items():
            if force or now - vm["last_seen"] > timedelta(minutes=PERSISTENCE_MINUTES):
                print(f"[!] Session expired for {client_ip}. Cleaning up.")
                to_remove.append(client_ip)

        for ip in to_remove:
            await self.cleanup_vm_entry(self.hot_vms[ip])
            del self.hot_vms[ip]

    async def cleanup_loop(self):
        """Background task to periodically remove old sessions."""
        while True:
            await asyncio.sleep(60)
            await self.cleanup_expired_sessions()

    async def get_target_for_client(self, client_ip):
        if client_ip in self.hot_vms:
            vm = self.hot_vms[client_ip]
            vm["last_seen"] = datetime.now()
            print(f"[->] Reconnecting {client_ip} to existing VM {vm['id']}")
            return vm["ip"]

        if len(self.hot_vms) >= MAX_HOT_VMS:
            print(f"[X] Max capacity reached. Dropping {client_ip}")
            return None

        async with self.lock:
            if self.warm_vm:
                target_vm = self.warm_vm
                self.warm_vm = None
                target_vm["last_seen"] = datetime.now()
                self.hot_vms[client_ip] = target_vm

                print(f"[+] Assigned Warm VM {target_vm['id']} to {client_ip}")

                asyncio.create_task(self.ensure_warm_vm())
                return target_vm["ip"]

            print(f"[!] No Warm VM ready for {client_ip}. Please wait.")
            asyncio.create_task(self.ensure_warm_vm())
            return None


manager = VMManager()


async def pipe(reader, writer):
    """Pipes data between two sockets"""
    try:
        while not reader.at_eof():
            data = await reader.read(2048)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle_client(reader, writer):
    client_ip = writer.get_extra_info("peername")[0]
    print(f"[*] Connection from {client_ip}")

    target_ip = await manager.get_target_for_client(client_ip)

    if not target_ip:
        writer.close()
        return

    try:
        remote_reader, remote_writer = await asyncio.open_connection(target_ip, 22)

        task1 = asyncio.create_task(pipe(reader, remote_writer))
        task2 = asyncio.create_task(pipe(remote_reader, writer))

        await asyncio.gather(task1, task2)
    except Exception as exc:
        print(f"[!] Proxy error for {client_ip}: {exc}")
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    asyncio.create_task(manager.cleanup_loop())
    await manager.ensure_warm_vm()

    server = await asyncio.start_server(handle_client, "0.0.0.0", LISTEN_PORT)
    print(f"[*] Honeypot Controller listening on port {LISTEN_PORT}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
        asyncio.run(manager.cleanup_expired_sessions(force=True))

