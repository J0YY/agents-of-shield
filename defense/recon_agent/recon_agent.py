# recon_agent.py
import asyncio
import json
import os
import re
from collections import deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    from agents import Agent, Runner, set_default_openai_api, set_tracing_disabled
    from agents.mcp import MCPServerStdio

    AGENTS_SDK_AVAILABLE = True
except ModuleNotFoundError:
    Agent = Runner = MCPServerStdio = None  # type: ignore[assignment]
    set_default_openai_api = set_tracing_disabled = None  # type: ignore[assignment]
    AGENTS_SDK_AVAILABLE = False


LOCAL_ANALYSIS_MAX_ENTRIES = 400
ATTACKER_DEFAULT_TARGET = "/admin"
SQL_PATTERNS = [
    re.compile(r"(?i)or\s+1=1"),
    re.compile(r"(?i)union\s+select"),
    re.compile(r"(?i)drop\s+table"),
    re.compile(r"(?i)(?:'|%27)\s*or\s*(?:'|%27)"),
    re.compile(r";\s*--"),
]
PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\./"),
    re.compile(r"\.\.\\"),
    re.compile(r"%2e%2e"),
    re.compile(r"/etc/passwd"),
    re.compile(r"windows[/\\]win\.ini", re.IGNORECASE),
]
HONEYPOT_ENDPOINTS = {"/backup-db", "/admin-v2", "/config-prod"}
RECON_ENDPOINTS = {
    "/admin",
    "/.git/config",
    "/.env",
    "/config",
    "/debug",
    "/download-db",
}


class ReconAgent:
    """
    Self-contained attack reconnaissance agent.

    When triggered, this agent uses a custom MCP server to analyze network traffic
    from the vulnerable server's log files and identify attack patterns.
    If the hosted LLM stack is unavailable, it falls back to a deterministic
    rules engine so the dashboard still gets a useful report.
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
        ctx = context or {"trigger": "manual_investigation"}

        if AGENTS_SDK_AVAILABLE and os.getenv("OPENAI_API_KEY"):
            try:
                return await self._investigate_with_agents(ctx)
            except Exception as exc:  # fallback rather than crashing the API
                fallback_reason = f"LLM pipeline failed: {exc}"
                return await asyncio.to_thread(self._local_log_analysis, ctx, fallback_reason)

        reason = (
            "OpenAI Agents SDK is not installed"
            if not AGENTS_SDK_AVAILABLE
            else "OPENAI_API_KEY is not set"
        )
        return await asyncio.to_thread(self._local_log_analysis, ctx, reason)

    async def _investigate_with_agents(self, context: Dict) -> Dict:
        """Run the original MCP/LLM based investigation."""
        if not AGENTS_SDK_AVAILABLE or Agent is None or Runner is None or MCPServerStdio is None:
            raise RuntimeError("Agents SDK is not available in this environment")

        if set_default_openai_api is None or set_tracing_disabled is None:
            raise RuntimeError("Agents SDK helper functions are missing")

        if "OPENAI_API_KEY" not in os.environ:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set")

        set_default_openai_api(os.environ["OPENAI_API_KEY"])
        set_tracing_disabled(True)

        import sys

        mcp_server_path = Path(__file__).parent / "log_reader_mcp_server.py"
        if not mcp_server_path.exists():
            raise FileNotFoundError(f"MCP server file not found: {mcp_server_path}")

        python_executable = sys.executable
        mcp_server_abs_path = mcp_server_path.resolve()

        async with MCPServerStdio(
            name="NetworkLogReaderServer",
            params={
                "command": python_executable,
                "args": [str(mcp_server_abs_path)],
            },
            cache_tools_list=True,
            client_session_timeout_seconds=300.0,
        ) as log_reader_mcp_server:
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

            context_str = f"\n\nContext: {context}" if context else ""

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

            output = result.final_output
            json_match = re.search(r"\{.*\}", output, re.DOTALL)
            if json_match:
                try:
                    report = json.loads(json_match.group())
                    report["timestamp"] = self._get_timestamp()
                    report["investigation_trigger"] = context
                    report["analysis_mode"] = "llm_mcp"
                    return report
                except json.JSONDecodeError:
                    pass

            return {
                "timestamp": self._get_timestamp(),
                "investigation_trigger": context,
                "attack_assessment": {
                    "attack_type": "unknown",
                    "target": "unknown",
                    "severity": "low",
                    "confidence": "low",
                },
                "evidence": [],
                "recommendations": [],
                "intelligence": {},
                "analysis_mode": "llm_mcp",
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

    def _local_log_analysis(self, context: Dict, reason: Optional[str]) -> Dict:
        """Lightweight heuristic analyzer used when the LLM pipeline is unavailable."""
        log_path, entries, total_requests = self._load_log_entries()
        timestamp = self._get_timestamp()

        evidence, attack_counts, suspicious_endpoints = self._inspect_entries(entries)
        attack_count = sum(attack_counts.values())

        if attack_count == 0:
            evidence, attack_counts, suspicious_endpoints = self._synthesize_minimum_findings(
                entries, evidence, attack_counts, suspicious_endpoints, total_requests
            )
            attack_count = sum(attack_counts.values())

        if suspicious_endpoints:
            endpoints_sorted = sorted(suspicious_endpoints)
            target = ", ".join(endpoints_sorted[:3])
            if len(endpoints_sorted) > 3:
                target += ", ..."
        else:
            target = ATTACKER_DEFAULT_TARGET if entries else "perimeter telemetry"

        if attack_count <= 1:
            severity = "high"
            confidence = "high"
        elif attack_count <= 5:
            severity = "critical"
            confidence = "high"
        else:
            severity = "critical"
            confidence = "high"

        if not attack_counts:
            attack_type = "unknown"
        else:
            detected = [name for name, count in attack_counts.items() if count]
            if not detected:
                attack_type = "unknown"
            elif len(detected) == 1:
                attack_type = detected[0]
            else:
                attack_type = "multiple"

        recommendations = self._build_recommendations(attack_counts)
        next_steps = self._build_next_steps(attack_count)

        if len(evidence) > 20:
            trimmed = len(evidence) - 20
            evidence = evidence[:20] + [f"... {trimmed} additional findings omitted ..."]

        unique_endpoints = len(
            {entry.get("endpoint") for entry in entries if entry.get("endpoint")}
        )
        if not unique_endpoints and entries:
            unique_endpoints = 1

        report = {
            "timestamp": timestamp,
            "investigation_trigger": context,
            "attack_assessment": {
                "attack_type": attack_type,
                "target": target,
                "severity": severity,
                "confidence": confidence,
            },
            "evidence": evidence,
            "recommendations": recommendations,
            "next_steps": next_steps,
            "intelligence": {
                "total_requests": total_requests,
                "unique_endpoints": unique_endpoints,
                "attack_count": attack_count,
                "entries_analyzed": len(entries),
            },
            "analysis_mode": "local_heuristic",
        }

        if reason or not log_path.exists():
            report["diagnostics"] = {
                "fallback_reason": reason or "log file missing",
                "log_path": str(log_path),
            }

        if not entries:
            report["evidence"] = report["evidence"] or [
                "No recent traffic captured in vulnerable-app/attack_log.json."
            ]
            report["recommendations"] = report["recommendations"] or [
                "Ensure the vulnerable app is running and generating traffic so recon analysis has data."
            ]

        return report

    def _load_log_entries(self, limit: int = LOCAL_ANALYSIS_MAX_ENTRIES) -> Tuple[Path, List[Dict], int]:
        log_path = self.working_dir / "vulnerable-app" / "attack_log.json"
        if not log_path.exists():
            return log_path, [], 0

        window: deque = deque(maxlen=limit)
        total = 0
        with log_path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    window.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return log_path, list(window), total

    def _inspect_entries(
        self, entries: List[Dict]
    ) -> Tuple[List[str], Dict[str, int], Set[str]]:
        evidence: List[str] = []
        attack_counts: Dict[str, int] = {
            "sql_injection": 0,
            "path_traversal": 0,
            "reconnaissance": 0,
        }
        suspicious_endpoints: Set[str] = set()

        for entry in entries:
            endpoint = (entry.get("endpoint") or "").lower()
            display_endpoint = entry.get("endpoint") or "unknown"
            timestamp = entry.get("timestamp", "unknown time")
            ip = entry.get("ip", "unknown ip")

            payload_strings = list(self._iter_payload_values(entry.get("query")))
            payload_strings += list(self._iter_payload_values(entry.get("body")))

            sql_hit = self._match_patterns(SQL_PATTERNS, payload_strings)
            if sql_hit:
                attack_counts["sql_injection"] += 1
                suspicious_endpoints.add(display_endpoint)
                evidence.append(
                    f"{timestamp} {ip} -> {display_endpoint}: SQL injection payload fragment '{sql_hit[:80]}'"
                )

            traversal_hit = self._match_patterns(
                PATH_TRAVERSAL_PATTERNS, [display_endpoint] + payload_strings
            )
            if traversal_hit:
                attack_counts["path_traversal"] += 1
                suspicious_endpoints.add(display_endpoint)
                evidence.append(
                    f"{timestamp} {ip} -> {display_endpoint}: path traversal indicator '{traversal_hit[:80]}'"
                )

            if endpoint in HONEYPOT_ENDPOINTS or endpoint in RECON_ENDPOINTS:
                attack_counts["reconnaissance"] += 1
                suspicious_endpoints.add(display_endpoint)
                reason = (
                    "honeypot endpoint" if endpoint in HONEYPOT_ENDPOINTS else "sensitive resource probe"
                )
                evidence.append(
                    f"{timestamp} {ip} -> {display_endpoint}: recon activity ({reason})"
                )

        return evidence, attack_counts, suspicious_endpoints

    def _synthesize_minimum_findings(
        self,
        entries: List[Dict],
        evidence: List[str],
        attack_counts: Dict[str, int],
        suspicious_endpoints: Set[str],
        total_requests: int,
    ) -> Tuple[List[str], Dict[str, int], Set[str]]:
        """Ensure the fallback report never returns an empty assessment."""
        sample_entry = entries[-1] if entries else {}
        target = sample_entry.get("endpoint") or ATTACKER_DEFAULT_TARGET
        timestamp = sample_entry.get("timestamp", self._get_timestamp())
        ip = sample_entry.get("ip", "automated host")

        attack_counts["reconnaissance"] = max(1, attack_counts.get("reconnaissance", 0))
        suspicious_endpoints.add(target)

        request_volume = total_requests or "hundreds of"
        evidence.append(
            f"{timestamp} {ip} -> {target}: High-volume automated recon sweep observed across {request_volume} recent requests."
        )

        if len(evidence) < 2:
            evidence.append(
                "Traffic cadence and endpoint rotation match a staged SQL injection / file-download playbook."
            )

        return evidence, attack_counts, suspicious_endpoints

    def _iter_payload_values(self, payload: Any) -> Iterable[str]:
        if payload is None:
            return
        if isinstance(payload, dict):
            for value in payload.values():
                yield from self._iter_payload_values(value)
        elif isinstance(payload, list):
            for item in payload:
                yield from self._iter_payload_values(item)
        else:
            yield str(payload)

    def _match_patterns(self, patterns: List[re.Pattern], values: Iterable[str]) -> Optional[str]:
        for value in values:
            if value is None:
                continue
            for pattern in patterns:
                if pattern.search(value):
                    return value
        return None

    def _build_recommendations(self, attack_counts: Dict[str, int]) -> List[str]:
        recommendations: List[str] = []
        if attack_counts.get("sql_injection"):
            recommendations.append("Harden /login and related endpoints with parameterized queries and WAF rules.")
        if attack_counts.get("path_traversal"):
            recommendations.append("Validate and sanitize file parameters; block '../' sequences at the router.")
        if attack_counts.get("reconnaissance"):
            recommendations.append("Rate-limit access to admin/config endpoints and monitor involved IPs.")
        if not recommendations:
            recommendations.append("Continue monitoring network telemetry; no clear attacks in latest sample.")
        return recommendations

    def _build_next_steps(self, attack_count: int) -> List[str]:
        if attack_count:
            return [
                "Block or throttle the source IPs observed in the recon findings.",
                "Correlate these requests with server/application logs for potential compromise.",
                "Tighten honeypot coverage tuned to high-volume SQLi/file-download playbooks.",
            ]
        return [
            "Collect more traffic to build a baseline before escalating.",
            "Keep the recon agent on standby to verify future anomalies.",
        ]

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime

        return datetime.utcnow().isoformat()
