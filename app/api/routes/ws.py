"""
WebSocket Connection Manager — phát sóng real-time events đến dashboard.

Tất cả routes import `manager` từ đây để broadcast khi có sự kiện.
"""
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info("WS connected — total: %d", len(self._connections))

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("WS disconnected — total: %d", len(self._connections))

    async def broadcast(self, event_type: str, data: Any = None):
        if not self._connections:
            return
        payload = json.dumps(
            {"event": event_type, "data": data or {}},
            ensure_ascii=False,
            default=str,
        )
        dead = []
        for ws in list(self._connections):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws/dashboard")
async def dashboard_ws(ws: WebSocket):
    """WebSocket endpoint cho dashboard — nhận live updates."""
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
