# obfuscation_mcp_server.py
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

mcp = FastMCP(
    "JsObfuscatorServer",
    json_response=True,
)

# Directories we never traverse when processing source trees
# (we copy them verbatim instead of obfuscating/minifying).
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
    """
    return path.suffix.lower() in {".js", ".jsx"}


def _is_html_file(path: Path) -> bool:
    return path.suffix.lower() in {".html", ".htm", ".ejs"}


def _is_css_file(path: Path) -> bool:
    return path.suffix.lower() == ".css"


def _ensure_dir(path: Path, stats: Dict[str, int]) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        stats["dirs_created"] += 1


def _copy_tree_verbatim(src: Path, dst: Path, stats: Dict[str, int]) -> None:
    """
    Recursively copy src -> dst, without overwriting existing files,
    and without any obfuscation/minification.
    """
    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        rel_root = root_path.relative_to(src)
        dst_root_dir = dst / rel_root

        _ensure_dir(dst_root_dir, stats)

        for filename in files:
            src_path = root_path / filename
            dst_path = dst_root_dir / filename
            if not dst_path.exists():
                shutil.copy2(src_path, dst_path)
                stats["files_copied"] += 1


def _copy_excluded_subdirs(
    root_path: Path,
    dst_root_dir: Path,
    dirs: List[str],
    stats: Dict[str, int],
) -> None:
    """
    For any immediate child directory under root_path whose name is in
    EXCLUDED_DIRS, copy it verbatim to dst_root_dir and prevent os.walk
    from traversing into it.
    """
    excluded = [d for d in dirs if d in EXCLUDED_DIRS]

    for dirname in excluded:
        src_excluded = root_path / dirname
        dst_excluded = dst_root_dir / dirname
        _copy_tree_verbatim(src_excluded, dst_excluded, stats)

    # Remove excluded dirs so os.walk does not traverse into them
    dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]


# ---------- Result models --------------------------------------------------


class ObfuscateDirectoryResult(BaseModel):
    files_obfuscated: int
    files_copied: int
    dirs_created: int
    source_dir: str
    output_dir: str


class MinifyHtmlDirectoryResult(BaseModel):
    files_minified: int
    files_copied: int
    dirs_created: int
    source_dir: str
    output_dir: str


class MinifyCssDirectoryResult(BaseModel):
    files_minified: int
    files_copied: int
    dirs_created: int
    source_dir: str
    output_dir: str


# ---------- Tools ----------------------------------------------------------


@mcp.tool()
def obfuscate_directory(
    source_dir: str,
    output_dir: str,
    obfuscator_cmd: str = "javascript-obfuscator",
    extra_args: Optional[List[str]] = None,
) -> ObfuscateDirectoryResult:
    """
    Recursively copy source_dir to output_dir, obfuscating JavaScript files.

    - Does not traverse into common dependency / VCS / build directories
      (EXCLUDED_DIRS) for obfuscation, but copies those directories verbatim
      to output_dir without modification.
    - Files with extensions .js or .jsx (outside EXCLUDED_DIRS) are obfuscated
      using the `javascript-obfuscator` CLI.
    - All other files are copied as-is, but will not overwrite existing files
      in output_dir. This allows other tools (HTML/CSS minifiers) to safely
      run over the same output_dir without clobbering each other's results.
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

        _ensure_dir(dst_root_dir, stats)
        _copy_excluded_subdirs(root_path, dst_root_dir, dirs, stats)

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
                # Copy non-JS files only if they don't already exist in output_dir
                if not dst_path.exists():
                    shutil.copy2(src_path, dst_path)
                    stats["files_copied"] += 1

    return ObfuscateDirectoryResult(
        files_obfuscated=stats["files_obfuscated"],
        files_copied=stats["files_copied"],
        dirs_created=stats["dirs_created"],
        source_dir=str(src_root),
        output_dir=str(dst_root),
    )


@mcp.tool()
def minify_html_directory(
    source_dir: str,
    output_dir: str,
    html_minifier_cmd: str = "html-minifier-terser",
    extra_args: Optional[List[str]] = None,
) -> MinifyHtmlDirectoryResult:
    """
    Recursively copy source_dir to output_dir, minifying .html/.htm files.

    - Does not traverse into common dependency / VCS / build directories
      (EXCLUDED_DIRS) for minification, but copies those directories verbatim
      to output_dir without modification.
    - Files with .html/.htm extensions (outside EXCLUDED_DIRS) are minified
      using the `html-minifier-terser` CLI.
      Default options:
        --collapse-whitespace
        --remove-comments
        --remove-optional-tags
        --minify-js true
        --minify-css true
      These can be augmented via extra_args.
    - All other files are copied as-is, but will not overwrite existing files
      in output_dir.

    Requires `html-minifier-terser` CLI on PATH
    (e.g. `npm install -g html-minifier-terser`).

    Returns statistics and resolved paths.
    """
    src_root = Path(source_dir).expanduser().resolve()
    dst_root = Path(output_dir).expanduser().resolve()

    if not src_root.exists() or not src_root.is_dir():
        raise ValueError(f"source_dir does not exist or is not a directory: {src_root}")

    dst_root.mkdir(parents=True, exist_ok=True)

    stats: Dict[str, int] = {
        "files_minified": 0,
        "files_copied": 0,
        "dirs_created": 0,
    }

    # Default options (can be extended by extra_args)
    args: List[str] = [
        "--collapse-whitespace",
        "--remove-comments",
        "--remove-optional-tags",
        "--minify-js",
        "true",
        "--minify-css",
        "true",
    ]
    if extra_args:
        args.extend(extra_args)

    for root, dirs, files in os.walk(src_root):
        root_path = Path(root)
        rel_root = root_path.relative_to(src_root)
        dst_root_dir = dst_root / rel_root

        _ensure_dir(dst_root_dir, stats)
        _copy_excluded_subdirs(root_path, dst_root_dir, dirs, stats)

        for filename in files:
            src_path = root_path / filename
            dst_path = dst_root_dir / filename

            if _is_html_file(src_path):
                cmd: List[str] = [
                    html_minifier_cmd,
                    str(src_path),
                    "-o",
                    str(dst_path),
                ]
                cmd.extend(args)

                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                if proc.returncode != 0:
                    raise RuntimeError(
                        f"HTML minifier failed for {src_path} with exit code "
                        f"{proc.returncode}.\nSTDERR:\n{proc.stderr}"
                    )

                stats["files_minified"] += 1
            else:
                # Copy non-HTML files only if they don't already exist in output_dir
                if not dst_path.exists():
                    shutil.copy2(src_path, dst_path)
                    stats["files_copied"] += 1

    return MinifyHtmlDirectoryResult(
        files_minified=stats["files_minified"],
        files_copied=stats["files_copied"],
        dirs_created=stats["dirs_created"],
        source_dir=str(src_root),
        output_dir=str(dst_root),
    )


@mcp.tool()
def minify_css_directory(
    source_dir: str,
    output_dir: str,
    css_minifier_cmd: str = "csso",
    extra_args: Optional[List[str]] = None,
) -> MinifyCssDirectoryResult:
    """
    Recursively copy source_dir to output_dir, minifying .css files.

    - Does not traverse into common dependency / VCS / build directories
      (EXCLUDED_DIRS) for minification, but copies those directories verbatim
      to output_dir without modification.
    - Files with .css extension (outside EXCLUDED_DIRS) are minified using
      the `csso` CLI (installed via `csso-cli`).
      Typical usage is `csso input.css -o output.css`.
    - All other files are copied as-is, but will not overwrite existing files
      in output_dir.

    Requires `csso` CLI on PATH
    (e.g. `npm install -g csso-cli`).

    Returns statistics and resolved paths.
    """
    src_root = Path(source_dir).expanduser().resolve()
    dst_root = Path(output_dir).expanduser().resolve()

    if not src_root.exists() or not src_root.is_dir():
        raise ValueError(f"source_dir does not exist or is not a directory: {src_root}")

    dst_root.mkdir(parents=True, exist_ok=True)

    stats: Dict[str, int] = {
        "files_minified": 0,
        "files_copied": 0,
        "dirs_created": 0,
    }

    args: List[str] = []
    if extra_args:
        args.extend(extra_args)

    for root, dirs, files in os.walk(src_root):
        root_path = Path(root)
        rel_root = root_path.relative_to(src_root)
        dst_root_dir = dst_root / rel_root

        _ensure_dir(dst_root_dir, stats)
        _copy_excluded_subdirs(root_path, dst_root_dir, dirs, stats)

        for filename in files:
            src_path = root_path / filename
            dst_path = dst_root_dir / filename

            if _is_css_file(src_path):
                cmd: List[str] = [
                    css_minifier_cmd,
                    str(src_path),
                    "-o",
                    str(dst_path),
                ]
                cmd.extend(args)

                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                if proc.returncode != 0:
                    raise RuntimeError(
                        f"CSS minifier failed for {src_path} with exit code "
                        f"{proc.returncode}.\nSTDERR:\n{proc.stderr}"
                    )

                stats["files_minified"] += 1
            else:
                # Copy non-CSS files only if they don't already exist in output_dir
                if not dst_path.exists():
                    shutil.copy2(src_path, dst_path)
                    stats["files_copied"] += 1

    return MinifyCssDirectoryResult(
        files_minified=stats["files_minified"],
        files_copied=stats["files_copied"],
        dirs_created=stats["dirs_created"],
        source_dir=str(src_root),
        output_dir=str(dst_root),
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()