#!/usr/bin/env python3
"""Test script to debug MCP server connection issues."""
import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.mcp import MCPServerStdio

async def test_mcp_connection():
    """Test if we can connect to the MCP server."""
    mcp_server_path = Path(__file__).parent / "log_reader_mcp_server.py"
    mcp_server_abs_path = mcp_server_path.resolve()
    python_executable = sys.executable
    
    print(f"Python executable: {python_executable}")
    print(f"MCP server path: {mcp_server_abs_path}")
    print(f"MCP server exists: {mcp_server_abs_path.exists()}")
    print()
    
    try:
        print("Attempting to connect to MCP server...")
        async with MCPServerStdio(
            name="NetworkLogReaderServer",
            params={
                "command": python_executable,
                "args": [str(mcp_server_abs_path)],
            },
            cache_tools_list=True,
            client_session_timeout_seconds=30.0,
        ) as log_reader_mcp_server:
            print("✓ MCP server connected successfully!")
            tools = await log_reader_mcp_server.list_tools()
            print(f"Available tools: {[tool.name for tool in tools]}")
            return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("Warning: OPENAI_API_KEY not set (not needed for MCP connection test)")
    
    result = asyncio.run(test_mcp_connection())
    sys.exit(0 if result else 1)

