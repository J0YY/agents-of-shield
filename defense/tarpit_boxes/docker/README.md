# Tarpit SSH MITM Container

This directory contains everything required to run the Paramiko-based honeypot controller (`honey_manager_paramiko.py`) together with its supporting FUSE lure filesystem and libvirt/QEMU payload inside a single container image.

## Included Assets

- `Dockerfile` – builds an Ubuntu 22.04 image with qemu/libvirt, virtiofsd, fuse tooling, guestfs utilities, Python runtime, and application dependencies.
- `entrypoint.sh` – runtime orchestration script that starts libvirtd, ensures the default network exists, mounts the lure FUSE filesystem, and finally launches the honeypot manager.
- `fuse-fuckry.py` – the FUSE filesystem that exposes `/opt/proprietary_data` and feeds guest VMs via virtio-fs.
- `honey_manager_paramiko.py` plus `id_ed25519*` – MITM SSH proxy and host keys.
- `libvirt/*.xml` – the exported `tarpit_vm` domain definition you provided and a default NAT network compatible with libvirt’s `virbr0`.
- `images/tarpit.qcow2` – the golden base image. Overlay clones are generated inside the container under `/var/lib/libvirt/images`.
- `netcfg.yaml` & `requirements.txt` – supporting artifacts for future VM customization and dependency tracking.

## Building

```bash
cd defense/tarpit_boxes/docker
docker build -t tarpit-honeypot .
```

Expect a large build (~1.5 GB) due to `tarpit.qcow2` and the virtualization stack.

## Runtime Requirements

Because libvirt uses hardware acceleration and needs to configure internal bridges, run the container with elevated privileges:

- Enable nested virtualization on the host and pass through `/dev/kvm`
- Allow FUSE by exposing `/dev/fuse`
- Grant NET_ADMIN (libvirt configures `virbr0` via iptables/nftables)
- Mount security-sensitive filesystems read-write (`/sys/fs/cgroup`, `/var/run`, etc.)
- Ensure the host allows module loading; the entrypoint will attempt `modprobe kvm`, `kvm_intel`, `kvm_amd`, and `fuse` to surface `/dev/kvm` and `/dev/fuse`. If `/dev/fuse` is still missing it will try creating the device node and appending `user_allow_other` to `/etc/fuse.conf`, but exposing `--device /dev/fuse` plus `--cap-add SYS_ADMIN` is the most reliable option. If KVM remains unavailable the bundled `tarpit_vm` definition now falls back to `virt='qemu'` with software emulation, which works but is significantly slower.
- The entrypoint tries to define and start libvirt’s `default` network; if that fails (e.g., due to missing `NET_ADMIN`) it rewrites the VM XML on the fly to use QEMU’s user-mode networking so the honeypot still has outbound access, albeit without bridge-level realism.
- Containerized libvirt cannot manage host cgroups, so the entrypoint configures `/etc/libvirt/qemu.conf` with `cgroup_controllers = []`, `dynamic_ownership = 0`, and `security_driver = "none"` to suppress cgroup-related errors. It also creates a fake `/sys/fs/cgroup/machine` directory structure that libvirt can write to. **Additionally, QEMU is configured to run as root** (`user = "root"`, `group = "root"`) to avoid file permission issues in the containerized environment. This is less secure but ensures reliable operation. If you provide your own qemu.conf, ensure these settings are present.

An example invocation:

```bash
docker run -it --rm \
  --name tarpit \
  --privileged \
  --device /dev/kvm \
  --device /dev/fuse \
  -e OPENAI_API_KEY=sk-... \
  -p 2222:2222 \
  tarpit-honeypot
```

For stricter deployments, replace `--privileged` with granular caps (`--cap-add=NET_ADMIN --cap-add=SYS_ADMIN --security-opt apparmor=unconfined`) and bind-mount `/run` + `/sys/fs/cgroup`. The honeypot process listens on port `2222` by default (see `LISTEN_PORT` in `honey_manager_paramiko.py` if you need to rebuild with a different port).

## What the Entrypoint Does

1. Copies `images/tarpit.qcow2` into `/var/lib/libvirt/images` if it is absent and fixes ownership for QEMU.
2. Ensures the lure FUSE filesystem is mounted at `/opt/proprietary_data` and symlinked to `/tmp/trap_layer` so it matches the `tarpit_vm` XML.
3. Starts `virtlogd` and `libvirtd`, defines/starts the `default` libvirt network from `libvirt/default-network.xml`, and (re)defines the `tarpit_vm` domain from `libvirt/tarpit_vm.xml`.
4. Sets `LIBGUESTFS_BACKEND=direct` so `virt-customize` inside the honeypot manager can mutate overlay disks.
5. Launches `honey_manager_paramiko.py`, which will spawn throwaway VMs from the `tarpit_vm` golden image whenever attackers connect.

When the container stops, the entrypoint attempts to unmount the FUSE filesystem, tear down libvirt networks, and destroy any live overlay VMs.

## Resource Considerations

- `tarpit_vm` requests 2 vCPUs and 2 GiB RAM. With `MAX_HOT_VMS=10`, worst-case consumption is ~20 GiB RAM and 20 vCPUs plus disk space for overlays. Size the host accordingly or tune those constants before building.
- libvirt NAT uses `virbr0` (192.168.122.0/24). Avoid clashes with existing bridges on the host.
- OpenAI realtime calls require outbound Internet access. Set `OPENAI_API_KEY` (and optionally `OPENAI_DEFENSE_MODEL`) at runtime.
- The container writes rotating qcow2 overlays under `/var/lib/libvirt/images`. Ensure the underlying Docker storage driver has several extra gigabytes free.

## Operational Notes

- The FUSE filesystem requires `/dev/fuse` with `allow_other`. Running the container as root simplifies this, but you can also pass a dedicated UID/GID and set `--device-cgroup-rule` appropriately.
- The provided `netcfg.yaml` can be injected into overlays via `virt-customize` if you need deterministic networking; for now the manager relies on DHCP from `virbr0`.
- Logs from libvirt and the honeypot are emitted to STDOUT/STDERR. You can bind-mount `/var/log/libvirt` if you prefer persistence.
- To refresh the base image, replace `images/tarpit.qcow2` and rebuild. The entrypoint copies it only when the destination file is missing to avoid overwriting live deployments.

## Troubleshooting

- **No /dev/kvm**: make sure the host CPU virtualization extensions are enabled and pass `/dev/kvm` into the container.
- **Libvirt network fails to start**: check host firewall rules; libvirt will attempt to run `iptables`/`nftables` inside the container.
- **FUSE mount errors**: ensure the container has the `SYS_ADMIN` capability and the host allows user-mode FUSE.
- **Cgroup errors**: the entrypoint automatically configures libvirt to disable cgroups and creates a fake cgroup structure. If you still see cgroup errors, ensure `/sys/fs/cgroup` is accessible (consider mounting it from the host with `-v /sys/fs/cgroup:/sys/fs/cgroup:rw`).
- **Realtime LLM errors**: confirm `OPENAI_API_KEY` is set and outbound TLS connections are permitted.

With these pieces in place, you can treat the image as a self-contained honeypot appliance: build once, run on any host that can provide KVM/FUSE and enough CPU/RAM headroom.

