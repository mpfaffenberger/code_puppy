"""WebSocket endpoint for server-sent events streaming."""

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def register_events_endpoint(app: FastAPI) -> None:
    """Register the /ws/events WebSocket endpoint."""

    @app.websocket("/ws/events")
    async def websocket_events(
        websocket: WebSocket, session_id: str | None = None
    ) -> None:
        """Stream real-time events to connected clients.

        Query Parameters:
            session_id: Optional session ID. If provided, only events for that
                session are streamed.
        """
        await websocket.accept()
        logger.debug("Events WebSocket client connected (session_id=%s)", session_id)

        from code_puppy.plugins.frontend_emitter.emitter import (
            get_recent_events,
            subscribe,
            unsubscribe,
        )

        event_queue = subscribe(session_id=session_id)

        try:
            for event in get_recent_events(session_id=session_id):
                await websocket.send_json(event)

            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                    await websocket.send_json(event)
                except asyncio.TimeoutError:
                    try:
                        await websocket.send_json({"type": "ping"})
                    except Exception:
                        break
        except WebSocketDisconnect:
            logger.debug("Events WebSocket client disconnected")
        except Exception as e:
            logger.error("Events WebSocket error: %s", e)
        finally:
            unsubscribe(event_queue)
