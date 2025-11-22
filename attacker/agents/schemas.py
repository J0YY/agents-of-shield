from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Action:
    action_type: str
    target_url: str
    payload: Optional[Dict[str, str]] = field(default_factory=dict)
    reasoning: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "action_type": self.action_type.upper(),
            "target_url": self.target_url,
            "payload": self.payload or {},
            "reasoning": self.reasoning,
        }


def coerce_action(data: Dict[str, object]) -> Action:
    action_type = str(data.get("action_type", "GET")).upper()
    if action_type not in {"GET", "POST"}:
        action_type = "GET"

    target_url = str(data.get("target_url", "http://localhost:3000/"))
    if not target_url.startswith("http://localhost:3000"):
        target_url = "http://localhost:3000/"

    payload = data.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    reasoning = str(data.get("reasoning", "Planner fallback"))
    return Action(action_type=action_type, target_url=target_url, payload=payload, reasoning=reasoning)


def default_memory() -> Dict[str, List[str]]:
    return {
        "visited": [],
        "known_forms": [],
        "suspected_vulns": [],
        "goals": [
            "recon_homepage",
            "enumerate_endpoints",
            "find_admin_panel",
            "dump_database",
            "steal_configs",
        ],
        "next_steps": [],
        "successes": [],
        "failures": [],
        "history": [],
        "recent_actions": [],
        "alerts": [],
        "honeypot_notes": [],
    }
