import asyncio
import libvirt
import uuid
import os
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

import asyncssh

# =================CONFIGURATION=================
LISTEN_PORT = 2222          # Port to trap attackers (Redirect Host:22 -> Host:2222 via iptables)
MASTER_VM = "tarpit_vm"   # The defined "Golden Image" VM in Libvirt
POOL_PATH = "/var/lib/libvirt/images/"
MAX_HOT_VMS = 10            # Max simultaneous attacks
PERSISTENCE_MINUTES = 10    # Time to keep VM alive after disconnect
HOST_KEY_PATH = os.environ.get("TARPIT_HOST_KEY_PATH", "/var/lib/tarpit/ssh_host_key")
SSH_LOG_PATH = os.environ.get("SSH_COMMAND_LOG", "/var/log/tarpit/ssh_commands.log")
# ===============================================

class VMManager:
    def __init__(self):
        self.conn = libvirt.open("qemu:///system")
        self.warm_vm = None
        self.hot_vms = {}  # {client_ip: {'vm_obj': domain, 'ip': str, 'last_seen': timestamp, 'id': str}}
        self.lock = asyncio.Lock()

    def _create_overlay_disk(self, run_id):
        """Creates a temporary QCOW2 overlay so we don't touch the master image"""
        # Get path of master disk from Libvirt XML
        dom = self.conn.lookupByName(MASTER_VM)
        raw_xml = dom.XMLDesc(0)
        tree = ET.fromstring(raw_xml)
        source_file = tree.find("./devices/disk/source").get("file")
        
        new_file = os.path.join(POOL_PATH, f"trap_{run_id}.qcow2")
        
        # qemu-img create -f qcow2 -b <backing_file> -F qcow2 <new_file>
        subprocess.run(["qemu-img", "create", "-f", "qcow2", "-b", source_file, "-F", "qcow2", new_file], check=True)
        return new_file

    def _create_transient_vm(self):
        """Creates a throwaway VM based on the Master XML"""
        run_id = str(uuid.uuid4())[:8]
        new_disk = self._create_overlay_disk(run_id)
        
        # Manipulate XML for the new instance
        dom = self.conn.lookupByName(MASTER_VM)
        xml = dom.XMLDesc(0)
        tree = ET.fromstring(xml)
        
        # 1. Change Name and UUID
        name_tag = tree.find("name")
        name_tag.text = f"trap_{run_id}"
        uuid_tag = tree.find("uuid")
        tree.remove(uuid_tag) # Let Libvirt generate a new one
        
        # 2. Point to the new overlay disk
        disk_source = tree.find("./devices/disk/source")
        disk_source.set("file", new_disk)
        
        # 3. Remove MAC address to generate a new one (prevents IP conflicts)
        mac_tag = tree.find("./devices/interface/mac")
        if mac_tag is not None:
            tree.find("./devices/interface").remove(mac_tag)

        # 4. Boot it (createXML boots a transient domain that disappears on shutdown)
        new_xml = ET.tostring(tree).decode()
        new_dom = self.conn.createXML(new_xml, 0)
        
        print(f"[+] Spun up instance: trap_{run_id}")
        return new_dom, run_id, new_disk

    async def get_vm_ip(self, dom):
        """Waits for QEMU Guest Agent to report an IP"""
        await asyncio.sleep(5)
        for _ in range(30): # Wait up to 30 seconds
            try:
                if dom.isActive() == 0: return None
                ifaces = dom.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT, 0)
                for (name, val) in ifaces.items():
                    for addr in val['addrs']:
                        if addr['type'] == libvirt.VIR_IP_ADDR_TYPE_IPV4 and addr['addr'] != '127.0.0.1':
                            return addr['addr']
            except libvirt.libvirtError:
                pass # Agent might not be ready
            await asyncio.sleep(1)
        return None

    async def ensure_warm_vm(self):
        """Ensures there is always one Warm VM ready to receive an attacker"""
        async with self.lock:
            if self.warm_vm is None:
                print("[*] Creating new Warm VM...")
                try:
                    # Run blocking libvirt calls in a thread to not freeze the network proxy
                    dom, run_id, disk_path = await asyncio.to_thread(self._create_transient_vm)
                    
                    ip = await self.get_vm_ip(dom)
                    if ip:
                        self.warm_vm = {'dom': dom, 'ip': ip, 'id': run_id, 'disk': disk_path}
                        print(f"[✓] Warm VM Ready: {ip}")
                    else:
                        print("[!] Warm VM timed out getting IP. Destroying.")
                        await self.cleanup_vm_entry({'dom': dom, 'disk': disk_path})
                except Exception as e:
                    print(f"[!] Error creating Warm VM: {e}")

    async def cleanup_vm_entry(self, vm_entry):
        """Destroys VM and deletes disk"""
        try:
            if vm_entry['dom'].isActive():
                vm_entry['dom'].destroy() # Hard power off
            print(f"[-] Destroyed VM")
        except: pass
        
        # Delete disk file
        if os.path.exists(vm_entry['disk']):
            os.remove(vm_entry['disk'])

    async def cleanup_expired_sessions(self, force=False):
        """Remove hot VMs whose sessions have exceeded their persistence window."""
        now = datetime.now()
        to_remove = []

        for client_ip, vm in self.hot_vms.items():
            if force or now - vm['last_seen'] > timedelta(minutes=PERSISTENCE_MINUTES):
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
        # 1. Check Persistence
        if client_ip in self.hot_vms:
            vm = self.hot_vms[client_ip]
            vm['last_seen'] = datetime.now() # Refresh timestamp
            print(f"[->] Reconnecting {client_ip} to existing VM {vm['id']}")
            return vm['ip']

        # 2. Check Capacity
        if len(self.hot_vms) >= MAX_HOT_VMS:
            print(f"[X] Max capacity reached. Dropping {client_ip}")
            return None

        # 3. Promote Warm to Hot
        async with self.lock:
            if self.warm_vm:
                target_vm = self.warm_vm
                self.warm_vm = None # Clear warm slot
                
                # Register as Hot
                target_vm['last_seen'] = datetime.now()
                self.hot_vms[client_ip] = target_vm
                
                print(f"[+] Assigned Warm VM {target_vm['id']} to {client_ip}")
                
                # Trigger creation of NEXT warm VM immediately
                asyncio.create_task(self.ensure_warm_vm())
                
                return target_vm['ip']
            else:
                print(f"[!] No Warm VM ready for {client_ip}. Please wait.")
                # Optional: Trigger creation if missing
                asyncio.create_task(self.ensure_warm_vm())
                return None

class CommandLogger:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def log(self, client_ip: str, username: str, line: str) -> None:
        timestamp = datetime.utcnow().isoformat()
        entry = f"{timestamp} {client_ip} {username}: {line}\n"
        async with self._lock:
            await asyncio.to_thread(self._write, entry)

    def _write(self, entry: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry)


def ensure_host_key(path: str) -> str:
    key_path = Path(path)
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key = asyncssh.generate_private_key("ssh-ed25519")
        key.write_private_key_file(str(key_path))
    return str(key_path)


class HoneypotSSHServer(asyncssh.SSHServer):
    def __init__(self, manager: VMManager, logger: CommandLogger):
        self.manager = manager
        self.logger = logger
        self.client_ip = "unknown"
        self.backend_ip = None
        self.username = None
        self.password = None
        self.backend_conn: asyncssh.SSHClientConnection | None = None

    def connection_made(self, conn):
        peer = conn.get_extra_info("peername")
        self.client_ip = peer[0] if peer else "unknown"
        print(f"[*] SSH connection from {self.client_ip}")

    def connection_lost(self, exc):
        if self.backend_conn:
            self.backend_conn.close()
            self.backend_conn = None

    def begin_auth(self, username):
        print(f"[AUTH] begin_auth for {username} from {self.client_ip}")
        # Always require password auth so we can reuse the credentials downstream.
        return True

    def password_auth_supported(self):
        return True

    async def validate_password(self, username, password):
        self.username = username
        self.password = password
        print(f"[AUTH] validate_password called for {username}@{self.client_ip}")
        if not self.backend_ip:
            self.backend_ip = await self.manager.get_target_for_client(self.client_ip)
        if not self.backend_ip:
            print(f"[!] No backend VM available for {self.client_ip}")
            return False
        try:
            print(f"[AUTH] Connecting to backend {self.backend_ip} for {username}")
            self.backend_conn = await asyncssh.connect(
                self.backend_ip,
                username=username,
                password=password,
                known_hosts=None,
                client_keys=None,
            )
            print(f"[+] Authenticated {username}@{self.client_ip}, proxied to {self.backend_ip}")
            return True
        except Exception as exc:
            print(f"[!] Backend auth failed for {username}@{self.client_ip}: {exc}")
            return False

    def session_requested(self):
        print(f"[SESSION] session_requested from {self.client_ip}")
        if not self.backend_conn:
            print("[SESSION] No backend connection yet, rejecting session")
            return None
        return SSHProxySession(self)


class BackendClientSession(asyncssh.SSHClientSession):
    def __init__(self, proxy_session: "SSHProxySession"):
        self.proxy_session = proxy_session

    def data_received(self, data, datatype):
        if self.proxy_session.client_chan:
            self.proxy_session.client_chan.write(data)

    def eof_received(self):
        if self.proxy_session.client_chan:
            self.proxy_session.client_chan.eof()
        return False

    def connection_lost(self, exc):
        if self.proxy_session.client_chan and not self.proxy_session.client_chan.is_closing():
            self.proxy_session.client_chan.close()


class SSHProxySession(asyncssh.SSHServerSession):
    def __init__(self, server: HoneypotSSHServer):
        self.server = server
        self.client_chan: asyncssh.SSHServerChannel | None = None
        self.backend_chan: asyncssh.SSHClientChannel | None = None
        self.command_buffer = ""
        self.pending_pty = None
        self.pending_data: list[bytes] = []
        self.pty_sent = False

    def connection_made(self, chan):
        self.client_chan = chan

    def connection_lost(self, exc):
        if self.backend_chan and not self.backend_chan.is_closing():
            self.backend_chan.close()

    def eof_received(self):
        if self.backend_chan:
            self.backend_chan.eof()
        return False

    async def pty_requested(self, term_type, width, height, pixelwidth, pixelheight, modes):
        self.pending_pty = (term_type, width, height, pixelwidth, pixelheight, modes)
        return await self._handle_pty_request()

    async def shell_requested(self):
        return await self._handle_shell_request()

    async def exec_requested(self, command):
        self._log_line(f"[exec] {command}")
        await self._handle_exec_request(command)
        return True

    def data_received(self, data, datatype):
        payload = data.encode("utf-8") if isinstance(data, str) else data
        self._buffer_and_log(data)
        if self.backend_chan:
            self.backend_chan.write(payload)
        else:
            if payload:
                self.pending_data.append(payload)

    async def _ensure_backend_channel(self):
        if self.backend_chan or not self.server.backend_conn:
            return
        session = BackendClientSession(self)
        print(f"[SESSION] Creating backend channel for {self.server.client_ip}")
        self.backend_chan, _ = await self.server.backend_conn.create_session(session)
        print(f"[SESSION] Backend channel established for {self.server.client_ip}")
        if self.pending_data and self.backend_chan:
            for chunk in self.pending_data:
                self.backend_chan.write(chunk)
            self.pending_data.clear()

    async def _handle_pty_request(self):
        print(f"[PTY] Handling PTY request for {self.server.client_ip}")
        await self._ensure_backend_channel()
        if self.backend_chan and self.pending_pty:
            await self.backend_chan.request_pty(*self.pending_pty)
            self.pty_sent = True
            print(f"[PTY] PTY requested upstream for {self.server.client_ip}")
        else:
            print(f"[PTY] Missing backend channel or PTY params for {self.server.client_ip}")
        return True

    async def _handle_shell_request(self):
        print(f"[SHELL] Handling shell request for {self.server.client_ip}")
        await self._ensure_backend_channel()
        if self.backend_chan:
            if self.pending_pty and not self.pty_sent:
                await self.backend_chan.request_pty(*self.pending_pty)
                self.pty_sent = True
            await self.backend_chan.shell()
            print(f"[SHELL] Shell started for {self.server.client_ip}")
            return True
        print(f"[SHELL] Cannot start shell; backend channel missing for {self.server.client_ip}")
        return False

    async def _handle_exec_request(self, command: str):
        backend_conn = self.server.backend_conn
        if not backend_conn:
            print(f"[EXEC] No backend connection for {self.server.client_ip}")
            if self.client_chan:
                self.client_chan.exit(1)
            return
        result = await backend_conn.run(command, check=False)
        if self.client_chan:
            if result.stdout:
                self.client_chan.write(result.stdout)
            if result.stderr:
                self.client_chan.write(result.stderr)
            self.client_chan.exit(result.exit_status or 0)
        print(f"[EXEC] Completed exec for {self.server.client_ip} with status {result.exit_status}")

    def _buffer_and_log(self, data):
        if not data:
            return
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError:
                data = data.decode("utf-8", errors="ignore")
        self.command_buffer += data
        while "\n" in self.command_buffer:
            line, self.command_buffer = self.command_buffer.split("\n", 1)
            clean = line.replace("\r", "").strip()
            if clean:
                asyncio.get_running_loop().create_task(
                    command_logger.log(
                        self.server.client_ip,
                        self.server.username or "unknown",
                        clean,
                    )
                )

    def _log_line(self, line: str):
        asyncio.get_running_loop().create_task(
            command_logger.log(
                self.server.client_ip,
                self.server.username or "unknown",
                line,
            )
        )

# =================MAIN=================

manager = VMManager()
command_logger = CommandLogger(SSH_LOG_PATH)

async def main():
    asyncio.create_task(manager.cleanup_loop())
    await manager.ensure_warm_vm()

    host_key = ensure_host_key(HOST_KEY_PATH)
    server = await asyncssh.listen(
        "",
        LISTEN_PORT,
        server_factory=lambda: HoneypotSSHServer(manager, command_logger),
        server_host_keys=[host_key],
        #auth_wait_timeout=30,
        keepalive_interval=30,
        compression_algs=None,
    )
    print(f"[*] SSH Honeypot Controller listening on port {LISTEN_PORT}")
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
        asyncio.run(manager.cleanup_expired_sessions(force=True))