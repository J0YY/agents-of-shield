from __future__ import annotations

import asyncio
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


class DashboardSocketManager:
    """Simple connection manager that broadcasts defense events to dashboards."""

    def __init__(self) -> None:
        self._connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def broadcast(self, message: Dict) -> None:
        async with self._lock:
            living: List[WebSocket] = []
            for connection in self._connections:
                try:
                    await connection.send_json(message)
                    living.append(connection)
                except WebSocketDisconnect:
                    continue
                except RuntimeError:
                    continue
            self._connections = living


router = APIRouter()
manager = DashboardSocketManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            # Pings from dashboard clients keep the socket alive; no server-side input needed.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)

