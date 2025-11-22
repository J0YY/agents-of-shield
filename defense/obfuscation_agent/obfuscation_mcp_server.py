# obfuscation_mcp_server.py
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "JsObfuscatorServer",
    json_response=True,
)


# Directories we never traverse (they are copied as-is if needed,
# but in practice you usually won't even point source_dir at them).
EXCLUDED_DIRS = {
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "dist",
    "build",
}


def _is_js_file(path: Path) -> bool:
    """
    Return True if the file is a JavaScript source file we want to obfuscate.

    Keep this conservative: .js and .jsx only.
    If you want .mjs/.cjs later, you can add them explicitly once
    you know your obfuscator setup handles them correctly.
    """
    return path.suffix.lower() in {".js", ".jsx"}


@mcp.tool()
def obfuscate_directory(
    source_dir: str,
    output_dir: str,
    obfuscator_cmd: str = "javascript-obfuscator",
    extra_args: Optional[List[str]] = None,
) -> Dict[str, int]:
    """
    Recursively copy source_dir to output_dir, obfuscating JavaScript files.

    - Skips common dependency / VCS / build directories such as:
      node_modules, .git, dist, build, etc.
    - Files with extensions .js or .jsx are obfuscated using the
      `javascript-obfuscator` CLI.
    - All other files are copied as-is.
    - Requires `javascript-obfuscator` CLI to be installed and on PATH
      (e.g. `npm install -g javascript-obfuscator`).

    Returns statistics and resolved paths.
    """
    src_root = Path(source_dir).expanduser().resolve()
    dst_root = Path(output_dir).expanduser().resolve()

    if not src_root.exists() or not src_root.is_dir():
        raise ValueError(f"source_dir does not exist or is not a directory: {src_root}")

    dst_root.mkdir(parents=True, exist_ok=True)

    stats: Dict[str, int] = {
        "files_obfuscated": 0,
        "files_copied": 0,
        "dirs_created": 0,
    }

    for root, dirs, files in os.walk(src_root):
        root_path = Path(root)
        rel_root = root_path.relative_to(src_root)
        dst_root_dir = dst_root / rel_root

        # Filter out dirs we don't want to traverse (node_modules, .git, dist, build, etc.)
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

        if not dst_root_dir.exists():
            dst_root_dir.mkdir(parents=True, exist_ok=True)
            stats["dirs_created"] += 1

        for filename in files:
            src_path = root_path / filename
            dst_path = dst_root_dir / filename

            if _is_js_file(src_path):
                cmd: List[str] = [
                    obfuscator_cmd,
                    str(src_path),
                    "--output",
                    str(dst_path),
                ]
                if extra_args:
                    cmd.extend(extra_args)

                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                if proc.returncode != 0:
                    raise RuntimeError(
                        f"Obfuscator failed for {src_path} with exit code "
                        f"{proc.returncode}.\nSTDERR:\n{proc.stderr}"
                    )

                stats["files_obfuscated"] += 1
            else:
                shutil.copy2(src_path, dst_path)
                stats["files_copied"] += 1

    # Attach resolved paths as strings for the agent to report
    return {
        **stats,
        "source_dir": str(src_root),
        "output_dir": str(dst_root),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()