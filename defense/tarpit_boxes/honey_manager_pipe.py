import asyncio
import concurrent.futures
import libvirt
import paramiko
import uuid
import os
import socket
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional
import logging

# Enable debug logging to console or file
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("paramiko").setLevel(logging.DEBUG)
# =================CONFIGURATION=================
LISTEN_PORT = 2222          # Port to trap attackers (Redirect Host:22 -> Host:2222 via iptables)
MASTER_VM = "tarpit_vm"   # The defined "Golden Image" VM in Libvirt
POOL_PATH = "/var/lib/libvirt/images/"
MAX_HOT_VMS = 10            # Max simultaneous attacks
PERSISTENCE_MINUTES = 10    # Time to keep VM alive after disconnect

# =================SSH MITM SETTINGS================
HOST_KEY_PATH = "./id_ed25519"  # Path to host key used for attacker-facing SSH
BACKEND_SSH_PORT = 22
BACKEND_USERNAME = "root"
BACKEND_PASSWORD = "root"
BACKEND_KEY_PATH = None      # Optional private key for backend auth
USE_ATTACKER_CREDENTIALS = True  # Flip to True to reuse attacker-supplied creds
CHANNEL_TIMEOUT_SECONDS = 20
RELAY_IDLE_SLEEP = 0.01
# ==================================================

paramiko.util.log_to_file("mitm_debug.log")

def load_host_key():
    if not os.path.exists(HOST_KEY_PATH):
        raise FileNotFoundError(
            f"Host key required for MITM SSH server not found at {HOST_KEY_PATH}"
        )
    key_classes = [
        paramiko.RSAKey,
        getattr(paramiko, "Ed25519Key", None),
        getattr(paramiko, "ECDSAKey", None),
        getattr(paramiko, "DSSKey", None),
    ]
    last_exc = None
    for key_cls in key_classes:
        if key_cls is None:
            continue
        try:
            return key_cls.from_private_key_file(HOST_KEY_PATH)
        except (paramiko.SSHException, ValueError) as exc:
            last_exc = exc
            continue
    raise RuntimeError(
        f"Failed to load host key at {HOST_KEY_PATH}; unsupported format or corrupt file"
    ) from last_exc


HOST_KEY = load_host_key()
# ===============================================
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_HOT_VMS * 2)
STOP_EVENT = threading.Event()
LISTENER_THREAD: Optional[threading.Thread] = None


def send_all(channel: paramiko.Channel, data: bytes, send_fn=None):
    """Ensure the entire payload is delivered to the Paramiko channel."""
    if not data:
        return
    view = memoryview(data)
    sender = send_fn or channel.send
    while view:
        sent = sender(view)
        if sent is None:
            # Paramiko send() returns None on success for str input; treat as all sent.
            break
        if sent == 0:
            raise EOFError("Channel closed while sending.")
        view = view[sent:]

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


class CommandLogger:
    """Very small helper to turn raw keystrokes into readable command logs."""

    def __init__(self, client_ip: str):
        self.client_ip = client_ip
        self._buffer: list[str] = []

    def log_auth(self, username: Optional[str], password: Optional[str]):
        print(f"[{self.client_ip}] AUTH username={username} password={password}")

    def log_exec(self, command: str):
        print(f"[{self.client_ip}] EXEC> {command}")

    def log_event(self, message: str):
        print(f"[{self.client_ip}] {message}")

    def feed_keystrokes(self, payload: bytes):
        text = payload.decode(errors="ignore")
        for ch in text:
            if ch in ("\r", "\n"):
                self._flush_line()
            elif ch == "\x7f":  # Backspace
                if self._buffer:
                    self._buffer.pop()
            elif ch.isprintable():
                self._buffer.append(ch)

    def _flush_line(self):
        if not self._buffer:
            return
        line = "".join(self._buffer).strip()
        if line:
            print(f"[{self.client_ip}] CMD> {line}")
        self._buffer.clear()

    def flush(self):
        self._flush_line()


class HoneypotServerInterface(paramiko.ServerInterface):
    """Paramiko server interface that accepts any attacker and records metadata."""

    def __init__(self, client_ip: str, logger: CommandLogger):
        self.client_ip = client_ip
        self.logger = logger
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.exec_command: Optional[str] = None
        self.pty_params: Optional[dict] = None
        self.shell_requested = False
        self.channel_ready = threading.Event()

    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel):
        self.shell_requested = True
        self.channel_ready.set()
        return True

    def check_channel_exec_request(self, channel, command):
        decoded = command.decode(errors="ignore") if isinstance(command, bytes) else command
        self.exec_command = decoded
        self.logger.log_exec(decoded)
        self.channel_ready.set()
        return True

    def check_channel_pty_request(
        self, channel, term, width, height, pixelwidth, pixelheight, modes
    ):
        self.pty_params = {
            "term": term,
            "width": width,
            "height": height,
            "pixelwidth": pixelwidth,
            "pixelheight": pixelheight,
        }
        return True

    def check_auth_password(self, username, password):
        self.username = username
        self.password = password
        self.logger.log_auth(username, password)
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_publickey(self, username, key):
        self.username = username
        self.logger.log_event(
            f"AUTH publickey user={username} fingerprint={key.get_fingerprint().hex()}"
        )
        return paramiko.AUTH_SUCCESSFUL

    def check_auth_none(self, username):
        self.username = username
        self.logger.log_event(f"AUTH none user={username} (rejecting)")
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password,publickey,none"


def _resolve_backend_credentials(server: HoneypotServerInterface):
    if USE_ATTACKER_CREDENTIALS and server.username:
        if server.password:
            return server.username, server.password, None
        server.logger.log_event(
            "Attacker authentication lacked reusable password; falling back to static creds"
        )
    if BACKEND_USERNAME:
        return BACKEND_USERNAME, BACKEND_PASSWORD, BACKEND_KEY_PATH
    raise RuntimeError("No backend credentials configured and attacker creds disabled.")


def establish_backend_client(target_ip: str, server: HoneypotServerInterface) -> paramiko.SSHClient:
    username, password, key_path = _resolve_backend_credentials(server)
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(
        target_ip,
        port=BACKEND_SSH_PORT,
        username=username,
        password=password,
        key_filename=key_path,
        allow_agent=False,
        gss_auth=False,       # Disable GSSAPI
        gss_kex=False,          # Disable GSSAPI key exchange  
        look_for_keys=False,
        timeout=10,
    )
    server.logger.log_event(f"Connected to backend {target_ip} as {username}")
    transport = ssh_client.get_transport()
    if transport:
        transport.set_keepalive(5)
    return ssh_client


def open_backend_channel(
    backend_client: paramiko.SSHClient, server: HoneypotServerInterface
) -> paramiko.Channel:
    if server.exec_command:
        vm_transport = backend_client.get_transport()
        vm_transport.default_window_size = 2 * 1024 * 1024
        vm_transport.default_max_packet_size = 32768 
        channel = vm_transport.open_session()
        if server.pty_params:
            channel.get_pty(
                term=server.pty_params["term"],
                width=server.pty_params["width"],
                height=server.pty_params["height"],
                width_pixels=server.pty_params["pixelwidth"],
                height_pixels=server.pty_params["pixelheight"],
            )
        channel.exec_command(server.exec_command)
        return channel

    term = "xterm"
    width = 80
    height = 24
    width_pixels = 0
    height_pixels = 0

    if server.pty_params:
        term = server.pty_params["term"]
        width = server.pty_params["width"]
        height = server.pty_params["height"]
        width_pixels = server.pty_params["pixelwidth"]
        height_pixels = server.pty_params["pixelheight"]

    return backend_client.invoke_shell(
        term=term,
        width=width,
        height=height,
        width_pixels=width_pixels,
        height_pixels=height_pixels,
    )


def relay_channels(
    attacker_channel: paramiko.Channel,
    backend_channel: paramiko.Channel,
    logger: CommandLogger,
):
    stop_reason = "unknown"
    try:
        while True:
            transferred = False

            if attacker_channel.recv_ready():
                data = attacker_channel.recv(4096)
                if not data:
                    stop_reason = "attacker EOF"
                    break
                logger.feed_keystrokes(data)
                send_all(backend_channel, data)
                transferred = True

            if backend_channel.recv_ready():
                data = backend_channel.recv(4096)
                if not data:
                    stop_reason = "backend STDOUT EOF"
                    break
                send_all(attacker_channel, data)
                transferred = True

            if backend_channel.recv_stderr_ready():
                data = backend_channel.recv_stderr(4096)
                if not data:
                    stop_reason = "backend STDERR EOF"
                    break
                send_all(attacker_channel, data, send_fn=attacker_channel.send_stderr)
                transferred = True

            if attacker_channel.closed:
                stop_reason = "attacker channel closed flag set"
                break
            if backend_channel.closed:
                stop_reason = "backend channel closed flag set"
                break

            if not transferred:
                if attacker_channel.exit_status_ready():
                    stop_reason = f"attacker exit status {attacker_channel.recv_exit_status()}"
                    break
                if backend_channel.exit_status_ready():
                    stop_reason = f"backend exit status {backend_channel.recv_exit_status()}"
                    break
                time.sleep(RELAY_IDLE_SLEEP)
    except Exception as exc:
        logger.log_event(f"Relay error: {exc}")
        stop_reason = f"exception: {exc}"
    finally:
        logger.log_event(f"Relay stopping ({stop_reason})")
        if backend_channel.exit_status_ready():
            logger.log_event(f"Backend exit status {backend_channel.recv_exit_status()}")
        backend_transport = backend_channel.transport if backend_channel else None
        if backend_transport and backend_transport.saved_exception:
            logger.log_event(
                f"Backend transport exception: {backend_transport.saved_exception!r}"
            )
        attacker_transport = attacker_channel.transport if attacker_channel else None
        if attacker_transport and attacker_transport.saved_exception:
            logger.log_event(
                f"Attacker transport exception: {attacker_transport.saved_exception!r}"
            )
        logger.flush()


def handle_paramiko_proxy(client_sock: socket.socket, client_ip: str, target_ip: str):
    logger = CommandLogger(client_ip)
    transport = None
    backend_client = None
    backend_channel = None
    attacker_channel = None

    try:
        transport = paramiko.Transport(client_sock)
        transport.set_keepalive(30)
        transport.add_server_key(HOST_KEY)
        server = HoneypotServerInterface(client_ip, logger)
        transport.start_server(server=server)

        attacker_channel = transport.accept(CHANNEL_TIMEOUT_SECONDS)
        if attacker_channel is None:
            raise TimeoutError("Attacker failed to open a channel in time.")

        if not server.channel_ready.wait(CHANNEL_TIMEOUT_SECONDS):
            raise TimeoutError("Attacker never requested shell/exec.")

        backend_client = establish_backend_client(target_ip, server)
        backend_channel = open_backend_channel(backend_client, server)

        relay_channels(attacker_channel, backend_channel, logger)
        logger.log_event("Session closed")
    except Exception as exc:
        logger.log_event(f"Session error: {exc}")
        raise
    finally:
        logger.flush()
        if attacker_channel is not None:
            attacker_channel.close()
        if backend_channel is not None:
            backend_channel.close()
        if backend_client is not None:
            backend_client.close()
        if transport is not None:
            transport.close()
            try:
                transport.join(2)
            except Exception:
                pass
        try:
            client_sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        client_sock.close()


def attacker_listener(loop: asyncio.AbstractEventLoop):
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("0.0.0.0", LISTEN_PORT))
    server_sock.listen(100)
    server_sock.settimeout(1.0)
    print(f"[*] Honeypot Controller listening on port {LISTEN_PORT}")

    try:
        while not STOP_EVENT.is_set():
            try:
                client_sock, addr = server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            client_ip = addr[0]
            print(f"[*] Connection from {client_ip}")

            fut = asyncio.run_coroutine_threadsafe(
                manager.get_target_for_client(client_ip), loop
            )

            try:
                target_ip = fut.result()
            except Exception as exc:
                print(f"[!] Failed to assign VM for {client_ip}: {exc}")
                client_sock.close()
                continue

            if not target_ip:
                client_sock.close()
                continue

            try:
                EXECUTOR.submit(handle_paramiko_proxy, client_sock, client_ip, target_ip)
            except Exception as exc:
                print(f"[!] Failed to schedule MITM for {client_ip}: {exc}")
                client_sock.close()
    finally:
        server_sock.close()
        print("[*] Honeypot listener stopped")


async def main():
    global LISTENER_THREAD

    asyncio.create_task(manager.cleanup_loop())
    await manager.ensure_warm_vm()

    loop = asyncio.get_running_loop()
    LISTENER_THREAD = threading.Thread(
        target=attacker_listener,
        args=(loop,),
        name="SSH-MITM-Listener",
        daemon=True,
    )
    LISTENER_THREAD.start()

    # Keep the loop alive; listener thread handles incoming sockets.
    await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        STOP_EVENT.set()
        EXECUTOR.shutdown(wait=False, cancel_futures=True)
        if LISTENER_THREAD is not None:
            LISTENER_THREAD.join(timeout=2)
        try:
            asyncio.run(manager.cleanup_expired_sessions(force=True))
        except RuntimeError:
            # Event loop may already be closed during interpreter shutdown.
            pass

