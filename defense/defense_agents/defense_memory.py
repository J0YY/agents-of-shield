from __future__ import annotations

import json
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse


class DefenseMemoryAgent:
    """Long-term defensive memory that accumulates learnings between runs."""

    def __init__(self, state_dir: Path) -> None:
        self.memory_file = state_dir / "defense_memory.json"
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self._memory = self._load()

    def _load(self) -> Dict:
        if self.memory_file.exists():
            try:
                return json.loads(self.memory_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {
            "honeypot_history": [],
            "attack_patterns": [],
            "suspicious_endpoints": [],
            "future_recommendations": [],
        }

    def _persist(self) -> None:
        self.memory_file.write_text(json.dumps(self._memory, indent=2), encoding="utf-8")

    def update(
        self,
        event: Dict,
        payload_report: Dict,
        classification: Dict,
        honeypot_result: Dict,
    ) -> Dict:
        path = urlparse(event.get("action", {}).get("target_url", "")).path

        if honeypot_result.get("triggered"):
            entry = {
                "step": event.get("step"),
                "endpoint": honeypot_result.get("honeypot"),
                "timestamp": event.get("timestamp"),
            }
            self._memory["honeypot_history"].append(entry)

        if classification.get("label") not in {"reconnaissance", "payload_probe"}:
            pattern = {"label": classification.get("label"), "path": path}
            if pattern not in self._memory["attack_patterns"]:
                self._memory["attack_patterns"].append(pattern)

        if payload_report.get("payload_risk_score", 0) >= 40 and path not in self._memory["suspicious_endpoints"]:
            self._memory["suspicious_endpoints"].append(path)

        recommendations = set(self._memory["future_recommendations"])
        label = classification.get("label")
        if label == "sql_injection":
            recommendations.add("Add prepared statements / WAF for login endpoints")
        if label == "path_traversal":
            recommendations.add("Normalize request paths before file access")
        if honeypot_result.get("triggered"):
            recommendations.add("Promote honeypot telemetry to SIEM rules")
        self._memory["future_recommendations"] = list(recommendations)

        self._persist()
        return self._memory

