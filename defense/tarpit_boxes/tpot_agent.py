# tpot_agent.py
import argparse
import asyncio
import os
import sys
from typing import List, Optional

from agents import Agent, Runner, set_default_openai_api
from agents import set_tracing_disabled
from agents.mcp import MCPServerStdio

from defense.initial_defense_orchestrator.tool_logging_hooks import ToolLoggingHooks


def parse_cli_args() -> tuple[str, Optional[List[str]], Optional[List[str]], Optional[str]]:
    """
    CLI parser for standalone usage.

    Usage examples:
        python tpot_agent.py list
        python tpot_agent.py start cowrie dionaea --compose-path /opt/tpot/docker-compose.yml
        python tpot_agent.py start cowrie --port-override 2222:22 --port-override 2223:23
        python tpot_agent.py stop        # stop all honeypots (default compose)
    """
    parser = argparse.ArgumentParser(
        description="TPotAgent CLI wrapper around TPotComposeServer tools."
    )
    parser.add_argument(
        "action",
        choices=["list", "start", "stop"],
        help="Action to perform: list, start, or stop honeypots.",
    )
    parser.add_argument(
        "services",
        nargs="*",
        help=(
            "Optional list of honeypot service names. "
            "If omitted for start/stop, all honeypots are targeted."
        ),
    )
    parser.add_argument(
        "--compose-path",
        dest="compose_path",
        default=None,
        help="Optional path to the T-Pot docker-compose file.",
    )
    parser.add_argument(
        "--port-override",
        dest="port_overrides",
        action="append",
        default=None,
        help=(
            "Port override of the form 'HOST_PORT:CONTAINER_PORT'. "
            "May be specified multiple times. Used only for 'start'."
        ),
    )

    args = parser.parse_args()

    action: str = args.action
    services: List[str] = args.services or []
    port_overrides: Optional[List[str]] = args.port_overrides
    compose_path: Optional[str] = args.compose_path

    if action != "start" and port_overrides:
        print(
            "Warning: --port-override is only meaningful for 'start'; "
            "it will be ignored for other actions.",
            file=sys.stderr,
        )

    return action, (services or None), port_overrides, compose_path


def build_tpot_agent(tpot_mcp_server: MCPServerStdio) -> Agent:
    """
    Create the TPotAgent configured to use the TPotComposeServer MCP server.

    This function is used by TPotAgentContext and can also be used directly
    if you already have an MCP server instance.
    """
    return Agent(
        name="TPotAgent",
        model="gpt-4.1-mini",
        instructions=(
            "You are a honeypot orchestration subagent for a T-Pot deployment.\n\n"
            "You have access to tools from TPotComposeServer:\n"
            "- `list_honeypots(compose_path=None)`\n"
            "    Return the honeypot services discovered in the compose file.\n\n"
            "- `start_honeypots(services=None, port_overrides=None, compose_path=None)`\n"
            "    Start one or more honeypot services. If `services` is omitted or empty,\n"
            "    all honeypot services in the compose file are started. Optional\n"
            "    `port_overrides` can be provided as strings like '2222:22'.\n\n"
            "- `stop_honeypots(services=None, compose_path=None)`\n"
            "    Stop one or more honeypot services. If `services` is omitted or empty,\n"
            "    all honeypot services in the compose file are stopped.\n\n"
            "You are called by an orchestrator agent (or via the CLI) that provides you\n"
            "with the following parameters inside the task text:\n"
            "- `action`: one of `list`, `start`, or `stop`.\n"
            "- `services`: optional comma- or space-separated list of honeypot names.\n"
            "- `compose_path`: optional path to the docker-compose file; if omitted,\n"
            "  use the default provided by the server.\n"
            "- `port_overrides`: optional comma- or newline-separated port override\n"
            "  strings, such as `2222:22`.\n\n"
            "Your job:\n"
            "1) Parse the input message to identify the `action` and any optional\n"
            "   `services`, `compose_path`, and `port_overrides` parameters.\n"
            "2) If `action` is `list`, call `list_honeypots(...)` exactly once.\n"
            "3) If `action` is `start`, call `start_honeypots(...)` exactly once with\n"
            "   the parsed services (or None) and port overrides (or None).\n"
            "4) If `action` is `stop`, call `stop_honeypots(...)` exactly once with\n"
            "   the parsed services (or None).\n\n"
            "When constructing tool arguments:\n"
            "- If no services are specified, pass `services=None` so the server can\n"
            "  apply the default of 'all honeypots'.\n"
            "- If no port overrides are specified, pass `port_overrides=None`.\n"
            "- If no compose path is specified, pass `compose_path=None`.\n\n"
            "Do not ask follow-up questions. Do not attempt to manipulate docker or\n"
            "compose files directly; always delegate to the provided tools.\n\n"
            "After the tool call completes, synthesize the JSON result into a concise\n"
            "final summary describing:\n"
            "- which compose file was used,\n"
            "- which honeypot services were listed/started/stopped, and\n"
            "- any port overrides that were applied (for start operations),\n"
            "plus any relevant status messages from the tool responses."
        ),
        mcp_servers=[tpot_mcp_server],
    )


class TPotAgentContext:
    """
    Async context manager that bundles:
    - Starting the TPotComposeServer MCP server over stdio.
    - Constructing a TPotAgent wired to that server.
    - Shutting down the MCP server when done.

    Usage (standalone or from an orchestrator):

        async with TPotAgentContext() as tpot_agent:
            result = await Runner.run(tpot_agent, task)
    """

    def __init__(
        self,
        server_command: str = "python",
        server_script: str | None = None,
        client_session_timeout_seconds: float = 600.0,
    ) -> None:
        self.server_command = server_command
        # Default to tpot_mcp_server.py in the same directory as this file.
        if server_script is None:
            server_script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "tpot_mcp_server.py",
            )
        self.server_script = server_script
        self.client_session_timeout_seconds = client_session_timeout_seconds

        self._mcp_cm: MCPServerStdio | None = None
        self._mcp_server = None
        self.agent: Agent | None = None

    async def __aenter__(self) -> Agent:
        self._mcp_cm = MCPServerStdio(
            name="TPotComposeServer",
            params={
                "command": self.server_command,
                "args": [self.server_script],
            },
            cache_tools_list=True,
            client_session_timeout_seconds=self.client_session_timeout_seconds,
        )
        # Enter the MCP context manager and get the server handle
        self._mcp_server = await self._mcp_cm.__aenter__()
        # Build the agent that uses this MCP server
        self.agent = build_tpot_agent(self._mcp_server)
        return self.agent

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._mcp_cm is not None:
            await self._mcp_cm.__aexit__(exc_type, exc, tb)


async def main() -> None:
    """
    Standalone entrypoint so you can run the TPot agent directly from the CLI.

    Example:
        python tpot_agent.py list
        python tpot_agent.py start cowrie dionaea --compose-path /opt/tpot/docker-compose.yml
        python tpot_agent.py stop
    """
    set_default_openai_api(os.environ["OPENAI_API_KEY"])
    set_tracing_disabled(True)

    action, services, port_overrides, compose_path = parse_cli_args()

    # Build a task string that encodes the parameters in a predictable format
    # for the agent, mirroring the obfuscation agent pattern.
    services_str = " ".join(services) if services else ""
    port_overrides_str = ", ".join(port_overrides or [])

    task = (
        "Manage T-Pot honeypot services using the tools from TPotComposeServer.\n\n"
        f"action: {action}\n"
        f"services: {services_str if services_str else '(all)'}\n"
        f"compose_path: {compose_path or '(default)'}\n"
        f"port_overrides: {port_overrides_str or '(none)'}\n\n"
        "Based on the action:\n"
        "- If action == 'list', call `list_honeypots` once with the compose_path.\n"
        "- If action == 'start', call `start_honeypots` once with these services\n"
        "  (or None for all), port_overrides (or None), and compose_path.\n"
        "- If action == 'stop', call `stop_honeypots` once with these services\n"
        "  (or None for all) and compose_path.\n\n"
        "After the tool call, summarize the JSON result concisely."
    )

    async with TPotAgentContext() as tpot_agent:
        result = await Runner.run(
            tpot_agent,
            task,
            hooks=ToolLoggingHooks(),
        )

        print("=== FINAL OUTPUT ===")
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())