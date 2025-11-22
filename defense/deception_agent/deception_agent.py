# deception_agent.py
"""
Deception Agent - Detects directory enumeration and serves fake responses.

This agent monitors network logs for directory enumeration patterns and dynamically
generates fake secrets, config files, and HTTP responses to mislead attackers.
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from agents import Agent, Runner, set_default_openai_api, set_tracing_disabled
from agents.mcp import MCPServerStdio


class DeceptionAgent:
    """
    Detects directory enumeration scans and generates fake deceptive responses.

    When enumeration is detected, this agent creates fake secrets, credentials,
    and misleading data to waste attacker time and gather intelligence.

    This class can be used:
    1. Standalone via analyze_and_deceive()
    2. As a sub-agent via get_agent().as_tool()
    """

    def __init__(self, working_dir: Optional[Path] = None, state_dir: Optional[Path] = None) -> None:
        """
        Initialize the deception agent.

        Args:
            working_dir: Optional working directory for logs
            state_dir: Optional directory for storing deception state
        """
        if working_dir is None:
            working_dir = Path.cwd()
        if state_dir is None:
            state_dir = working_dir / "state"

        self.working_dir = working_dir
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.deception_state_file = self.state_dir / "deception_state.json"

        # Initialize deception state
        self._load_or_create_state()

        # Cache for the Agent instance
        self._agent_instance = None
        self._mcp_servers = None

    def _load_or_create_state(self) -> None:
        """Load existing deception state or create a new one."""
        if self.deception_state_file.exists():
            try:
                with self.deception_state_file.open("r") as f:
                    self.state = json.load(f)
            except json.JSONDecodeError:
                self.state = self._create_default_state()
        else:
            self.state = self._create_default_state()
        self._persist_state()

    def _create_default_state(self) -> Dict:
        """Create default deception state with fake responses."""
        return {
            "enumeration_detected": False,
            "enumeration_count": 0,
            "last_detection": None,
            "fake_endpoints": {},
            "served_deceptions": [],
            "attacker_ips": [],
        }

    def _persist_state(self) -> None:
        """Persist deception state to disk."""
        with self.deception_state_file.open("w") as f:
            json.dump(self.state, f, indent=2)

    async def analyze_and_deceive_async(self, context: Optional[Dict] = None) -> Dict:
        """
        Main entry point: Analyze logs for enumeration and generate deceptions.

        Args:
            context: Optional context from orchestrator

        Returns:
            Report with enumeration detection and deception responses
        """
        # Ensure API key is present
        if "OPENAI_API_KEY" not in os.environ:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set")

        set_default_openai_api(os.environ["OPENAI_API_KEY"])
        set_tracing_disabled(True)

        # Start the log reader MCP server (from recon_agent)
        log_reader_path = Path(__file__).parent.parent / "recon_agent" / "log_reader_mcp_server.py"

        # Start the deception response generator MCP server
        deception_mcp_path = Path(__file__).parent / "deception_response_mcp_server.py"

        log_reader_server, deception_server = await self.get_mcp_servers_async()

        async with log_reader_server, deception_server:
            agent = self.get_agent(log_reader_server, deception_server)

            context_str = ""
            if context:
                context_str = f"\n\nContext from orchestrator: {json.dumps(context, indent=2)}"

            task = (
                "Analyze network logs for directory enumeration and generate deceptive responses.\n\n"
                f"Working directory: {self.working_dir}\n"
                f"Deception state directory: {self.state_dir}\n\n"

                "EXECUTE THIS WORKFLOW:\n\n"

                "STEP 1 - READ LOGS:\n"
                f"Call read_network_logs with:\n"
                f"  lines=100\n"
                f"  working_dir=\"{self.working_dir}\"\n\n"

                "STEP 2 - ANALYZE FOR ENUMERATION:\n"
                "Look through the log entries for these patterns:\n"
                "- Are there 5+ different unique endpoints being accessed?\n"
                "- Are requests happening close together in time (within 2 minutes)?\n"
                "- Are there multiple 404s or failed requests?\n"
                "- Are sensitive paths being probed (.env, .git, admin, config, backup)?\n"
                "- Does it look like wordlist scanning?\n\n"

                "STEP 3 - IF ENUMERATION DETECTED:\n"
                "For each suspicious path that was probed, generate appropriate fake response:\n"
                "- If they probed /.env or /config → generate_fake_env_file or generate_fake_config\n"
                "- If they probed /admin* → generate_fake_admin_panel\n"
                "- If they probed /backup* or *.sql → generate_fake_backup\n"
                "- If they probed /api/* → generate_fake_api_response\n\n"

                "STEP 4 - RETURN REPORT:\n"
                "Provide detailed JSON report with:\n"
                "- Clear enumeration verdict (detected: true/false)\n"
                "- Confidence level based on evidence strength\n"
                "- Evidence details (counts, paths, timing)\n"
                "- List of generated deception responses\n"
                "- Attacker intelligence assessment\n"
                "- Defensive recommendations\n\n"

                f"{context_str}"
            )

            result = await Runner.run(agent, task)

            # Parse the result
            import re
            output = result.final_output

            # Try to extract JSON
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
            if json_match:
                try:
                    report = json.loads(json_match.group())

                    # Update our state if enumeration was detected
                    if report.get("enumeration_detected"):
                        self.state["enumeration_detected"] = True
                        self.state["enumeration_count"] += 1
                        self.state["last_detection"] = self._get_timestamp()

                        # Store generated deceptions
                        if "deception_responses" in report:
                            self.state["served_deceptions"].extend(report["deception_responses"])

                        self._persist_state()

                    report["timestamp"] = self._get_timestamp()
                    report["state_file"] = str(self.deception_state_file)
                    return report

                except json.JSONDecodeError:
                    pass

            # Fallback response
            return {
                "timestamp": self._get_timestamp(),
                "enumeration_detected": False,
                "confidence": "low",
                "enumeration_evidence": {},
                "deception_responses": [],
                "recommendations": [],
                "raw_output": output,
            }

    def analyze_and_deceive(self, context: Optional[Dict] = None) -> Dict:
        """
        Synchronous wrapper for analyze_and_deceive_async.

        Args:
            context: Optional context from orchestrator

        Returns:
            Deception analysis report
        """
        return asyncio.run(self.analyze_and_deceive_async(context))

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.utcnow().isoformat()

    def get_state(self) -> Dict:
        """Get current deception state."""
        return self.state

    def reset_state(self) -> None:
        """Reset deception state."""
        self.state = self._create_default_state()
        self._persist_state()

    async def get_mcp_servers_async(self):
        """
        Get MCP servers for this agent (async context manager).

        Returns tuple of (log_reader_server, deception_server) for use in async with.
        """
        log_reader_path = Path(__file__).parent.parent / "recon_agent" / "log_reader_mcp_server.py"
        deception_mcp_path = Path(__file__).parent / "deception_response_mcp_server.py"

        log_reader_server = MCPServerStdio(
            name="NetworkLogReaderServer",
            params={
                "command": "python",
                "args": [str(log_reader_path)],
            },
            cache_tools_list=True,
        )

        deception_server = MCPServerStdio(
            name="DeceptionResponseServer",
            params={
                "command": "python",
                "args": [str(deception_mcp_path)],
            },
            cache_tools_list=True,
        )

        return log_reader_server, deception_server

    def _get_instructions(self) -> str:
        """Get agent instructions."""
        return (
            "You are a deception specialist detecting directory enumeration attacks and generating fake responses.\n\n"

            "MISSION:\n"
            "1. Detect directory enumeration scans in network logs\n"
            "2. Generate convincing fake secrets and responses to mislead attackers\n"
            "3. Track enumeration patterns and served deceptions\n\n"

            "DIRECTORY ENUMERATION INDICATORS:\n"
            "- Multiple 404 responses to different paths in short timeframe\n"
            "- Sequential probing of common paths: /admin, /backup, /config, /.env, /.git\n"
            "- Wordlist-based scanning: /login, /api, /debug, /test, /dev, etc.\n"
            "- Path variations: /admin, /admin/, /Admin, /ADMIN, /admin.php\n"
            "- Tool signatures: gobuster, dirbuster, ffuf, wfuzz patterns\n"
            "- High request rate to non-existent endpoints\n\n"

            "ENUMERATION DETECTION CRITERIA:\n"
            "Consider it enumeration if ANY of these:\n"
            "- 5+ different endpoints accessed within 2 minutes\n"
            "- 3+ sequential 404s to common admin/config paths\n"
            "- Probing of sensitive paths: /.env, /.git, /backup, /admin\n"
            "- Pattern matching common wordlists (admin, config, backup, api)\n\n"

            "DECEPTION STRATEGIES:\n"
            "When enumeration is detected, generate fake responses for:\n\n"

            "1. FAKE CREDENTIALS (.env, config files):\n"
            "   - Fake database credentials with honeypot DB details\n"
            "   - Fake API keys that trigger alerts when used\n"
            "   - Fake admin passwords (never real ones!)\n"
            "   - Realistic but fake AWS/GCP credentials\n\n"

            "2. FAKE ADMIN PANELS:\n"
            "   - Generate HTML for fake admin login pages\n"
            "   - Include fake session tokens\n"
            "   - Add fake CSRF tokens and form fields\n\n"

            "3. FAKE BACKUP FILES:\n"
            "   - SQL dumps with fake data\n"
            "   - Tar.gz files with decoy contents\n"
            "   - Old config files with outdated fake info\n\n"

            "4. FAKE DEBUG ENDPOINTS:\n"
            "   - Phpinfo pages with fake PHP configuration\n"
            "   - Server status with fake server info\n"
            "   - Debug logs with misleading traces\n\n"

            "AVAILABLE TOOLS:\n"
            "- read_network_logs: Read recent network traffic (from NetworkLogReaderServer)\n"
            "- generate_fake_env_file: Create fake .env with credentials (from DeceptionResponseServer)\n"
            "- generate_fake_admin_panel: Create fake admin HTML (from DeceptionResponseServer)\n"
            "- generate_fake_config: Create fake config JSON/YAML (from DeceptionResponseServer)\n"
            "- generate_fake_backup: Create fake SQL dump or tar contents (from DeceptionResponseServer)\n"
            "- generate_fake_api_response: Create fake API JSON response (from DeceptionResponseServer)\n\n"

            "ANALYSIS PROCESS:\n"
            "STEP 1: Call read_network_logs with lines=100 to get recent traffic\n"
            f"        Use working_dir=\"{self.working_dir}\"\n"
            "STEP 2: Analyze the logs for enumeration patterns:\n"
            "        - Count unique endpoints accessed\n"
            "        - Identify time gaps between requests\n"
            "        - Look for common wordlist patterns\n"
            "        - Check for sequential 404s\n"
            "STEP 3: If enumeration detected (threshold met):\n"
            "        - Identify which paths were probed\n"
            "        - Generate appropriate fake responses using deception tools\n"
            "        - Track which deceptions were generated\n"
            "STEP 4: Return comprehensive report\n\n"

            "OUTPUT FORMAT (JSON only, no markdown):\n"
            "{\n"
            '  "enumeration_detected": true/false,\n'
            '  "confidence": "low|medium|high",\n'
            '  "enumeration_evidence": {\n'
            '    "unique_endpoints_accessed": <count>,\n'
            '    "time_window_seconds": <duration>,\n'
            '    "sequential_404_count": <count>,\n'
            '    "suspicious_paths": ["list", "of", "paths"],\n'
            '    "request_rate": <requests_per_minute>,\n'
            '    "tool_signature": "gobuster|dirbuster|manual|unknown"\n'
            "  },\n"
            '  "deception_responses": [\n'
            "    {\n"
            '      "endpoint": "/path/probed",\n'
            '      "response_type": "fake_env|fake_admin|fake_config|fake_backup",\n'
            '      "content_preview": "preview of fake content",\n'
            '      "purpose": "explanation of deception goal"\n'
            "    }\n"
            "  ],\n"
            '  "recommendations": [\n'
            '    "specific defensive actions"\n'
            "  ],\n"
            '  "attacker_intelligence": {\n'
            '    "likely_tool": "tool name or manual",\n'
            '    "skill_level": "novice|intermediate|advanced",\n'
            '    "targets_of_interest": ["what they are looking for"]\n'
            "  }\n"
            "}\n\n"

            "IMPORTANT RULES:\n"
            "- NEVER include real credentials or secrets in fake responses\n"
            "- Make fake data realistic but obviously fake to forensic analysis\n"
            "- Track all generated deceptions for later analysis\n"
            "- Provide clear evidence for enumeration detection\n"
            "- Be creative with fake data - vary it each time\n"
        )

    def get_agent(self, log_reader_server, deception_server) -> Agent:
        """
        Get the underlying Agent instance for use as a sub-agent.

        This allows DeceptionAgent to be used with the agents-as-tools pattern.

        Args:
            log_reader_server: MCP server for reading network logs
            deception_server: MCP server for generating fake responses

        Returns:
            Agent instance that can be used with .as_tool()

        Example:
            ```python
            async with deception_agent.get_mcp_servers_async() as (log_server, dec_server):
                agent = deception_agent.get_agent(log_server, dec_server)
                tool = agent.as_tool(
                    tool_name="detect_enumeration",
                    tool_description="Detects directory enumeration and generates deceptions"
                )
                # Use tool in orchestrator
            ```
        """
        return Agent(
            name="DeceptionAgent",
            model="gpt-4o-mini",
            instructions=self._get_instructions(),
            mcp_servers=[log_reader_server, deception_server],
        )
