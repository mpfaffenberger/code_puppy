"""WebSocket endpoint for real-time event streaming."""

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def setup_websocket(app: FastAPI) -> None:
    """Setup WebSocket endpoint for real-time events.

    Args:
        app: The FastAPI application instance to add WebSocket routes to.
    """

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket) -> None:
        """Stream real-time events to connected clients.

        Events are JSON messages with structure:
        {
            "id": "uuid",
            "type": "event_type",
            "timestamp": "ISO8601",
            "data": {...}
        }

        On connect, sends recent events for catch-up, then streams new events.
        Sends ping messages every 30s if no events to keep connection alive.
        """
        await websocket.accept()
        logger.info("WebSocket client connected")

        # Lazy import to avoid circular imports between API and plugin modules
        from code_puppy.plugins.frontend_emitter.emitter import (
            get_recent_events,
            subscribe,
            unsubscribe,
        )

        event_queue = subscribe()

        try:
            # Send recent events for catch-up
            recent_events = get_recent_events()
            for event in recent_events:
                await websocket.send_json(event)

            # Stream new events
            while True:
                try:
                    # Wait for next event with timeout to check connection
                    event = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=30.0,  # Send ping if no events for 30s
                    )
                    await websocket.send_json(event)
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    try:
                        await websocket.send_json({"type": "ping"})
                    except Exception:
                        break  # Client disconnected

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            unsubscribe(event_queue)
            logger.info("WebSocket subscription cleaned up")

    @app.websocket("/ws/health")
    async def websocket_health(websocket: WebSocket) -> None:
        """Simple WebSocket health check - echoes messages back.

        Useful for testing WebSocket connectivity without needing
        the full event subscription machinery.
        """
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                await websocket.send_text(f"echo: {data}")
        except WebSocketDisconnect:
            pass
