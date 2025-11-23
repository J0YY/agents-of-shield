#!/usr/bin/env python3
"""
Stream Cowrie SSH honeypot events into the defense orchestrator so the dashboard can
display them in real time.

Usage:
    python defense/tools/cowrie_bridge.py

Environment variables / CLI flags allow overriding log path, API endpoint, etc.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = REPO_ROOT / "tpotce" / "data" / "cowrie" / "log" / "cowrie.json"
STATE_FILE = REPO_ROOT / "defense" / "state" / "cowrie_bridge_state.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Forward Cowrie events to the defense orchestrator.")
    parser.add_argument(
        "--log",
        default=os.getenv("COWRIE_LOG_PATH", str(DEFAULT_LOG_PATH)),
        help="Path to cowrie.json (default: %(default)s)",
    )
    parser.add_argument(
        "--api",
        default=os.getenv("COWRIE_BRIDGE_DEFENSE_API", "http://localhost:7700"),
        help="Defense orchestrator base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--state",
        default=os.getenv("COWRIE_BRIDGE_STATE_FILE", str(STATE_FILE)),
        help="Path to store reader offset/step (default: %(default)s)",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=float(os.getenv("COWRIE_BRIDGE_POLL_INTERVAL", "1.0")),
        help="Seconds between EOF polls (default: %(default)s)",
    )
    return parser.parse_args()


def load_state(path: Path) -> Tuple[int, int]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return int(data.get("offset", 0)), int(data.get("step", 0))
        except (json.JSONDecodeError, ValueError):
            pass
    return 0, 0


def save_state(path: Path, offset: int, step: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"offset": offset, "step": step}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def post_event(defense_api: str, payload: Dict[str, object]) -> None:
    url = defense_api.rstrip("/") + "/attack-event"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)  # nosec B310
    except urllib.error.URLError as exc:
        print(f"[cowrie-bridge] Failed to post event: {exc}")


def build_attack_event(entry: Dict[str, object], step: int) -> Dict[str, object]:
    event_type = str(entry.get("eventid", "cowrie.event"))
    dst_ip = entry.get("dst_ip") or entry.get("sensor") or "cowrie"
    dst_port = entry.get("dst_port") or 2222
    summary = entry.get("message") or event_type
    timestamp = entry.get("timestamp") or datetime.now(timezone.utc).isoformat()

    action = {
        "action_type": f"COWRIE_{event_type}",
        "target_url": f"ssh://{dst_ip}:{dst_port}",
        "payload": entry,
    }
    return {
        "step": step,
        "action": action,
        "status": 0,
        "response_summary": summary,
        "timestamp": timestamp,
    }


def tail_log(args: argparse.Namespace) -> None:
    log_path = Path(args.log)
    state_path = Path(args.state)

    if not log_path.exists():
        raise FileNotFoundError(f"Cowrie log not found at {log_path}")

    offset, step = load_state(state_path)
    print(f"[cowrie-bridge] Starting from offset {offset}, step {step}")

    with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
        handle.seek(offset)
        while True:
            line = handle.readline()
            if not line:
                time.sleep(args.poll)
                continue

            offset = handle.tell()
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                print(f"[cowrie-bridge] Skipping malformed line: {line.strip()[:80]}")
                save_state(state_path, offset, step)
                continue

            step += 1
            event_payload = build_attack_event(entry, step)
            post_event(args.api, event_payload)
            save_state(state_path, offset, step)


def main() -> None:
    args = parse_args()
    try:
        tail_log(args)
    except KeyboardInterrupt:
        print("\n[cowrie-bridge] Stopped by user.")


if __name__ == "__main__":
    main()

