"""WebSocket endpoint for health checks."""

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def register_health_endpoint(app: FastAPI) -> None:
    """Register the /ws/health WebSocket endpoint."""

    @app.websocket("/ws/health")
    async def websocket_health(websocket: WebSocket) -> None:
        """Simple WebSocket health check - echoes messages back."""
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                await websocket.send_text(f"echo: {data}")
        except WebSocketDisconnect:
            pass
