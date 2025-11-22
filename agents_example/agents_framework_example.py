import asyncio
import os
from pathlib import Path

from agents import Agent, Runner
from agents.mcp import MCPServerStdio


async def main() -> None:
    # Ensure API key is present (Agents SDK uses the OpenAI Python SDK under the hood)
    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    # Directory that the filesystem MCP server will expose
    current_dir = Path(__file__).parent
    samples_dir = current_dir / "sample_files"

    if not samples_dir.exists():
        raise RuntimeError(
            f"Expected directory {samples_dir} to exist. "
            "Create it and put a README.md inside for the demo."
        )

    # 1. Create the MCP server (filesystem over stdio via npx)
    #    This uses the official MCP filesystem server, run via Node's npx. 
    async with MCPServerStdio(
        # Example: Using custom MCP Server defined in my_mcp_server.py
        name="MyCustomServer",
        params={
            "command": "python",
            "args": ["my_mcp_server.py"],  # path to the file from step 2
        },
        cache_tools_list=True,

        # Example: using the official filesystem MCP server
        # name="filesystem-mcp",
        # params={
        #     "command": "npx",
        #     "args": [
        #         "-y",
        #         "@modelcontextprotocol/server-filesystem",
        #         str(samples_dir),
        #     ],
        # },
        # cache_tools_list=True,

    ) as my_mcp_server:
        # 2. Define subagent A: file fetcher using MCP tools
        fetcher_agent = Agent(
            name="FileFetcher",
            instructions=(
                "You are a file-fetching specialist.\n"
                "You ONLY access files via the attached MCP filesystem tools.\n"
                "When asked, locate the requested file(s) and return their contents as plain text.\n"
                "Do not invent content that is not actually present in the files."
            ),
            model="gpt-4.1-mini",  # any Responses-compatible model
            mcp_servers=[],  # attach MCP server so tools are available 
        )

        # 3. Define subagent B: text analyst (also allowed to use MCP if useful)
        analyst_agent = Agent(
            name="TextAnalyst",
            instructions=(
                "You analyze text provided by other agents.\n"
                "You can summarise, extract key points, and suggest research questions.\n"
                "Be concise and structured in your answers."
                "You have access to tools from MyCustomServer. "
                "Use `add` for arithmetic and `word_count` for text analysis."
            ),
            model="gpt-4.1-mini",
            mcp_servers=[my_mcp_server],
        )

        # 4. Wrap each subagent as a tool (agents-as-tools pattern). 
        fetcher_tool = fetcher_agent.as_tool(
            tool_name="fetch_from_filesystem",
            tool_description=(
                "Reads one or more files from the sample_files directory using MCP "
                "filesystem tools and returns their full text."
            ),
        )

        analyst_tool = analyst_agent.as_tool(
            tool_name="analyze_text",
            tool_description=(
                "Analyzes arbitrary text (e.g. output of fetch_from_filesystem) and "
                "produces summaries and research questions."
            ),
        )

        # 5. Orchestrator agent that decides when to call each subagent
        orchestrator = Agent(
            name="Orchestrator",
            model="gpt-4.1-mini",
            instructions=(
                "You are an orchestrator that coordinates two specialist sub-agents:\n\n"
                "- fetch_from_filesystem: use this FIRST to read any files the user mentions.\n"
                "  Pass a clear description of which files to read (for example, "
                '"README.md in the root sample_files directory").\n'
                "- analyze_text: use this AFTER you have file contents. Pass the fetched text\n"
                "  plus the analysis task (summarise, extract questions, etc.).\n\n"
                "Policy:\n"
                "1. Parse the user request.\n"
                "2. Call fetch_from_filesystem to obtain the relevant file contents.\n"
                "3. Call analyze_text, passing the tool output from step 2 and the user's task.\n"
                "4. Return only the final analysis to the user.\n"
                "5. If a file is missing, explain clearly what went wrong."
            ),
            tools=[fetcher_tool, analyst_tool],
        )

        # 6. Example: LLM-driven orchestration (agents-as-tools)
        user_task = (
            "Using the project files in the sample_files directory, read README.md and "
            "give me:\n"
            "- A 3-bullet summary.\n"
            "- One potential research question inspired by the content."
        )

        print("--- Running orchestrator (LLM-driven orchestration) ---")
        orchestrator_result = await Runner.run(orchestrator, user_task)
        print("\n=== Final orchestrator answer ===\n")
        print(orchestrator_result.final_output)

        # 7. Example: explicit pipeline (code-driven orchestration)
        print("\n--- Running explicit pipeline (FileFetcher -> TextAnalyst) ---")

        fetcher_result = await Runner.run(
            fetcher_agent,
            "Read README.md from the sample_files directory and return its full text.",
        )

        fetched_text = fetcher_result.final_output

        analyst_prompt = (
            "You are given the following file contents:\n\n"
            f"{fetched_text}\n\n"
            "Task:\n"
            "1. Provide a 3-bullet summary.\n"
            "2. Suggest one potential follow-up experiment or research question."
        )

        analyst_result = await Runner.run(analyst_agent, analyst_prompt)

        print("\n=== Direct pipeline (FileFetcher -> TextAnalyst) ===\n")
        print(analyst_result.final_output)


if __name__ == "__main__":
    asyncio.run(main())