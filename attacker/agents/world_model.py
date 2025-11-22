from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from openai import OpenAI

from .schemas import default_memory

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "system_world_model.txt"
MODEL_NAME = os.getenv("OPENAI_ATTACK_MODEL", "gpt-4o-mini")
client = OpenAI()


def _collect_output_text(result) -> str:
    if hasattr(result, "choices"):
        choice = result.choices[0]
        content = choice.message.get("content") if isinstance(choice.message, dict) else choice.message.content
        if isinstance(content, list):
            return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
        return content or ""
    return ""


def _parse_json_block(text: str) -> Dict[str, object]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Missing JSON braces")
    snippet = text[start : end + 1]
    return json.loads(snippet)


def update_memory(
    memory: Dict[str, List[str]],
    perception: Dict[str, object],
    last_action: Dict[str, object],
    last_status: int,
) -> Dict[str, List[str]]:
    """Use the world model LLM to evolve long-term memory."""

    if not memory:
        memory = default_memory()

    payload = json.dumps(
        {
            "memory": memory,
            "perception": perception,
            "last_action": last_action,
            "status": last_status,
        },
        ensure_ascii=False,
    )

    system_prompt = PROMPT_PATH.read_text().strip()
    result = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0.25,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": payload},
        ],
    )

    response_text = _collect_output_text(result).strip()

    try:
        updated = _parse_json_block(response_text)
    except (ValueError, json.JSONDecodeError):
        return memory

    # Ensure all required keys exist to avoid KeyError later
    base = default_memory()
    for key, default_value in base.items():
        updated.setdefault(key, default_value)
    return updated
