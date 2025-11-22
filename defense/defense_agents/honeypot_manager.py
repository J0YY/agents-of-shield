from __future__ import annotations

import json
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse


class HoneypotManager:
    """Tracks decoy endpoints and notes when attackers touch them."""

    HONEYPOTS = {
        "/admin-v2": "Decoy admin interface",
        "/backup-db": "Decoy backup snapshot",
        "/config-prod": "Decoy production config",
    }

    def __init__(self, state_dir: Path) -> None:
        self.state_file = state_dir / "honeypot_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()

    def _load_state(self) -> Dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {"honeypots": {hp: {"description": desc, "last_trigger_step": None} for hp, desc in self.HONEYPOTS.items()}}

    def _persist(self) -> None:
        self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def inspect(self, event: Dict) -> Dict:
        target_url = event.get("action", {}).get("target_url", "")
        path = urlparse(target_url).path or target_url

        result = {"triggered": False, "honeypot": None}
        for endpoint, description in self.HONEYPOTS.items():
            if path.startswith(endpoint):
                self._state["honeypots"][endpoint] = {
                    "description": description,
                    "last_trigger_step": event.get("step"),
                    "payload": event.get("action", {}).get("payload", {}),
                    "timestamp": event.get("timestamp"),
                }
                self._persist()
                result.update(
                    {
                        "triggered": True,
                        "honeypot": endpoint,
                        "description": description,
                    }
                )
                break
        return result

