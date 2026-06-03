"""WebSocket send helpers extracted from ``chat_handler.py`` (Phase 3).

``WebSocketSender`` encapsulates the mutable ``ws_closed`` flag and the
four send/persist closures that were previously defined inside
``websocket_chat()``.  Moving them to a class makes them independently
testable and removes four levels of closure nesting.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import WebSocket

    from code_puppy.api.ws.schemas import (
        ServerMessage,
        ServerToolCall,
        ServerToolResult,
    )

logger = logging.getLogger(__name__)


class WebSocketSender:
    """Manages safe JSON sends over a WebSocket with closed-socket detection.

    Parameters
    ----------
    websocket:
        The connected ``WebSocket`` instance.
    session_id:
        Current session identifier (used for logging and error persistence).
    """

    __slots__ = ("_websocket", "_session_id", "ws_closed", "_ctx")

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
    ) -> None:
        self._websocket = websocket
        self._session_id = session_id
        self.ws_closed: bool = False
        self._ctx: Any = None

    # -- ctx property (set after construction, mirrors closure lifecycle) ----

    @property
    def ctx(self) -> Any:
        return self._ctx

    @ctx.setter
    def ctx(self, value: Any) -> None:
        self._ctx = value

    @property
    def session_id(self) -> str:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        self._session_id = value

    # -- persistence helper --------------------------------------------------

    async def persist_error_payload(self, data: dict[str, Any]) -> None:
        """Persist structured error frames so they survive page reloads."""
        if data.get("type") != "error" or not self._session_id:
            return

        try:
            from code_puppy.api.db.queries import write_error_message_to_sqlite

            await write_error_message_to_sqlite(
                session_id=self._session_id,
                error=str(data.get("error") or "An unknown error occurred"),
                error_type=str(data.get("error_type") or "unknown"),
                technical_details=str(data.get("technical_details") or ""),
                action_required=data.get("action_required"),
                agent_name=(self._ctx.agent_name if self._ctx else ""),
                model_name=(self._ctx.model_name if self._ctx else ""),
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
        except Exception:
            logger.warning(
                "[WS:%s] Failed to persist error payload to SQLite",
                self._session_id,
                exc_info=True,
            )

    # -- send helpers --------------------------------------------------------

    async def safe_send_json(self, data: dict) -> bool:
        """Send JSON to WebSocket; returns ``False`` if the connection is closed."""
        if self.ws_closed:
            logger.debug(
                "[WS:%s] safe_send_json skipped (ws_closed=True): type=%s",
                self._session_id,
                data.get("type"),
            )
            return False

        msg_type = data.get("type")
        if msg_type in {
            "error",
            "response",
            "assistant_message_start",
            "assistant_message_end",
        }:
            logger.debug(
                "[WS:%s] → send_json type=%s keys=%s",
                self._session_id,
                msg_type,
                sorted(list(data.keys())),
            )
            if msg_type == "error":
                logger.debug(
                    "[WS:%s] error payload: error_type=%r action_required=%r error=%r",
                    self._session_id,
                    data.get("error_type"),
                    data.get("action_required"),
                    (data.get("error") or "")[:300],
                )

        try:
            if msg_type == "error":
                await self.persist_error_payload(data)
            await self._websocket.send_json(data)
            return True
        except Exception as e:
            logger.warning(
                "[WS:%s] send_json failed for type=%s: %s",
                self._session_id,
                msg_type,
                e,
                exc_info=True,
            )
            if "close message" in str(e).lower() or "closed" in str(e).lower():
                self.ws_closed = True
                logger.debug("WebSocket closed, stopping sends")
            return False

    async def send_typed(self, msg: ServerMessage) -> bool:
        """Send a typed protocol message to the client."""
        return await self.safe_send_json(msg.model_dump(exclude_none=True))

    async def send_typed_tool_lifecycle(
        self, msg: ServerToolCall | ServerToolResult
    ) -> bool:
        """Send tool lifecycle frames to the client."""
        return await self.send_typed(msg)
