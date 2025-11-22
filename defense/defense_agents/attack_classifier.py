from __future__ import annotations

from typing import Dict
from urllib.parse import urlparse


class AttackClassifier:
    """Classifies attacker intent based on endpoint + payload heuristics."""

    def classify(self, event: Dict, payload_report: Dict) -> Dict:
        endpoint = event.get("action", {}).get("target_url", "")
        path = urlparse(endpoint).path or endpoint
        summary = (event.get("response_summary") or "").lower()
        score = payload_report.get("payload_risk_score", 0)

        label = "reconnaissance"
        reasoning = "Initial probing phase"

        if "/login" in path and score >= 40:
            label = "sql_injection"
            reasoning = "SQLi risk score triggered on authentication endpoint"
        elif "../" in path or "etc" in path.lower():
            label = "path_traversal"
            reasoning = "Suspicious traversal-like path detected"
        elif "/admin" in path:
            label = "admin_exposure"
            reasoning = "Attempt to reach administrative surface"
        elif "/config" in path or "api key" in summary:
            label = "config_leak"
            reasoning = "Attacker is extracting configuration"
        elif "honeypot" in summary:
            label = "honeypot_hit"
            reasoning = "Event summary indicates decoy interaction"
        elif score >= 30:
            label = "payload_probe"
            reasoning = "Payload triggered medium risk heuristics"

        return {"label": label, "reasoning": reasoning}

