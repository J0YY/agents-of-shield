#!/usr/bin/env python3
import atexit
import errno
import json
import os
import random
import stat
import string
import sys
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import websocket
from fuse import FUSE, FuseOSError, LoggingMixIn, Operations


def debug(msg: str) -> None:
    return
    print(f"[tarpit-debug] {msg}", flush=True)

# ==========================================
# Configuration: The Lures
# ==========================================

DIR_NAMES = [
    "backup", "old", "archive", "deploy", "staging", 
    "secrets", "conf", "private", "credentials", 
    "aws", "v1", "v2", "legacy", "temp", "root"
]

ENTICING_EXTENSIONS = [
    ".env",
    ".key",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".md",
    ".sh",
    ".cfg",
]

REALTIME_MODEL = os.getenv(
    "OPENAI_DEFENSE_MODEL", "gpt-4o-mini-realtime-preview-2024-12-17"
)
REALTIME_URL = "wss://api.openai.com/v1/realtime"


class RealtimeLLMClient:
    """
    Maintains a persistent connection to the OpenAI Realtime API.
    Requests are serialized behind a lock to keep the implementation simple.
    """

    def __init__(self, model: str):
        self.model = model
        self.api_key = os.getenv("OPENAI_API_KEY")
        self._lock = threading.Lock()
        self._ws: Optional[websocket.WebSocket] = None

        if not self.api_key:
            debug("OPENAI_API_KEY not set; realtime generation disabled. Using fallback content.")

        atexit.register(self.close)

    # Public API ---------------------------------------------------------
    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for realtime generation.")

        with self._lock:
            ws = self._ensure_connection()
            payload = {
                "type": "response.create",
                "response": {
                    "modalities": ["text"],
                    "instructions": f"{system_prompt}\n\n{user_prompt}",
                    "metadata": {"source": "fuse-tarpit"},
                },
            }
            debug(f"Realtime request queued ({len(system_prompt)} sys chars, {len(user_prompt)} user chars).")
            ws.send(json.dumps(payload))

            chunks: List[str] = []
            while True:
                try:
                    message = json.loads(ws.recv())
                except websocket.WebSocketConnectionClosedException as exc:
                    self._teardown_connection()
                    raise RuntimeError("Realtime connection closed unexpectedly.") from exc

                event_type = message.get("type")
                if event_type in ["response.text.delta", "response.output_text.delta"]:
                    chunks.append(message.get("delta", ""))
                elif event_type in ["response.done", "response.complete"]:
                    debug(f"Realtime event: {event_type}")
                    break
                elif event_type in ["response.output_text.done", "response.text.done"]:
                    debug(f"Realtime event: {event_type}")
                    # Ignore, completion event will follow
                    continue
                elif event_type == "error":
                    detail = message.get("error", {}).get("message", "Unknown realtime error")
                    raise RuntimeError(detail)
                else:
                    debug(f"Unknown realtime event: {event_type}")

            return "".join(chunks).strip()

    def close(self) -> None:
        with self._lock:
            self._teardown_connection()

    # Internal helpers ---------------------------------------------------
    def _ensure_connection(self) -> websocket.WebSocket:
        if self._ws and self._ws.connected:
            return self._ws
        headers = [
            f"Authorization: Bearer {self.api_key}",
            "OpenAI-Beta: realtime=v1",
        ]
        try:
            debug("Opening realtime websocket connection...")
            self._ws = websocket.create_connection(
                f"{REALTIME_URL}?model={self.model}",
                header=headers,
                suppress_origin=True,
            )
            debug("Realtime websocket connection established.")
        except Exception as exc:  # pragma: no cover - network errors are runtime concerns
            self._ws = None
            raise RuntimeError(f"Failed to connect to OpenAI Realtime API: {exc}") from exc
        return self._ws

    def _teardown_connection(self) -> None:
        if self._ws:
            try:
                self._ws.close()
                debug("Realtime websocket connection closed.")
            except Exception:
                pass
            self._ws = None


@dataclass
class DirectoryEntry:
    name: str
    is_dir: bool
    bait: str = "mundane"  # or "enticing"
    description: str = ""
    size_hint: int = 0


class LLMBaitGenerator:
    """
    Generates believable directory listings and file contents using OpenAI models.

    Falls back to deterministic pseudo-random content if the API call fails.
    """

    def __init__(self):
        self.realtime = RealtimeLLMClient(REALTIME_MODEL)
        self._dir_cache: Dict[str, List[DirectoryEntry]] = {}
        self._file_cache: Dict[str, str] = {}
        self._lock = threading.Lock()

    # --------- Public API -------------------------------------------------
    def get_directory_entries(self, path: str) -> List[DirectoryEntry]:
        normalized = self._normalize(path)
        debug ("waiting for lock")
        with self._lock:
            debug ("lock acquired")
            if normalized in self._dir_cache:
                debug(f"Cache hit for directory {normalized}")
                return self._dir_cache[normalized]

        debug(f"Cache miss for directory {normalized}, generating entries...")
        entries = self._generate_directory_entries(normalized)
        with self._lock:
            self._dir_cache[normalized] = entries
        return entries

    def get_entry(self, path: str) -> Optional[DirectoryEntry]:
        if path == "/":
            return DirectoryEntry(name="/", is_dir=True)
        parent, name = os.path.split(self._normalize(path).rstrip("/"))
        parent = parent or "/"
        name = name or "/"
        for entry in self.get_directory_entries(parent):
            if entry.name == name:
                return entry
        return None

    def get_file_content(self, path: str, entry: DirectoryEntry) -> str:
        normalized = self._normalize(path)
        with self._lock:
            if normalized in self._file_cache:
                debug(f"Cache hit for file {normalized}")
                return self._file_cache[normalized]

        debug(f"Cache miss for file {normalized}, generating content...")
        content = self._generate_file_content(normalized, entry)
        with self._lock:
            self._file_cache[normalized] = content
            entry.size_hint = len(content.encode("utf-8"))
        return content

    # --------- Generation helpers ----------------------------------------
    def _generate_directory_entries(self, path: str) -> List[DirectoryEntry]:
        if self.realtime.available():
            try:
                debug(f"Requesting realtime directory entries for {path}")
                entries = self._llm_directory_listing(path)
                if entries:
                    return entries
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[!] LLM directory generation failed for {path}: {exc}")
        debug(f"Falling back to deterministic directory entries for {path}")
        return self._fallback_directory_listing(path)

    def _generate_file_content(self, path: str, entry: DirectoryEntry) -> str:
        if self.realtime.available():
            try:
                debug(f"Requesting realtime file content for {path}")
                content = self._llm_file_body(path, entry)
                if content:
                    return content
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[!] LLM file generation failed for {path}: {exc}")
        debug(f"Falling back to deterministic file content for {path}")
        return self._fallback_file_body(path, entry)

    # --------- LLM-backed generators -------------------------------------
    def _llm_directory_listing(self, path: str) -> List[DirectoryEntry]:
        system_prompt = (
            "You curate realistic Linux filesystem trees for a production "
            "server that an attacker might explore. For the provided path, "
            "return JSON describing between 6 and 12 entries. Always include "
            "at least 3 directories and at least 3 files. Mix mundane names "
            "with enticing targets; attackers should second-guess whether the "
            "data is genuine. Use believable naming tied to the path context. "
            "Directories should hint at further depth so the tree feels infinite."
        )
        user_prompt = (
            f"Path: {path}\n"
            "Return ONLY JSON (no markdown). Format:\n"
            "[\n"
            '  {"name": "string", "type": "dir|file", '
            '"bait": "enticing|mundane", '
            '"description": "short purpose", '
            '"extension": ".txt (files only)"}\n'
            "]\n"
            "Rules:\n"
            "- Directory names cannot include file extensions.\n"
            "- File names must use common extensions (.env, .json, .yaml, "
            ".sql, .txt, .md, .cfg, .sh).\n"
            "- Not every file should be enticing. Provide believable mundane "
            "files (e.g., README.md, rotate-logs.sh) alongside high-value ones.\n"
            "- Descriptions help future content generation; keep them short.\n"
            "- Never repeat names already used for this path."
            "- File and directory names should be relative to the provided path. DO NOT try and generate files for subdirectories (e.g. if the path is /, generate var ONLY, not var/www)"
        )

        text = self.realtime.complete(system_prompt, user_prompt)
        data = self._parse_json_array(text)
        print(f"Realtime directory response for {path}: {data}")

        entries: List[DirectoryEntry] = []
        seen: set[str] = set()
        dir_count = 0
        file_count = 0

        for item in data:
            raw_name = str(item.get("name", "")).strip()
            if not raw_name:
                continue
            sanitized = self._sanitize_name(raw_name)
            if sanitized in (".", "..") or sanitized in seen:
                continue

            entry_type = item.get("type", "file")
            is_dir = entry_type == "dir"
            bait = item.get("bait", "mundane")
            description = item.get("description", "")

            if is_dir:
                dir_count += 1
            else:
                file_count += 1
                sanitized = self._ensure_extension(
                    sanitized, preferred=item.get("extension")
                )

            entry = DirectoryEntry(
                name=sanitized,
                is_dir=is_dir,
                bait=bait if bait in {"mundane", "enticing"} else "mundane",
                description=description,
                size_hint=self._estimate_size(sanitized, is_dir),
            )
            entries.append(entry)
            seen.add(sanitized)

        if dir_count < 3 or file_count < 3:
            entries.extend(self._fallback_directory_listing(path))
            return self._dedupe(entries)

        return entries

    def _llm_file_body(self, path: str, entry: DirectoryEntry) -> str:
        extension = os.path.splitext(entry.name)[1] or ".txt"
        tone = (
            "urgent memo referencing security incidents"
            if entry.bait == "enticing"
            else "mundane operational note"
        )
        system_prompt = (
            "You write convincing text or config files for a security honeypot. "
            "Make the content plausible for the filename. Keep it short (<600 words) "
            "and never include markdown code fences."
        )
        user_prompt = (
            f"File path: {path}\n"
            f"Extension: {extension}\n"
            f"Persona: {tone}\n"
            f"Description/Context: {entry.description or 'not provided'}\n"
            "Produce the full file content now."
        )
        result = self.realtime.complete(system_prompt, user_prompt)
        debug(f"Realtime file content generated for {path} ({len(result)} chars)")
        return result

    # --------- Fallback generators ---------------------------------------
    def _fallback_directory_listing(self, path: str) -> List[DirectoryEntry]:
        random.seed(path)
        debug(f"Generating fallback directory listing for {path}")
        entries: List[DirectoryEntry] = []
        used: set[str] = set()

        dir_targets = random.randint(3, 4)
        file_targets = random.randint(3, 5)

        while len(entries) < dir_targets + file_targets:
            is_dir = len([e for e in entries if e.is_dir]) < dir_targets
            if is_dir:
                name = f"{random.choice(DIR_NAMES)}_{random.randint(2018, 2029)}"
            else:
                stem = random.choice(
                    ["access", "deploy", "archive", "incident", "budget", "diag"]
                )
                ext = random.choice(ENTICING_EXTENSIONS)
                name = f"{stem}_{random.randint(1,9999)}{ext}"
            if name in used:
                continue
            used.add(name)
            entries.append(
                DirectoryEntry(
                    name=name,
                    is_dir=is_dir,
                    bait="enticing" if not is_dir and random.random() > 0.5 else "mundane",
                    description="fallback generated entry",
                    size_hint=self._estimate_size(name, is_dir),
                )
            )

        return entries

    def _fallback_file_body(self, path: str, entry: DirectoryEntry) -> str:
        random.seed(path)
        ext = os.path.splitext(entry.name)[1]
        if ext in {".json", ".yaml", ".yml"}:
            content = json.dumps(
                {
                    "service": os.path.basename(path).replace(ext, ""),
                    "host": f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,250)}",
                    "token": "sk_" + "".join(random.choices(string.ascii_letters + string.digits, k=32)),
                    "note": "auto-generated fallback secret",
                },
                indent=2,
            )
        elif ext in {".txt", ".md"}:
            content = (
                f"{entry.description or 'Internal note'}\n"
                "Audit trail:\n"
                f"- {time.strftime('%Y-%m-%d')} Placeholder entry generated.\n"
                "- Credentials moved to another directory.\n"
            )
        elif ext in {".env"}:
            content = (
                "DB_HOST=prod-db.internal\n"
                "DB_USER=svc_app\n"
                f"DB_PASS=fallBack{random.randint(1000,9999)}\n"
                "API_KEY=sk-auto-generated\n"
            )
        else:
            # Generic binary-ish filler
            content = "".join(random.choices(string.printable, k=500))
        debug(f"Generated fallback file content for {path} ({len(content)} chars)")
        return content

    @staticmethod
    def _estimate_size(name: str, is_dir: bool) -> int:
        if is_dir:
            return 0
        ext = os.path.splitext(name)[1]
        if ext in {".json", ".yaml", ".yml", ".cfg"}:
            return random.randint(800, 3000)
        if ext in {".txt", ".md"}:
            return random.randint(400, 2000)
        if ext in {".env", ".key"}:
            return random.randint(200, 1200)
        if ext in {".sql"}:
            return random.randint(2000, 12000)
        return random.randint(256, 4096)

    # --------- Utilities --------------------------------------------------
    @staticmethod
    def _normalize(path: str) -> str:
        if not path:
            return "/"
        if not path.startswith("/"):
            path = "/" + path
        return os.path.normpath(path)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        cleaned = "".join(c for c in name if c.isalnum() or c in {"-", "_", ".", " "})
        cleaned = cleaned.strip().replace(" ", "_")
        cleaned = cleaned.strip("_") or "misc"
        if cleaned in {".", ".."}:
            cleaned = f"{cleaned.strip('.') or 'node'}_{random.randint(100,999)}"
        return cleaned

    @staticmethod
    def _ensure_extension(name: str, preferred: Optional[str]) -> str:
        current_ext = os.path.splitext(name)[1]
        target = preferred if preferred in ENTICING_EXTENSIONS else current_ext
        if target not in ENTICING_EXTENSIONS:
            target = random.choice(ENTICING_EXTENSIONS)
        if not name.endswith(target):
            base = os.path.splitext(name)[0] or "file"
            return f"{base}{target}"
        return name

    @staticmethod
    def _parse_json_array(text: str) -> List[Dict]:
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "entries" in data:
                return data["entries"]  # type: ignore[return-value]
            if isinstance(data, list):
                return data  # type: ignore[return-value]
        except json.JSONDecodeError:
            pass
        return []

    @staticmethod
    def _dedupe(entries: List[DirectoryEntry]) -> List[DirectoryEntry]:
        seen: set[str] = set()
        unique: List[DirectoryEntry] = []
        for entry in entries:
            if entry.name in seen:
                continue
            seen.add(entry.name)
            unique.append(entry)
        return unique

class RabbitHole(LoggingMixIn, Operations):
    """
    An infinite, read-only filesystem designed to waste time.
    """

    def __init__(self):
        self.start_time = time.time() - 100000
        self.generator = LLMBaitGenerator()

    def getattr(self, path, fh=None):
        debug(f"getattr called for {path}")
        st = self._base_stat()
        debug(f"base stat finished")

        if path == "/":
            st["st_mode"] = stat.S_IFDIR | 0o755
            st["st_nlink"] = 2
            return st

        debug(f"getting entry for {path}")
        entry = self.generator.get_entry(path)
        if entry is None:
            raise FuseOSError(errno.ENOENT)

        if entry.is_dir:
            st["st_mode"] = stat.S_IFDIR | 0o755
            st["st_nlink"] = 2
        else:
            st["st_mode"] = stat.S_IFREG | 0o444
            st["st_nlink"] = 1
            size = entry.size_hint
            if not size:
                size = self.generator._estimate_size(entry.name, False)
            st["st_size"] = size
        debug(f"getattr finished for {path}")
        return st

    def readdir(self, path, fh):
        debug(f"readdir called for {path}")
        entries = ["." , ".."]
        directory_entries = self.generator.get_directory_entries(path)
        entries.extend(entry.name for entry in directory_entries)
        debug(f"readdir returning {len(entries)} entries for {path}")
        return entries

    def read(self, path, length, offset, fh):
        debug(f"read called for {path} (length={length}, offset={offset})")
        entry = self.generator.get_entry(path)
        if entry is None:
            raise FuseOSError(errno.ENOENT)
        if entry.is_dir:
            raise FuseOSError(errno.EISDIR)

        content = self.generator.get_file_content(path, entry)
        data = content.encode("utf-8")
        debug(f"read returning {len(data[offset:offset + length])} bytes for {path}")
        return data[offset : offset + length]

    def write(self, path, buf, offset, fh):
        raise FuseOSError(errno.EROFS)

    def _base_stat(self) -> Dict[str, float]:
        return {
            "st_atime": self.start_time + random.randint(0, 10000),
            "st_mtime": self.start_time + random.randint(0, 10000),
            "st_ctime": self.start_time + random.randint(0, 10000),
            "st_uid": 1000,
            "st_gid": 1000,
        }


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: %s <mountpoint>' % sys.argv[0])
        exit(1)

    # foreground=True is helpful for debugging
    # allow_other=True allows the Cowrie user/Docker container to see it
    fuse = FUSE(RabbitHole(), sys.argv[1], foreground=True, allow_other=True)