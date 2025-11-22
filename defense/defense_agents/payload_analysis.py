from __future__ import annotations

import json
from typing import Dict, List


class PayloadAnalysisAgent:
    """Lightweight heuristics for spotting suspicious payloads."""

    SQLI_SIGNS = ["' OR '", "\" OR \"", "SELECT", "UNION", ";--", "'--", "DROP", "INSERT"]
    TRAVERSAL_SIGNS = ["../", "..\\", "%2e%2e", "%252e%252e"]

    def analyze(self, event: Dict) -> Dict:
        payload = event.get("action", {}).get("payload") or {}
        headers = event.get("action", {}).get("headers") or {}
        payload_blob = json.dumps(payload, ensure_ascii=False).upper()
        indicators: List[str] = []
        score = 0

        if any(sig in payload_blob for sig in self.SQLI_SIGNS):
            indicators.append("SQLi pattern detected")
            score += 45

        if any(sig.upper() in payload_blob for sig in self.TRAVERSAL_SIGNS):
            indicators.append("Path traversal attempt")
            score += 35

        user_agent = headers.get("User-Agent", "")
        if "sqlmap" in user_agent.lower():
            indicators.append("sqlmap user-agent observed")
            score += 20

        if payload_blob.count("'") > 5:
            indicators.append("Unusual quote density")
            score += 10

        risk_score = min(100, score)
        return {
            "payload_risk_score": risk_score,
            "indicators": indicators,
            "payload_excerpt": payload_blob[:160],
        }

