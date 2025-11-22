"""Utilities for controlling the honeypot services defined in T-Pot compose.

This module discovers the services listed in the `#### Honeypots` section of the
`tpotce/docker-compose.yml` file and exposes helpers to start or stop those
containers using `docker compose`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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

    def start(
        self,
        services: Sequence[str] | None = None,
        port_bindings: Sequence[str] | None = None,
    ) -> None:
        """Start one or more honeypot services (defaults to all).

        Args:
            services: Iterable of service names to operate on. If omitted, all
                honeypot services will be targeted.
            port_bindings: Optional overrides in the format
                ``service=HOST:CONTAINER[/PROTOCOL]``. Multiple overrides for
                the same service are allowed (repeat the argument).
        """
        targets = self._validate_targets(services)
        override_file = None
        if port_bindings:
            overrides = self._parse_port_overrides(port_bindings, targets)
            override_file = self._write_override_file(overrides)
        try:
            self._run_compose("up", "-d", *targets, override_file=override_file)
        finally:
            if override_file:
                override_file.unlink(missing_ok=True)

    def stop(self, services: Sequence[str] | None = None) -> None:
        """Stop one or more honeypot services (defaults to all)."""
        targets = self._validate_targets(services)
        self._run_compose("stop", *targets)

    def list_services(self) -> List[str]:
        """Return the discovered honeypot service names."""
        return list(self.honeypot_services)

    # Internal helpers -----------------------------------------------------
    def _run_compose(self, *args: str, override_file: Path | None = None) -> None:
        command = ["docker", "compose", "-f", str(self.compose_path)]
        if override_file is not None:
            command.extend(["-f", str(override_file)])
        command.extend(args)
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

    def _parse_port_overrides(
        self, raw_bindings: Sequence[str], allowed_services: Sequence[str]
    ) -> Dict[str, List[str]]:
        """Parse strings like 'service=host:container[/proto]'."""
        valid_services = set(allowed_services or self.honeypot_services)
        overrides: Dict[str, List[str]] = {}
        for binding in raw_bindings:
            if "=" not in binding:
                raise HoneypotServiceError(
                    f"Port override '{binding}' is missing '=' "
                    "(expected service=HOST:CONTAINER[/PROTO])"
                )
            service, portspec = binding.split("=", 1)
            service = service.strip()
            portspec = portspec.strip().strip('"').strip("'")
            if service not in valid_services:
                raise HoneypotServiceError(
                    f"Cannot override ports for unknown or inactive service '{service}'"
                )
            if not portspec:
                raise HoneypotServiceError(
                    f"Port override for '{service}' is empty"
                )
            overrides.setdefault(service, []).append(portspec)
        return overrides

    def _write_override_file(self, overrides: Dict[str, List[str]]) -> Path:
        """Create a temporary docker-compose override file with new ports."""
        lines = ["services:"]
        for service, ports in overrides.items():
            lines.append(f"  {service}:")
            lines.append("    ports:")
            for port in ports:
                if port.startswith(("\"", "'")):
                    lines.append(f"      - {port}")
                else:
                    lines.append(f'      - "{port}"')
        temp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix="-ports.yml"
        )
        temp.write("\n".join(lines) + "\n")
        temp.flush()
        temp.close()
        return Path(temp.name)


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

    start_parser = subparsers.add_parser("start", help="start services")
    start_parser.add_argument(
        "services",
        nargs="*",
        help="Optional list of honeypot service names",
    )
    start_parser.add_argument(
        "--port",
        dest="ports",
        action="append",
        default=[],
        help=(
            "Override port binding(s) in the form service=HOST:CONTAINER[/PROTO]. "
            "Repeat for multiple overrides."
        ),
    )

    stop_parser = subparsers.add_parser("stop", help="stop services")
    stop_parser.add_argument(
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
        port_overrides = getattr(args, "ports", None) or None
        manager.start(services, port_overrides)
    elif args.command == "stop":
        manager.stop(services)
    else:  # pragma: no cover - argparse ensures this doesn't happen
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
