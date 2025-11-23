# Honeypot Setup Guide

## 🐳 Docker-Based Honeypots (T-Pot) - **NO VM NEEDED!**

### Simple Setup (Recommended)

The `tpot.py` script uses **Docker Compose** to run honeypots in containers. **No VM setup required!**

#### Requirements

**Minimum (for Docker-based honeypots):**
- ✅ **Docker** and **Docker Compose**
- ✅ Python 3.x

**That's it!** The README mentions `fuse`, `qemu`, `libfuse`, and `libvirt`, but those are only needed for the **VM-based system** (see below).

#### Quick Start

1. **Make sure Docker is running:**
   ```bash
   docker --version
   docker compose version
   ```

2. **List available honeypots:**
   ```bash
   cd defense/tarpit_boxes
   python tpot.py list
   ```

3. **Start Cowrie SSH honeypot:**
   ```bash
   python tpot.py start cowrie
   ```
   
   This will:
   - Pull the Cowrie Docker image (if needed)
   - Start Cowrie container
   - Bind to port **22** (SSH) and **23** (Telnet) by default
   - **No VM needed!**

4. **Verify it's running:**
   ```bash
   docker ps | grep cowrie
   ```

5. **Test it:**
   ```bash
   ssh root@localhost  # Will connect to Cowrie honeypot
   ```

#### Custom Port Binding

If port 22 is already in use, you can bind to a different port:

```bash
python tpot.py start cowrie --ports cowrie=2222:22
```

This binds host port 2222 to container port 22.

#### Stop Honeypots

```bash
python tpot.py stop cowrie
# or stop all
python tpot.py stop
```

---

## 🖥️ VM-Based Honeypots (Advanced)

### When You Need VMs

The files `honey_manager.py` and `honey_manager_pipe.py` use **libvirt** to manage VMs. This is a more advanced setup that:

- Creates isolated VMs for each attacker
- Provides real shell access (not just emulated)
- Requires more setup

### VM Setup Requirements

**For VM-based system only:**
- ✅ Docker
- ✅ **libvirt** (for VM management)
- ✅ **qemu** (virtualization)
- ✅ **fuse** and **libfuse** (for filesystem operations)
- ✅ A base VM image (`tarpit_vm`)

### VM Setup Steps

1. **Install libvirt and qemu:**
   ```bash
   # macOS (using Homebrew)
   brew install libvirt qemu
   
   # Linux
   sudo apt-get install libvirt-daemon-system qemu-kvm
   ```

2. **Create base VM:**
   - See `nukem.sh` for VM creation script
   - Requires a base image (`tarpit.qcow2`)

3. **Run VM-based honeypot:**
   ```bash
   python honey_manager.py
   ```

**Note:** This is more complex and typically not needed for basic testing. The Docker-based system is sufficient for most use cases.

---

## 🎯 Which System to Use?

### Use Docker-Based (T-Pot) If:
- ✅ You want quick setup
- ✅ You're testing SSH honeypots
- ✅ You don't need real VM isolation
- ✅ You just want to capture login attempts

### Use VM-Based If:
- ✅ You need real shell access for attackers
- ✅ You want complete isolation per attacker
- ✅ You're doing advanced research
- ✅ You have libvirt/VMs already set up

---

## 📋 Quick Reference

### Docker-Based (Recommended)

```bash
# Setup
cd defense/tarpit_boxes

# List honeypots
python tpot.py list

# Start Cowrie (SSH/Telnet honeypot)
python tpot.py start cowrie

# Start with custom port
python tpot.py start cowrie --ports cowrie=2222:22

# Stop
python tpot.py stop cowrie
```

### Default Ports (from docker-compose.yml)

- **Cowrie**: Port 22 (SSH) and 23 (Telnet)
- **Dionaea**: Various ports (FTP, SMB, SQL)
- **ElasticPot**: Port 9200 (Elasticsearch)
- **Endlessh**: Port 2222 (SSH tarpit)

---

## ✅ Summary

**For most users:** Just use the Docker-based system with `tpot.py`. **No VM setup needed!**

The Docker containers handle everything - you just need Docker installed and running.

