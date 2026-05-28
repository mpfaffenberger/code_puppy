"""WebSocket endpoint for interactive PTY terminal sessions."""

import asyncio
import base64
import logging
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def register_terminal_endpoint(app: FastAPI) -> None:
    """Register the /ws/terminal WebSocket endpoint."""

    @app.websocket("/ws/terminal")
    async def websocket_terminal(websocket: WebSocket) -> None:
        """Interactive terminal WebSocket endpoint."""
        await websocket.accept()
        logger.debug("Terminal WebSocket client connected")

        from code_puppy.api.pty_manager import get_pty_manager

        manager = get_pty_manager()
        session_id = str(uuid.uuid4())[:8]
        session = None

        loop = asyncio.get_running_loop()
        output_queue: asyncio.Queue[bytes] = asyncio.Queue()

        def on_output(data: bytes) -> None:
            try:
                loop.call_soon_threadsafe(output_queue.put_nowait, data)
            except Exception as e:
                logger.error("on_output error: %s", e)

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
                logger.error("output_sender error: %s", e)

        sender_task = None

        try:
            session = await manager.create_session(
                session_id=session_id,
                on_output=on_output,
            )

            from code_puppy.api.session_context import session_manager

            try:
                ctx = await session_manager.create_session(f"terminal_{session_id}")
                current_agent_name = ctx.agent_name
            except Exception:
                current_agent_name = "code-puppy"
                ctx = None

            await websocket.send_json(
                {
                    "type": "session_started",
                    "session_id": session_id,
                    "current_agent": current_agent_name,
                }
            )

            sender_task = asyncio.create_task(output_sender())

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
                    elif msg.get("type") == "switch_agent":
                        agent_name = msg.get("agent_name")
                        if agent_name:
                            try:
                                await session_manager.switch_agent(
                                    f"terminal_{session_id}", agent_name
                                )
                                if ctx:
                                    ctx = await session_manager.get_session(
                                        f"terminal_{session_id}"
                                    )
                                await websocket.send_json(
                                    {"type": "agent_changed", "agent_name": agent_name}
                                )
                            except Exception as e:
                                logger.error("Error switching agent: %s", e)
                                await websocket.send_json(
                                    {
                                        "type": "error",
                                        "message": f"Failed to switch to agent {agent_name}: {str(e)}",
                                    }
                                )
                    elif msg.get("type") == "get_current_agent":
                        if ctx:
                            current_agent_name = ctx.agent_name
                        else:
                            current_agent_name = "code-puppy"
                        await websocket.send_json(
                            {"type": "current_agent", "agent_name": current_agent_name}
                        )
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error("Terminal WebSocket error: %s", e)
                    break
        except Exception as e:
            logger.error("Terminal session error: %s", e)
        finally:
            if sender_task:
                sender_task.cancel()
                try:
                    await sender_task
                except asyncio.CancelledError:
                    pass
            if ctx:
                await session_manager.destroy_session(f"terminal_{session_id}")
            if session:
                await manager.close_session(session_id)
            logger.debug("Terminal WebSocket disconnected")
