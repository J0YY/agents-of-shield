#!/usr/bin/env bash
set -euo pipefail

LIBVIRT_STORAGE=/var/lib/libvirt/images
DATA_MOUNT=/opt/proprietary_data
TRAP_LAYER=/tmp/trap_layer
LIBVIRT_DIR=/opt/tarpit/libvirt
IMAGES_DIR=/opt/tarpit/images
HOST_KEY=/opt/tarpit/id_ed25519
FUSE_SCRIPT=/opt/tarpit/fuse-fuckry.py
HONEY_MANAGER=/opt/tarpit/honey_manager_paramiko.py
NET_XML="${LIBVIRT_DIR}/default-network.xml"
VM_XML="${LIBVIRT_DIR}/tarpit_vm.xml"
VM_RUNTIME_XML="/tmp/tarpit_vm.runtime.xml"
QCOW_SRC="${IMAGES_DIR}/tarpit.qcow2"
OPENAI_MODEL="${OPENAI_DEFENSE_MODEL:-gpt-4o-mini-realtime-preview-2024-12-17}"

cleanup() {
  echo "[entrypoint] Caught signal, shutting down services..."
  pkill -P $$ >/dev/null 2>&1 || true
  trap_output="$(virsh list --name 2>/dev/null || true)"
  if [ -n "${trap_output}" ]; then
    mapfile -t trap_domains < <(printf "%s\n" "${trap_output}" | grep -E '^trap_' || true)
    for dom in "${trap_domains[@]}"; do
      if [ -n "${dom}" ]; then
        virsh destroy "${dom}" >/dev/null 2>&1 || true
        virsh undefine "${dom}" >/dev/null 2>&1 || true
      fi
    done
  fi
  virsh destroy tarpit_vm >/dev/null 2>&1 || true
  virsh undefine tarpit_vm >/dev/null 2>&1 || true
  virsh net-destroy default >/dev/null 2>&1 || true
  fusermount3 -u "${DATA_MOUNT}" >/dev/null 2>&1 || true
  exit 0
}

trap cleanup INT TERM

mkdir -p "${LIBVIRT_STORAGE}" "${LIBVIRT_DIR}" "${DATA_MOUNT}"
mkdir -p /var/run/libvirt /var/run/libvirt/qemu /var/log/libvirt
cp "${VM_XML}" "${VM_RUNTIME_XML}"

if ! id -u qemu >/dev/null 2>&1; then
  echo "[entrypoint] Creating qemu user/group..."
  groupadd -r qemu >/dev/null 2>&1 || true
  useradd -r -g qemu qemu >/dev/null 2>&1 || true
fi

# Configure libvirt qemu.conf to disable cgroups and run QEMU as root (nuclear option)
# This ensures no permission issues but is less secure
if [ -f /etc/libvirt/qemu.conf ]; then
  echo "[entrypoint] Configuring libvirt (nuclear option: QEMU runs as root)..."
  # Create a backup
  cp /etc/libvirt/qemu.conf /etc/libvirt/qemu.conf.bak
  
  # Remove any existing lines we want to override
  sed -i '/^cgroup_controllers/d' /etc/libvirt/qemu.conf
  sed -i '/^dynamic_ownership/d' /etc/libvirt/qemu.conf
  sed -i '/^security_driver/d' /etc/libvirt/qemu.conf
  sed -i '/^user[[:space:]]*=/d' /etc/libvirt/qemu.conf
  sed -i '/^group[[:space:]]*=/d' /etc/libvirt/qemu.conf
  
  # Append the correct settings
  cat >> /etc/libvirt/qemu.conf <<EOF

# Container-specific settings: run QEMU as root to avoid permission issues
# WARNING: This is less secure but ensures file access works
user = "root"
group = "root"
cgroup_controllers = []
dynamic_ownership = 0
security_driver = "none"
EOF
fi

# Create fake cgroup structure that libvirt can write to
# This prevents errors when libvirt tries to create cgroup directories
if [ ! -d /sys/fs/cgroup/machine ]; then
  echo "[entrypoint] Creating fake cgroup structure for libvirt..."
  mkdir -p /sys/fs/cgroup/machine
  # Make it writable so libvirt doesn't fail
  chmod 755 /sys/fs/cgroup/machine
fi

if command -v modprobe >/dev/null 2>&1; then
  echo "[entrypoint] Loading KVM kernel modules..."
  modprobe kvm >/dev/null 2>&1 || true
  modprobe kvm_intel >/dev/null 2>&1 || true
  modprobe kvm_amd >/dev/null 2>&1 || true
  echo "[entrypoint] Loading FUSE kernel module..."
  modprobe fuse >/dev/null 2>&1 || true
fi

if [ ! -e /dev/kvm ]; then
  echo "[entrypoint] WARNING: /dev/kvm missing; KVM acceleration unavailable."
fi

if [ ! -c /dev/fuse ]; then
  echo "[entrypoint] /dev/fuse missing; attempting to create device node."
  mknod /dev/fuse c 10 229 >/dev/null 2>&1 || true
  chmod 0666 /dev/fuse >/dev/null 2>&1 || true
fi

if [ ! -c /dev/fuse ]; then
  echo "[entrypoint] WARNING: FUSE device unavailable; rabbit-hole FS will fail."
fi

if [ ! -f /etc/fuse.conf ]; then
  echo "[entrypoint] Creating /etc/fuse.conf"
  echo "user_allow_other" > /etc/fuse.conf
elif ! grep -q "^user_allow_other" /etc/fuse.conf; then
  echo "[entrypoint] Enabling user_allow_other in /etc/fuse.conf"
  echo "user_allow_other" >> /etc/fuse.conf
fi

if [ ! -f "${LIBVIRT_STORAGE}/tarpit.qcow2" ]; then
  echo "[entrypoint] Installing base QCOW image..."
  cp "${QCOW_SRC}" "${LIBVIRT_STORAGE}/"
fi

# Ensure libvirt storage directory exists and has correct permissions
chown -R qemu:qemu "${LIBVIRT_STORAGE}"
chmod 755 "${LIBVIRT_STORAGE}"
# Ensure newly created files inherit qemu group (setgid)
chmod g+s "${LIBVIRT_STORAGE}" 2>/dev/null || true
# Explicitly ensure base image is readable/writable by qemu user
chown qemu:qemu "${LIBVIRT_STORAGE}/tarpit.qcow2" 2>/dev/null || true
chmod 660 "${LIBVIRT_STORAGE}/tarpit.qcow2" 2>/dev/null || true

chmod 600 "${HOST_KEY}"
chown root:root "${HOST_KEY}"

ln -sfn "${DATA_MOUNT}" "${TRAP_LAYER}"

echo "[entrypoint] Starting libvirt daemons..."
/usr/sbin/virtlogd &
/usr/sbin/libvirtd -d

echo "[entrypoint] Waiting for libvirt socket..."
for attempt in $(seq 1 20); do
  if virsh version >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [ "$attempt" -eq 20 ]; then
    echo "[entrypoint] ERROR: libvirtd failed to start."
    exit 1
  fi
done

echo "[entrypoint] Setting up libvirt default network..." >&2

# Clean up orphaned bridge interfaces that may exist from previous container runs
# This handles the case where virbr0 exists from a previous run but libvirt doesn't know about it
if ip link show virbr0 >/dev/null 2>&1; then
  # Bridge exists, check if libvirt has an active network using it
  net_active="no"
  if virsh net-info default >/dev/null 2>&1; then
    net_status=$(virsh net-info default 2>/dev/null | grep "Active:" | awk '{print $2}')
    net_active="${net_status:-no}"
  fi
  
  if [ "$net_active" != "yes" ]; then
    # Bridge exists but network is not active - this is the ghost interface case
    echo "[entrypoint] Detected orphaned bridge interface virbr0, cleaning up..." >&2
    
    # First, try to destroy the network in libvirt (in case it's defined but not active)
    virsh net-destroy default >/dev/null 2>&1 || true
    
    # Remove any tap interfaces that might be attached (though there shouldn't be any at startup)
    for tap_if in $(ip link show | grep -oE '^[0-9]+: (tap[0-9a-f]+|vnet[0-9]+)' | awk '{print $2}' | tr -d ':'); do
      if ip link show "$tap_if" >/dev/null 2>&1; then
        ip link set "$tap_if" down >/dev/null 2>&1 || true
        ip link delete "$tap_if" >/dev/null 2>&1 || true
      fi
    done
    
    # Bring down the bridge and remove it
    ip link set virbr0 down >/dev/null 2>&1 || true
    sleep 0.5  # Give kernel time to process
    ip link delete virbr0 >/dev/null 2>&1 || true
    
    # Verify it's gone
    if ip link show virbr0 >/dev/null 2>&1; then
      echo "[entrypoint] WARNING: Could not fully remove virbr0, but continuing..." >&2
    else
      echo "[entrypoint] Orphaned bridge interface removed successfully" >&2
    fi
  fi
fi

# Check if network exists and get its status
if virsh net-info default >/dev/null 2>&1; then
  # Network exists, check if it's already active
  net_status=$(virsh net-info default 2>/dev/null | grep "Active:" | awk '{print $2}')
  if [ "$net_status" = "yes" ]; then
    echo "[entrypoint] Default libvirt network is already active, using it." >&2
    virsh net-autostart default >/dev/null 2>&1 || true
  else
    # Network exists but is not active, try to start it
    echo "[entrypoint] Default libvirt network exists but is not active, starting it..." >&2
    if ! virsh net-start default 2>&1; then
      echo "[entrypoint] ERROR: Failed to start libvirt default network" >&2
      echo "[entrypoint] Network status:" >&2
      virsh net-info default 2>&1 || true
      exit 1
    fi
    virsh net-autostart default >/dev/null 2>&1 || true
    echo "[entrypoint] Default libvirt network started successfully" >&2
  fi
else
  # Network doesn't exist, define and start it
  echo "[entrypoint] Defining default libvirt network..." >&2
  if ! virsh net-define "${NET_XML}" 2>&1; then
    echo "[entrypoint] ERROR: Failed to define default libvirt network" >&2
    exit 1
  fi
  
  echo "[entrypoint] Starting default libvirt network..." >&2
  if ! virsh net-start default 2>&1; then
    echo "[entrypoint] ERROR: Failed to start libvirt default network" >&2
    echo "[entrypoint] Network status:" >&2
    virsh net-info default 2>&1 || true
    exit 1
  fi
  
  virsh net-autostart default >/dev/null 2>&1 || true
  echo "[entrypoint] Default libvirt network started successfully" >&2
fi

if ! virsh dominfo tarpit_vm >/dev/null 2>&1; then
  echo "[entrypoint] Defining tarpit_vm..."
  virsh define "${VM_RUNTIME_XML}"
else
  virsh define "${VM_RUNTIME_XML}" --replace >/dev/null 2>&1 || true
fi

virsh autostart tarpit_vm >/dev/null 2>&1 || true

echo "[entrypoint] Spawning background FUSE rabbit hole..."
python3 -u "${FUSE_SCRIPT}" "${DATA_MOUNT}" &
FUSE_PID=$!

# Use libvirt backend for libguestfs - it will use libvirt to launch appliance VMs
# This avoids needing a kernel installed in the container (direct backend requires kernel)
export LIBGUESTFS_BACKEND=direct
#libvirt:qemu:///system
export OPENAI_DEFENSE_MODEL="${OPENAI_MODEL}"
export PYTHONUNBUFFERED=1
export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1

echo "[entrypoint] Starting honey manager..."
cd /opt/tarpit
exec python3 -u "${HONEY_MANAGER}"

