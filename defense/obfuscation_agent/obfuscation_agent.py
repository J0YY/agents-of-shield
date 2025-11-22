# obfuscation_agent.py
import asyncio
import os
import sys

from agents import Agent, Runner, RunHooks, set_default_openai_api
from agents import set_tracing_disabled
from agents.mcp import MCPServerStdio


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


class ToolLoggingHooks(RunHooks):
    async def on_tool_start(self, context, agent, tool):
        print(
            f"[TOOL START] agent={agent.name}, tool={tool.name}, "
            f"type={tool.__class__.__name__}"
        )

    async def on_tool_end(self, context, agent, tool, result):
        print(
            f"[TOOL END]   agent={agent.name}, tool={tool.name}\n"
            f"  result={result}\n"
            "----------------------------------------"
        )


async def main() -> None:
    set_default_openai_api(os.environ["OPENAI_API_KEY"])
    set_tracing_disabled(True)

    source_dir, output_dir = require_args()

    async with MCPServerStdio(
        name="JsObfuscatorServer",
        params={
            "command": "python",
            "args": ["obfuscation_mcp_server.py"],  # path to your MCP server file
        },
        cache_tools_list=True,
        client_session_timeout_seconds=600.0,
    ) as obfuscation_mcp_server:
        agent = Agent(
            name="ObfuscationAgent",
            model="gpt-4.1-mini",
            instructions=(
                "You are a web application obfuscation agent.\n\n"
                "You have access to tools from JsObfuscatorServer:\n"
                "- `obfuscate_directory(source_dir, output_dir, ...)` "
                "  Recursively copies a directory, obfuscating .js/.jsx files and "
                "  skipping common dependency/build directories. Non-JS files are "
                "  copied only if they do not already exist in the output.\n"
                "- `minify_html_directory(source_dir, output_dir, ...)` "
                "  Recursively copies a directory, minifying .html/.htm files and "
                "  skipping common dependency/build directories. Non-HTML files are "
                "  copied only if they do not already exist in the output.\n"
                "- `minify_css_directory(source_dir, output_dir, ...)` "
                "  Recursively copies a directory, minifying .css files and "
                "  skipping common dependency/build directories. Non-CSS files are "
                "  copied only if they do not already exist in the output.\n\n"
                "Given a source_dir and output_dir, you must:\n"
                "1) Call `obfuscate_directory` with the provided source_dir and "
                "   output_dir to obfuscate JavaScript.\n"
                "2) Call `minify_html_directory` with the same source_dir and "
                "   output_dir to minify HTML.\n"
                "3) Call `minify_css_directory` with the same source_dir and "
                "   output_dir to minify CSS.\n\n"
                "Call each tool exactly once per run, in any order, always using "
                "the provided source_dir and output_dir. Do not ask the user "
                "follow-up questions. Do not attempt to implement obfuscation or "
                "minification yourself; always delegate to these tools.\n\n"
                "After all three tools have completed, synthesize their JSON "
                "results into a concise summary of what was processed, including "
                "the paths and basic statistics (e.g., files_obfuscated, "
                "files_minified, files_copied, dirs_created)."
            ),
            mcp_servers=[obfuscation_mcp_server],
        )

        task = (
            "Obfuscate and minify the web application assets in the given "
            "directory.\n\n"
            f"source_dir: {source_dir}\n"
            f"output_dir: {output_dir}\n\n"
            "Use the tools from JsObfuscatorServer to:\n"
            "- Obfuscate JavaScript (.js/.jsx) files.\n"
            "- Minify HTML (.html/.htm) files.\n"
            "- Minify CSS (.css) files.\n\n"
            "Call `obfuscate_directory`, `minify_html_directory`, and "
            "`minify_css_directory`, each exactly once with these arguments, then "
            "summarize their JSON outputs."
        )

        result = await Runner.run(
            agent,
            task,
            hooks=ToolLoggingHooks(),
        )

        print("=== FINAL OUTPUT ===")
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())