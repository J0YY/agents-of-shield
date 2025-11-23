from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _safe_json_parse(blob: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        pass
    if not blob:
        return None
    start = blob.find("{")
    end = blob.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = blob[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            return None
    return None


def _default_state() -> Dict[str, Any]:
    return {
        "steps": [],
        "findings": [],
        "pending_targets": [],
    }


@dataclass
class AttackMemory:
    """Persistence helper for attacker2 runs."""

    path: Path
    state: Dict[str, Any] = field(default_factory=_default_state)

    @classmethod
    def load(cls, path: Path) -> "AttackMemory":
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError:
                data = _default_state()
        else:
            data = _default_state()
        instance = cls(path=path, state=data)
        instance._ensure_structure()
        return instance

    def _ensure_structure(self) -> None:
        for key in ("steps", "findings", "pending_targets"):
            if key not in self.state or not isinstance(self.state[key], list):
                self.state[key] = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2))

    # ------------------------------------------------------------------ updates

    def record_step(self, step: int, task: str, output: str, channel: str) -> Dict[str, Any]:
        parsed = _safe_json_parse(output)
        trimmed_output = output
        if isinstance(trimmed_output, str) and len(trimmed_output) > 1500:
            trimmed_output = trimmed_output[:1500] + " …[truncated]…"
        entry = {
            "step": step,
            "task": task,
            "raw_output": trimmed_output,
            "channel": channel,
        }
        if parsed:
            entry.update(parsed)
            self._merge_findings(parsed.get("findings"))
            self._merge_targets(parsed.get("next_targets"))
        self.state["steps"].append(entry)
        self.state["steps"] = self.state["steps"][-20:]
        self.save()
        return entry

    def _merge_findings(self, findings: Optional[List[str]]) -> None:
        if not findings:
            return
        store = self.state.setdefault("findings", [])
        for finding in findings:
            if isinstance(finding, str) and finding not in store:
                store.append(finding)

    def _merge_targets(self, targets: Optional[List[str]]) -> None:
        if not targets:
            return
        store = self.state.setdefault("pending_targets", [])
        for target in targets:
            if isinstance(target, str) and target not in store:
                store.append(target)
        self.state["pending_targets"] = store[-20:]

    # ------------------------------------------------------------------ context

    def render_context(self, limit: int = 4) -> str:
        steps = self.state.get("steps", [])
        if not steps:
            return "No previous steps recorded."
        recent = steps[-limit:]
        lines = []
        for item in recent:
            summary = item.get("action_summary") or item.get("raw_output", "").split("\n", 1)[0]
            channel = item.get("channel", "WEB")
            lines.append(f"{channel} step {item.get('step')}: {summary}")
        findings = self.state.get("findings") or []
        if findings:
            lines.append("Findings: " + "; ".join(findings[-3:]))
        pending = self.state.get("pending_targets") or []
        if pending:
            lines.append("Target queue: " + ", ".join(pending[:3]))
        return "\n".join(lines)

