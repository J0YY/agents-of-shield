# obfuscation_agent.py
import asyncio
import os
import sys

from agents import Agent, Runner, set_default_openai_api
from agents import set_tracing_disabled
from agents.mcp import MCPServerStdio

from defense.initial_defense_orchestrator.tool_logging_hooks import ToolLoggingHooks

def require_args() -> tuple[str, str]:
    """
    CLI-only: require source and output directories as positional args.
    """
    if len(sys.argv) != 3:
        print(
            "Usage: python obfuscation_agent.py <source_dir> <output_dir>",
            file=sys.stderr,
        )
        sys.exit(1)

    source_dir = os.path.abspath(sys.argv[1])
    output_dir = os.path.abspath(sys.argv[2])
    return source_dir, output_dir


def build_obfuscation_agent(obfuscation_mcp_server: MCPServerStdio) -> Agent:
    """
    Create the ObfuscationAgent configured to use the JsObfuscatorServer MCP server.

    This function is used by ObfuscationAgentContext and can also be used directly
    if you already have an MCP server instance.
    """
    return Agent(
        name="ObfuscationAgent",
        model="gpt-4.1-mini",
        instructions=(
            "You are a web application obfuscation subagent.\n\n"
            "You have access to tools from JsObfuscatorServer:\n"
            "- `obfuscate_directory(source_dir, output_dir, ...)` "
            "  Recursively copies a directory, obfuscating .js/.jsx files and "
            "  skipping common dependency/build directories. Non-JS files are "
            "  copied only if they do not already exist in the output.\n"
            "- `minify_html_directory(source_dir, output_dir, ...)` "
            "  Recursively copies a directory, minifying .html/.htm/.ejs files and "
            "  skipping common dependency/build directories. Non-HTML files are "
            "  copied only if they do not already exist in the output.\n"
            "- `minify_css_directory(source_dir, output_dir, ...)` "
            "  Recursively copies a directory, minifying .css files and "
            "  skipping common dependency/build directories. Non-CSS files are "
            "  copied only if they do not already exist in the output.\n\n"
            "You are called by an orchestrator agent that provides you with:\n"
            "- a `source_dir` (root of the target web app code), and\n"
            "- an `output_dir` (where obfuscated/minified output should be written).\n\n"
            "Your job:\n"
            "1) Parse the input message to identify `source_dir` and `output_dir` "
            "   (they will be given explicitly in the text).\n"
            "2) Call `obfuscate_directory(source_dir, output_dir, ...)` exactly once.\n"
            "3) Call `minify_html_directory(source_dir, output_dir, ...)` exactly once.\n"
            "4) Call `minify_css_directory(source_dir, output_dir, ...)` exactly once.\n\n"
            "Always use the same source_dir and output_dir for all three calls.\n"
            "Do not ask follow-up questions. Do not attempt to implement any "
            "obfuscation or minification yourself; always delegate to these tools.\n\n"
            "After all three tools have completed, synthesize their JSON results "
            "into a concise final summary describing:\n"
            "- which directories were processed,\n"
            "- how many files were obfuscated/minified/copied, and\n"
            "- where the final outputs are located."
        ),
        mcp_servers=[obfuscation_mcp_server],
    )


class ObfuscationAgentContext:
    """
    Async context manager that bundles:
    - Starting the JsObfuscatorServer MCP server over stdio.
    - Constructing an ObfuscationAgent wired to that server.
    - Shutting down the MCP server when done.

    Usage (standalone or from an orchestrator):

        async with ObfuscationAgentContext() as obfuscation_agent:
            result = await Runner.run(obfuscation_agent, task)
    """

    def __init__(
        self,
        server_command: str = "python",
        server_script: str | None = None,
        client_session_timeout_seconds: float = 600.0,
    ) -> None:
        self.server_command = server_command
        # Default to obfuscation_mcp_server.py in the same directory as this file
        if server_script is None:
            server_script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "obfuscation_mcp_server.py",
            )
        self.server_script = server_script
        self.client_session_timeout_seconds = client_session_timeout_seconds

        self._mcp_cm: MCPServerStdio | None = None
        self._mcp_server = None
        self.agent: Agent | None = None

    async def __aenter__(self) -> Agent:
        self._mcp_cm = MCPServerStdio(
            name="JsObfuscatorServer",
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
        self.agent = build_obfuscation_agent(self._mcp_server)
        return self.agent

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._mcp_cm is not None:
            await self._mcp_cm.__aexit__(exc_type, exc, tb)


async def main() -> None:
    """
    Standalone entrypoint so you can run the obfuscation agent directly from the CLI.

    Example:
        python obfuscation_agent.py ./source ./obfuscated
    """
    set_default_openai_api(os.environ["OPENAI_API_KEY"])
    set_tracing_disabled(True)

    source_dir, output_dir = require_args()

    async with ObfuscationAgentContext() as obfuscation_agent:
        task = (
            "Obfuscate and minify the web application assets in the given "
            "directory.\n\n"
            f"source_dir: {source_dir}\n"
            f"output_dir: {output_dir}\n\n"
            "Use the tools from JsObfuscatorServer to:\n"
            "- Obfuscate JavaScript (.js/.jsx) files.\n"
            "- Minify HTML (.html/.htm/.ejs) files.\n"
            "- Minify CSS (.css) files.\n\n"
            "Call `obfuscate_directory`, `minify_html_directory`, and "
            "`minify_css_directory`, each exactly once with these arguments, then "
            "summarize their JSON outputs."
        )

        result = await Runner.run(
            obfuscation_agent,
            task,
            hooks=ToolLoggingHooks(),
        )

        print("=== FINAL OUTPUT ===")
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())