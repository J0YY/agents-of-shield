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
import sys

# Configure logging to go to stderr (unbuffered, captured by Docker)
#logging.basicConfig(
#    level=logging.INFO,
#    format='[%(asctime)s] %(levelname)s: %(message)s',
#    datefmt='%Y-%m-%d %H:%M:%S',
#    stream=sys.stderr,
#    force=True  # Override any existing config
#)
#logging.getLogger("paramiko").setLevel(logging.WARNING)  # Reduce paramiko noise

# Helper function to ensure print statements are immediately visible in Docker logs
def log_print(*args, **kwargs):
    """Print that flushes immediately to ensure Docker logs capture it"""
    print(*args, **kwargs, flush=True, file=sys.stderr)

def strip_ansi_codes(text: str) -> str:
    """
    Strip all ANSI escape sequences and ASCII representations from text.
    Handles both escape sequences (\x1b[...m) and ASCII representations ([...m, [?2004h], etc.)
    """
    import re
    
    # Pattern to match ANSI escape sequences: \x1b[...m or \033[...m
    # Also matches ASCII representations: [...m or [...h or other CSI terminator letters
    # CSI (Control Sequence Introducer) codes can end with letters: A-Z, a-z, @, etc.
    # Common ones: m (SGR - Select Graphic Rendition), h (SM - Set Mode), l (RM - Reset Mode)
    
    # First, remove actual escape sequences
    text = re.sub(r'\x1b\[[0-9;?]*[A-Za-z@]', '', text)
    text = re.sub(r'\033\[[0-9;?]*[A-Za-z@]', '', text)
    
    # Then remove ASCII representations: [digits/semicolons/question]letter
    # This handles patterns like [01;34m, [0m, [?2004h], [0;, etc.
    # More specific pattern: [ followed by (digits/semicolons/question mark) and ending with a letter
    # This avoids matching regular text in brackets like [hello]
    # Pattern: [ optionally followed by ? then digits/semicolons, ending with A-Za-z@
    text = re.sub(r'\[(?:\?)?[0-9;]*[A-Za-z@]', '', text)
    
    return text

def append_log_line(line: str):
    toks = line.split("RESP>")
    if len(toks) > 1:
        # Extract the response text (everything after "RESP>")
        response_text = toks[1].strip()
        # Strip ANSI codes (should already be stripped, but be safe)
        cleaned_response = strip_ansi_codes(response_text)
        # Ensure log directory exists
        log_dir = "/var/log/tarpitssh"
        os.makedirs(log_dir, exist_ok=True)
        if cleaned_response.startswith("]0;"): cleaned_response = "\n" +cleaned_response[3:]
        if cleaned_response.startswith("Welcome to Ubuntu"):
            with open(f"{log_dir}/honey_manager_paramiko.log", "w") as f:
                f.write(cleaned_response + "\n")
        else:
            with open(f"{log_dir}/honey_manager_paramiko.log", "a") as f:
                f.write(cleaned_response + "\n")

        log_print("[L]", cleaned_response)
    else:
        log_print("[L]", line)

# =================CONFIGURATION=================
LISTEN_PORT = 2222          # Port to trap attackers (Redirect Host:22 -> Host:2222 via iptables)
MASTER_VM = "tarpit_vm"   # The defined "Golden Image" VM in Libvirt
POOL_PATH = "/var/lib/libvirt/images/"
MAX_HOT_VMS = 1            # Max simultaneous attacks
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

#paramiko.util.log_to_file("mitm_debug.log")

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
        """Creates a temporary QCOW2 overlay and configures SSH/network identity"""
        dom = self.conn.lookupByName(MASTER_VM)
        raw_xml = dom.XMLDesc(0)
        tree = ET.fromstring(raw_xml)
        source_file = tree.find("./devices/disk/source").get("file")

        new_file = os.path.join(POOL_PATH, f"trap_{run_id}.qcow2")

        log_print(f"[VM] Creating overlay disk: {new_file}")
        subprocess.run(
            ["qemu-img", "create", "-f", "qcow2", "-b", source_file, "-F", "qcow2", new_file],
            check=True,
        )
        log_print(f"[VM] Overlay disk created successfully")
        
        # QEMU runs as root (configured in qemu.conf), so no special permissions needed
        # Just ensure the file is readable/writable
        os.chmod(new_file, 0o644)  # rw-r--r-- (readable by all, writable by owner)
        
        self._configure_vm_identity(new_file)
        
        return new_file

    def _configure_vm_identity(self, disk_path):
        """Configure SSH server and reset DHCP/machine identity for unique IPs."""
        try:
            cmd = [
                "virt-customize",
                "-a", disk_path,
                # SSH hardening / keepalive settings
                "--run-command", "sed -i 's/^#*ClientAliveInterval.*/ClientAliveInterval 60/' /etc/ssh/sshd_config",
                "--run-command", "sed -i 's/^#*ClientAliveCountMax.*/ClientAliveCountMax 10/' /etc/ssh/sshd_config",
                "--run-command", "grep -q '^ClientAliveInterval' /etc/ssh/sshd_config || echo 'ClientAliveInterval 60' >> /etc/ssh/sshd_config",
                "--run-command", "grep -q '^ClientAliveCountMax' /etc/ssh/sshd_config || echo 'ClientAliveCountMax 10' >> /etc/ssh/sshd_config",
                "--run-command", "sed -i 's/^#*TCPKeepAlive.*/TCPKeepAlive yes/' /etc/ssh/sshd_config",
                "--run-command", "grep -q '^TCPKeepAlive' /etc/ssh/sshd_config || echo 'TCPKeepAlive yes' >> /etc/ssh/sshd_config",
                "--run-command", "sed -i 's/^#*MaxStartups.*/MaxStartups 100:30:200/' /etc/ssh/sshd_config",
                "--run-command", "grep -q '^MaxStartups' /etc/ssh/sshd_config || echo 'MaxStartups 100:30:200' >> /etc/ssh/sshd_config",
                "--run-command", "sed -i 's/^#*MaxSessions.*/MaxSessions 100/' /etc/ssh/sshd_config",
                "--run-command", "grep -q '^MaxSessions' /etc/ssh/sshd_config || echo 'MaxSessions 100' >> /etc/ssh/sshd_config",
                "--run-command", "sed -i 's/^#*MaxAuthTries.*/MaxAuthTries 100/' /etc/ssh/sshd_config",
                "--run-command", "grep -q '^MaxAuthTries' /etc/ssh/sshd_config || echo 'MaxAuthTries 100' >> /etc/ssh/sshd_config",
                "--run-command", "sed -i 's/^#*LoginGraceTime.*/LoginGraceTime 0/' /etc/ssh/sshd_config",
                "--run-command", "grep -q '^LoginGraceTime' /etc/ssh/sshd_config || echo 'LoginGraceTime 0' >> /etc/ssh/sshd_config",
                # Reset DHCP/network identity so every clone gets a fresh IP
                "--run-command", "mkdir -p /var/lib/dhcp /var/lib/dbus",
                "--run-command", "rm -rf /var/lib/dhcp/dhclient*.lease /var/lib/dhcp/dhclient*.leases /var/lib/dhcp/*.lease*",
                "--run-command", "rm -rf /var/lib/NetworkManager/*",
                "--run-command", "rm -f /var/lib/NetworkManager/NetworkManager.state",
                "--run-command", "rm -rf /run/NetworkManager/*",
                "--run-command", "rm -f /etc/machine-id /var/lib/dbus/machine-id",
                "--run-command", "rm -rf /etc/NetworkManager/system-connections/*",
                "--run-command", "systemd-machine-id-setup",
                # Force network interface to use DHCP and renew on boot
                "--run-command", "if [ -f /etc/netplan/*.yaml ]; then rm -f /etc/netplan/*.yaml; fi",
                "--run-command", "echo 'network:\n  version: 2\n  ethernets:\n    enp1s0:\n      dhcp4: true\n      dhcp6: false' > /etc/netplan/01-netcfg.yaml",
                "--run-command", "if [ -d /etc/systemd/network ]; then rm -f /etc/systemd/network/*; fi",
                # Create a systemd service to force DHCP renewal on boot
                "--run-command", "echo '[Unit]\nDescription=Force DHCP Renewal\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=oneshot\nExecStart=/bin/bash -c \"sleep 2; dhclient -r enp1s0 2>/dev/null || true; dhclient enp1s0 2>/dev/null || true; systemctl restart NetworkManager 2>/dev/null || true\"\nRemainAfterExit=yes\n\n[Install]\nWantedBy=multi-user.target' > /etc/systemd/system/dhcp-renew.service",
                "--run-command", "systemctl enable dhcp-renew.service || true",
            ]

            log_print(f"[VM] Configuring VM identity for {os.path.basename(disk_path)}...")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            log_print(f"[VM] VM identity configuration completed")
            
            if result.returncode != 0:
                log_print(f"[!] VM identity customization failed: {result.stderr}")
            else:
                log_print(f"[+] SSH/DHCP identity configured for {os.path.basename(disk_path)}")
        except subprocess.TimeoutExpired:
            log_print("[!] VM identity customization timed out")
        except FileNotFoundError:
            log_print("[!] virt-customize not found; skipping VM identity setup")
        except Exception as exc:
            log_print(f"[!] Failed to customize VM identity: {exc}")

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

        # Generate a unique MAC address for this VM to ensure unique IP assignment
        import random
        mac_address = "52:54:00:%02x:%02x:%02x" % (
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255)
        )
        interface_elem = tree.find("./devices/interface")
        if interface_elem is not None:
            mac_tag = interface_elem.find("mac")
            if mac_tag is not None:
                mac_tag.set("address", mac_address)
            else:
                # Create MAC tag if it doesn't exist
                mac_elem = ET.SubElement(interface_elem, "mac")
                mac_elem.set("address", mac_address)
        log_print(f"[VM] Generated MAC address: {mac_address}")

        new_xml = ET.tostring(tree).decode()
        # Define the domain first (don't start it yet)
        log_print(f"[VM] Defining VM domain: trap_{run_id}")
        new_dom = self.conn.defineXML(new_xml)
        
        # Start the VM - it needs to be running for guest agent to work
        log_print(f"[VM] Starting VM instance: trap_{run_id}")
        new_dom.create()
        log_print(f"[VM] VM instance trap_{run_id} started successfully")

        log_print(f"[+] Spun up instance: trap_{run_id}")
        return new_dom, run_id, new_disk

    async def get_vm_ip(self, dom):
        """Waits for QEMU Guest Agent to report an IP"""
        # Wait a bit for VM to start booting
        log_print("[VM] Waiting 10 seconds for VM to start booting...")
        await asyncio.sleep(10)
        
        log_print("[VM] Starting to query guest agent for IP address...")
        for attempt in range(60):  # Wait up to 60 seconds
            try:
                if dom.isActive() == 0:
                    log_print(f"[!] VM is not active (attempt {attempt + 1}/60)")
                    await asyncio.sleep(1)
                    continue
                
                # Try to get interface addresses via guest agent
                # This will fail if guest agent isn't ready yet, which is expected
                try:
                    ifaces = dom.interfaceAddresses(
                        libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT, 0
                    )
                    for (iface_name, val) in ifaces.items():
                        # Log MAC address for debugging
                        mac = val.get("hwaddr", "unknown")
                        log_print(f"[VM] Interface {iface_name} MAC: {mac}")
                        for addr in val["addrs"]:
                            if (
                                addr["type"] == libvirt.VIR_IP_ADDR_TYPE_IPV4
                                and addr["addr"] != "127.0.0.1"
                            ):
                                log_print(f"[+] Got IP from guest agent: {addr['addr']} (MAC: {mac})")
                                return addr["addr"]
                except libvirt.libvirtError as e:
                    # Guest agent not ready yet - this is normal during boot
                    if "not connected" in str(e).lower() or "not responding" in str(e).lower():
                        if attempt % 10 == 0:  # Log every 10 attempts
                            log_print(f"[*] Waiting for guest agent to connect (attempt {attempt + 1}/60)...")
                        await asyncio.sleep(1)
                        continue
                    else:
                        # Some other error - log it but keep trying
                        if attempt % 10 == 0:
                            log_print(f"[!] Guest agent error (attempt {attempt + 1}/60): {e}")
                        await asyncio.sleep(1)
                        continue
            except Exception as e:
                if attempt % 10 == 0:
                    log_print(f"[!] Error checking VM IP (attempt {attempt + 1}/60): {e}")
                await asyncio.sleep(1)
                continue
        
        log_print("[!] Timed out waiting for guest agent to report IP")
        return None

    async def ensure_warm_vm(self):
        """Ensures there is always one Warm VM ready to receive an attacker"""
        async with self.lock:
            if len(self.hot_vms) >= MAX_HOT_VMS:
                log_print(f"[X] Max capacity reached. Not creating new Warm VM.")
                return
            if self.warm_vm is None:
                log_print("[*] Creating new Warm VM...")
                try:
                    dom, run_id, disk_path = await asyncio.to_thread(
                        self._create_transient_vm
                    )
                    log_print(f"[VM] VM created, now waiting for IP address...")
                    ip = await self.get_vm_ip(dom)
                    if ip:
                        self.warm_vm = {
                            "dom": dom,
                            "ip": ip,
                            "id": run_id,
                            "disk": disk_path,
                        }
                        log_print(f"[✓] Warm VM Ready: {ip}")
                    else:
                        log_print("[!] Warm VM timed out getting IP. Destroying.")
                        await self.cleanup_vm_entry({"dom": dom, "disk": disk_path})
                except Exception as exc:
                    log_print(f"[!] Error creating Warm VM: {exc}")
                    import traceback
                    log_print(f"[!] Traceback: {traceback.format_exc()}")

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
            log_print(f"[->] Reconnecting {client_ip} to existing VM {vm['id']}")
            return vm["ip"]

        if len(self.hot_vms) >= MAX_HOT_VMS:
            log_print(f"[X] Max capacity reached. Dropping {client_ip}")
            return None

        async with self.lock:
            if self.warm_vm:
                target_vm = self.warm_vm
                self.warm_vm = None
                target_vm["last_seen"] = datetime.now()
                self.hot_vms[client_ip] = target_vm

                log_print(f"[+] Assigned Warm VM {target_vm['id']} (IP: {target_vm['ip']}) to {client_ip}")

                asyncio.create_task(self.ensure_warm_vm())
                return target_vm["ip"]

            log_print(f"[!] No Warm VM ready for {client_ip}. Triggering VM creation...")
            asyncio.create_task(self.ensure_warm_vm())
            return None


manager = VMManager()


class CommandLogger:
    """Very small helper to turn raw keystrokes into readable command logs."""

    def __init__(self, client_ip: str):
        self.client_ip = client_ip
        self._buffer: list[str] = []
        self._response_buffer: list[str] = []
        self._response_lines: list[str] = []  # Track response lines for truncation

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

    def feed_response(self, payload: bytes):
        """Feed response data from VM to attacker, logging complete lines."""
        text = payload.decode(errors="ignore")
        for ch in text:
            if ch in ("\r", "\n"):
                self._flush_response_line()
            elif ch.isprintable() or ch == "\t":
                self._response_buffer.append(ch)

    def _write_truncated_responses(self):
        """Write response lines truncated to first 4 + last 1."""
        if not self._response_lines:
            return
        
        # Strip ANSI codes from all lines
        cleaned_lines = [strip_ansi_codes(line) for line in self._response_lines]
        
        # Truncate to first 4 + last 1 (total 5 lines max)
        N = 10
        if len(cleaned_lines) <= N:
            # If 5 or fewer lines, write all
            truncated = cleaned_lines
        else:
            # First 4 + ellipsis + last 1
            truncated = cleaned_lines[:N - 2] + ["..."] + cleaned_lines[-2:]
        
        # Write truncated lines
        for line in truncated:
            append_log_line(f"[{self.client_ip}] RESP> {line}")
        
        # Clear the response lines list
        self._response_lines.clear()

    def _flush_line(self):
        # Before processing new command, write truncated responses from previous command
        self._write_truncated_responses()
        
        if not self._buffer:
            return
        line = "".join(self._buffer).strip()
        if line:
            append_log_line(f"[{self.client_ip}] CMD> {line}")
        self._buffer.clear()

    def _flush_response_line(self):
        if not self._response_buffer:
            return
        line = "".join(self._response_buffer).strip()
        if line:
            # Store the line instead of logging immediately
            self._response_lines.append(line)
        self._response_buffer.clear()

    def flush(self):
        self._flush_line()
        # Write any remaining response lines
        self._write_truncated_responses()


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
                logger.feed_response(data)
                send_all(attacker_channel, data)
                transferred = True

            if backend_channel.recv_stderr_ready():
                data = backend_channel.recv_stderr(4096)
                if not data:
                    stop_reason = "backend STDERR EOF"
                    break
                logger.feed_response(data)
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
    log_print(f"[*] Honeypot Controller listening on port {LISTEN_PORT}")

    try:
        while not STOP_EVENT.is_set():
            try:
                client_sock, addr = server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            client_ip = addr[0]
            log_print(f"[*] Connection from {client_ip}")

            fut = asyncio.run_coroutine_threadsafe(
                manager.get_target_for_client(client_ip), loop
            )

            try:
                target_ip = fut.result(timeout=30)  # Wait up to 30 seconds for VM assignment
                log_print(f"[*] Got target IP for {client_ip}: {target_ip}")
            except Exception as exc:
                log_print(f"[!] Failed to assign VM for {client_ip}: {exc}")
                import traceback
                log_print(f"[!] Traceback: {traceback.format_exc()}")
                client_sock.close()
                continue

            if not target_ip:
                log_print(f"[!] No target IP returned for {client_ip}, closing connection")
                client_sock.close()
                continue

            try:
                log_print(f"[*] Scheduling MITM proxy for {client_ip} -> {target_ip}")
                EXECUTOR.submit(handle_paramiko_proxy, client_sock, client_ip, target_ip)
            except Exception as exc:
                log_print(f"[!] Failed to schedule MITM for {client_ip}: {exc}")
                import traceback
                log_print(f"[!] Traceback: {traceback.format_exc()}")
                client_sock.close()
    finally:
        server_sock.close()
        log_print("[*] Honeypot listener stopped")


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

