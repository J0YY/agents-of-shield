# ReconAgentPcap

PCAP-based reconnaissance agent for analyzing network traffic and detecting security threats.

**Pattern**: Matches the structure of `defense/recon_agent` for seamless integration with existing orchestration code.

## What It Does

Analyzes packet capture (PCAP) files to detect:

- **Port Scanning** - Multiple SYN packets to different ports
- **HTTP Enumeration** - Scanner user agents, directory bruteforcing
- **Data Exfiltration** - Large outbound data transfers
- **Traffic Anomalies** - Unusual patterns and behaviors

## Quick Start

### 1. Install tshark

```bash
# macOS
brew install wireshark

# Linux
sudo apt install tshark
```

### 2. Capture Traffic

```bash
# macOS
sudo tshark -i lo0 -w traffic.pcap

# Linux
sudo tshark -i lo -w traffic.pcap

# Stop with Ctrl+C after capturing some traffic
```

### 3. Run Agent

```python
from pathlib import Path
from defense.recon_agent_pcap.recon_agent_pcap import ReconAgentPcap

# Initialize (same pattern as ReconAgent)
agent = ReconAgentPcap(working_dir=Path("/path/to/repo"))

# Run investigation
result = agent.investigate(context={"trigger": "manual"})

# Check results
print(result["attack_assessment"])
print(result["evidence"])
print(result["recommendations"])
```

## Usage

### Standalone

```python
from recon_agent_pcap import ReconAgentPcap
from pathlib import Path

agent = ReconAgentPcap(working_dir=Path("."))
report = agent.investigate()
```

### Orchestrator Integration

```python
# In your orchestrator (matches recon_agent pattern):
from defense.recon_agent_pcap.recon_agent_pcap import ReconAgentPcap

def _execute():
    agent = ReconAgentPcap(working_dir=REPO_ROOT)
    return agent.investigate(context={"trigger": "orchestrator"})

loop = asyncio.get_running_loop()
report = await loop.run_in_executor(None, _execute)
```

## API Reference

### ReconAgentPcap

Main agent class with synchronous and asynchronous investigation methods.

#### `__init__(working_dir, pcap_file="traffic.pcap", ...)`

**Parameters:**
- `working_dir` - Path to directory containing PCAP file (default: current dir)
- `pcap_file` - Name of PCAP file (default: "traffic.pcap")
- `server_command` - Python executable for MCP server (default: sys.executable)
- `server_script` - Path to MCP server script (default: auto-detected)
- `client_session_timeout_seconds` - MCP session timeout (default: 300.0)

#### `investigate(context=None) -> Dict`

Synchronous investigation method.

**Parameters:**
- `context` - Optional dict with investigation context/trigger

**Returns:**
```python
{
    "timestamp": "2024-11-23T10:00:00",
    "investigation_trigger": "manual|orchestrator|...",
    "pcap_file": "/path/to/traffic.pcap",
    "attack_assessment": {
        "attack_type": "port_scan|http_enumeration|data_exfiltration|multiple|unknown",
        "target": "IP or multiple_targets",
        "severity": "low|medium|high|critical",
        "confidence": "low|medium|high"
    },
    "evidence": ["finding 1", "finding 2", ...],
    "recommendations": ["action 1", "action 2", ...],
    "intelligence": {
        "total_packets": 1234,
        "unique_ips": 10,
        "threat_count": 2
    }
}
```

#### `async investigate_async(context=None) -> Dict`

Async version of `investigate()`. Same parameters and return format.

## MCP Tools

The `pcap_analysis_mcp_server.py` provides these tools:

- `read_pcap_summary` - Overview of traffic (protocols, IPs, ports)
- `detect_port_scanning` - Find port scan attempts
- `detect_http_anomalies` - Detect HTTP enumeration and scanners
- `detect_data_exfiltration` - Find large data transfers
- `get_traffic_timeline` - Analyze traffic patterns over time

All tools accept `pcap_file` and `working_dir` parameters.

## Detection Capabilities

### Port Scanning
- **Signature**: 10+ TCP SYN packets to different ports from same source
- **Severity**: Medium (10-50 ports), High (50+)
- **Evidence**: Source IP, target IP, ports scanned, packet count

### HTTP Enumeration
- **Signatures**:
  - Scanner user agents (gobuster, dirbuster, nikto, sqlmap)
  - High request volume (50+ requests)
  - Many unique paths (20+ URLs)
  - Enumeration paths (/.env, /admin, /.git, etc.)
- **Severity**: Medium (volume), High (confirmed scanner)

### Data Exfiltration
- **Signature**: 1MB+ TCP data transfer
- **Severity**: Medium (1-10MB), High (10MB+)
- **Evidence**: IPs, ports, total bytes

## Files

### Core Files
- `recon_agent_pcap.py` - Main agent implementation
- `pcap_analysis_mcp_server.py` - MCP server with PCAP analysis tools
- `__init__.py` - Package exports
- `requirements.txt` - Dependencies

### Documentation
- `README.md` - This file
- `QUICKSTART.md` - Quick start guide
- `PACKET_CAPTURE_HOW_TO.md` - tshark capture guide

### Test Files
- `test_recon_agent_pcap.py` - Test script

## Integration with Existing Code

This agent is designed to slot into code that uses `ReconAgent`:

```python
# Original code using ReconAgent:
from defense.recon_agent.recon_agent import ReconAgent
agent = ReconAgent(working_dir=REPO_ROOT)
result = agent.investigate(context=ctx)

# New code using ReconAgentPcap:
from defense.recon_agent_pcap.recon_agent_pcap import ReconAgentPcap
agent = ReconAgentPcap(working_dir=REPO_ROOT)
result = agent.investigate(context=ctx)

# Same API, same patterns, same integration
```

## Testing

```bash
# Run test script
cd defense/recon_agent_pcap
python test_recon_agent_pcap.py
```

## Troubleshooting

### tshark not found
```bash
# Verify installation
tshark -v

# Install if needed
brew install wireshark  # macOS
sudo apt install tshark  # Linux
```

### PCAP file not found
- Ensure traffic.pcap exists in working directory
- Or specify custom path: `ReconAgentPcap(pcap_file="custom.pcap")`

### Permission denied on PCAP
```bash
# Fix permissions (PCAP files created with sudo need this)
sudo chmod 644 /path/to/traffic.pcap
```

### No packets captured
- Verify capture with: `tshark -r traffic.pcap`
- Ensure traffic was actually captured during tshark session
- Check you captured on the correct interface (lo0/lo)

### OPENAI_API_KEY not set
```bash
export OPENAI_API_KEY='sk-...'
```

## License

Part of the Agents of Shield defense framework.
