from __future__ import annotations

import json
from copy import deepcopy
import asyncio
import os
from pathlib import Path
import sys
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from rich.console import Console

from .event_router import EventRouter
from .websocket_server import manager, router as ws_router
from .codebase_scanner import scan_repository
from .telemetry import ActiveDefenseTracker, SignalHeatmapTracker
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parent
STATE_DIR = BASE_DIR / "state"
REPORT_DIR = BASE_DIR / "reports"
EVENT_LOG = STATE_DIR / "attacker_events.jsonl"
DEFENSE_EVENT_LOG = STATE_DIR / "defense_events.jsonl"
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

RECON_DIR = REPO_ROOT / "recon_agent"
if str(RECON_DIR) not in sys.path:
    sys.path.append(str(RECON_DIR))

from recon_agent import recon_agent  # pylint: disable=wrong-import-position

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
ops_tracker = ActiveDefenseTracker()
signal_tracker = SignalHeatmapTracker()


class AttackEvent(BaseModel):
    step: int
    action: Dict[str, Any]
    status: int
    response_summary: str
    timestamp: str


class HoneypotArmRequest(BaseModel):
    reason: str | None = None
    delta: int | None = None
    source: str | None = None
    services: List[str] | None = None


class ReconRunRequest(BaseModel):
    context: Dict[str, Any] | None = None


def append_event_log(record: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    EVENT_LOG.touch(exist_ok=True)
    with EVENT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_defense_event(record: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEFENSE_EVENT_LOG.touch(exist_ok=True)
    with DEFENSE_EVENT_LOG.open("a", encoding="utf-8") as fh:
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


def load_defense_events(limit: int = 100) -> List[Dict[str, Any]]:
    if not DEFENSE_EVENT_LOG.exists():
        return []
    with DEFENSE_EVENT_LOG.open("r", encoding="utf-8") as fh:
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
        raise FileNotFoundError(f"attack_log.json not found at {ATTACK_LOG_PATH}")
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


@app.on_event("startup")
async def bootstrap() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    EVENT_LOG.touch(exist_ok=True)
    DEFENSE_EVENT_LOG.touch(exist_ok=True)
    console.rule("[bold green]Defense Orchestrator Ready")
    console.print(f"[cyan]HTTP http://localhost:{DEFAULT_PORT} · WebSocket ws://localhost:{DEFAULT_PORT}/ws")


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
    defense_payload["operations"] = ops_tracker.ingest(defense_payload)
    defense_payload["signals"] = signal_tracker.ingest(defense_payload)
    sanitized = sanitize_payload(defense_payload)
    append_defense_event(sanitized)
    await manager.broadcast(sanitized)

    return JSONResponse({"status": "ok", "defense_event": sanitized})


@app.post("/honeypots/arm")
async def arm_honeypots(payload: HoneypotArmRequest):
    """Allow the dashboard (or other callers) to proactively arm honeypots."""

    source = payload.source or "dashboard"
    report = router.honeypot_manager.arm(
        reason=payload.reason,
        delta=payload.delta,
        source=source,
        services=payload.services,
    )
    console.log(
        f"[bold cyan]HONEYPOTS[/] armed via {source} "
        f"(reason={payload.reason or 'unspecified'}, Δ={payload.delta or 0}, "
        f"services={payload.services or 'all'})"
    )
    return JSONResponse({"status": "armed", **report})


@app.post("/recon/run")
async def run_recon(request: ReconRunRequest):
    """Trigger the recon agent and return its report."""

    def _execute():
        agent = recon_agent.ReconAgent(working_dir=REPO_ROOT)
        return agent.investigate(context=request.context or {"trigger": "dashboard"})

    loop = asyncio.get_running_loop()
    report = await loop.run_in_executor(None, _execute)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    recon_path = REPORT_DIR / "latest_recon_report.json"
    recon_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return JSONResponse(report)


@app.get("/honeypots")
async def honeypot_inventory() -> JSONResponse:
    """Expose the current honeypot inventory for the dashboard."""

    payload = router.honeypot_manager.inventory()
    return JSONResponse(payload)


@app.get("/defense-scan")
async def defense_scan() -> JSONResponse:
    try:
        payload = scan_repository(REPO_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive logging
        console.log(f"[red]Scan failed: {exc}")
        raise HTTPException(status_code=500, detail="Codebase scan failed") from exc
    return JSONResponse(payload)


@app.get("/attack-log")
async def attack_log(limit: int = 60) -> Dict[str, List[Dict[str, Any]]]:
    limit = max(1, min(limit, 200))
    try:
        entries = load_attack_log(limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"entries": entries}


@app.get("/telemetry/snapshot")
async def telemetry_snapshot(limit: int = 60) -> Dict[str, Any]:
    limit = max(1, min(limit, MAX_TIMELINE))
    events = load_defense_events(limit)
    latest = events[-1] if events else None
    return {
        "operations": latest.get("operations", []) if latest else [],
        "signals": latest.get("signals", []) if latest else [],
        "generated_at": latest.get("event", {}).get("timestamp") if latest else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("orchestrator.orchestrator:app", host="0.0.0.0", port=7000, reload=True)

