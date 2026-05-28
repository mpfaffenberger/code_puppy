"""WebSocket connection manager for broadcasting session updates.

This is a singleton that tracks connected WebSocket clients monitoring
session state changes.
"""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """Manages WebSocket connections for broadcasting session updates."""

    def __init__(self):
        self.session_connections: list[WebSocket] = []

    async def connect_session_client(self, websocket: WebSocket):
        """Connect a session monitoring client."""
        self.session_connections.append(websocket)
        logger.debug(
            f"Session client connected. Total: {len(self.session_connections)}"
        )

    def disconnect_session_client(self, websocket: WebSocket):
        """Disconnect a session monitoring client."""
        if websocket in self.session_connections:
            self.session_connections.remove(websocket)
            logger.debug(
                f"Session client disconnected. Total: {len(self.session_connections)}"
            )

    async def broadcast_session_update(self, session_data: dict):
        """Broadcast session update to all connected session clients."""
        if not self.session_connections:
            return

        connections = self.session_connections.copy()
        disconnected = []

        for conn in connections:
            try:
                await conn.send_json({"type": "session_update", "data": session_data})
            except Exception as e:
                logger.warning("Failed to send session update: %s", e)
                disconnected.append(conn)

        for conn in disconnected:
            self.disconnect_session_client(conn)


# Global singleton instance
connection_manager = WebSocketConnectionManager()
