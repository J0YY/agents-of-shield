from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict

from agents import Agent, Runner, set_default_openai_api, set_tracing_disabled

from kali_mcp import KaliMCPConfig, KaliMCPSession
from memory import AttackMemory

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "kali_mcp_attacker.md"
MEMORY_PATH = Path(__file__).resolve().parent / "state" / "memory.json"
OPERATIONS_LOG = Path(__file__).resolve().parent / "state" / "operations.jsonl"


GREEN = "\033[92m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class AttackConfig:
    target_base: str = os.getenv("ATTACKER2_TARGET_BASE", "http://localhost:3000")
    max_steps: int = int(os.getenv("ATTACKER2_MAX_STEPS", "5"))
    model: str = os.getenv("ATTACKER2_MODEL", os.getenv("OPENAI_ATTACK_MODEL", "gpt-4o-mini"))


def _build_task(step: int, cfg: AttackConfig, memory: AttackMemory) -> str:
    context = memory.render_context()
    return (
        f"You are running offensive step {step}/{cfg.max_steps}.\n"
        f"Base target: {cfg.target_base}\n\n"
        "Context from memory:\n"
        f"{context}\n\n"
        "Objectives:\n"
        "1. Use Kali MCP tools to execute reconnaissance or exploit commands.\n"
        "2. Prioritize pending targets mentioned above before inventing new ones.\n"
        "3. Keep outputs concise and highlight artifacts worth saving.\n"
        "4. Avoid obvious honeypots or noisy scans unless risk is acceptable.\n\n"
        "Return strictly the JSON contract described in your system instructions."
    )


def _log_operation(entry: Dict[str, object]) -> None:
    OPERATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with OPERATIONS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**entry, "timestamp": datetime.utcnow().isoformat()}) + "\n")


def _print_step(entry: Dict[str, object]) -> None:
    divider = GREEN + "=" * 70 + RESET
    print("\n" + divider)
    print(f"{BOLD}{GREEN}STEP {entry.get('step')}:{RESET} {entry.get('action_summary', 'No summary provided')}")
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


async def run_attack_loop() -> None:
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("OPENAI_API_KEY must be set to run attacker2.")
    set_default_openai_api(os.environ["OPENAI_API_KEY"])
    set_tracing_disabled(True)

    cfg = AttackConfig()
    instructions = PROMPT_PATH.read_text(encoding="utf-8").strip()
    memory = AttackMemory.load(MEMORY_PATH)
    mcp_config = KaliMCPConfig()

    print("Launching attacker2 with Kali MCP configuration:", mcp_config.summary())

    async with KaliMCPSession(mcp_config) as kali_server:
        agent = Agent(
            name="KaliMCPAttacker",
            model=cfg.model,
            instructions=instructions,
            mcp_servers=[kali_server],
        )

        for step in range(1, cfg.max_steps + 1):
            task = _build_task(step, cfg, memory)
            print(f"\n{GREEN}{BOLD}>>> DEPLOYING STEP {step}/{cfg.max_steps}{RESET}")
            result = await Runner.run(agent, task)
            entry = memory.record_step(step, task, result.final_output)
            _log_operation(entry)
            _print_step(entry)

    print(f"\n{GREEN}{BOLD}Attack loop complete.{RESET} State saved to {MEMORY_PATH}")


def main() -> None:
    asyncio.run(run_attack_loop())


if __name__ == "__main__":
    main()

