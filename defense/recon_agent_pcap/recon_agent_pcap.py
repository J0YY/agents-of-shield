# recon_agent_pcap.py
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

from agents import Agent, Runner, set_default_openai_api, set_tracing_disabled
from agents.mcp import MCPServerStdio

# Try to import ToolLoggingHooks, but make it optional
try:
    from defense.initial_defense_orchestrator.tool_logging_hooks import ToolLoggingHooks
except ImportError:
    # If running standalone, ToolLoggingHooks may not be available
    ToolLoggingHooks = None


def build_recon_agent_pcap(pcap_analysis_mcp_server: MCPServerStdio) -> Agent:
    """
    Create the ReconAgentPcap configured to use the PcapAnalysisServer MCP server.

    This function is used by ReconAgentPcapContext and can also be used directly
    if you already have an MCP server instance.
    """
    return Agent(
        name="ReconAgentPcap",
        model="gpt-4o-mini",
        instructions=(
            "You are a network traffic reconnaissance agent analyzing packet captures for security threats.\n\n"
            "PCAP FILE FORMAT:\n"
            "- The PCAP file contains network packet captures in standard pcap format\n"
            "- Default location: traffic.pcap in the working directory\n"
            "- Analyzed using tshark tools via MCP server\n\n"
            "HOW TO ANALYZE PCAP FILES:\n"
            "- Use read_pcap_summary to get an overview (protocols, IPs, ports)\n"
            "- Use detect_port_scanning to find port scan attempts\n"
            "- Use detect_http_anomalies to identify HTTP enumeration and scanners\n"
            "- Use detect_data_exfiltration to find large data transfers\n"
            "- Use get_traffic_timeline to analyze patterns over time\n"
            "- All tools accept pcap_file and working_dir parameters\n\n"
            "WHAT TO LOOK FOR:\n"
            "- Port scanning: Multiple SYN packets to different ports from same source\n"
            "- HTTP enumeration: Scanner user agents (gobuster, dirbuster), high request volume, many unique paths\n"
            "- Data exfiltration: Large outbound transfers (>1MB by default)\n"
            "- Traffic anomalies: Unusual protocol distributions, timing patterns\n\n"
            "OUTPUT FORMAT:\n"
            "Return a JSON object with this exact structure:\n"
            "{\n"
            '  "attack_assessment": {\n'
            '    "attack_type": "port_scan|http_enumeration|data_exfiltration|multiple|unknown",\n'
            '    "target": "specific IP or multiple_targets",\n'
            '    "severity": "low|medium|high|critical",\n'
            '    "confidence": "low|medium|high"\n'
            "  },\n"
            '  "evidence": ["specific finding 1", "specific finding 2", ...],\n'
            '  "recommendations": ["action 1", "action 2", ...],\n'
            '  "intelligence": {"total_packets": N, "unique_ips": N, "threat_count": N}\n'
            "}\n\n"
            "CRITICAL: Always start with read_pcap_summary, then run detection tools based on what you find!"
        ),
        mcp_servers=[pcap_analysis_mcp_server],
    )


class ReconAgentPcapContext:
    """
    Async context manager that bundles:
    - Starting the PcapAnalysisServer MCP server over stdio.
    - Constructing a ReconAgentPcap wired to that server.
    - Shutting down the MCP server when done.

    Usage (standalone or from an orchestrator):

        async with ReconAgentPcapContext() as recon_agent:
            result = await Runner.run(recon_agent, task, hooks=ToolLoggingHooks())
    """

    def __init__(
        self,
        server_command: Optional[str] = None,
        server_script: Optional[str] = None,
        client_session_timeout_seconds: float = 300.0,
    ) -> None:
        # Default to the current Python executable if not provided
        if server_command is None:
            server_command = sys.executable
        self.server_command = server_command

        # Default to pcap_analysis_mcp_server.py in the same directory as this file
        if server_script is None:
            server_script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "pcap_analysis_mcp_server.py",
            )
        self.server_script = server_script
        self.client_session_timeout_seconds = client_session_timeout_seconds

        self._mcp_cm: Optional[MCPServerStdio] = None
        self._mcp_server: Optional[MCPServerStdio] = None
        self.agent: Optional[Agent] = None

    async def __aenter__(self) -> Agent:
        self._mcp_cm = MCPServerStdio(
            name="PcapAnalysisServer",
            params={
                "command": self.server_command,
                "args": [self.server_script],
            },
            cache_tools_list=True,
            client_session_timeout_seconds=self.client_session_timeout_seconds,
        )
        # Enter the MCP context manager and get the server handle
        self._mcp_server = await self._mcp_cm.__aenter__()
        # Build the agent that uses this MCP server
        self.agent = build_recon_agent_pcap(self._mcp_server)
        return self.agent

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._mcp_cm is not None:
            await self._mcp_cm.__aexit__(exc_type, exc, tb)


class ReconAgentPcap:
    """
    Self-contained PCAP reconnaissance agent.

    When triggered, this agent uses a custom MCP server to analyze packet capture
    files and identify network security threats.
    """

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        pcap_file: str = "traffic.pcap",
        server_command: Optional[str] = None,
        server_script: Optional[str] = None,
        client_session_timeout_seconds: float = 300.0,
    ) -> None:
        """
        Initialize the PCAP recon agent.

        Args:
            working_dir: Optional working directory. If None, uses current directory.
                         Expects traffic.pcap relative to working directory.
            pcap_file: Name of the PCAP file to analyze (default: traffic.pcap)
            server_command: Command used to start the MCP server (defaults to the
                            current Python executable).
            server_script: Path to the MCP server script. If None, defaults to
                           pcap_analysis_mcp_server.py in the same directory as this file.
            client_session_timeout_seconds: Timeout in seconds for the MCP client session.
        """
        if working_dir is None:
            working_dir = Path.cwd()
        self.working_dir = working_dir
        self.pcap_file = pcap_file

        self.server_command = server_command
        self.server_script = server_script
        self.client_session_timeout_seconds = client_session_timeout_seconds

    async def investigate_async(self, context: Optional[Dict] = None) -> Dict:
        """
        Main entry point: Conduct reconnaissance analysis using PCAP file.

        Args:
            context: Optional context from orchestrator (e.g., suspicious activity trigger)

        Returns:
            Comprehensive recon report with threat assessment
        """
        # Ensure API key is present (Agents SDK uses the OpenAI Python SDK under the hood)
        if "OPENAI_API_KEY" not in os.environ:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set")

        set_default_openai_api(os.environ["OPENAI_API_KEY"])
        set_tracing_disabled(True)

        async with ReconAgentPcapContext(
            server_command=self.server_command,
            server_script=self.server_script,
            client_session_timeout_seconds=self.client_session_timeout_seconds,
        ) as recon_agent:
            context_str = ""
            if context:
                context_str = f"\n\nContext: {context}"

            task = (
                "Analyze network packet capture for security threats.\n\n"
                f"Working directory: {self.working_dir}\n"
                f"PCAP file: {self.pcap_file}\n\n"
                "STEP 1: Call read_pcap_summary to get an overview of the traffic.\n"
                "  - Use pcap_file parameter (if not default traffic.pcap)\n"
                f'  - Use working_dir="{self.working_dir}"\n'
                "  - This returns protocol distribution, top IPs, top ports\n\n"
                "STEP 2: Based on the summary, run relevant detection tools:\n"
                "  - detect_port_scanning: Look for port scan attempts (multiple SYN packets)\n"
                "  - detect_http_anomalies: Look for HTTP enumeration, scanner user agents\n"
                "  - detect_data_exfiltration: Look for large data transfers\n"
                "  - get_traffic_timeline: Analyze traffic patterns over time\n\n"
                "STEP 3: Analyze ALL results and correlate findings.\n\n"
                "Look for these attack patterns:\n\n"
                "1. PORT SCANNING - Multiple SYN packets to different ports:\n"
                "   - Threshold: 10+ unique ports from same source\n"
                "   - Evidence: Source IP, target IP, number of ports scanned\n"
                "   - Severity: medium (10-50 ports), high (50+ ports)\n\n"
                "2. HTTP ENUMERATION - Scanner activity or directory bruteforcing:\n"
                "   - Scanner user agents: gobuster, dirbuster, nikto, sqlmap\n"
                "   - High request volume: 50+ requests from same IP\n"
                "   - Many unique paths: 20+ different URLs\n"
                "   - Enumeration paths: /.env, /admin, /.git, /backup\n"
                "   - Severity: high if scanner detected, medium if just high volume\n\n"
                "3. DATA EXFILTRATION - Large outbound transfers:\n"
                "   - Threshold: 1MB+ data transfer\n"
                "   - Evidence: Source/dest IPs, ports, total bytes\n"
                "   - Severity: medium (1-10MB), high (10MB+)\n\n"
                "4. TRAFFIC ANOMALIES - Unusual patterns:\n"
                "   - Unusual protocol distribution\n"
                "   - Suspicious timing patterns\n"
                "   - Concentrated bursts of activity\n\n"
                "Return ONLY a valid JSON object (no markdown, no code blocks, just the JSON) with this structure:\n"
                "{\n"
                '  \"attack_assessment\": {\n'
                '    \"attack_type\": \"port_scan\" or \"http_enumeration\" or '
                '\"data_exfiltration\" or \"multiple\" or \"unknown\",\n'
                '    \"target\": \"specific IP or multiple_targets\",\n'
                '    \"severity\": \"high\" or \"critical\" if ANY threats found, '
                '\"low\" ONLY if zero threats found,\n'
                '    \"confidence\": \"high\" if clear threat patterns found\n'
                "  },\n"
                '  \"evidence\": [\"Specific finding from PCAP analysis\", '
                "\"Another finding\", ...],\n"
                '  \"recommendations\": [\"Defensive action 1\", \"Defensive action 2\", ...],\n'
                '  \"intelligence\": {\"total_packets\": <from summary>, '
                '"unique_ips\": <count>, '
                '"threat_count\": <actual count of threats found>}\n'
                "}\n\n"
                "IMPORTANT: If you find port scans, HTTP enumeration, or data exfiltration, "
                "threat_count should be > 0 and severity should be 'high' or 'critical', not 'low'!"
                f"{context_str}"
            )

            # Use ToolLoggingHooks if available
            if ToolLoggingHooks is not None:
                result = await Runner.run(
                    recon_agent,
                    task,
                    hooks=ToolLoggingHooks(),
                )
            else:
                result = await Runner.run(
                    recon_agent,
                    task,
                )

        # Parse the result - try to extract JSON if present
        import re

        output = result.final_output

        # Try to find JSON in the output
        json_match = re.search(r"\{.*\}", output, re.DOTALL)
        if json_match:
            try:
                report = json.loads(json_match.group())
                report["timestamp"] = self._get_timestamp()
                report["investigation_trigger"] = context or "manual_investigation"
                report["pcap_file"] = str(self.working_dir / self.pcap_file)
                return report
            except json.JSONDecodeError:
                pass

        # If no JSON found, return a structured response with the text output
        return {
            "timestamp": self._get_timestamp(),
            "investigation_trigger": context or "manual_investigation",
            "pcap_file": str(self.working_dir / self.pcap_file),
            "attack_assessment": {
                "attack_type": "unknown",
                "target": "unknown",
                "severity": "low",
                "confidence": "low",
            },
            "evidence": [],
            "recommendations": [],
            "intelligence": {},
            "raw_output": output,
        }

    def investigate(self, context: Optional[Dict] = None) -> Dict:
        """
        Synchronous wrapper for investigate_async.

        Args:
            context: Optional context from orchestrator (e.g., suspicious activity trigger)

        Returns:
            Comprehensive recon report with threat assessment
        """
        return asyncio.run(self.investigate_async(context))

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime

        return datetime.utcnow().isoformat()
