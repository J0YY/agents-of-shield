# log_reader_mcp_server.py
import json
from pathlib import Path
from typing import Dict, List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "NetworkLogReaderServer",
    json_response=True,
)


@mcp.tool()
def read_network_logs(
    lines: int = 50,
    log_path: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Dict:
    """
    Read recent network traffic logs from the log file.

    - Reads from vulnerable-app/attack_log.json in the working directory by default
    - Returns the last N lines of log entries
    - Each log entry is a JSON object with: timestamp, ip, method, endpoint, query, body
    - Logs are in JSONL format (one JSON object per line)

    Args:
        lines: Number of recent log lines to read (default: 50)
        log_path: Optional custom path to log file. If not provided, uses vulnerable-app/attack_log.json
        working_dir: Optional working directory. If not provided, uses current directory.

    Returns:
        Dictionary with:
        - entries: List of log entries (parsed JSON objects)
        - total_count: Total number of entries returned
        - log_file: Path to the log file that was read
    """
    if working_dir:
        base_dir = Path(working_dir).expanduser().resolve()
    else:
        base_dir = Path.cwd()

    if log_path:
        log_file = Path(log_path).expanduser().resolve()
    else:
        log_file = base_dir / "attack_log.json"

    if not log_file.exists():
        return {
            "entries": [],
            "total_count": 0,
            "log_file": str(log_file),
            "error": f"Log file not found: {log_file}",
        }

    entries = []
    try:
        with log_file.open("r", encoding="utf-8") as fh:
            file_lines = fh.readlines()
            # Get the last 'lines' entries
            for line in file_lines[-lines:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        return {
            "entries": [],
            "total_count": 0,
            "log_file": str(log_file),
            "error": f"Failed to read log file: {str(e)}",
        }

    # Return most recent first
    entries.reverse()

    return {
        "entries": entries,
        "total_count": len(entries),
        "log_file": str(log_file),
    }


@mcp.tool()
def get_all_network_logs(
    log_path: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Dict:
    """
    Read all network traffic logs from the log file.

    Args:
        log_path: Optional custom path to log file. If not provided, uses vulnerable-app/attack_log.json
        working_dir: Optional working directory. If not provided, uses current directory.

    Returns:
        Dictionary with:
        - entries: List of all log entries (parsed JSON objects)
        - total_count: Total number of entries
        - log_file: Path to the log file that was read
    """
    if working_dir:
        base_dir = Path(working_dir).expanduser().resolve()
    else:
        base_dir = Path.cwd()

    if log_path:
        log_file = Path(log_path).expanduser().resolve()
    else:
        log_file = base_dir / "attack_log.json"

    if not log_file.exists():
        return {
            "entries": [],
            "total_count": 0,
            "log_file": str(log_file),
            "error": f"Log file not found: {log_file}",
        }

    entries = []
    try:
        with log_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        return {
            "entries": [],
            "total_count": 0,
            "log_file": str(log_file),
            "error": f"Failed to read log file: {str(e)}",
        }

    return {
        "entries": entries,
        "total_count": len(entries),
        "log_file": str(log_file),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
