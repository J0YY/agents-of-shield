from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from rich.console import Console

from .event_router import EventRouter
from .websocket_server import manager, router as ws_router
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
STATE_DIR = BASE_DIR / "state"
REPORT_DIR = BASE_DIR / "reports"
EVENT_LOG = STATE_DIR / "attacker_events.jsonl"
MAX_TIMELINE = 200

load_dotenv()

console = Console()
app = FastAPI(title="Agents of Shield – Defense Orchestrator", version="0.1.0")
app.include_router(ws_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    console.rule("[bold green]Defense Orchestrator Ready")
    console.print("[cyan]HTTP http://localhost:7000 · WebSocket ws://localhost:7000/ws")


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("orchestrator.orchestrator:app", host="0.0.0.0", port=7000, reload=True)

