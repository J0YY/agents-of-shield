# recon_agent.py
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Optional

from agents import Agent, Runner, set_default_openai_api, set_tracing_disabled
from agents.mcp import MCPServerStdio


class ReconAgent:
    """
    Self-contained attack reconnaissance agent.

    When triggered, this agent uses a custom MCP server to analyze network traffic
    from the vulnerable server's log files and identify attack patterns.
    """

    def __init__(self, working_dir: Optional[Path] = None) -> None:
        """
        Initialize the recon agent.

        Args:
            working_dir: Optional working directory. If None, uses current directory.
                          Expects vulnerable-app/attack_log.json relative to working directory.
        """
        if working_dir is None:
            working_dir = Path.cwd()
        self.working_dir = working_dir

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
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is not set")

        set_default_openai_api(os.environ["OPENAI_API_KEY"])
        set_tracing_disabled(True)

        # Start our custom log reader MCP server as a subprocess over stdio
        import sys

        mcp_server_path = Path(__file__).parent / "log_reader_mcp_server.py"
        if not mcp_server_path.exists():
            raise FileNotFoundError(
                f"MCP server file not found: {mcp_server_path}")

        # Use absolute path for the MCP server script
        mcp_server_abs_path = mcp_server_path.resolve()

        # Use sys.executable to ensure we use the same Python interpreter
        # This is important when running from different environments
        python_executable = sys.executable

        async with MCPServerStdio(
            name="NetworkLogReaderServer",
            params={
                "command": python_executable,
                # absolute path to the server file
                "args": [str(mcp_server_abs_path)],
            },
            cache_tools_list=True,
            client_session_timeout_seconds=300.0,  # 5 minute timeout for investigation
        ) as log_reader_mcp_server:
            # Agent can now call tools from the custom MCP server
            agent = Agent(
                name="ReconAgent",
                model="gpt-4o-mini",
                instructions=(
                    "You are an attack reconnaissance agent analyzing network traffic logs.\n\n"
                    "LOG FORMAT:\n"
                    "- The logs are at vulnerable-app/attack_log.json in JSONL format (one JSON per line)\n"
                    "- Each entry has: timestamp, ip, method, endpoint, query (object), body (object, optional)\n"
                    "- Example: {\"timestamp\":\"...\",\"ip\":\"::1\",\"method\":\"GET\",\"endpoint\":\"/login\",\"query\":{},\"body\":{}}\n\n"
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
                    '  "intelligence": {"total_requests": <use total_count from tool>, "unique_endpoints": N, "attack_count": N}\n'
                    "}\n\n"
                    "CRITICAL: You MUST call the read_network_logs tool first to get the log data before analyzing!"
                ),
                mcp_servers=[log_reader_mcp_server],
            )

            context_str = ""
            if context:
                context_str = f"\n\nContext: {context}"

            task = (
                "Analyze network traffic logs for security attacks.\n\n"
                f"Working directory: {self.working_dir}\n"
                "The logs are located at vulnerable-app/attack_log.json in the working directory.\n\n"
                f"STEP 1: Call the read_network_logs tool with lines=50 and working_dir=\"{self.working_dir}\" to read the recent log entries.\n"
                "STEP 2: The tool will return a dictionary with 'entries' (list of log objects) and 'total_count'.\n"
                "STEP 3: Analyze ALL entries in the 'entries' list for attack patterns.\n\n"
                "Look for these attack patterns:\n\n"
                "1. SQL INJECTION - Found in 'query' values or 'body' values:\n"
                '   - Contains: "OR 1=1", "OR \'1\'=\'1\'", "UNION SELECT", "DROP TABLE", single quotes with SQL keywords\n'
                '   - Examples: "admin\' OR \'1\'=\'1\' --", "\' UNION SELECT * FROM users --", "\'; DROP TABLE users; --"\n\n'
                "2. PATH TRAVERSAL - Found in 'endpoint' or 'query' file parameters:\n"
                '   - Contains: "../", "..\\", "/etc/passwd", multiple "../" sequences\n'
                '   - Examples: "/download-db?file=../../../etc/passwd", "/source?file=../../../../etc/passwd"\n\n'
                "3. RECONNAISSANCE/HONEYPOT - Found in 'endpoint':\n"
                '   - Honeypots: "/admin-v2", "/config-prod", "/backup-db"\n'
                '   - Recon: "/.env", "/.git/config", "/debug"\n\n'
                "Return ONLY a valid JSON object (no markdown, no code blocks, just the JSON) with this structure:\n"
                "{\n"
                '  "attack_assessment": {\n'
                '    "attack_type": "sql_injection" or "path_traversal" or "reconnaissance" or "multiple" or "unknown",\n'
                '    "target": "specific endpoint or multiple_endpoints",\n'
                '    "severity": "high" or "critical" if ANY attacks found, "low" ONLY if zero attacks found,\n'
                '    "confidence": "high" if clear attack patterns found\n'
                "  },\n"
                '  "evidence": ["Specific finding from logs with details", "Another finding", ...],\n'
                '  "recommendations": ["Defensive action 1", "Defensive action 2", ...],\n'
                '  "intelligence": {"total_requests": <use total_count from tool result>, "unique_endpoints": <actual count>, "attack_count": <actual count of attacks found>}\n'
                "}\n\n"
                "IMPORTANT: Use the 'total_count' from the tool result for total_requests. Count the actual number of attacks you find! "
                "If you see SQL injection, path traversal, or honeypot hits, attack_count should be > 0 and severity should be 'high' or 'critical', not 'low'!"
                f"{context_str}"
            )

            result = await Runner.run(agent, task)

            # Parse the result - try to extract JSON if present
            import re

            output = result.final_output

            # Try to find JSON in the output
            json_match = re.search(r'\{.*\}', output, re.DOTALL)
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
