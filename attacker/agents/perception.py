from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from openai import OpenAI

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "system_perception.txt"
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


def _safe_json_parse(content: str) -> Dict[str, object]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = content[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                pass
    raise ValueError("Unable to parse JSON from perception response")


def perceive(raw_response: str, status: int) -> Dict[str, object]:
    """Call the Perception LLM to derive structured context from an HTTP response."""

    system_prompt = PROMPT_PATH.read_text().strip()
    user_payload = json.dumps({"status": status, "body": raw_response}, ensure_ascii=False)

    result = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
    )

    response_text = _collect_output_text(result).strip()

    default = {
        "links": [],
        "forms": [],
        "keywords": [],
        "errors": [],
        "summary": "",
    }

    try:
        parsed = _safe_json_parse(response_text)
    except ValueError:
        return default

    return {
        "links": parsed.get("links", []) or [],
        "forms": parsed.get("forms", []) or [],
        "keywords": parsed.get("keywords", []) or [],
        "errors": parsed.get("errors", []) or [],
        "summary": parsed.get("summary", ""),
    }
