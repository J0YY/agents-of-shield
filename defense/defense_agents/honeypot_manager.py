from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse


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

    ENDPOINT_ALIAS = {
        "/admin-v2": "cowrie",
        "/backup-db": "dionaea",
        "/config-prod": "elasticpot",
    }

    TPOT_HEADER = "#### Honeypots"
    TPOT_DIVIDER = "##################"

    def __init__(self, state_dir: Path) -> None:
        self.state_file = state_dir / "honeypot_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._tpot_error = None
        self._tpot_services = self._discover_tpot_services()
        self._catalog = self._build_catalog()
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

    def _persist(self) -> None:
        self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    def inspect(self, event: Dict) -> Dict:
        target_url = event.get("action", {}).get("target_url", "")
        path = urlparse(target_url).path or target_url

        result = {"triggered": False, "honeypot": None}
        matched_service = None
        for endpoint, service in self.ENDPOINT_ALIAS.items():
            if path.startswith(endpoint):
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

        return {"armed_at": timestamp, "honeypots": armed_records}

    def inventory(self) -> Dict[str, Any]:
        timestamp = datetime.utcnow().isoformat()
        managed = []
        for service, meta in self._catalog.items():
            record = self._state["honeypots"].setdefault(service, self._default_entry(service))
            status = "triggered" if record.get("last_trigger_step") else ("armed" if record.get("armed") else "idle")
            managed.append(
                {
                    "id": service,
                    "label": meta["label"],
                    "method": meta["method"],
                    "description": meta["description"],
                    "vector": meta["vector"],
                    "emoji": meta["emoji"],
                    "color": meta["color"],
                    "status": status,
                    "armed_at": record.get("armed_at"),
                    "armed_reason": record.get("armed_reason"),
                    "armed_source": record.get("armed_source"),
                    "last_delta": record.get("last_delta"),
                    "last_trigger_step": record.get("last_trigger_step"),
                    "last_trigger_at": record.get("last_trigger_at"),
                }
            )

        tpot_entries = [
            {
                "id": service,
                "label": service.replace("-", " ").title(),
                "status": "available",
                "source": "tpot",
                "description": "TPot honeypot service",
            }
            for service in self._tpot_services
        ]

        return {
            "managed": managed,
            "tpot": {"services": tpot_entries, "error": self._tpot_error},
            "generated_at": timestamp,
        }

