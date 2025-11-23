from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import logging
import os
import subprocess
import sys
from collections import deque
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
TPOT_SCRIPT_PATH = Path(
    os.getenv("TPOT_SCRIPT_PATH", BASE_DIR / "tarpit_boxes" / "tpot.py")
).resolve()
TARPIT_LOG_PATH = Path(
    os.getenv("TARPIT_SSH_LOG", BASE_DIR / "tarpit_boxes" / "ssh_commands.log")
).resolve()
TARPIT_STATE_FILE = Path(
    os.getenv("TARPIT_STATE_FILE", BASE_DIR / "state" / "tarpit_state.json")
).resolve()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class HoneypotManager:
    """Tracks decoy endpoints and notes when attackers touch them."""

    TPOT_SERVICE_META: Dict[str, Dict[str, str]] = {
        "cowrie": {
            "label": "Cowrie",
            "description": "SSH / Telnet credential trap",
            "vector": "SSH · Telnet",
            "method": "Emulates shell access to capture brute-force attempts.",
            "emoji": "🐍",
            "color": "#ffb5d6",
        },
        "dionaea": {
            "label": "Dionaea",
            "description": "Multiprotocol malware catcher",
            "vector": "FTP · SMB · SQL",
            "method": "Listens on common enterprise ports and stores payloads.",
            "emoji": "🧪",
            "color": "#a5f0ff",
        },
        "elasticpot": {
            "label": "ElasticPot",
            "description": "Open Elasticsearch façade",
            "vector": "Elasticsearch",
            "method": "Simulates exposed clusters to bait data exfiltration.",
            "emoji": "📊",
            "color": "#c0b8ff",
        },
        "adbhoney": {
            "label": "ADB Honey",
            "description": "Android debug bridge lure",
            "vector": "ADB",
            "method": "Offers weak Android debug interfaces for takeover attempts.",
            "emoji": "📱",
            "color": "#f9c97d",
        },
        "heralding": {
            "label": "Heralding",
            "description": "Protocol credential snare",
            "vector": "SMTP · DB · VNC",
            "method": "Captures authentication attempts across mixed protocols.",
            "emoji": "🎯",
            "color": "#81f8c0",
        },
    }

    SERVICE_ENDPOINTS = {
        "cowrie": ["/admin-v2", "/admin", "/admin/", "/admin/login"],
        "dionaea": ["/backup-db", "/backup-db/", "/download-db", "/download-db/"],
        "elasticpot": ["/config-prod", "/config-prod/", "/debug", "/env"],
    }

    TPOT_HEADER = "#### Honeypots"
    TPOT_DIVIDER = "##################"

    def __init__(self, state_dir: Path) -> None:
        self.state_file = state_dir / "honeypot_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._tpot_error = None
        self._tpot_services = self._discover_tpot_services()
        self._catalog = self._build_catalog()
        self.runtime_enabled = _env_bool("TPOT_AUTOSTART_ENABLED", True)
        self.stop_unselected = _env_bool("TPOT_STOP_UNSELECTED", False)
        self._state = self._load_state()

    def _build_catalog(self) -> Dict[str, Dict[str, str]]:
        services = self._tpot_services or list(self.TPOT_SERVICE_META.keys())
        catalog: Dict[str, Dict[str, str]] = {}
        fallback_emojis = ["🛰️", "🕵️", "🪤", "🛡️", "🧲"]
        for idx, service in enumerate(services):
            base = self.TPOT_SERVICE_META.get(service, {})
            catalog[service] = {
                "label": base.get("label", service.replace("_", " ").replace("-", " ").title()),
                "description": base.get("description", "TPot honeypot service"),
                "vector": base.get("vector", "Multi-protocol"),
                "method": base.get("method", "Collects telemetry from opportunistic scans."),
                "emoji": base.get("emoji", fallback_emojis[idx % len(fallback_emojis)]),
                "color": base.get("color", "#9da1ff"),
            }
        return catalog

    def _default_entry(self, service: str) -> Dict[str, Any]:
        meta = self._catalog[service]
        return {
            "description": meta["description"],
            "label": meta["label"],
            "vector": meta["vector"],
            "method": meta["method"],
            "emoji": meta["emoji"],
            "color": meta["color"],
            "armed": False,
            "armed_at": None,
            "armed_reason": None,
            "armed_source": None,
            "last_delta": None,
            "last_trigger_step": None,
            "last_trigger_at": None,
            "payload": {},
        }

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        existing = data.get("honeypots", {})
        normalized: Dict[str, Dict[str, Any]] = {}
        for service in self._catalog:
            normalized[service] = {
                **self._default_entry(service),
                **existing.get(service, {}),
            }
        data["honeypots"] = normalized
        return data

    def _discover_tpot_services(self) -> List[str]:
        compose_path = Path(__file__).resolve().parents[2] / "tpotce" / "docker-compose.yml"
        if not compose_path.exists():
            self._tpot_error = f"Compose file missing: {compose_path}"
            return []
        text = compose_path.read_text(encoding="utf-8")
        try:
            header_idx = text.index(self.TPOT_HEADER)
            divider_idx = text.index(self.TPOT_DIVIDER, header_idx)
        except ValueError:
            self._tpot_error = "Unable to locate honeypot block in compose file"
            return []
        section_start = text.find("\n", divider_idx)
        if section_start == -1:
            self._tpot_error = "Malformed compose honeypot block"
            return []
        section_start += 1
        section_end = text.find(self.TPOT_DIVIDER, section_start)
        if section_end == -1:
            self._tpot_error = "Could not find end of honeypot block"
            return []
        block = text[section_start:section_end]
        names = re.findall(r"(?m)^\s{2}([A-Za-z0-9_-]+):\s*$", block)
        if not names:
            self._tpot_error = "No honeypot services detected in compose file"
        return names

    def _invoke_tpot(self, action: str, services: List[str]) -> bool:
        if not self.runtime_enabled or not services:
            return False
        if not TPOT_SCRIPT_PATH.exists():
            logger.warning("TPot controller script not found at %s", TPOT_SCRIPT_PATH)
            return False
        command = [sys.executable, str(TPOT_SCRIPT_PATH), action, *services]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            logger.info("TPot %s executed for services: %s", action, ", ".join(services))
            return True
        except subprocess.CalledProcessError as exc:
            logger.warning("TPot %s failed: %s", action, exc)
            if exc.stdout:
                logger.debug("TPot stdout: %s", exc.stdout)
            if exc.stderr:
                logger.debug("TPot stderr: %s", exc.stderr)
            return False

    def _sync_runtime(self, target_services: List[str]) -> None:
        started = self._invoke_tpot("start", sorted(target_services))
        if self.stop_unselected:
            remaining = [svc for svc in self._catalog if svc not in target_services]
            if remaining:
                self._invoke_tpot("stop", remaining)
        if started and "cowrie" in target_services:
            self._write_tarpit_state({"armed": True, "services": target_services})
        elif self.stop_unselected:
            self._write_tarpit_state({"armed": bool(target_services), "services": target_services})

    def _write_tarpit_state(self, payload: Dict[str, Any]) -> None:
        try:
            TARPIT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            TARPIT_STATE_FILE.write_text(json.dumps({**payload, "timestamp": datetime.utcnow().isoformat()}))
        except OSError as exc:
            logger.debug("Unable to update tarpit state file: %s", exc)

    def _tail_tarpit_log(self, limit: int = 5) -> List[str]:
        if not TARPIT_LOG_PATH.exists():
            return []
        try:
            with TARPIT_LOG_PATH.open("r", encoding="utf-8", errors="ignore") as handle:
                dq: deque[str] = deque(maxlen=limit)
                for line in handle:
                    clean = line.strip()
                    if clean:
                        dq.append(clean)
            return list(dq)
        except OSError as exc:
            logger.debug("Unable to read tarpit log: %s", exc)
            return []

    def _persist(self) -> None:
        self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def inspect(self, event: Dict) -> Dict:
        target_url = event.get("action", {}).get("target_url", "")
        path = urlparse(target_url).path or target_url

        result = {"triggered": False, "honeypot": None}
        matched_service = None
        for service, endpoints in self.SERVICE_ENDPOINTS.items():
            if any(path.startswith(ep) for ep in endpoints):
                matched_service = service
                break
        if matched_service and matched_service in self._catalog:
            meta = self._catalog[matched_service]
            record = self._state["honeypots"].setdefault(matched_service, self._default_entry(matched_service))
            record.update(
                {
                    "description": meta["description"],
                    "label": meta["label"],
                    "vector": meta["vector"],
                    "method": meta["method"],
                    "last_trigger_step": event.get("step"),
                    "last_trigger_at": event.get("timestamp"),
                    "payload": event.get("action", {}).get("payload", {}),
                }
            )
            self._persist()
            result.update(
                {
                    "triggered": True,
                    "honeypot": matched_service,
                    "label": meta["label"],
                    "description": meta["description"],
                }
            )
        return result

    def arm(
        self,
        *,
        reason: str | None = None,
        delta: int | None = None,
        source: str | None = None,
        services: List[str] | None = None,
    ) -> Dict[str, Any]:
        """Flag all honeypots as armed so the orchestrator can communicate readiness downstream."""

        timestamp = datetime.utcnow().isoformat()
        armed_records: List[Dict[str, Any]] = []
        target_set = {svc for svc in (services or self._catalog.keys()) if svc in self._catalog}
        if not target_set:
            target_set = set(self._catalog.keys())

        for service, meta in self._catalog.items():
            record = self._state["honeypots"].setdefault(service, self._default_entry(service))
            if service in target_set:
                record.update(
                    {
                        "armed": True,
                        "armed_at": timestamp,
                        "armed_reason": reason,
                        "armed_source": source,
                        "last_delta": delta,
                    }
                )
                armed_records.append(
                    {
                        "endpoint": service,
                        "label": meta["label"],
                        "description": meta["description"],
                        "vector": meta["vector"],
                        "method": meta["method"],
                        "emoji": meta["emoji"],
                        "color": meta["color"],
                        "armed_at": timestamp,
                    }
                )
            else:
                record.update(
                    {
                        "armed": False,
                        "armed_at": None,
                        "armed_reason": None,
                        "armed_source": None,
                        "last_delta": None,
                    }
                )

        self._state["last_armed_at"] = timestamp
        self._state["last_arm_reason"] = reason
        self._state["last_arm_source"] = source
        self._state["last_delta"] = delta
        self._persist()

        self._sync_runtime(sorted(target_set))

        return {"armed_at": timestamp, "honeypots": armed_records}

    def _load_cowrie_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Load Cowrie logs from the JSON log file."""
        cowrie_log_path = Path(__file__).resolve().parents[2] / "tpotce" / "data" / "cowrie" / "log" / "cowrie.json"
        if not cowrie_log_path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        try:
            with cowrie_log_path.open("r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
            for line in lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except (IOError, OSError) as exc:
            logger.debug("Unable to read Cowrie logs: %s", exc)
            return []
        return entries

    def inventory(self) -> Dict[str, Any]:
        timestamp = datetime.utcnow().isoformat()
        managed = []
        
        # Ensure state has honeypots dict
        if "honeypots" not in self._state:
            self._state["honeypots"] = {}
        
        # Ensure catalog exists
        if not self._catalog:
            logger.warning("Honeypot catalog is empty, using fallback services")
            self._catalog = self._build_catalog()
        
        for service, meta in self._catalog.items():
            try:
                record = self._state["honeypots"].setdefault(service, self._default_entry(service))
                status = "triggered" if record.get("last_trigger_step") else ("armed" if record.get("armed") else "idle")
                managed.append(
                    {
                        "id": service,
                        "label": meta.get("label", service),
                        "method": meta.get("method", ""),
                        "description": meta.get("description", ""),
                        "vector": meta.get("vector", ""),
                        "emoji": meta.get("emoji", "🛡️"),
                        "color": meta.get("color", "#9da1ff"),
                        "status": status,
                        "armed_at": record.get("armed_at"),
                        "armed_reason": record.get("armed_reason"),
                        "armed_source": record.get("armed_source"),
                        "last_delta": record.get("last_delta"),
                        "last_trigger_step": record.get("last_trigger_step"),
                        "last_trigger_at": record.get("last_trigger_at"),
                    }
                )
                if service == "cowrie":
                    commands = self._tail_tarpit_log()
                    if commands:
                        managed[-1]["recent_commands"] = commands
                    # Load Cowrie logs from JSON file
                    cowrie_logs = self._load_cowrie_logs(limit=50)
                    if cowrie_logs:
                        managed[-1]["cowrie_logs"] = cowrie_logs
            except Exception as exc:
                logger.warning("Error processing honeypot service %s: %s", service, exc)
                continue

        tpot_entries = [
            {
                "id": service,
                "label": service.replace("-", " ").title(),
                "status": "available",
                "source": "tpot",
                "description": "TPot honeypot service",
            }
            for service in (self._tpot_services or [])
        ]

        return {
            "managed": managed,
            "tpot": {"services": tpot_entries, "error": self._tpot_error},
            "generated_at": timestamp,
        }

