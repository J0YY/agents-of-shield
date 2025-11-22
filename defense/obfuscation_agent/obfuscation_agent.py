# obfuscation_agent.py
import asyncio
import os
import sys

from agents import Agent, Runner, set_default_openai_api
from agents import set_tracing_disabled
from agents.mcp import MCPServerStdio  # MCP integration in Agents SDK


def require_args() -> tuple[str, str]:
    if len(sys.argv) != 3:
        print(
            "Usage: python obfuscation_agent.py <source_dir> <output_dir>",
            file=sys.stderr,
        )
        sys.exit(1)

    source_dir = os.path.abspath(sys.argv[1])
    output_dir = os.path.abspath(sys.argv[2])
    return source_dir, output_dir


async def main() -> None:
    set_default_openai_api(os.environ["OPENAI_API_KEY"])
    set_tracing_disabled(True)

    source_dir, output_dir = require_args()

    # Start your custom MCP server as a subprocess over stdio
    async with MCPServerStdio(
        name="JsObfuscatorServer",
        params={
            "command": "python",
            "args": ["obfuscation_mcp_server.py"],  # path to the server file
        },
        cache_tools_list=True,
        client_session_timeout_seconds=600.0,
    ) as obfuscation_mcp_server:
        # Agent can now call the `obfuscate_directory` tool
        agent = Agent(
            name="ObfuscationAgent",
            model="gpt-4.1-mini",
            instructions=(
                "You are an obfuscation agent.\n"
                "- You have access to tools from JsObfuscatorServer.\n"
                "- Always call the `obfuscate_directory` tool exactly once using the "
                "given source_dir and output_dir.\n"
                "- The tool already skips node_modules and build artifacts; do not "
                "ask the user about them and do not attempt to implement obfuscation "
                "yourself.\n"
                "- After the tool finishes, simply report the JSON result."
            ),
            mcp_servers=[obfuscation_mcp_server],
        )

        task = (
            "Obfuscate the JavaScript source code in the given directory.\n\n"
            f"source_dir: {source_dir}\n"
            f"output_dir: {output_dir}\n\n"
            "Call the `obfuscate_directory` tool once with these arguments "
            "and then report the tool's returned JSON summary."
        )

        result = await Runner.run(agent, task)
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())