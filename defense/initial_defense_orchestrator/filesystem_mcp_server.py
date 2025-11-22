# filesystem_mcp_server.py
from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Optional, Sequence

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("FilesystemServer", json_response=True)


# ---------- Models ----------------------------------------------------------


class FileInfo(BaseModel):
    path: str = Field(..., description="Absolute path to the file or directory")
    is_dir: bool = Field(..., description="True if this is a directory")
    size: Optional[int] = Field(
        None, description="File size in bytes (None for directories)"
    )
    mtime: Optional[float] = Field(
        None, description="Last modification time as a POSIX timestamp"
    )


class ListDirectoryResult(BaseModel):
    directory: str = Field(..., description="Directory that was listed")
    entries: List[FileInfo] = Field(
        ..., description="Entries (files and directories) in this directory"
    )


class DirectoryTreeEntry(BaseModel):
    path: str = Field(..., description="Absolute path of this entry")
    is_dir: bool = Field(..., description="True if this is a directory")
    depth: int = Field(..., description="Depth relative to the root directory (0 = root)")


class DirectoryTreeResult(BaseModel):
    root: str = Field(..., description="Root directory for the tree")
    max_depth: int = Field(..., description="Maximum depth that was traversed")
    entries: List[DirectoryTreeEntry] = Field(
        ..., description="Flat list of entries in the directory tree"
    )


class SearchFilesResult(BaseModel):
    root: str = Field(..., description="Root directory that was searched")
    pattern: str = Field(..., description="Glob-style pattern that was applied")
    matches: List[str] = Field(..., description="Absolute paths of matching files")


class ReadTextFileResult(BaseModel):
    path: str = Field(..., description="Absolute path to the file that was read")
    content: str = Field(..., description="File contents (possibly truncated)")
    truncated: bool = Field(
        ...,
        description="True if the content was truncated due to the max_bytes limit",
    )
    bytes_read: int = Field(..., description="Number of bytes actually read")


class GetFileInfoResult(BaseModel):
    info: FileInfo = Field(..., description="Metadata for the given path")


# ---------- Helpers ---------------------------------------------------------


def _resolve_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    return p


def _path_matches_any(path: Path, patterns: Optional[Sequence[str]]) -> bool:
    if not patterns:
        return False
    s = str(path)
    return any(fnmatch(s, pat) for pat in patterns)


def _file_info_for_path(path: Path) -> FileInfo:
    try:
        st = path.stat()
    except FileNotFoundError:
        raise ValueError(f"Path does not exist: {path}") from None

    return FileInfo(
        path=str(path),
        is_dir=path.is_dir(),
        size=None if path.is_dir() else st.st_size,
        mtime=st.st_mtime,
    )


# ---------- Tools -----------------------------------------------------------


@mcp.tool()
def list_directory(path: str) -> ListDirectoryResult:
    """
    List the immediate contents of a directory (non-recursive).

    Returns file and directory entries with basic metadata.
    """
    dir_path = _resolve_path(path)
    if not dir_path.exists() or not dir_path.is_dir():
        raise ValueError(f"Path is not a directory: {dir_path}")

    entries: List[FileInfo] = []
    for entry in dir_path.iterdir():
        entries.append(_file_info_for_path(entry))

    return ListDirectoryResult(directory=str(dir_path), entries=entries)


@mcp.tool()
def directory_tree(
    path: str,
    max_depth: int = 3,
    exclude_patterns: Optional[List[str]] = None,
) -> DirectoryTreeResult:
    """
    Recursively walk a directory up to max_depth and return a flat tree listing.

    - path: Root directory to walk.
    - max_depth: Maximum depth relative to the root (0 = only root).
    - exclude_patterns: Optional list of glob-style patterns; any path that
      matches one of these patterns will be skipped.
    """
    root = _resolve_path(path)
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Path is not a directory: {root}")

    entries: List[DirectoryTreeEntry] = []

    root_depth = len(root.parts)
    for current_root, dirs, files in os.walk(root):
        current_path = Path(current_root)

        # Exclude directories matching patterns
        dirs[:] = [
            d for d in dirs
            if not _path_matches_any(current_path / d, exclude_patterns)
        ]

        rel_depth = len(current_path.parts) - root_depth
        if rel_depth > max_depth:
            # Stop descending further
            dirs[:] = []
            continue

        # Add current directory
        entries.append(
            DirectoryTreeEntry(
                path=str(current_path),
                is_dir=True,
                depth=rel_depth,
            )
        )

        # Add files at this level (if not excluded)
        for fname in files:
            fpath = current_path / fname
            if _path_matches_any(fpath, exclude_patterns):
                continue
            entries.append(
                DirectoryTreeEntry(
                    path=str(fpath),
                    is_dir=False,
                    depth=rel_depth + 1,
                )
            )

    return DirectoryTreeResult(
        root=str(root),
        max_depth=max_depth,
        entries=entries,
    )


@mcp.tool()
def search_files(
    root: str,
    pattern: str = "**/*",
    exclude_patterns: Optional[List[str]] = None,
    max_results: int = 512,
) -> SearchFilesResult:
    """
    Search for files under a root directory using a glob-style pattern.

    - root: Root directory to search.
    - pattern: Glob-style pattern relative to the root (e.g. '**/*.js').
    - exclude_patterns: Optional list of glob-style patterns for paths to skip.
    - max_results: Upper bound on the number of matches to return.
    """
    root_path = _resolve_path(root)
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"Root is not a directory: {root_path}")

    matches: List[str] = []

    # Use fnmatch on paths relative to root for consistent behavior
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        if _path_matches_any(path, exclude_patterns):
            continue
        rel = str(path.relative_to(root_path))
        if fnmatch(rel, pattern):
            matches.append(str(path))
            if len(matches) >= max_results:
                break

    return SearchFilesResult(root=str(root_path), pattern=pattern, matches=matches)


@mcp.tool()
def read_text_file(
    path: str,
    max_bytes: int = 65536,
    encoding: str = "utf-8",
) -> ReadTextFileResult:
    """
    Read up to max_bytes from a text file.

    - path: Path to the file.
    - max_bytes: Maximum number of bytes to read.
    - encoding: Text encoding to use when decoding bytes.
    """
    file_path = _resolve_path(path)
    if not file_path.exists() or not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    with open(file_path, "rb") as f:
        data = f.read(max_bytes + 1)

    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]

    text = data.decode(encoding, errors="replace")

    return ReadTextFileResult(
        path=str(file_path),
        content=text,
        truncated=truncated,
        bytes_read=len(data),
    )


@mcp.tool()
def get_file_info(path: str) -> GetFileInfoResult:
    """
    Return basic metadata for a file or directory.
    """
    p = _resolve_path(path)
    info = _file_info_for_path(p)
    return GetFileInfoResult(info=info)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()