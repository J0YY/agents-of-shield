# ReconAgentPcap - Quick Start

Get started with PCAP network traffic analysis in 5 minutes.

## 1. Install Dependencies

```bash
# Install tshark
brew install wireshark  # macOS
# sudo apt install tshark  # Linux

# Install Python packages
cd defense/recon_agent_pcap
pip install -r requirements.txt

# Set API key
export OPENAI_API_KEY='sk-...'
```

## 2. Capture Traffic

```bash
# Capture localhost traffic (macOS)
sudo tshark -i lo0 -w traffic.pcap

# Generate some traffic, then stop with Ctrl+C
```

## 3. Run Analysis

### Option A: Standalone

```bash
python example_as_subagent.py standalone
```

### Option B: As Sub-Agent

```bash
python example_as_subagent.py subagent
```

### Option C: Python Code

```python
from recon_agent_pcap import ReconAgentPcap
from pathlib import Path

agent = ReconAgentPcap(
    working_dir=Path("."),
    pcap_file="traffic.pcap"
)

result = agent.analyze()
print(result["report"])
```

## What It Detects

✅ Port scanning (10+ ports from same IP)
✅ HTTP enumeration (gobuster, dirbuster, etc.)
✅ Data exfiltration (large transfers)
✅ Traffic anomalies (unusual patterns)

## Report Output

```json
{
  "summary": {
    "threat_level": "high",
    "suspicious_activity_detected": true
  },
  "findings": [
    {
      "type": "port_scan",
      "severity": "high",
      "source_ips": ["192.168.1.100"],
      "evidence": {...}
    }
  ],
  "recommendations": [
    "Block IP 192.168.1.100",
    "Review firewall rules"
  ]
}
```

## Use as Sub-Agent Tool

```python
# In your orchestrator
wrapper = ReconAgentPcap(working_dir=Path("."))
pcap_server = await wrapper.get_mcp_server_async()

async with pcap_server:
    agent = wrapper.get_agent(pcap_server)
    tool = agent.as_tool(
        tool_name="analyze_traffic",
        tool_description="Analyzes PCAP for threats"
    )

    # Use in orchestrator
    orchestrator = Agent(tools=[tool])
```

## Troubleshooting

**tshark not found?**
Install Wireshark which includes tshark

**No packets?**
Verify PCAP exists: `tshark -r traffic.pcap`

**Permission denied?**
Run tshark with sudo for capture

See [README.md](README.md) for full documentation.
