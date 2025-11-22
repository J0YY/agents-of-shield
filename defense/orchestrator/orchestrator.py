from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from rich.console import Console

from .codebase_scanner import scan_repository
from .event_router import EventRouter
from .websocket_server import manager
from .websocket_server import router as ws_router

BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parent
STATE_DIR = BASE_DIR / "state"
REPORT_DIR = BASE_DIR / "reports"
EVENT_LOG = STATE_DIR / "attacker_events.jsonl"
RECON_REPORT_PATH = STATE_DIR / "recon_report.json"
VULN_APP_DIR = REPO_ROOT / "vulnerable-app"
ATTACK_LOG_PATH = VULN_APP_DIR / "attack_log.json"
MAX_TIMELINE = 200
DEFAULT_PORT = int(os.getenv("DEFENSE_ORCHESTRATOR_PORT", "7700"))

DEFAULT_ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://localhost:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
}

extra_origins = os.getenv("DEFENSE_DASHBOARD_ORIGINS", "")
for origin in (item.strip() for item in extra_origins.split(",") if item.strip()):
    DEFAULT_ALLOWED_ORIGINS.add(origin)

ALLOWED_ORIGINS = sorted(DEFAULT_ALLOWED_ORIGINS)

load_dotenv()

console = Console()
app = FastAPI(title="Agents of Shield – Defense Orchestrator", version="0.1.0")
app.include_router(ws_router)
# Wide-open CORS because dashboard requests are proxied via Vite during dev and may carry varying origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = EventRouter(state_dir=STATE_DIR, report_dir=REPORT_DIR)


class AttackEvent(BaseModel):
    step: int
    action: Dict[str, Any]
    status: int
    response_summary: str
    timestamp: str


def append_event_log(record: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    EVENT_LOG.touch(exist_ok=True)
    with EVENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_recent_events(limit: int = 100) -> List[Dict[str, Any]]:
    if not EVENT_LOG.exists():
        return []
    with EVENT_LOG.open("r", encoding="utf-8") as fh:
        lines = fh.readlines()
    events: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def load_attack_log(limit: int = 60) -> List[Dict[str, Any]]:
    if not ATTACK_LOG_PATH.exists():
        raise FileNotFoundError(
            f"attack_log.json not found at {ATTACK_LOG_PATH}")
    with ATTACK_LOG_PATH.open("r", encoding="utf-8", errors="ignore") as fh:
        lines = fh.readlines()
    entries: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    for idx, entry in enumerate(entries[-limit:], start=1):
        entry.setdefault("step", idx)
    return entries


def find_latest_report(extension: str) -> Path | None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = sorted(
        REPORT_DIR.glob(f"incident_report_*.{extension}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    safe = deepcopy(payload)
    reports = safe.get("reports", [])
    safe["reports"] = [str(path) for path in reports]
    return safe


def save_recon_report(report: Dict[str, Any]) -> None:
    """Save recon report to state directory."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with RECON_REPORT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)


def load_recon_report() -> Dict[str, Any] | None:
    """Load the latest recon report from state directory."""
    if not RECON_REPORT_PATH.exists():
        return None
    try:
        with RECON_REPORT_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, IOError):
        return None


@app.on_event("startup")
async def bootstrap() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    EVENT_LOG.touch(exist_ok=True)
    console.rule("[bold green]Defense Orchestrator Ready")
    console.print(
        f"[cyan]HTTP http://localhost:{DEFAULT_PORT} · WebSocket ws://localhost:{DEFAULT_PORT}/ws")


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/timeline")
async def timeline(limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    limit = max(1, min(limit, MAX_TIMELINE))
    return {"events": load_recent_events(limit)}


@app.get("/reports/latest")
async def download_latest_report(
    fmt: str = Query("json", pattern="^(json|html)$"),
) -> FileResponse:
    path = find_latest_report(fmt)
    if not path:
        raise HTTPException(status_code=404, detail="No reports generated yet")
    media_type = "text/html" if fmt == "html" else "application/json"
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.post("/attack-event")
async def receive_attack_event(event: AttackEvent):
    data = event.dict()
    append_event_log(data)

    console.log(
        f"[bold yellow]ATTACK[/] step {data['step']} "
        f"{data['action'].get('action_type', 'GET')} "
        f"{data['action'].get('target_url', 'unknown')} -> {data['status']}"
    )

    defense_payload = router.route(data)
    sanitized = sanitize_payload(defense_payload)
    await manager.broadcast(sanitized)

    return JSONResponse({"status": "ok", "defense_event": sanitized})


@app.get("/defense-scan")
async def defense_scan() -> JSONResponse:
    try:
        payload = scan_repository(REPO_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive logging
        console.log(f"[red]Scan failed: {exc}")
        raise HTTPException(
            status_code=500, detail="Codebase scan failed") from exc
    return JSONResponse(payload)


@app.get("/attack-log")
async def attack_log(limit: int = 60) -> Dict[str, List[Dict[str, Any]]]:
    limit = max(1, min(limit, 200))
    try:
        entries = load_attack_log(limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"entries": entries}


@app.post("/recon-investigate")
async def trigger_recon_investigation() -> JSONResponse:
    """Trigger recon agent investigation and store the report."""
    try:
        # Import here to avoid circular dependencies and handle missing dependencies gracefully
        import sys
        import traceback

        recon_agent_path = REPO_ROOT / "defense" / "recon_agent"
        if str(recon_agent_path) not in sys.path:
            sys.path.insert(0, str(recon_agent_path))

        # Verify MCP server file exists
        mcp_server_file = recon_agent_path / "log_reader_mcp_server.py"
        if not mcp_server_file.exists():
            raise FileNotFoundError(
                f"MCP server file not found: {mcp_server_file}")

        from recon_agent import ReconAgent

        agent = ReconAgent(working_dir=REPO_ROOT)
        # Use investigate_async since we're in an async context
        console.log("[bold cyan]RECON[/] Starting investigation...")
        console.log(f"[cyan]Working directory: {REPO_ROOT}")
        console.log(f"[cyan]Python executable: {sys.executable}")
        try:
            report = await agent.investigate_async(context={"trigger": "orchestrator_api"})
        except Exception as inner_exc:
            console.log(f"[red]Inner investigation error: {inner_exc}")
            console.log(f"[red]Inner traceback: {traceback.format_exc()}")
            raise

        save_recon_report(report)
        console.log(
            f"[bold cyan]RECON[/] Investigation completed: {report.get('attack_assessment', {}).get('attack_type', 'unknown')}")

        return JSONResponse({"status": "ok", "report": report})
    except ImportError as exc:
        error_msg = f"Recon agent import failed: {exc}"
        console.log(f"[red]{error_msg}[/]")
        console.log(f"[red]Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, detail=error_msg) from exc
    except Exception as exc:
        error_msg = f"Investigation failed: {exc}"
        console.log(f"[red]{error_msg}[/]")
        console.log(f"[red]Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, detail=error_msg) from exc


@app.get("/recon-report")
async def get_recon_report() -> Dict[str, Any]:
    """Get the latest recon report."""
    report = load_recon_report()
    if not report:
        raise HTTPException(
            status_code=404, detail="No recon report available yet")
    return report


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("orchestrator.orchestrator:app",
                host="0.0.0.0", port=DEFAULT_PORT, reload=True)
