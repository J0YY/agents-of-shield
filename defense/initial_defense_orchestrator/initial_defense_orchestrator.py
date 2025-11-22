# initial_defense_orchestrator.py
import asyncio
import os
import sys

from agents import Agent, Runner, set_default_openai_api
from agents import set_tracing_disabled
from agents.mcp import MCPServerStdio

from defense.obfuscation_agent.obfuscation_agent import ObfuscationAgentContext
from defense.tarpit_boxes.tpot_agent import TPotAgentContext
from defense.initial_defense_orchestrator.tool_logging_hooks import ToolLoggingHooks


def require_args() -> tuple[str, str]:
    """
    CLI arguments for the orchestrator:

    - repo_root: the root directory of the target source code repository.
    - defense_root: a directory under which defense artifacts (like obfuscated code)
      will be written.

    Example:
        python initial_defense_orchestrator.py ./vulnerable-app ./defense-output
    """
    if len(sys.argv) != 3:
        print(
            "Usage: python initial_defense_orchestrator.py <repo_root> <defense_root>",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = os.path.abspath(sys.argv[1])
    defense_root = os.path.abspath(sys.argv[2])
    return repo_root, defense_root


def build_defense_orchestrator(
    obfuscation_tool,
    honeypot_tool,
    filesystem_server,
) -> Agent:
    """
    Build the 'defense setup' orchestrator agent.

    This agent is responsible for setting up multiple defense mechanisms for a
    target source code repository by delegating to specialized subagents that are
    exposed as tools, and by using a filesystem MCP server to inspect the code.
    """
    return Agent(
        name="DefenseSetupAgent",
        model="gpt-4.1-mini",
        instructions=(
            "You are the Defense Setup Orchestrator for a source code repository.\n\n"
            "You coordinate a set of specialized defense tools that each apply a "
            "particular defense mechanism (e.g., code obfuscation, honeypots, "
            "hardening steps).\n\n"
            "You have access to:\n\n"
            "1) A code obfuscation subagent tool:\n"
            "- `obfuscate_web_app(source_dir, output_dir, ...)`:\n"
            "  This tool runs a dedicated ObfuscationAgent that knows how to:\n"
            "  - Obfuscate JavaScript (.js/.jsx) files using an MCP server.\n"
            "  - Minify HTML (.html/.htm/.ejs) files.\n"
            "  - Minify CSS (.css) files.\n"
            "  It expects to receive a single text input that clearly specifies\n"
            "  `source_dir` and `output_dir` (usually as lines like\n"
            "  `source_dir: ...` and `output_dir: ...`).\n\n"
            "2) A honeypot orchestration subagent tool:\n"
            "- `run_initial_honeypots(action, services, compose_path, "
            "port_overrides, ...)`:\n"
            "  This tool runs a dedicated TPotAgent that manages T-Pot honeypot\n"
            "  services via an MCP server. It expects a single text input that\n"
            "  clearly specifies the desired action and parameters, typically as\n"
            "  lines like:\n"
            "    action: start\n"
            "    services: a small, explicit list of honeypot names (no more than 3)\n"
            "    compose_path: (default) or an explicit path\n"
            "    port_overrides: (none) or a comma-separated list such as 2222:22\n\n"
            "3) A filesystem MCP server (`FilesystemServer`) that provides these tools:\n"
            "- `list_directory(path)`:\n"
            "    List the direct children of a directory.\n"
            "- `directory_tree(path, max_depth, exclude_patterns)`:\n"
            "    Recursively enumerate the structure under a directory up to a\n"
            "    maximum depth, optionally skipping paths that match\n"
            "    `exclude_patterns` (glob-style patterns like '**/node_modules/**').\n"
            "- `search_files(root, pattern, exclude_patterns, max_results)`:\n"
            "    Search for files under `root` whose relative path matches a\n"
            "    glob-style pattern such as '**/*.js'.\n"
            "- `read_text_file(path, max_bytes, encoding)`:\n"
            "    Read (at most) max_bytes of a file as text.\n"
            "- `get_file_info(path)`:\n"
            "    Retrieve basic metadata for a file or directory.\n\n"
            "Treat the filesystem MCP server as read-only in this workflow.\n\n"
            "Your responsibilities when given a repository root and a defense_root:\n"
            "1) Use the filesystem tools to scan and assess the codebase located under\n"
            "   repo_root. At a minimum, you should:\n"
            "   - Inspect the top-level structure via `directory_tree` or\n"
            "     `list_directory`.\n"
            "   - Identify key files such as `package.json`, `Dockerfile`, `.env`,\n"
            "     or framework-specific configuration files by using `search_files`.\n"
            "   - Use `read_text_file` on selected files (for example `package.json`,\n"
            "     main server entry points, or route definition files) to infer:\n"
            "       * The frameworks and libraries in use (e.g., Express, Passport,\n"
            "         Mongoose, MySQL clients, Redis, etc.).\n"
            "       * Whether the app likely exposes HTTP(S) APIs, authentication\n"
            "         endpoints, admin panels, or external services.\n"
            "       * Whether there are hints of SSH, database access, or other\n"
            "         networked services.\n"
            "   - Use `exclude_patterns` such as `**/node_modules/**`, `**/dist/**`,\n"
            "     and `**/build/**` to avoid scanning dependency/build directories.\n"
            "2) Based on this evidence, infer the most relevant attack vectors for\n"
            "   the web application (e.g., HTTP/web exploitation, credential theft,\n"
            "   SSH brute-force, database probing).\n"
            "3) Decide how to apply defenses to this repository. At a minimum, you\n"
            "   must set up JavaScript/HTML/CSS obfuscation for the web application\n"
            "   code and start a small initial set of honeypot services via T-Pot.\n"
            "4) Construct a clear plan for obfuscation that specifies:\n"
            "   - source_dir: the path within the repo that should be obfuscated\n"
            "   - output_dir: where obfuscated/minified artifacts should be written\n"
            "5) Call the `obfuscate_web_app` tool exactly once, with a single string\n"
            "   argument that includes:\n"
            "   - `source_dir: <absolute path>`\n"
            "   - `output_dir: <absolute path>`\n"
            "   and a short explanation that the tool should fully obfuscate and\n"
            "   minify the web app assets.\n"
            "6) Based on your evidence-based assessment of the codebase and its\n"
            "   likely attack surface, select a small, targeted subset of honeypot\n"
            "   services that best match those attack vectors. You must not start all\n"
            "   available honeypots, and you must limit the initial deployment to no\n"
            "   more than 3 honeypots to avoid excessive bandwidth and resource usage.\n"
            "7) Call the `run_initial_honeypots` tool exactly once, with a single\n"
            "   string argument that clearly indicates you want to:\n"
            "   - `action: start`\n"
            "   - `services: <a concise list of the selected honeypot names>`\n"
            "   - `compose_path: (default)` unless there is a clear reason to use a\n"
            "     different path\n"
            "   - `port_overrides: (none)` unless you identify a clear need for custom\n"
            "     port bindings\n"
            "   The input should also explain, briefly, why these specific honeypots\n"
            "   were chosen given the observed codebase.\n"
            "8) After both tools return, summarize what defenses were applied,\n"
            "   where the outputs were written, which honeypots were started (and why\n"
            "   they were chosen), and any next steps for additional defenses.\n\n"
            "Important rules:\n"
            "- Always perform at least one obfuscation pass using `obfuscate_web_app`.\n"
            "- Always perform at least one honeypot start operation using\n"
            "  `run_initial_honeypots`.\n"
            "- Never start the entire set of honeypots; restrict the initial deployment\n"
            "  to a small, well-justified subset (no more than 3 honeypots) that aligns\n"
            "  with the likely attack surface of the application.\n"
            "- Only use the filesystem MCP tools for reading/listing/searching; do not\n"
            "  modify files.\n"
            "- Do not attempt to call lower-level MCP tools directly; instead, rely on\n"
            "  the `obfuscate_web_app` and `run_initial_honeypots` tools to run their\n"
            "  internal subagents, and the filesystem MCP tools for inspection.\n"
            "- Do not ask follow-up questions; assume the repository structure and paths\n"
            "  provided are correct.\n"
            "- Your final answer should be a clear, concise description of what you did,\n"
            "  what honeypots were started and why, and where the results live on disk."
        ),
        tools=[obfuscation_tool, honeypot_tool],
        mcp_servers=[filesystem_server],
    )


async def main() -> None:
    """
    Run the defense orchestrator from the CLI.

    Example:
        python initial_defense_orchestrator.py ./vulnerable-app ./defense-output
    """
    set_default_openai_api(os.environ["OPENAI_API_KEY"])
    set_tracing_disabled(True)

    repo_root, defense_root = require_args()
    obfuscated_output_dir = os.path.join(defense_root, "obfuscated-app")

    # Start the Python-based filesystem MCP server.
    filesystem_server_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "filesystem_mcp_server.py",
    )

    async with MCPServerStdio(
        name="FilesystemServer",
        params={
            "command": "python",
            "args": [filesystem_server_script],
        },
        cache_tools_list=True,
        client_session_timeout_seconds=600.0,
    ) as filesystem_server:
        # Bundle MCP server + obfuscation agent via ObfuscationAgentContext.
        # Bundle MCP server + honeypot agent via TPotAgentContext.
        # Then wrap each agent as a tool using .as_tool().
        async with ObfuscationAgentContext() as obfuscation_agent:
            async with TPotAgentContext() as honeypot_agent:
                obfuscation_tool = obfuscation_agent.as_tool(
                    tool_name="obfuscate_web_app",
                    tool_description=(
                        "Obfuscate JavaScript and minify HTML/CSS for a web application. "
                        "The input should clearly specify `source_dir` and `output_dir` "
                        "paths in the text (e.g., lines like `source_dir: ...` and "
                        "`output_dir: ...`)."
                    ),
                )

                honeypot_tool = honeypot_agent.as_tool(
                    tool_name="run_initial_honeypots",
                    tool_description=(
                        "Run the TPotAgent to plan and start a small set of honeypot "
                        "services managed by a T-Pot docker-compose deployment. The input "
                        "should clearly specify an `action` (typically `start`), a short "
                        "list of selected `services` (no more than 3 honeypots), an "
                        "optional `compose_path`, and optional `port_overrides` as text "
                        "lines such as:\n"
                        "  action: start\n"
                        "  services: cowrie heralding\n"
                        "  compose_path: (default)\n"
                        "  port_overrides: (none)\n"
                        "The agent may assume the orchestrator has already analyzed the "
                        "codebase and chosen appropriate honeypot services."
                    ),
                )

                orchestrator_agent = build_defense_orchestrator(
                    obfuscation_tool=obfuscation_tool,
                    honeypot_tool=honeypot_tool,
                    filesystem_server=filesystem_server,
                )

                # Initial instruction to the orchestrator.
                task = (
                    "Set up initial defenses for the following source code repository.\n\n"
                    f"Repository root (repo_root): {repo_root}\n"
                    f"Defense root (defense_root): {defense_root}\n"
                    f"Suggested obfuscation output directory: {obfuscated_output_dir}\n\n"
                    "The repository is an Express-based web application with frontend assets.\n"
                    "You should use the filesystem MCP tools to inspect the codebase under "
                    "repo_root in order to infer likely attack vectors. For example, you may:\n"
                    "- List the top-level structure and key subdirectories.\n"
                    "- Identify route handlers, middleware, authentication modules, and any\n"
                    "  database or cache clients.\n"
                    "- Inspect configuration files (such as package.json, Dockerfile, .env,\n"
                    "  or Express configuration) to understand which services and ports are\n"
                    "  in play.\n\n"
                    "At a minimum, you must:\n"
                    "- Obfuscate the JavaScript for the web app.\n"
                    "- Minify HTML (including any EJS templates) and CSS.\n"
                    "- Start a small, targeted set of honeypot services using T-Pot, chosen "
                    "to reflect the most plausible attacks against this web app based on the "
                    "evidence you observe in the codebase.\n\n"
                    "To handle obfuscation, call the `obfuscate_web_app` tool exactly once "
                    "with a single string argument that includes:\n"
                    f"- `source_dir: {repo_root}`\n"
                    f"- `output_dir: {obfuscated_output_dir}`\n"
                    "and a short explanation that the tool should fully obfuscate and "
                    "minify the web app assets.\n\n"
                    "To handle honeypots, first use the filesystem tools (directory_tree, "
                    "search_files, read_text_file, etc.) to identify the dominant attack "
                    "surface (for example, web-facing HTTP services, credential flows, SSH, "
                    "or database connectivity). Then select no more than three honeypot "
                    "types that best cover those attacks. Call the `run_initial_honeypots` "
                    "tool exactly once with a single string argument that clearly indicates "
                    "you want to start those specific honeypot services using the default "
                    "T-Pot compose file and no port overrides, unless there is a strong "
                    "reason to customize ports.\n\n"
                    "After both tools return, summarize what defenses were applied, where "
                    "the resulting obfuscated/minified code was written, which honeypots "
                    "were started (and how they relate to the inferred attack surface), "
                    "and any recommended next steps."
                )

                result = await Runner.run(
                    orchestrator_agent,
                    task,
                    hooks=ToolLoggingHooks(),
                )

                print("=== DEFENSE ORCHESTRATOR FINAL OUTPUT ===")
                print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())