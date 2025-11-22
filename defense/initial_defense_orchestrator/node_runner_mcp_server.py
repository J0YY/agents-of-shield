# node_runner_mcp_server.py
import os
import subprocess

from mcp.server.fastmcp import FastMCP

# Create an MCP server instance
mcp = FastMCP("NodeRunnerServer")


@mcp.tool()
def start_node_app(working_dir: str) -> str:
    """
    Start a Node.js application by running `npm start` in the specified
    working directory. Intended for starting the obfuscated copy of the app.

    Parameters
    ----------
    working_dir : str
        Absolute path to the directory where `npm start` should be run
        (e.g., the root of the obfuscated app).
    """
    if not isinstance(working_dir, str) or not working_dir:
        return "ERROR: Missing or invalid 'working_dir' argument."

    if not os.path.isdir(working_dir):
        return f"ERROR: working_dir does not exist or is not a directory: {working_dir}"

    # Fire-and-forget: run npm start detached from this process's stdio so it
    # doesn't interfere with the MCP JSON-RPC stream.
    proc = subprocess.Popen(
        ["npm", "start"],
        cwd=working_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )

    return (
        f"Started Node.js app with `npm start` in: {working_dir}\n"
        f"PID: {proc.pid}"
    )


if __name__ == "__main__":
    # Run the MCP server over stdio so it works with MCPServerStdio(...)
    mcp.run(transport="stdio")