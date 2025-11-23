"""
Fire-and-forget runner that performs the HTTP playbook from
`kali_mcp_web.md` and immediately follows up with aggressive SSH
authentication attempts so Cowrie-style honeypot logs light up without
manual operator input.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
import random
import shlex
import string
import subprocess
import sys
import time
import urllib.parse
from textwrap import dedent

import paramiko
import requests

requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

from ..react.react import ReAct


NOISE_PATHS = [
    "",
    "login",
    "admin",
    "api/status",
    "dashboard",
    "assets/logo.png",
    "static/js/app.js",
    "health",
    "metrics",
]
NOISE_METHODS = ("GET", "POST", "HEAD")

SCRIPTED_HTTP_COMMANDS = [
    "httpx -silent -status-code -title -web-server -ip -content-length -follow-redirects -u {url}",
    "curl -s -I {url}",
    "curl -s {url}",
    "gobuster dir -u {url} -w /usr/share/wordlists/dirb/common.txt -q -o /tmp/gobuster_common.txt",
    "gobuster dir -u {url} -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt -q -o /tmp/gobuster_dirbuster.txt",
    "wfuzz -c -z file,/usr/share/wordlists/wfuzz/general/common.txt --hc 404 {url}/FUZZ -o /tmp/wfuzz_common.txt",
    "html2text {url}",
]


HTTP_BRIEF = dedent(
    """
    You are `Cerberus-Web`, a Kali MCP operator for HTTP targets. Operate
    like a SOC log writer: fast, terse, no fluff. Work autonomously on the
    supplied base URL; no additional clarification will be provided.

    Mission checklist (complete in order, looping back as needed):
    1. Probe and fingerprint HTTP endpoints (curl/gobuster/httpx/etc.).
    2. Attempt lightweight exploitation (auth bypass, SQLi, download interesting files).
    3. Capture concrete artifacts or traces for every notable result.
    4. Keep a short queue of URLs that deserve the next pass and iterate.

    When you finish a sweep, emit a compact SOC-style summary that calls
    out commands executed, loot collected, and immediate next targets.
    """
).strip()


def _build_http_prompt(
    display_url: str,
    extra_tasking: str | None,
    alias_note: str | None = None,
) -> str:
    """Construct a single prompt that encodes the kali_mcp_web playbook."""
    reminder = (
        "\nAdditional mission detail:\n" + extra_tasking.strip()
        if extra_tasking
        else ""
    )
    alias_line = (
        f"\nReachable alias inside the container: {alias_note}"
        if alias_note
        else ""
    )
    return dedent(
        f"""
        {HTTP_BRIEF}

        Base URL: {display_url}
        {alias_line}
        Stay scoped to this host; do not wander.
        {reminder}
        """
    ).strip()


def _run_http_phase(
    display_url: str,
    extra_tasking: str | None,
    alias_note: str | None = None,
) -> None:
    """Run the scripted HTTP reconnaissance/exploitation loop via ReAct."""
    prompt = _build_http_prompt(display_url, extra_tasking, alias_note)
    logging.info("HTTP phase starting for %s", display_url)
    agent = ReAct(task=None)
    agent.exec_task(prompt)
    logging.info("HTTP phase completed")


def _random_token(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def _noise_worker(base_url: str, timeout: float) -> int | Exception:
    """Fire a single synthetic HTTP request to generate traffic."""
    method = random.choice(NOISE_METHODS)
    path = random.choice(NOISE_PATHS)
    target = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    params = {"rid": _random_token(6), "ts": time.time_ns()}
    data = {"payload": _random_token(24), "token": _random_token(12)}
    try:
        resp = requests.request(
            method,
            target,
            params=params if method != "POST" else None,
            data=data if method == "POST" else None,
            timeout=timeout,
            verify=False,
        )
        return resp.status_code
    except Exception as exc:  # noqa: BLE001
        return exc


def _generate_http_noise(
    base_url: str,
    total_requests: int,
    concurrency: int,
    timeout: float,
) -> None:
    if total_requests <= 0 or concurrency <= 0:
        return
    logging.info(
        "Blasting %s HTTP noise requests at %s (concurrency=%s)",
        total_requests,
        base_url,
        concurrency,
    )
    successes = failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_noise_worker, base_url, timeout)
            for _ in range(total_requests)
        ]
        for idx, fut in enumerate(concurrent.futures.as_completed(futures), start=1):
            result = fut.result()
            if isinstance(result, int):
                successes += 1
                if idx % 50 == 0:
                    logging.debug("Noise request #%s status=%s", idx, result)
            else:
                failures += 1
                logging.debug("Noise request #%s error=%s", idx, result)
    logging.info(
        "HTTP noise finished (%s successes / %s errors)", successes, failures
    )


def _run_scripted_http_commands(
    base_url: str,
    dry_run: bool,
) -> None:
    if dry_run:
        logging.info("Scripted HTTP commands (dry-run only)")
    else:
        logging.info("Running scripted HTTP commands")
    for cmd_template in SCRIPTED_HTTP_COMMANDS:
        command = cmd_template.format(url=base_url.rstrip("/"))
        logging.info("HTTP CMD: %s", command)
        if dry_run:
            continue
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            if stdout:
                logging.debug("stdout: %s", stdout[:1000])
            if stderr:
                logging.debug("stderr: %s", stderr[:1000])
        except FileNotFoundError:
            logging.warning("Command executable missing for: %s", command)
        except subprocess.TimeoutExpired:
            logging.warning("Command timed out: %s", command)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Command %s raised %s", command, exc)


def _attempt_ssh(
    host: str,
    port: int,
    username: str,
    password: str,
    timeout: float,
) -> None:
    """Carry out a single SSH login attempt."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
        )
    finally:
        client.close()


def _run_ssh_phase(
    host: str,
    port: int,
    username: str,
    passwords: list[str],
    cycles: int,
    delay: float,
    timeout: float,
) -> None:
    """Aggressively rotate through password guesses to mimic Cowrie noise."""
    logging.info(
        "SSH phase starting against %s:%s (%s cycles, %s candidates)",
        host,
        port,
        cycles,
        len(passwords),
    )
    total_attempts = 0
    for _ in range(cycles):
        for password in passwords:
            total_attempts += 1
            try:
                _attempt_ssh(host, port, username, password, timeout)
                logging.info(
                    "SSH attempt #%s unexpectedly succeeded with password=%s",
                    total_attempts,
                    password,
                )
            except paramiko.AuthenticationException:
                logging.debug(
                    "SSH attempt #%s failed (user=%s password=%s)",
                    total_attempts,
                    username,
                    password,
                )
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "SSH attempt #%s produced %s: %s",
                    total_attempts,
                    exc.__class__.__name__,
                    exc,
                )
            time.sleep(delay)
    logging.info("SSH phase completed (%s total attempts)", total_attempts)


def _rewrite_base_url(base_url: str, alias: str | None) -> tuple[str, str | None]:
    if not alias:
        return base_url, None
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme and parsed.netloc:
        host = parsed.hostname or ""
        if host in {"localhost", "127.0.0.1"}:
            netloc = alias
            if parsed.port:
                netloc = f"{alias}:{parsed.port}"
            rewritten = urllib.parse.urlunparse(parsed._replace(netloc=netloc))
            return rewritten, alias
    return base_url, None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomously run the kali_mcp_web playbook then hammer SSH.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="HTTP target that should receive the Cerberus-Web playbook.",
    )
    parser.add_argument(
        "--extra-tasking",
        help="Optional natural-language tasking appended to the HTTP prompt.",
    )
    parser.add_argument(
        "--ssh-host",
        required=True,
        help="Host/IP of the SSH honeypot (e.g., Cowrie).",
    )
    parser.add_argument("--ssh-port", type=int, default=2222)
    parser.add_argument("--ssh-username", default="root")
    parser.add_argument(
        "--ssh-passwords",
        default="password,root,toor,admin,changeme",
        help="Comma-separated password list rotated for each cycle.",
    )
    parser.add_argument(
        "--ssh-cycles",
        type=int,
        default=5,
        help="Number of times to iterate through the password list.",
    )
    parser.add_argument(
        "--ssh-delay",
        type=float,
        default=0.35,
        help="Seconds to wait between SSH attempts.",
    )
    parser.add_argument(
        "--ssh-timeout",
        type=float,
        default=1.0,
        help="Socket/authentication timeout passed to Paramiko.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Controls verbosity of this launcher (agent output is untouched).",
    )
    parser.add_argument(
        "--noise-requests",
        type=int,
        default=250,
        help="Total synthetic HTTP requests to issue before the ReAct phase.",
    )
    parser.add_argument(
        "--noise-concurrency",
        type=int,
        default=30,
        help="Concurrent workers used for the HTTP noise burst.",
    )
    parser.add_argument(
        "--noise-timeout",
        type=float,
        default=5.0,
        help="Per-request timeout for HTTP noise traffic.",
    )
    parser.add_argument(
        "--disable-noise",
        action="store_true",
        help="Skip the synthetic HTTP burst and go straight to ReAct.",
    )
    parser.add_argument(
        "--skip-react",
        action="store_true",
        help="Skip the LLM-driven ReAct phase (noise + SSH only).",
    )
    parser.add_argument(
        "--disable-scripted-http",
        action="store_true",
        help="Skip the deterministic HTTP command playback phase.",
    )
    parser.add_argument(
        "--scripted-http-dry-run",
        action="store_true",
        help="Only log scripted HTTP commands without executing them.",
    )
    parser.add_argument(
        "--http-host-alias",
        help="Rewrite localhost-based URLs to this host (e.g. host.docker.internal).",
    )
    parser.add_argument(
        "--ssh-host-alias",
        help="Use this host for SSH connections but keep the original in logs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    effective_base_url, alias_note = _rewrite_base_url(
        args.base_url, args.http_host_alias
    )
    if alias_note:
        logging.info(
            "Rewriting base URL host to %s for in-container reachability",
            alias_note,
        )
    ssh_target_host = args.ssh_host_alias or args.ssh_host
    if args.ssh_host_alias:
        logging.info(
            "Using SSH host alias %s (original target %s)",
            args.ssh_host_alias,
            args.ssh_host,
        )
    passwords = [
        candidate.strip() for candidate in args.ssh_passwords.split(",") if candidate
    ]
    if not passwords:
        raise SystemExit("At least one SSH password must be supplied.")

    if not args.disable_noise:
        _generate_http_noise(
            base_url=effective_base_url,
            total_requests=args.noise_requests,
            concurrency=args.noise_concurrency,
            timeout=args.noise_timeout,
        )

    if not args.disable_scripted_http:
        _run_scripted_http_commands(
            base_url=effective_base_url,
            dry_run=args.scripted_http_dry_run,
        )

    if not args.skip_react:
        alias_text = None
        if effective_base_url != args.base_url:
            alias_text = effective_base_url
        _run_http_phase(args.base_url, args.extra_tasking, alias_text)
    _run_ssh_phase(
        host=ssh_target_host,
        port=args.ssh_port,
        username=args.ssh_username,
        passwords=passwords,
        cycles=args.ssh_cycles,
        delay=args.ssh_delay,
        timeout=args.ssh_timeout,
    )


if __name__ == "__main__":
    main()


