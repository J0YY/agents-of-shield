from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List
from urllib.parse import urlparse


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    normalized = value
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class ActiveDefenseTracker:
    """Tracks active defensive operations for the dashboard."""

    def __init__(
        self,
        *,
        max_entries: int = 18,
        respond_threshold: int = 60,
        resolve_threshold: int = 25,
        auto_resolve_after: int = 90,
        expire_resolved_after: int = 240,
    ) -> None:
        self.max_entries = max_entries
        self.respond_threshold = respond_threshold
        self.resolve_threshold = resolve_threshold
        self.auto_resolve_after = timedelta(seconds=auto_resolve_after)
        self.expire_resolved_after = timedelta(seconds=expire_resolved_after)
        self._ops: Dict[str, Dict[str, Any]] = {}
        self._order: Deque[str] = deque()

    def ingest(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        timestamp = _parse_timestamp(payload.get("event", {}).get("timestamp"))
        self._prune(timestamp)

        key = self._build_key(payload)
        severity = self._score(payload)
        status = self._derive_status(key, severity, timestamp, payload)

        entry = self._ops.get(key, {})
        record = {
            "id": key,
            "title": self._build_title(payload),
            "detail": self._build_detail(payload),
            "status": status,
            "severity": severity,
            "updated_at": _format_timestamp(timestamp),
            "status_changed_at": entry.get("status_changed_at", _format_timestamp(timestamp)),
        }

        if entry.get("status") != status:
            record["status_changed_at"] = _format_timestamp(timestamp)
        self._ops[key] = record
        self._promote(key)
        return self.snapshot()

    def snapshot(self) -> List[Dict[str, Any]]:
        ops: List[Dict[str, Any]] = []
        for key in self._order:
            entry = self._ops.get(key)
            if not entry:
                continue
            ops.append(
                {
                    "id": entry["id"],
                    "title": entry["title"],
                    "detail": entry["detail"],
                    "status": entry["status"],
                    "severity": entry["severity"],
                    "updated_at": entry["updated_at"],
                }
            )
        return ops

    def _should_respond(self, payload: Dict[str, Any], severity: int) -> bool:
        if payload.get("honeypot", {}).get("triggered"):
            return True
        return severity >= self.respond_threshold

    def _should_resolve(self, entry: Dict[str, Any], severity: int, timestamp: datetime) -> bool:
        if severity <= self.resolve_threshold:
            return True
        changed = _parse_timestamp(entry.get("status_changed_at"))
        return timestamp - changed >= self.auto_resolve_after

    def _derive_status(self, key: str, severity: int, timestamp: datetime, payload: Dict[str, Any]) -> str:
        entry = self._ops.get(key)
        if self._should_respond(payload, severity):
            return "Responding"
        if entry:
            if entry["status"] == "Responding" and self._should_resolve(entry, severity, timestamp):
                return "Resolved"
            if entry["status"] == "Resolved":
                # Stay resolved unless another alert escalates severity.
                if severity >= self.respond_threshold:
                    return "Responding"
                return "Resolved"
            return entry["status"]
        return "Monitoring"

    def _build_key(self, payload: Dict[str, Any]) -> str:
        action = payload.get("event", {}).get("action", {})
        action_type = action.get("action_type") or "UNKNOWN"
        endpoint = action.get("target_url") or action.get("target_host") or "unknown"
        parsed = urlparse(endpoint)
        path = parsed.path or parsed.netloc or endpoint
        return f"{action_type}:{path}".lower()

    def _score(self, payload: Dict[str, Any]) -> int:
        score = int(payload.get("payload", {}).get("payload_risk_score") or 0)
        label = (payload.get("classification", {}).get("label") or "").lower()
        status = int(payload.get("event", {}).get("status") or 0)
        action_type = payload.get("event", {}).get("action", {}).get("action_type") or ""

        if label in {"sql_injection", "config_leak", "admin_exposure", "path_traversal"}:
            score += 20
        if "SYSTEM" in action_type.upper():
            score += 10
        if status >= 400:
            score += 15
        if payload.get("honeypot", {}).get("triggered"):
            score += 35
        return max(0, min(100, score))

    def _build_title(self, payload: Dict[str, Any]) -> str:
        label = payload.get("classification", {}).get("label")
        if label:
            return label.replace("_", " ").title()
        action_type = payload.get("event", {}).get("action", {}).get("action_type") or "Event"
        return action_type.replace("_", " ").title()

    def _build_detail(self, payload: Dict[str, Any]) -> str:
        summary = payload.get("event", {}).get("response_summary")
        if summary:
            return summary
        return payload.get("event", {}).get("action", {}).get("target_url") or ""

    def _promote(self, key: str) -> None:
        if key in self._order:
            self._order.remove(key)
        self._order.appendleft(key)
        while len(self._order) > self.max_entries:
            tail = self._order.pop()
            self._ops.pop(tail, None)

    def _prune(self, timestamp: datetime) -> None:
        expired: List[str] = []
        for key, entry in self._ops.items():
            if entry["status"] != "Resolved":
                continue
            changed = _parse_timestamp(entry.get("status_changed_at"))
            if timestamp - changed >= self.expire_resolved_after:
                expired.append(key)
        for key in expired:
            self._ops.pop(key, None)
            if key in self._order:
                self._order.remove(key)


def _normalize_series(series: List[float]) -> List[int]:
    if not series:
        return []
    peak = max(series)
    if peak <= 0:
        return [0 for _ in series]
    return [int(round((value / peak) * 100)) for value in series]


class SignalHeatmapTracker:
    """Maintains a rolling window of defense telemetry metrics."""

    def __init__(self, *, bucket_seconds: int = 5, history: int = 12) -> None:
        self.bucket_seconds = bucket_seconds
        self.history = history
        self._buckets: Deque[Dict[str, Any]] = deque()

    def ingest(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        timestamp = _parse_timestamp(payload.get("event", {}).get("timestamp"))
        bucket_id = int(timestamp.timestamp() // self.bucket_seconds)
        bucket = self._ensure_bucket(bucket_id, timestamp)

        bucket["events"] += 1
        if payload.get("honeypot", {}).get("triggered"):
            bucket["honeypot"] += 1
        action_type = payload.get("event", {}).get("action", {}).get("action_type") or ""
        if "SYSTEM" in action_type.upper():
            bucket["system"] += 1

        risk = payload.get("payload", {}).get("payload_risk_score")
        if isinstance(risk, (int, float)):
            bucket["risk_sum"] += float(risk)
            bucket["risk_count"] += 1

        return self.snapshot()

    def snapshot(self) -> List[Dict[str, Any]]:
        buckets = self._padded_buckets()
        if not buckets:
            buckets = [
                {
                    "events": 0,
                    "honeypot": 0,
                    "system": 0,
                    "risk_sum": 0.0,
                    "risk_count": 0,
                }
                for _ in range(self.history)
            ]

        events_series = [bucket["events"] for bucket in buckets]
        honeypot_series = [bucket["honeypot"] for bucket in buckets]
        system_series = [bucket["system"] for bucket in buckets]
        risk_series = [
            int(round(bucket["risk_sum"] / bucket["risk_count"])) if bucket["risk_count"] else 0 for bucket in buckets
        ]
        total_risk_sum = sum(bucket["risk_sum"] for bucket in buckets)
        total_risk_count = sum(bucket["risk_count"] for bucket in buckets)

        latest_events = events_series[-1] if events_series else 0
        honeypot_total = int(sum(honeypot_series))
        system_total = int(sum(system_series))
        avg_risk_value = (
            int(round(total_risk_sum / total_risk_count))
            if total_risk_count
            else (risk_series[-1] if risk_series else 0)
        )

        return [
            {"label": "Events/5s", "value": latest_events, "trend": _normalize_series(events_series)},
            {"label": "Honeypot trips", "value": honeypot_total, "trend": _normalize_series(honeypot_series)},
            {"label": "System probes", "value": system_total, "trend": _normalize_series(system_series)},
            {"label": "Avg risk", "value": avg_risk_value, "trend": risk_series},
        ]

    def _ensure_bucket(self, bucket_id: int, timestamp: datetime) -> Dict[str, Any]:
        if self._buckets and self._buckets[-1]["id"] == bucket_id:
            return self._buckets[-1]

        if self._buckets and bucket_id < self._buckets[-1]["id"]:
            # Late event: insert at appropriate position if within window.
            for bucket in self._buckets:
                if bucket["id"] == bucket_id:
                    return bucket

        self._append_bucket(bucket_id, timestamp)
        return self._buckets[-1]

    def _append_bucket(self, bucket_id: int, timestamp: datetime) -> None:
        while self._buckets and bucket_id - self._buckets[-1]["id"] > 1:
            missing_id = self._buckets[-1]["id"] + 1
            self._buckets.append(self._new_bucket(missing_id, timestamp))
            if len(self._buckets) > self.history:
                self._buckets.popleft()
        self._buckets.append(self._new_bucket(bucket_id, timestamp))
        if len(self._buckets) > self.history:
            self._buckets.popleft()

    def _new_bucket(self, bucket_id: int, timestamp: datetime) -> Dict[str, Any]:
        return {
            "id": bucket_id,
            "started_at": _format_timestamp(timestamp),
            "events": 0,
            "honeypot": 0,
            "system": 0,
            "risk_sum": 0.0,
            "risk_count": 0,
        }

    def _padded_buckets(self) -> List[Dict[str, Any]]:
        items = list(self._buckets)
        if len(items) >= self.history:
            return items
        missing = self.history - len(items)
        padding = [
            {
                "id": -idx,
                "started_at": None,
                "events": 0,
                "honeypot": 0,
                "system": 0,
                "risk_sum": 0.0,
                "risk_count": 0,
            }
            for idx in range(missing, 0, -1)
        ]
        return padding + items


