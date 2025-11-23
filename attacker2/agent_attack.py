from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from agents import Agent, Runner, set_default_openai_api, set_tracing_disabled

from kali_mcp import KaliMCPConfig, KaliMCPSession
from memory import AttackMemory

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
MEMORY_PATH = Path(__file__).resolve().parent / "state" / "memory.json"
OPERATIONS_LOG = Path(__file__).resolve().parent / "state" / "operations.jsonl"

GREEN = "\033[92m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class AttackConfig:
    target_base: str = os.getenv("ATTACKER2_TARGET_BASE", "http://localhost:3000")
    system_host: str = os.getenv("ATTACKER2_SYSTEM_HOST", "localhost")
    system_port: int = int(os.getenv("ATTACKER2_SYSTEM_PORT", "22"))
    defense_api: str = os.getenv("ATTACKER2_DEFENSE_API", "http://localhost:7700")
    max_steps: int = int(os.getenv("ATTACKER2_MAX_STEPS", "5"))
    model: str = os.getenv("ATTACKER2_MODEL", os.getenv("OPENAI_ATTACK_MODEL", "gpt-4o-mini"))


@dataclass
class Specialist:
    name: str
    prompt_file: Path
    channel: str
    focus: str


SPECIALISTS = [
    Specialist(
        name="WebProbe",
        prompt_file=PROMPT_DIR / "kali_mcp_web.md",
        channel="WEB",
        focus="HTTP probes, auth bypass, file download traps",
    ),
    Specialist(
        name="SystemSweep",
        prompt_file=PROMPT_DIR / "kali_mcp_system.md",
        channel="SYSTEM",
        focus="port sweeps, SSH banner grabs, quick filesystem pokes",
    ),
]


def _target_for_channel(cfg: AttackConfig, channel: str) -> str:
    if channel == "SYSTEM":
        return f"ssh://{cfg.system_host}:{cfg.system_port}"
    return cfg.target_base


def _build_task(
    step: int,
    cfg: AttackConfig,
    memory: AttackMemory,
    specialist: Specialist,
    active_honeypots: List[Dict[str, str]],
) -> str:
    context = memory.render_context()
    if active_honeypots:
        summary = ", ".join(f"{hp.get('label')}[{hp.get('vector')}]" for hp in active_honeypots)
    else:
        summary = "none armed"
    target_hint = _target_for_channel(cfg, specialist.channel)
    return (
        f"Channel: {specialist.channel}\n"
        f"Step {step}/{cfg.max_steps}\n"
        f"Primary target: {target_hint}\n"
        f"Active honeypots: {summary}\n\n"
        "Context from memory:\n"
        f"{context}\n\n"
        "Objectives:\n"
        f"- {specialist.focus}.\n"
        "- Keep every response JSON-only, log-tight, and <= 60 words per field.\n"
        "- Do not restate these instructions.\n\n"
        "Return strictly the JSON contract defined in your system instructions."
    )


def _log_operation(entry: Dict[str, object]) -> None:
    OPERATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with OPERATIONS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**entry, "timestamp": datetime.utcnow().isoformat()}) + "\n")


def _print_step(entry: Dict[str, object]) -> None:
    channel = entry.get("channel", "WEB")
    divider = GREEN + "=" * 70 + RESET
    print("\n" + divider)
    print(
        f"{BOLD}{GREEN}[{channel}] STEP {entry.get('step')}:{RESET} "
        f"{entry.get('action_summary', 'No summary provided')}"
    )
    commands = entry.get("commands_executed") or []
    if commands:
        print(f"{GREEN}CMD:{RESET}")
        for cmd in commands[:3]:
            print(f"  • {cmd}")
    findings = entry.get("findings") or []
    if findings:
        print(f"{GREEN}FINDINGS:{RESET}")
        for finding in findings[:3]:
            print(f"  • {finding}")
    warnings = entry.get("warnings") or []
    if warnings:
        print(f"{GREEN}WARNINGS:{RESET}")
        for warn in warnings[:3]:
            print(f"  • {warn}")
    snippet = entry.get("raw_output_snippet") or entry.get("raw_output", "")[:140]
    if snippet:
        print(f"{DIM}SNIPPET:{RESET} {snippet}")
    next_targets = entry.get("next_targets") or []
    if next_targets:
        print(f"{GREEN}NEXT:{RESET} " + ", ".join(next_targets[:4]))
    print(divider)


def _fetch_active_honeypots_sync(cfg: AttackConfig) -> List[Dict[str, str]]:
    url = cfg.defense_api.rstrip("/") + "/honeypots"
    try:
        with urllib.request.urlopen(url, timeout=4) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError):
        return []
    managed = data.get("managed", [])
    return [hp for hp in managed if hp.get("status") != "idle"]


async def _get_active_honeypots(cfg: AttackConfig) -> List[Dict[str, str]]:
    return await asyncio.to_thread(_fetch_active_honeypots_sync, cfg)


def _post_attack_event(cfg: AttackConfig, entry: Dict[str, object], specialist: Specialist) -> None:
    url = cfg.defense_api.rstrip("/") + "/attack-event"
    payload = {
        "step": entry.get("step"),
        "action": {
            "action_type": f"{specialist.channel}_MCP",
            "target_url": _target_for_channel(cfg, specialist.channel),
            "payload": {
                "commands": entry.get("commands_executed", []),
                "findings": entry.get("findings", []),
            },
        },
        "status": entry.get("status") or 0,
        "response_summary": entry.get("action_summary") or "",
        "timestamp": datetime.utcnow().isoformat(),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=4)  # nosec B310
    except urllib.error.URLError:
        pass


async def run_attack_loop() -> None:
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("OPENAI_API_KEY must be set to run attacker2.")
    set_default_openai_api(os.environ["OPENAI_API_KEY"])
    set_tracing_disabled(True)

    cfg = AttackConfig()
    memory = AttackMemory.load(MEMORY_PATH)
    mcp_config = KaliMCPConfig()

    print("Launching attacker2 with Kali MCP configuration:", mcp_config.summary())

    async with KaliMCPSession(mcp_config) as kali_server:
        agents = {
            spec.channel: Agent(
                name=spec.name,
                model=cfg.model,
                instructions=spec.prompt_file.read_text(encoding="utf-8").strip(),
                mcp_servers=[kali_server],
            )
            for spec in SPECIALISTS
        }

        for step in range(1, cfg.max_steps + 1):
            active = await _get_active_honeypots(cfg)
            print(f"\n{GREEN}{BOLD}>>> DEPLOYING STEP {step}/{cfg.max_steps}{RESET}")
            for specialist in SPECIALISTS:
                task = _build_task(step, cfg, memory, specialist, active)
                result = await Runner.run(agents[specialist.channel], task)
                entry = memory.record_step(step, task, result.final_output, channel=specialist.channel)
                _log_operation(entry)
                _print_step(entry)
                await asyncio.to_thread(_post_attack_event, cfg, entry, specialist)

    print(f"\n{GREEN}{BOLD}Attack loop complete.{RESET} State saved to {MEMORY_PATH}")


def main() -> None:
    asyncio.run(run_attack_loop())


if __name__ == "__main__":
    main()

