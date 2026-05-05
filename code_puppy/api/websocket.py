"""WebSocket endpoints for Code Puppy API.

Provides real-time communication channels:
- /ws/events - Server-sent events stream
- /ws/terminal - Interactive PTY terminal sessions
- /ws/health - Simple health check endpoint
"""

import asyncio
import base64
import logging
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def setup_websocket(app: FastAPI) -> None:
    """Setup WebSocket endpoints for the application."""

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket) -> None:
        """Stream real-time events to connected clients."""
        await websocket.accept()
        logger.info("Events WebSocket client connected")

        from code_puppy.plugins.frontend_emitter.emitter import (
            get_recent_events,
            subscribe,
            unsubscribe,
        )

        event_queue = subscribe()

        try:
            recent_events = get_recent_events()
            for event in recent_events:
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
            logger.info("Events WebSocket client disconnected")
        except Exception as e:
            logger.error(f"Events WebSocket error: {e}")
        finally:
            unsubscribe(event_queue)

    @app.websocket("/ws/terminal")
    async def websocket_terminal(websocket: WebSocket) -> None:
        """Interactive terminal WebSocket endpoint."""
        await websocket.accept()
        logger.info("Terminal WebSocket client connected")

        from code_puppy.api.pty_manager import get_pty_manager

        manager = get_pty_manager()
        session_id = str(uuid.uuid4())[:8]
        session = None

        # Get the current event loop for thread-safe scheduling
        loop = asyncio.get_running_loop()

        # Queue to receive PTY output in a thread-safe way
        output_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Output callback - called from thread pool, puts data in queue
        def on_output(data: bytes) -> None:
            try:
                loop.call_soon_threadsafe(output_queue.put_nowait, data)
            except Exception as e:
                logger.error(f"on_output error: {e}")

        async def output_sender() -> None:
            """Coroutine that sends queued output to WebSocket."""
            try:
                while True:
                    data = await output_queue.get()
                    await websocket.send_json(
                        {
                            "type": "output",
                            "data": base64.b64encode(data).decode("ascii"),
                        }
                    )
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"output_sender error: {e}")

        sender_task = None

        try:
            # Create PTY session
            session = await manager.create_session(
                session_id=session_id,
                on_output=on_output,
            )

            # Send session info
            await websocket.send_json({"type": "session", "id": session_id})

            # Start output sender task
            sender_task = asyncio.create_task(output_sender())

            # Handle incoming messages
            while True:
                try:
                    msg = await websocket.receive_json()

                    if msg.get("type") == "input":
                        data = msg.get("data", "")
                        if isinstance(data, str):
                            data = data.encode("utf-8")
                        await manager.write(session_id, data)
                    elif msg.get("type") == "resize":
                        cols = msg.get("cols", 80)
                        rows = msg.get("rows", 24)
                        await manager.resize(session_id, cols, rows)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Terminal WebSocket error: {e}")
                    break
        except Exception as e:
            logger.error(f"Terminal session error: {e}")
        finally:
            if sender_task:
                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass
            if session:
                await manager.close_session(session_id)
            logger.info("Terminal WebSocket disconnected")

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
