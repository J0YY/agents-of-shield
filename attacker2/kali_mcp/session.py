from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from agents.mcp import MCPServerStdio  # type: ignore[import]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_list(name: str) -> List[str]:
    value = os.getenv(name)
    if not value:
        return []
    return [token for token in value.split() if token]


def _default_port(server_url: str) -> int:
    parsed = urlparse(server_url)
    if parsed.port:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    return 80


@dataclass
class KaliMCPConfig:
    """Runtime configuration for launching a Kali MCP bridge."""

    server_url: str = field(default_factory=lambda: os.getenv("KALI_MCP_SERVER_URL", "http://127.0.0.1:5000"))
    session_name: str = field(default_factory=lambda: os.getenv("KALI_MCP_SESSION_NAME", "KaliMCPBridge"))
    auto_start_api: bool = field(default_factory=lambda: _env_bool("KALI_MCP_AUTO_START", False))
    api_command: str = field(default_factory=lambda: os.getenv("KALI_MCP_API_COMMAND", "kali-server-mcp"))
    api_port: int = field(default_factory=lambda: int(os.getenv("KALI_MCP_API_PORT", "0")))
    api_debug: bool = field(default_factory=lambda: _env_bool("KALI_MCP_API_DEBUG", False))
    client_command: str = field(default_factory=lambda: os.getenv("KALI_MCP_CLIENT_COMMAND", "mcp-server"))
    client_timeout: float = field(default_factory=lambda: float(os.getenv("KALI_MCP_CLIENT_TIMEOUT", "300")))
    client_debug: bool = field(default_factory=lambda: _env_bool("KALI_MCP_CLIENT_DEBUG", False))
    client_extra_args: Sequence[str] = field(default_factory=lambda: _env_list("KALI_MCP_CLIENT_EXTRA_ARGS"))

    def __post_init__(self) -> None:
        if self.api_port == 0:
            self.api_port = _default_port(self.server_url)

    @property
    def socket_target(self) -> Tuple[str, int]:
        parsed = urlparse(self.server_url)
        host = parsed.hostname or "127.0.0.1"
        return host, self.api_port

    def build_client_args(self) -> List[str]:
        args: List[str] = []
        if self.server_url:
            args.extend(["--server", self.server_url])
        if self.client_timeout:
            args.extend(["--timeout", str(int(self.client_timeout))])
        if self.client_debug:
            args.append("--debug")
        args.extend(self.client_extra_args)
        return args

    def build_api_args(self) -> List[str]:
        args: List[str] = []
        if self.api_port:
            args.extend(["--port", str(self.api_port)])
        if self.api_debug:
            args.append("--debug")
        return args

    def summary(self) -> Dict[str, str]:
        return {
            "server_url": self.server_url,
            "session_name": self.session_name,
            "auto_start_api": str(self.auto_start_api),
            "client_command": self.client_command,
            "api_command": self.api_command,
        }


class KaliMCPSession:
    """Async context manager that ensures a Kali MCP client/server pairing is available."""

    def __init__(self, config: Optional[KaliMCPConfig] = None) -> None:
        self.config = config or KaliMCPConfig()
        self._api_process: Optional[subprocess.Popen] = None
        self._mcp_ctx: Optional[MCPServerStdio] = None
        self._server_handle = None

    async def __aenter__(self):
        if self.config.auto_start_api:
            self._api_process = self._launch_api_process()
            await self._wait_for_api()

        self._mcp_ctx = MCPServerStdio(
            name=self.config.session_name,
            params={
                "command": self.config.client_command,
                "args": list(self.config.build_client_args()),
            },
            cache_tools_list=True,
            client_session_timeout_seconds=self.config.client_timeout,
        )
        self._server_handle = await self._mcp_ctx.__aenter__()
        return self._server_handle

    async def __aexit__(self, exc_type, exc, tb):
        if self._mcp_ctx:
            await self._mcp_ctx.__aexit__(exc_type, exc, tb)
        if self._api_process:
            self._terminate_api_process()

    # ------------------------------------------------------------------ helpers

    def _launch_api_process(self) -> subprocess.Popen:
        args = [self.config.api_command, *self.config.build_api_args()]
        return subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    async def _wait_for_api(self, timeout: float = 15.0) -> None:
        host, port = self.config.socket_target
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._api_process and self._api_process.poll() is not None:
                stdout, stderr = self._api_process.communicate(timeout=0)
                raise RuntimeError(
                    "kali-server-mcp exited prematurely:\n"
                    f"STDOUT: {stdout.decode(errors='ignore')}\n"
                    f"STDERR: {stderr.decode(errors='ignore')}"
                )
            if self._port_open(host, port):
                return
            await asyncio.sleep(0.25)
        raise TimeoutError(f"Kali MCP API did not open port {port} within {timeout} seconds")

    def _port_open(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            return False

    def _terminate_api_process(self) -> None:
        if not self._api_process:
            return
        self._api_process.terminate()
        try:
            self._api_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._api_process.kill()

