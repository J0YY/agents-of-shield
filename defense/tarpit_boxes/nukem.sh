    
#!/bin/bash
echo "--- FLUSHING ALL FIREWALLS ---"
sudo iptables -F
sudo iptables -t nat -F
sudo nft flush ruleset

echo "--- ENABLING FORWARDING ---"
sudo sysctl -w net.ipv4.ip_forward=1
# Force load the bridge module (Arch specific quirk)
sudo modprobe br_netfilter
sudo sysctl -w net.bridge.bridge-nf-call-iptables=1

echo "--- DISABLING CHECKSUMS (The Silent Killer) ---"
sudo ethtool -K virbr0 tx off 2>/dev/null

echo "--- APPLYING CATCH-ALL NAT ---"
# Using legacy iptables syntax because it is often more reliable for one-offs
sudo iptables -t nat -A POSTROUTING -s 192.168.122.0/24 -j MASQUERADE

echo "--- ALLOWING FORWARDING ---"
sudo iptables -P FORWARD ACCEPT

echo "Done. Try pinging 8.8.8.8 from the VM now."

sudo virt-customize -a tarpit.qcow2 \
  --root-password password:toor \
  --uninstall cloud-init \
  --run-command 'useradd -m -s /bin/bash support' \
  --password support:password:123456 \
  --run-command 'mkdir -p /opt/proprietary_data' \
  --install python3,net-tools,auditd,nano,git \
  --run-command 'systemctl enable ssh'

  sudo virt-install \
  --name tarpit_vm \
  --ram 2048 \
  --vcpus 2 \
  --disk path=/var/lib/libvirt/images/tarpit.qcow2,format=qcow2,bus=virtio \
  --network network=default,model=virtio \
  --graphics none \
  --import \
  --os-variant ubuntu22.04 \
  --noautoconsole

sudo virt-customize -a /var/lib/libvirt/images/tarpit.qcow2 \
  --run-command 'systemctl mask systemd-networkd-wait-online.service'

      

  