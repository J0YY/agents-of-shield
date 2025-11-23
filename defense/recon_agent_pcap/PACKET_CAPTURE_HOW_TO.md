# Capturing Localhost Traffic with TShark

This guide explains how to:

- Install TShark  
- Capture **all traffic on localhost**  
- Store it in a `.pcap` file for later analysis or JSON conversion

TShark is the command‑line version of Wireshark and is ideal for traffic monitoring, debugging, security demos, and AI ingestion pipelines.

---

# 1. Installation

## Linux (Ubuntu / Debian / Kali / Mint)

```bash
sudo apt update
sudo apt install tshark
```

If prompted about non‑root users capturing packets, choose **Yes** only if you trust the system users.

---

## Linux (Fedora / CentOS / RHEL)

```bash
sudo dnf install wireshark-cli
```

---

## macOS (Homebrew)

```bash
brew update
brew install wireshark
```

When prompted, allow packet capture permissions (or run with sudo).

---

## Windows

1. Download Wireshark (which includes TShark) from:
   https://www.wireshark.org/download.html

2. During setup, ensure the following are selected:
   - **TShark component**
   - **Npcap** (required for packet capture)
   - Optionally: "Install Npcap in WinPcap API-compatible Mode"

3. After installation, open **PowerShell** or **cmd** and verify:

```powershell
tshark -v
```

---

# 2. Finding the Loopback Interface

Localhost traffic uses a loopback interface. It differs by OS.

### Linux
Loopback interface is always:

```
lo
```

### macOS
Loopback interface is:

```
lo0
```

### Windows
List all interfaces:

```powershell
tshark -D
```

Look for:

```
Adapter for loopback traffic capture
```

Its number (e.g., `3`) is the interface ID used below.

---

# 3. Capture ALL Localhost Traffic to a PCAP File

## Linux

```bash
sudo tshark -i lo -w traffic.pcap
```

---

## macOS

```bash
sudo tshark -i lo0 -w traffic.pcap
```

---

## Windows

```powershell
tshark -i <interface_number> -w traffic.pcap
```

Example:

```powershell
tshark -i 3 -w traffic.pcap
```

(Replace `3` with your loopback interface from `tshark -D`.)

---

# 4. Stopping the Capture

Press:

```
Ctrl + C
```

Your capture will be saved to `traffic.pcap` in the current directory.

---

# 5. Optional: Read the PCAP File

Print packet summary:

```bash
tshark -r traffic.pcap
```

Convert to JSON:

```bash
tshark -r traffic.pcap -T json > traffic.json
```

Filter later (e.g., only HTTP):

```bash
tshark -r traffic.pcap -Y "http" -T json > http.json
```

---

# Summary

- Install TShark using your system package manager  
- Identify the loopback interface for your OS  
- Capture all localhost traffic with `-i lo` / `-i lo0` / `-i <id>`  
- Save to `traffic.pcap` for later JSON or security analysis  

This workflow is ideal for demos, AI monitoring, packet inspection, and red‑team detection experiments.
