from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

ROUTE_REGEX = re.compile(r"app\.(get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
HONEYPOT_PATHS = {
    "/admin-v2": "Decoy admin console returning feature flags and fake token",
    "/backup-db": "Synthetic backup job metadata",
    "/config-prod": "Pretend production config payload with fake secrets",
}

ROUTE_HINTS: Dict[str, Dict[str, str]] = {
    "/signup": {"risk": "high", "note": "Blind SQL insert built via string concatenation"},
    "/login": {"risk": "high", "note": "Credential check uses interpolated SQL and leaks errors"},
    "/dashboard": {"risk": "medium", "note": "User lookup trusts query param ?user without auth"},
    "/admin": {"risk": "critical", "note": "Lists all users and reveals DB path without auth"},
    "/download-db": {"risk": "critical", "note": "Arbitrary file download via ?file, enables LFI/RFI"},
    "/debug": {"risk": "critical", "note": "Returns env secrets, sample accounts, and headers"},
    "/env": {"risk": "high", "note": "Full process environment leakage"},
    "/source": {"risk": "medium", "note": "Lets attackers read arbitrary source files"},
}

SUGGESTION_LIBRARY = [
    {
        "id": "phantom-admin-console",
        "name": "Phantom Admin Console",
        "short": "Phantom Admin",
        "description": "Mirror /admin with telemetry beacons to trap credential stuffing.",
        "vector": "Web Portal",
        "emoji": "🛡️",
        "service": "cowrie",
        "auto_select": True,
        "recommended": True,
        "triggers": {"/admin", "/dashboard"},
        "reasons": ["Admin surfaces leak raw user tables with no session controls"],
    },
    {
        "id": "s3-backup-tripwire",
        "name": "S3 Backup Tripwire",
        "short": "Backup Trap",
        "description": "Fake /download-db backup bundle wired to alert on exfil attempts.",
        "vector": "Data Exfil",
        "emoji": "🗄️",
        "service": "dionaea",
        "auto_select": True,
        "recommended": True,
        "triggers": {"/download-db", "/backup-db"},
        "reasons": ["Backup endpoints expose filesystem paths and database dumps"],
    },
    {
        "id": "config-registry-decoy",
        "name": "Config Registry Mirage",
        "short": "Config Mirage",
        "description": "Synthetic /config-prod payload with honey API keys.",
        "vector": "Secrets",
        "emoji": "🔐",
        "service": "elasticpot",
        "auto_select": False,
        "recommended": True,
        "triggers": {"/config-prod", "/debug", "/env"},
        "reasons": ["Config and debug endpoints leak environment secrets"],
    },
    {
        "id": "source-map-snare",
        "name": "Source Map Snare",
        "short": "Source Snare",
        "description": "Serve enticing source files instrumented for exfil alerts.",
        "vector": "Recon",
        "emoji": "🧬",
        "service": "heralding",
        "auto_select": False,
        "recommended": False,
        "triggers": {"/source"},
        "reasons": ["Source endpoint lets attackers read arbitrary files post-auth"],
    },
]

SERVICE_ACCENTS = ["#ffb8d2", "#82f5ff", "#e0b1ff", "#9d8bff", "#ffd29d"]


class CodebaseScanner:
    """Lightweight scanner that inspects the vulnerable-app to feed the dashboard."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.target_dir = repo_root / "vulnerable-app"
        self.logs: List[Dict[str, str]] = []
        self.checkpoints: List[Dict[str, str]] = []

    def _log(self, message: str, level: str = "info") -> None:
        self.logs.append(
            {
                "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
                "level": level,
                "message": message,
            }
        )

    def _checkpoint(self, title: str, detail: str, summary: str) -> None:
        self.checkpoints.append(
            {
                "id": f"step-{len(self.checkpoints)+1}",
                "title": title,
                "detail": detail,
                "summary": summary,
            }
        )

    def _read_manifest(self) -> Dict:
        manifest_path = self.target_dir / "package.json"
        if not manifest_path.exists():
            raise FileNotFoundError("package.json not found inside vulnerable-app")
        self._log(f"Parsing manifest {manifest_path.relative_to(self.repo_root)}")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        deps = sorted((data.get("dependencies") or {}).keys())
        dev_deps = sorted((data.get("devDependencies") or {}).keys())
        self._checkpoint(
            "package.json",
            f"{len(deps)} runtime deps · {len(dev_deps)} dev deps fingerprinted",
            f"{', '.join(deps[:3])}..." if deps else "No deps listed",
        )
        if "express" not in deps:
            self._log("Express dependency missing; server may not boot", level="warn")
        return data

    def _parse_routes(self, app_js: Path) -> List[Dict[str, str]]:
        if not app_js.exists():
            raise FileNotFoundError("app.js missing inside vulnerable-app")
        self._log(f"Scanning Express routes in {app_js.relative_to(self.repo_root)}")
        source = app_js.read_text(encoding="utf-8")
        matches = ROUTE_REGEX.findall(source)
        routes: List[Dict[str, str]] = []
        seen: set[Tuple[str, str]] = set()
        for method, path in matches:
            key = (method.upper(), path)
            if key in seen:
                continue
            seen.add(key)
            route_info = {
                "method": method.upper(),
                "path": path,
                "honeypot": path in HONEYPOT_PATHS,
                "description": ROUTE_HINTS.get(path, {}).get("note", ""),
                "risk": ROUTE_HINTS.get(path, {}).get("risk", "info"),
            }
            routes.append(route_info)

        honey = [route for route in routes if route["honeypot"]]
        self._checkpoint(
            "Express routes",
            f"Indexed {len(routes)} routes · {len(honey)} honeypots",
            "/".join(route["path"].lstrip("/") for route in routes[:3]) + ("..." if len(routes) > 3 else ""),
        )

        if "unsafeInsert" in source or "unsafeQuery" in source or "INSERT INTO users" in source:
            self._log("Detected raw SQL strings in signup/login handlers", level="warn")
        if "?file" in source and "/download-db" in source:
            self._log("Download endpoint trusts ?file parameter (LFI risk)", level="warn")
        if "process.env" in source:
            self._log("Process env leaked via /debug or /config-prod", level="warn")

        return routes

    def _tail_attack_log(self) -> List[Dict[str, str]]:
        log_path = self.target_dir / "attack_log.json"
        if not log_path.exists():
            self._log("No attack_log.json found; logging middleware may be disabled", level="warn")
            return []
        lines = log_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        tail = lines[-20:]
        parsed: List[Dict[str, str]] = []
        for line in tail:
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._log(f"Collected {len(parsed)} recent entries from attack_log.json")
        self._checkpoint(
            "Attack telemetry",
            f"Tail sampled {len(parsed)} log entries",
            f"{log_path.stat().st_size // 1024} KB log buffer",
        )
        return parsed

    def _gather_services(self, routes: List[Dict[str, str]], manifest: Dict) -> List[Dict[str, str]]:
        services: List[Dict[str, str]] = []
        accents = iter(SERVICE_ACCENTS)

        def next_accent() -> str:
            return next(accents, "#82f5ff")

        app_name = manifest.get("name") or "vulnerable-app"
        app_version = manifest.get("version")
        server_label = f"{app_name} Express Server"
        if app_version:
            server_label += f" v{app_version}"

        route_paths = {route["path"] for route in routes}
        user_db = self.target_dir / "users.db"
        attack_log = self.target_dir / "attack_log.json"

        services.append(
            {
                "id": "express-core",
                "name": server_label,
                "role": "web",
                "status": "Online",
                "detail": f"{len(routes)} routes defined in app.js",
                "issues": [
                    "Unchecked query params on /dashboard and /download-db",
                    "No auth middleware guarding admin surfaces",
                ],
                "accent": next_accent(),
                "recommendations": ["phantom-admin-console"] if "/admin" in route_paths else [],
            }
        )

        if user_db.exists():
            size_kb = max(user_db.stat().st_size // 1024, 1)
            services.append(
                {
                    "id": "sqlite-users",
                    "name": "SQLite users.db",
                    "role": "database",
                    "status": "Mounted",
                    "detail": f"{size_kb} KB · table users(name, email, phone, password, credit_card_last4)",
                    "issues": [
                        "Signup/login handlers use raw SQL strings (SQLi likely).",
                        "Database downloadable via /download-db without auth.",
                    ],
                    "accent": next_accent(),
                    "recommendations": ["s3-backup-tripwire"],
                }
            )
        else:
            self._log("users.db missing; database bootstrap may have failed", level="warn")

        if attack_log.exists():
            services.append(
                {
                    "id": "attack-log",
                    "name": "Attack Log Stream",
                    "role": "telemetry",
                    "status": "Recording",
                    "detail": f"attack_log.json tailing {attack_log.stat().st_size // 1024} KB",
                    "issues": ["Log file stored alongside app; consider remote shipping for tamper safety."],
                    "accent": next_accent(),
                    "recommendations": [],
                }
            )

        if route_paths & {"/debug", "/env", "/config-prod"}:
            services.append(
                {
                    "id": "secrets-surface",
                    "name": "Secrets Surfaces",
                    "role": "config",
                    "status": "Exposed",
                    "detail": "Debug/config endpoints leak environment keys and faux secrets.",
                    "issues": [
                        "Config endpoints emit real env vars.",
                        "No API auth or IP restrictions enforced.",
                    ],
                    "accent": next_accent(),
                    "recommendations": ["config-registry-decoy"],
                }
            )

        return services

    def _build_suggestions(self, routes: List[Dict[str, str]]) -> List[Dict[str, str]]:
        observed_paths = {route["path"] for route in routes}
        picks: List[Dict[str, str]] = []
        for suggestion in SUGGESTION_LIBRARY:
            if suggestion["triggers"] & observed_paths:
                entry = dict(suggestion)
                entry["auto_select"] = suggestion.get("auto_select", False)
                entry["recommended"] = suggestion.get("recommended", False)
                entry["reasons"] = list(suggestion.get("reasons", []))
                entry["triggers"] = sorted(suggestion.get("triggers", []))
                picks.append(entry)
        return picks

    def run(self) -> Dict[str, object]:
        start = time.perf_counter()
        if not self.target_dir.exists():
            raise FileNotFoundError(f"Expected vulnerable-app directory at {self.target_dir}")
        self._log(f"Repository root: {self.repo_root}")
        self._log(f"Targeting {self.target_dir.relative_to(self.repo_root)} for deep scan")

        manifest = self._read_manifest()
        routes = self._parse_routes(self.target_dir / "app.js")
        telemetry_tail = self._tail_attack_log()
        services = self._gather_services(routes, manifest)
        suggestions = self._build_suggestions(routes)
        existing_decoys = [
            {
                "path": route["path"],
                "detail": HONEYPOT_PATHS.get(route["path"], "Synthetic endpoint"),
            }
            for route in routes
            if route["honeypot"]
        ]

        self._checkpoint(
            "Secrets & config",
            "Inspected debug/env endpoints for leaked keys",
            f"{len(existing_decoys)} decoys + {len(suggestions)} suggested traps",
        )

        duration_ms = int((time.perf_counter() - start) * 1000)
        self._log(f"Scan complete in {duration_ms}ms", level="success")

        return {
            "scan_id": str(uuid.uuid4()),
            "target": str(self.target_dir.relative_to(self.repo_root)),
            "started_at": self.logs[0]["timestamp"] if self.logs else datetime.utcnow().isoformat(),
            "duration_ms": duration_ms,
            "checkpoints": self.checkpoints,
            "services": services,
            "routes": routes,
            "existing_decoys": existing_decoys,
            "suggestions": suggestions,
            "logs": self.logs,
            "telemetry_tail": telemetry_tail,
        }


def scan_repository(repo_root: Path) -> Dict[str, object]:
    scanner = CodebaseScanner(repo_root)
    return scanner.run()

