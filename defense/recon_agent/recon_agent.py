# recon_agent.py
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

from agents import Agent, Runner, set_default_openai_api, set_tracing_disabled
from agents.mcp import MCPServerStdio

from defense.initial_defense_orchestrator.tool_logging_hooks import ToolLoggingHooks


def build_recon_agent(log_reader_mcp_server: MCPServerStdio) -> Agent:
    """
    Create the ReconAgent configured to use the NetworkLogReaderServer MCP server.

    This function is used by ReconAgentContext and can also be used directly
    if you already have an MCP server instance.
    """
    return Agent(
        name="ReconAgent",
        model="gpt-4o-mini",
        instructions=(
            "You are an attack reconnaissance agent analyzing network traffic logs.\n\n"
            "LOG FORMAT:\n"
            "- The logs are at vulnerable-app/attack_log.json in JSONL format (one JSON per line)\n"
            "- Each entry has: timestamp, ip, method, endpoint, query (object), body (object, optional)\n"
            "- Example: {\"timestamp\":\"...\",\"ip\":\"::1\",\"method\":\"GET\",\"endpoint\":\"/login\","
            "\"query\":{},\"body\":{}}\n\n"
            "HOW, FOR EXAMPLE, TO READ LOGS:\n"
            "- Use the read_network_logs tool from NetworkLogReaderServer (it should be in your available tools)\n"
            "- Call it with lines=50 and working_dir parameter set to the working directory provided in the task\n"
            "- The tool returns a dictionary with 'entries' (list of log objects) and 'total_count'\n"
            "- Analyze the entries in the 'entries' list\n\n"
            "WHAT TO LOOK FOR, INCLUDING BUT NOT LIMITED TO:\n"
            "- SQL injection: 'OR 1=1', 'OR', UNION, SELECT in query parameters or body values\n"
            "- Path traversal: ../, ..\\, %2e%2e in endpoints\n"
            "- Reconnaissance: Access to /admin, /backup-db, /download-db, /config, /debug\n"
            "- Honeypot hits: /backup-db, /admin-v2, /config-prod endpoints\n"
            "- Suspicious patterns: Canary tokens, repeated probing, etc.\n\n"
            "OUTPUT FORMAT:\n"
            "Return a JSON object with this exact structure:\n"
            "{\n"
            '  "attack_assessment": {\n'
            '    "attack_type": "sql_injection|path_traversal|reconnaissance|unknown",\n'
            '    "target": "endpoint or multiple_endpoints",\n'
            '    "severity": "low|medium|high|critical",\n'
            '    "confidence": "low|medium|high"\n'
            "  },\n"
            '  "evidence": ["specific finding 1", "specific finding 2", ...],\n'
            '  "intelligence": {"total_requests": <use total_count from tool>, '
            '"unique_endpoints": N, "attack_count": N}\n'
            "}\n\n"
            "CRITICAL: You MUST call the read_network_logs tool first to get the log data before analyzing!"
        ),
        mcp_servers=[log_reader_mcp_server],
    )


class ReconAgentContext:
    """
    Async context manager that bundles:
    - Starting the NetworkLogReaderServer MCP server over stdio.
    - Constructing a ReconAgent wired to that server.
    - Shutting down the MCP server when done.

    Usage (standalone or from an orchestrator):

        async with ReconAgentContext() as recon_agent:
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

        # Default to log_reader_mcp_server.py in the same directory as this file
        if server_script is None:
            server_script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "log_reader_mcp_server.py",
            )
        self.server_script = server_script
        self.client_session_timeout_seconds = client_session_timeout_seconds

        self._mcp_cm: Optional[MCPServerStdio] = None
        self._mcp_server: Optional[MCPServerStdio] = None
        self.agent: Optional[Agent] = None

    async def __aenter__(self) -> Agent:
        self._mcp_cm = MCPServerStdio(
            name="NetworkLogReaderServer",
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
        self.agent = build_recon_agent(self._mcp_server)
        return self.agent

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._mcp_cm is not None:
            await self._mcp_cm.__aexit__(exc_type, exc, tb)


class ReconAgent:
    """
    Self-contained attack reconnaissance agent.

    When triggered, this agent uses a custom MCP server to analyze network traffic
    from the vulnerable server's log files and identify attack patterns.
    """

    def __init__(
        self,
        working_dir: Optional[Path] = None,
        server_command: Optional[str] = None,
        server_script: Optional[str] = None,
        client_session_timeout_seconds: float = 300.0,
    ) -> None:
        """
        Initialize the recon agent.

        Args:
            working_dir: Optional working directory. If None, uses current directory.
                         Expects vulnerable-app/attack_log.json relative to working directory.
            server_command: Command used to start the MCP server (defaults to the
                            current Python executable).
            server_script: Path to the MCP server script. If None, defaults to
                           log_reader_mcp_server.py in the same directory as this file.
            client_session_timeout_seconds: Timeout in seconds for the MCP client session.
        """
        if working_dir is None:
            working_dir = Path.cwd()
        self.working_dir = working_dir

        self.server_command = server_command
        self.server_script = server_script
        self.client_session_timeout_seconds = client_session_timeout_seconds

    async def investigate_async(self, context: Optional[Dict] = None) -> Dict:
        """
        Main entry point: Conduct reconnaissance analysis using network traffic.

        Args:
            context: Optional context from orchestrator (e.g., suspicious activity trigger)

        Returns:
            Comprehensive recon report with attack assessment
        """
        # Ensure API key is present (Agents SDK uses the OpenAI Python SDK under the hood)
        if "OPENAI_API_KEY" not in os.environ:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set")

        set_default_openai_api(os.environ["OPENAI_API_KEY"])
        set_tracing_disabled(True)

        async with ReconAgentContext(
            server_command=self.server_command,
            server_script=self.server_script,
            client_session_timeout_seconds=self.client_session_timeout_seconds,
        ) as recon_agent:
            context_str = ""
            if context:
                context_str = f"\n\nContext: {context}"

            task = (
                "Analyze network traffic logs for security attacks.\n\n"
                f"Working directory: {self.working_dir}\n"
                "The logs are located at vulnerable-app/attack_log.json in the working directory.\n\n"
                f"STEP 1: Call the read_network_logs tool with lines=50 and "
                f'working_dir="{self.working_dir}" to read the recent log entries.\n'
                "STEP 2: The tool will return a dictionary with 'entries' (list of log objects) "
                "and 'total_count'.\n"
                "STEP 3: Analyze ALL entries in the 'entries' list for attack patterns.\n\n"
                "Look for these attack patterns:\n\n"
                "1. SQL INJECTION - Found in 'query' values or 'body' values:\n"
                '   - Contains: \"OR 1=1\", \"OR \'1\'=\'1\'\", \"UNION SELECT\", \"DROP TABLE\", '
                "single quotes with SQL keywords\n"
                '   - Examples: \"admin\' OR \'1\'=\'1\' --\", \"\' UNION SELECT * FROM users --\", '
                "\"'; DROP TABLE users; --\"\n\n"
                "2. PATH TRAVERSAL - Found in 'endpoint' or 'query' file parameters:\n"
                '   - Contains: \"../\", \"..\\\\\", \"/etc/passwd\", multiple \"../\" sequences\n'
                '   - Examples: \"/download-db?file=../../../etc/passwd\", '
                '\"/source?file=../../../../etc/passwd\"\n\n'
                "3. RECONNAISSANCE/HONEYPOT - Found in 'endpoint':\n"
                '   - Honeypots: \"/admin-v2\", \"/config-prod\", \"/backup-db\"\n'
                '   - Recon: \"/.env\", \"/.git/config\", \"/debug\"\n\n'
                "Return ONLY a valid JSON object (no markdown, no code blocks, just the JSON) with this structure:\n"
                "{\n"
                '  \"attack_assessment\": {\n'
                '    \"attack_type\": \"sql_injection\" or \"path_traversal\" or '
                '\"reconnaissance\" or \"multiple\" or \"unknown\",\n'
                '    \"target\": \"specific endpoint or multiple_endpoints\",\n'
                '    \"severity\": \"high\" or \"critical\" if ANY attacks found, '
                '\"low\" ONLY if zero attacks found,\n'
                '    \"confidence\": \"high\" if clear attack patterns found\n'
                "  },\n"
                '  \"evidence\": [\"Specific finding from logs with details\", '
                "\"Another finding\", ...],\n"
                '  \"recommendations\": [\"Defensive action 1\", \"Defensive action 2\", ...],\n'
                '  \"intelligence\": {\"total_requests\": <use total_count from tool result>, '
                '"unique_endpoints\": <actual count>, '
                '"attack_count\": <actual count of attacks found>}\n'
                "}\n\n"
                "IMPORTANT: Use the 'total_count' from the tool result for total_requests. "
                "Count the actual number of attacks you find! "
                "If you see SQL injection, path traversal, or honeypot hits, attack_count should be > 0 "
                "and severity should be 'high' or 'critical', not 'low'!"
                f"{context_str}"
            )

            result = await Runner.run(
                recon_agent,
                task,
                hooks=ToolLoggingHooks(),
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
                return report
            except json.JSONDecodeError:
                pass

        # If no JSON found, return a structured response with the text output
        return {
            "timestamp": self._get_timestamp(),
            "investigation_trigger": context or "manual_investigation",
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
            Comprehensive recon report with attack assessment
        """
        return asyncio.run(self.investigate_async(context))

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime

        return datetime.utcnow().isoformat()