"""Utilities for controlling the honeypot services defined in T-Pot compose.

This module discovers the services listed in the `#### Honeypots` section of the
`tpotce/docker-compose.yml` file and exposes helpers to start or stop those
containers using `docker compose`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Iterable, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_COMPOSE_PATH = PROJECT_ROOT / "tpotce" / "docker-compose.yml"
HONEYPOT_SECTION_HEADER = "#### Honeypots"
SECTION_DIVIDER = "##################"


class HoneypotServiceError(RuntimeError):
    """Raised when composing honeypot commands fails."""


class TPotComposeManager:
    """Wrapper around docker compose for the honeypot services."""

    def __init__(self, compose_path: Path | str = DEFAULT_COMPOSE_PATH):
        self.compose_path = Path(compose_path).expanduser().resolve()
        if not self.compose_path.exists():
            raise FileNotFoundError(
                f"Compose file does not exist: {self.compose_path}"
            )
        self.honeypot_services = self._discover_honeypot_services()

    def start(self, services: Sequence[str] | None = None) -> None:
        """Start one or more honeypot services (defaults to all)."""
        targets = self._validate_targets(services)
        self._run_compose("up", "-d", *targets)

    def stop(self, services: Sequence[str] | None = None) -> None:
        """Stop one or more honeypot services (defaults to all)."""
        targets = self._validate_targets(services)
        self._run_compose("stop", *targets)

    def list_services(self) -> List[str]:
        """Return the discovered honeypot service names."""
        return list(self.honeypot_services)

    # Internal helpers -----------------------------------------------------
    def _run_compose(self, *args: str) -> None:
        command = ["docker", "compose", "-f", str(self.compose_path), *args]
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as exc:
            raise HoneypotServiceError(
                f"docker compose command failed: {' '.join(command)}"
            ) from exc

    def _validate_targets(self, services: Sequence[str] | None) -> List[str]:
        if services is None or len(services) == 0:
            return self.list_services()
        unknown = sorted(set(services) - set(self.honeypot_services))
        if unknown:
            raise HoneypotServiceError(
                f"Unknown honeypot service(s): {', '.join(unknown)}"
            )
        return list(services)

    def _discover_honeypot_services(self) -> List[str]:
        """Extract service names between the honeypot markers."""
        text = self.compose_path.read_text(encoding="utf-8")
        try:
            header_idx = text.index(HONEYPOT_SECTION_HEADER)
        except ValueError as exc:  # pragma: no cover - defensive
            raise HoneypotServiceError(
                f"Could not find '{HONEYPOT_SECTION_HEADER}' in compose file"
            ) from exc

        # Skip the divider line that immediately follows the header.
        divider_after_header = text.find(SECTION_DIVIDER, header_idx)
        if divider_after_header == -1:
            raise HoneypotServiceError(
                f"Could not find divider following '{HONEYPOT_SECTION_HEADER}'"
            )
        section_start = text.find("\n", divider_after_header)
        if section_start == -1:
            raise HoneypotServiceError(
                "Unexpected EOF while locating honeypot section start"
            )
        section_start += 1

        end = text.find(SECTION_DIVIDER, section_start)
        if end == -1:
            raise HoneypotServiceError(
                f"Could not find section divider '{SECTION_DIVIDER}' after "
                f"honeypot section"
            )

        block = text[section_start:end]
        names = re.findall(r"(?m)^\s{2}([A-Za-z0-9_-]+):\s*$", block)
        if not names:
            raise HoneypotServiceError(
                "No honeypot services detected inside the compose file"
            )
        return names


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Control honeypot services from the T-Pot docker-compose file. "
            "Usage examples:\n"
            "  python tpot.py start             # start all honeypots\n"
            "  python tpot.py stop ddospot      # stop a single service"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--compose",
        default=str(DEFAULT_COMPOSE_PATH),
        help=f"Path to docker-compose file (default: {DEFAULT_COMPOSE_PATH})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    for action in ("start", "stop"):
        action_parser = subparsers.add_parser(action, help=f"{action} services")
        action_parser.add_argument(
            "services",
            nargs="*",
            help="Optional list of honeypot service names",
        )

    subparsers.add_parser("list", help="List discovered honeypot services")
    return parser


def main(argv: Iterable[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    manager = TPotComposeManager(compose_path=args.compose)

    if args.command == "list":
        for service in manager.list_services():
            print(service)
        return

    services = getattr(args, "services", None)
    if args.command == "start":
        manager.start(services)
    elif args.command == "stop":
        manager.stop(services)
    else:  # pragma: no cover - argparse ensures this doesn't happen
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
