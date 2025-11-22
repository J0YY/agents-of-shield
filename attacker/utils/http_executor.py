from __future__ import annotations

from typing import Dict, Tuple

import requests

DEFAULT_HEADERS = {
    "User-Agent": "Agents-of-Shield-Attack-Agent/1.0",
    "Accept": "*/*",
}


def execute(action: Dict[str, object], timeout: int = 5) -> Tuple[str, int]:
    """Execute the HTTP request described by the planner action."""

    method = action.get("action_type", "GET").upper()
    url = action.get("target_url", "http://localhost:3000/")
    payload = action.get("payload") or {}

    try:
        if method == "POST":
            resp = requests.post(url, data=payload, headers=DEFAULT_HEADERS, timeout=timeout)
        else:
            resp = requests.get(url, params=payload if method == "GET" else None, headers=DEFAULT_HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        return f"REQUEST ERROR: {exc}", 0

    body = resp.text[:800]
    return body, resp.status_code
