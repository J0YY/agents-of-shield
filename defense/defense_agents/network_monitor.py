from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict


class NetworkMonitor:
    """Persists every attacker action for chronological replay."""

    def __init__(self, state_dir: Path) -> None:
        self.log_file = state_dir / "network_events.jsonl"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.touch(exist_ok=True)

    def record(self, event: Dict) -> Dict:
        record = {
            "step": event.get("step"),
            "endpoint": event.get("action", {}).get("target_url"),
            "method": event.get("action", {}).get("action_type"),
            "status": event.get("status"),
            "summary": event.get("response_summary"),
            "timestamp": event.get("timestamp") or datetime.utcnow().isoformat(),
        }
        with self.log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

