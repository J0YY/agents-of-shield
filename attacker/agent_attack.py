from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from colorama import Fore, Style, init

from agents.perception import perceive
from agents.planner import choose_action
from agents.schemas import default_memory
from agents.world_model import update_memory
from utils.http_executor import execute

BASE_URL = "http://localhost:3000"
MEMORY_PATH = Path(__file__).resolve().parent / "state" / "memory.json"
MAX_STEPS = 20


def load_memory() -> Dict[str, List[str]]:
    if MEMORY_PATH.exists():
        try:
            with open(MEMORY_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            return default_memory()
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    memory = default_memory()
    save_memory(memory)
    return memory


def save_memory(memory: Dict[str, List[str]]) -> None:
    with open(MEMORY_PATH, "w", encoding="utf-8") as fh:
        json.dump(memory, fh, indent=2)


def banner() -> None:
    print(Fore.CYAN + "=" * 60)
    print(Fore.CYAN + "   Agents of Shield – Attack Agent".center(60))
    print(Fore.CYAN + "   autonomous offensive ops demo".center(60))
    print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)


def _color_status(status: int) -> str:
    if 200 <= status < 300:
        return Fore.GREEN
    if 300 <= status < 400:
        return Fore.YELLOW
    return Fore.RED


def _format_snippet(body: str, limit: int = 240) -> str:
    cleaned = body.replace("\x00", " ")
    snippet = cleaned[:limit].replace("\n", " ").strip()
    return snippet or "[no body]"


def _normalize_url(path: str) -> str:
    if not path:
        return f"{BASE_URL}/"
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return f"{BASE_URL}{path}"


def enrich_memory(
    memory: Dict[str, List[str]],
    action: Dict[str, object],
    perception: Dict[str, object],
    status: int,
) -> Dict[str, List[str]]:
    if not memory:
        memory = default_memory()

    target_url = _normalize_url(str(action.get("target_url", "")))
    visited = memory.setdefault("visited", [])
    if target_url not in visited:
        visited.append(target_url)

    recent = memory.setdefault("recent_actions", [])
    recent.append(target_url)
    memory["recent_actions"] = recent[-5:]

    history = memory.setdefault("history", [])
    history.append(f"{action.get('action_type', 'GET')} {target_url} -> {status}")
    memory["history"] = history[-60:]

    next_steps = memory.setdefault("next_steps", [])
    next_steps = [_normalize_url(step) for step in next_steps if _normalize_url(step) != target_url]
    for link in perception.get("links") or []:
        normalized = _normalize_url(link)
        if normalized not in next_steps:
            next_steps.append(normalized)
    memory["next_steps"] = next_steps

    forms = perception.get("forms") or []
    known_forms = memory.setdefault("known_forms", [])
    for form in forms:
        form_action = _normalize_url(form.get("action") or target_url)
        method = str(form.get("method", "GET")).upper()
        descriptor = f"{method} {form_action}"
        if descriptor not in known_forms:
            known_forms.append(descriptor)

    keywords = " ".join(perception.get("keywords") or []).lower()
    suspected = memory.setdefault("suspected_vulns", [])
    if "sqlite" in keywords:
        clue = f"DB leak via {target_url}"
        if clue not in suspected:
            suspected.append(clue)
    if any("error" in err.lower() for err in perception.get("errors") or []):
        clue = f"Server error observed after {target_url}"
        if clue not in suspected:
            suspected.append(clue)

    return memory


def step_block(
    step: int,
    action: Dict[str, object],
    status: int,
    summary: str,
    next_goals: List[str],
    active_goals: List[str],
    perception: Dict[str, object],
    body_snippet: str,
) -> None:
    divider = "\n" + Fore.GREEN + Style.BRIGHT + "═" * 14 + f" ATTACK STEP {step:02d} " + "═" * 14 + Style.RESET_ALL
    print(divider)

    status_color = _color_status(status)
    print(f"{Fore.GREEN}{Style.BRIGHT}ACTION{Style.RESET_ALL}: {Fore.YELLOW}{action['action_type']} {action['target_url']}{Style.RESET_ALL}")
    if action.get("payload"):
        print(f"{Fore.RED}PAYLOAD{Style.RESET_ALL}: {Fore.YELLOW}{action['payload']}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}REASON{Style.RESET_ALL}: {action.get('reasoning', 'Planner rationale unavailable')}")
    print(f"{Fore.GREEN}STATUS{Style.RESET_ALL}: {status_color}{status}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}SUMMARY{Style.RESET_ALL}: {summary}")
    if perception.get("errors"):
        print(f"{Fore.RED}ERROR CLUES{Style.RESET_ALL}: {perception['errors'][:3]}")
    if perception.get("keywords"):
        print(f"{Fore.RED}KEYWORDS{Style.RESET_ALL}: {perception['keywords'][:6]}")
    if perception.get("links"):
        print(f"{Fore.RED}LINKS NOTED{Style.RESET_ALL}: {perception['links'][:4]}")
    if perception.get("forms"):
        forms_summary = [
            f"{form.get('method', 'GET')}->{form.get('action', action['target_url'])}"
            for form in perception["forms"][:3]
        ]
        print(f"{Fore.RED}FORMS FOUND{Style.RESET_ALL}: {forms_summary}")
    print(f"{Fore.RED}RESPONSE{Style.RESET_ALL}: {Style.DIM}{body_snippet}{Style.RESET_ALL}")
    if active_goals:
        print(f"{Fore.GREEN}ACTIVE GOALS{Style.RESET_ALL}: {active_goals[:3]}")
    if next_goals:
        print(f"{Fore.RED}NEXT-GOALS{Style.RESET_ALL}: {next_goals[:4]}")
    print(Fore.RED + "═" * 45 + Style.RESET_ALL)


def final_summary(history: List[Dict[str, object]]) -> None:
    print("\n" + Fore.CYAN + "═" * 60 + Style.RESET_ALL)
    print(Fore.CYAN + " Attack loop complete".center(60) + Style.RESET_ALL)
    successes = sum(1 for item in history if 200 <= item["status"] < 400)
    failures = len(history) - successes
    print(f"{Fore.GREEN}Successful responses:{Style.RESET_ALL} {successes}")
    print(f"{Fore.YELLOW}Other responses:{Style.RESET_ALL} {failures}")
    print(Fore.CYAN + "Recent summaries:" + Style.RESET_ALL)
    for item in history[-5:]:
        print(f"  • Step {item['step']}: {item['summary']}")
    print(Fore.CYAN + "═" * 60 + Style.RESET_ALL)


def main() -> None:
    init(autoreset=True)
    memory = load_memory()
    history: List[Dict[str, object]] = []

    banner()
    print("Using OpenAI model:", os.getenv("OPENAI_ATTACK_MODEL", "gpt-4o-mini"))

    for step in range(1, MAX_STEPS + 1):
        action = choose_action(memory)
        raw_body, status = execute(action)
        perception = perceive(raw_body, status)
        memory = update_memory(memory, perception, action, status)
        memory = enrich_memory(memory, action, perception, status)
        save_memory(memory)

        summary = perception.get("summary") or "No summary"
        next_goals = memory.get("next_steps", [])
        active_goals = memory.get("goals", [])
        response_snippet = _format_snippet(raw_body)

        step_block(step, action, status, summary, next_goals, active_goals, perception, response_snippet)
        history.append({"step": step, "status": status, "summary": summary})

    final_summary(history)


if __name__ == "__main__":
    main()
