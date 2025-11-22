"""MCP server exposing the T-Pot compose controls defined in tpot.py."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Sequence

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# Ensure we can import the sibling tpot.py module despite the hyphenated folder.
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from tpot import (  # type: ignore  # pylint: disable=wrong-import-position
    DEFAULT_COMPOSE_PATH,
    HoneypotServiceError,
    TPotComposeManager,
)

mcp = FastMCP("TPotComposeServer", json_response=True)


class ToolResult(BaseModel):
    compose_file: str = Field(..., description="Resolved compose file path")
    services: List[str] = Field(..., description="Services impacted by the call")
    overrides: Optional[List[str]] = Field(
        None, description="Port override strings, if any were used"
    )
    message: str = Field(..., description="Human-readable status summary")


class ListResult(BaseModel):
    compose_file: str = Field(..., description="Resolved compose file path")
    honeypots: List[str] = Field(..., description="Discovered honeypot services")


def _build_manager(compose_path: Optional[str]) -> TPotComposeManager:
    resolved = Path(compose_path or DEFAULT_COMPOSE_PATH).expanduser()
    return TPotComposeManager(resolved)


def _resolve_targets(
    manager: TPotComposeManager, requested: Optional[Sequence[str]]
) -> List[str]:
    available = manager.list_services()
    if not requested:
        return available
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise ValueError(f"Unknown honeypot service(s): {', '.join(unknown)}")
    return list(requested)


@mcp.tool()
def list_honeypots(compose_path: Optional[str] = None) -> ListResult:
    """
    Return the honeypot services discovered in the compose file.
    """
    manager = _build_manager(compose_path)
    services = manager.list_services()
    return ListResult(compose_file=str(manager.compose_path), honeypots=services)


@mcp.tool()
def start_honeypots(
    services: Optional[Sequence[str]] = None,
    port_overrides: Optional[Sequence[str]] = None,
    compose_path: Optional[str] = None,
) -> ToolResult:
    """
    Start one or more honeypot services, optionally overriding port bindings.
    """
    manager = _build_manager(compose_path)
    targets = _resolve_targets(manager, services)
    try:
        manager.start(targets, port_overrides)
    except HoneypotServiceError as exc:
        raise ValueError(str(exc)) from exc
    return ToolResult(
        compose_file=str(manager.compose_path),
        services=targets,
        overrides=list(port_overrides or []),
        message="Honeypot services started",
    )


@mcp.tool()
def stop_honeypots(
    services: Optional[Sequence[str]] = None,
    compose_path: Optional[str] = None,
) -> ToolResult:
    """
    Stop one or more honeypot services.
    """
    manager = _build_manager(compose_path)
    targets = _resolve_targets(manager, services)
    try:
        manager.stop(targets)
    except HoneypotServiceError as exc:
        raise ValueError(str(exc)) from exc
    return ToolResult(
        compose_file=str(manager.compose_path),
        services=targets,
        overrides=None,
        message="Honeypot services stopped",
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
