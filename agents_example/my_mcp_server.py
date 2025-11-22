# my_mcp_server.py
from typing import Dict

from mcp.server.fastmcp import FastMCP

# Create the MCP server instance
mcp = FastMCP(
    "MyCustomServer",
    json_response=True,   # JSON responses are convenient for agents
)

# --- Custom tools ---------------------------------------------------------


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool()
def word_count(text: str) -> Dict[str, int]:
    """Count how many words are in the given text."""
    words = text.split()
    return {"word_count": len(words)}


# Entry point for direct execution (stdio transport by default)
def main() -> None:
    # mcp.run() with no transport argument uses stdio, which works well
    # with OpenAI Agents' MCPServerStdio. 
    mcp.run()


if __name__ == "__main__":
    main()