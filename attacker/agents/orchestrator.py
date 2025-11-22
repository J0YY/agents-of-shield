from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from .schemas import coerce_action

MODEL_NAME = os.getenv("OPENAI_ATTACK_MODEL", "gpt-4o-mini")
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _collect_output_text(result) -> str:
    if hasattr(result, "choices"):
        choice = result.choices[0]
        content = choice.message.get("content") if isinstance(choice.message, dict) else choice.message.content
        if isinstance(content, list):
            return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
        return content or ""
    return ""


def _safe_json_parse(blob: str) -> Dict[str, object]:
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        start = blob.find("{")
        end = blob.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = blob[start : end + 1]
            return json.loads(snippet)
    raise ValueError("Unable to parse JSON payload from orchestrator response")


@dataclass
class AgentTool:
    key: str
    prompt_name: str
    description: str
    toolbox: List[Dict[str, str]]
    temperature: float = 0.25

    def run(
        self,
        client: OpenAI,
        memory: Dict[str, object],
        context: Dict[str, object],
    ) -> Tuple[Dict[str, object], Dict[str, object]]:
        """Execute the specialist prompt and return the coerced action plus metadata."""

        payload = {
            "memory": memory,
            "context": context,
            "toolbox": self.toolbox,
        }

        system_prompt = (PROMPTS_DIR / self.prompt_name).read_text().strip()
        result = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )

        response_text = _collect_output_text(result).strip()

        try:
            parsed = _safe_json_parse(response_text)
        except ValueError:
            parsed = {}

        action = coerce_action(parsed)
        metadata = {
            "agent": self.key,
            "selected_tool": parsed.get("selected_tool") or parsed.get("tool_used") or "",
            "agent_notes": parsed.get("notes") or parsed.get("reasoning") or action.reasoning,
        }
        return action.to_dict(), metadata


@dataclass
class HoneypotAssessment:
    suspected: bool = False
    verified: bool = False
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def to_payload(self) -> Dict[str, object]:
        return {
            "suspected": self.suspected,
            "verified": self.verified,
            "score": round(self.score, 2),
            "reasons": self.reasons[-5:],
        }


class HoneypotMonitor:
    """Track qualitative honeypot suspicion across the attack loop."""

    def __init__(self, suspicion_threshold: float = 1.2, verification_threshold: float = 3.0):
        self.suspicion_threshold = suspicion_threshold
        self.verification_threshold = verification_threshold
        self._state = HoneypotAssessment()
        self._body_fingerprints: List[str] = []

    @property
    def state(self) -> HoneypotAssessment:
        return self._state

    def evaluate(
        self,
        raw_body: str,
        perception: Dict[str, object],
        status: int,
        action: Dict[str, object],
    ) -> HoneypotAssessment:
        reasons: List[str] = []
        delta = 0.0

        body = (raw_body or "").lower()
        keywords = [kw.lower() for kw in (perception.get("keywords") or [])]
        errors = [err.lower() for err in (perception.get("errors") or [])]

        if "honeypot" in body or any("honeypot" in kw for kw in keywords):
            delta += 1.6
            reasons.append("Server explicitly references honeypot terminology.")
        if "training" in body or "simulation" in body:
            delta += 0.6
            reasons.append("Copy hints at training or simulation environment.")
        if any("deception" in err or "trap" in err for err in errors):
            delta += 0.8
            reasons.append("Error output signals deception/trap keywords.")

        if status in (401, 403) and action.get("target_url", "").rstrip("/").endswith(("/admin", "/debug", "/root")):
            delta += 0.4
            reasons.append("Restricted admin/debug endpoint repeatedly blocked.")

        snippet = body[:160]
        self._body_fingerprints.append(snippet)
        if len(self._body_fingerprints) >= 3:
            last_three = self._body_fingerprints[-3:]
            if all(f == last_three[0] for f in last_three):
                delta += 0.5
                reasons.append("Received identical body three times in a row.")

        # natural decay nudges suspicion down slowly
        score = max(0.0, self._state.score + delta - 0.1)
        suspected = score >= self.suspicion_threshold
        verified = score >= self.verification_threshold or (suspected and any("honeypot" in r.lower() for r in reasons))

        merged_reasons = (self._state.reasons + reasons)[-6:]
        self._state = HoneypotAssessment(
            suspected=suspected,
            verified=verified,
            score=score,
            reasons=merged_reasons,
        )
        return self._state


class AttackOrchestrator:
    """Routes control between specialist agents/tool calls for the attacker."""

    def __init__(self) -> None:
        self.client = OpenAI()
        self.selection_prompt = (PROMPTS_DIR / "system_orchestrator.txt").read_text().strip()
        self.agent_tools: Dict[str, AgentTool] = {
            "recon": AgentTool(
                key="recon",
                prompt_name="system_recon_agent.txt",
                description="Perform reconnaissance sweeps and enumerate new MCP points.",
                toolbox=[
                    {"name": "LinkWalker", "description": "Traverse anchors and directory listings."},
                    {"name": "HeaderPeek", "description": "Inspect HTTP headers for tech fingerprinting."},
                    {"name": "AssetMap", "description": "Collect asset references (/js, /css, /img)."},
                ],
            ),
            "mcp_point_scan": AgentTool(
                key="mcp_point_scan",
                prompt_name="system_mcp_scanner.txt",
                description="Run MCP point scanning to fuzz parameters and context pivots.",
                toolbox=[
                    {"name": "ParamFuzzer", "description": "Inject crafted query/body parameters."},
                    {"name": "ContextDiff", "description": "Compare responses for subtle clue changes."},
                    {"name": "HeuristicProbe", "description": "Toggle auth/session hints to locate control points."},
                ],
                temperature=0.35,
            ),
            "attack": AgentTool(
                key="attack",
                prompt_name="system_attack_agent.txt",
                description="Execute primary exploit attempts leveraging gathered intel.",
                toolbox=[
                    {"name": "AuthBypass", "description": "Reuse cookies/tokens/fields to skip auth."},
                    {"name": "Traversal", "description": "Leverage path traversal (../) in download endpoints."},
                    {"name": "DataExfil", "description": "Dump DB/config artifacts like /download-db."},
                ],
                temperature=0.4,
            ),
            "mcp_sql_generator": AgentTool(
                key="mcp_sql_generator",
                prompt_name="system_mcp_sql.txt",
                description="Model Context Protocol → SQL generator for offensive payload crafting.",
                toolbox=[
                    {"name": "BooleanBlind", "description": "Use true/false SQL predicates to infer data."},
                    {"name": "UnionJack", "description": "Inject UNION SELECT payloads for data exfil."},
                    {"name": "TimeDelay", "description": "Use sleep-based payloads to confirm injection."},
                ],
                temperature=0.45,
            ),
            "utility": AgentTool(
                key="utility",
                prompt_name="system_utility_agent.txt",
                description="Other tools: health checks, wordlists, config pokes.",
                toolbox=[
                    {"name": "RobotsScout", "description": "Fetch robots.txt / sitemap for hidden dirs."},
                    {"name": "HealthProbe", "description": "Hit /status, /healthz for environment leaks."},
                    {"name": "Wordlist", "description": "Try curated paths (debug, backup, console)."},
                ],
            ),
            "honeypot_verifier": AgentTool(
                key="honeypot_verifier",
                prompt_name="system_honeypot_verifier.txt",
                description="Low-and-slow probe to confirm or dismiss honeypot suspicions.",
                toolbox=[
                    {"name": "HeaderCheck", "description": "Request innocuous endpoint and inspect headers."},
                    {"name": "TimingProbe", "description": "Measure latency differences with harmless payloads."},
                    {"name": "Canary", "description": "Drop distinctive token and see if mirrored back."},
                ],
                temperature=0.2,
            ),
        }

    def plan_action(
        self,
        memory: Dict[str, object],
        last_perception: Optional[Dict[str, object]],
        honeypot_state: HoneypotAssessment,
    ) -> Tuple[Dict[str, object], Dict[str, object]]:
        agent_key, selection_meta = self._select_agent(memory, last_perception, honeypot_state)
        tool = self.agent_tools.get(agent_key, self.agent_tools["attack"])

        context = {
            "last_perception": last_perception or {},
            "honeypot": honeypot_state.to_payload(),
            "selection": selection_meta,
        }

        action, agent_meta = tool.run(self.client, memory, context)
        orchestration_meta = {**selection_meta, **agent_meta}
        return action, orchestration_meta

    def _select_agent(
        self,
        memory: Dict[str, object],
        last_perception: Optional[Dict[str, object]],
        honeypot_state: HoneypotAssessment,
    ) -> Tuple[str, Dict[str, object]]:
        payload = {
            "memory_snapshot": memory,
            "last_perception": last_perception or {},
            "honeypot_state": honeypot_state.to_payload(),
            "agents": [
                {"key": tool.key, "description": tool.description}
                for tool in self.agent_tools.values()
            ],
        }

        result = self.client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.0,
            messages=[
                {"role": "system", "content": self.selection_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )

        response_text = _collect_output_text(result).strip()
        try:
            parsed = _safe_json_parse(response_text)
        except ValueError:
            parsed = {}

        agent_key = parsed.get("agent") or parsed.get("mode") or "attack"
        confidence = parsed.get("confidence")
        if agent_key not in self.agent_tools:
            agent_key = "attack"
        selection_meta = {
            "agent": agent_key,
            "selection_reason": parsed.get("reasoning", ""),
            "confidence": confidence if isinstance(confidence, (int, float)) else None,
        }
        return agent_key, selection_meta

