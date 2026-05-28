"""WebSocket endpoint for real-time session monitoring."""

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from code_puppy.api.ws.connection_manager import connection_manager

logger = logging.getLogger(__name__)


def register_sessions_endpoint(app: FastAPI) -> None:
    """Register the /ws/sessions WebSocket endpoint."""

    @app.websocket("/ws/sessions")
    async def websocket_sessions(websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time session updates.

        Clients can connect to this endpoint to receive real-time notifications
        when WebSocket sessions are created, updated, or deleted.

        Messages sent to clients:
        - {"type": "session_update", "data": WSSessionInfo}
        - {"type": "ping"} (keepalive)
        """
        await websocket.accept()
        logger.debug("Sessions monitoring WebSocket client connected")

        try:
            await connection_manager.connect_session_client(websocket)

            # Send initial session list
            try:
                from code_puppy.api.routers.ws_sessions import list_ws_sessions

                current_sessions = await list_ws_sessions()
                await websocket.send_json(
                    {
                        "type": "initial_sessions",
                        "data": [session.model_dump() for session in current_sessions],
                    }
                )
            except Exception as e:
                logger.error("Failed to send initial sessions: %s", e)
                await websocket.send_json(
                    {"type": "error", "error": f"Failed to load sessions: {str(e)}"}
                )

            # Keep connection alive
            while True:
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(), timeout=30.0
                    )
                    if message.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except asyncio.TimeoutError:
                    try:
                        await websocket.send_json({"type": "ping"})
                    except Exception:
                        break

        except WebSocketDisconnect:
            logger.debug("Sessions monitoring WebSocket client disconnected")
        except Exception as e:
            logger.error("Sessions WebSocket error: %s", e)
        finally:
            connection_manager.disconnect_session_client(websocket)
