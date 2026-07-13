"""
Permission System for Tool Call Execution.

WebSocket-side permission requests are tracked per request_id and bound to the
originating session_id to prevent cross-session response confusion.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import WebSocket

from code_puppy.api.ws.schemas import ServerPermissionRequest

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingPermissionRequest:
    future: asyncio.Future
    session_id: str


# Global dictionary to track pending permission requests
permission_futures: Dict[str, PendingPermissionRequest] = {}


async def request_permission(
    websocket: Optional[WebSocket],
    session_id: str,
    request_type: str,
    title: str,
    description: str,
    details: Dict[str, Any],
    timeout: int = 300,
) -> bool:
    """Request permission from user via WebSocket."""
    # Check if yolo mode is enabled (auto-approve everything).
    # Use the canonical config helper instead of reading CONFIG_FILE directly:
    # the config backend is not guaranteed to be JSON, supports values like
    # yes/on/1, and defaults YOLO to enabled when unset.
    try:
        from code_puppy.config import get_yolo_mode

        if get_yolo_mode():
            logger.info(
                "[Permission] YOLO mode enabled, auto-approving %s",
                request_type,
            )
            return True
    except Exception as exc:
        logger.warning(
            "[Permission] Could not read YOLO mode; falling back to UI prompt for %s: %s",
            request_type,
            exc,
        )

    if websocket is None:
        logger.warning("[Permission] No WebSocket connection, denying %s", request_type)
        return False

    request_id = str(uuid.uuid4())
    future: asyncio.Future = asyncio.get_running_loop().create_future()
    permission_futures[request_id] = PendingPermissionRequest(
        future=future,
        session_id=session_id,
    )

    try:
        await websocket.send_json(
            ServerPermissionRequest(
                request_id=request_id,
                permission_type=request_type,
                title=title,
                description=description,
                details=details,
                session_id=session_id,
                timeout_seconds=timeout,
            ).model_dump(exclude_none=True)
        )
        logger.info("[Permission] Sent request %s for %s", request_id, request_type)
    except Exception as e:
        permission_futures.pop(request_id, None)
        logger.error("[Permission] Failed to send request: %s", e)
        return False

    try:
        approved = await asyncio.wait_for(future, timeout=timeout)
        logger.info(
            "[Permission]  Got response for %s: %s",
            request_id,
            "APPROVED" if approved else "DENIED",
        )
        return bool(approved)
    except asyncio.TimeoutError:
        logger.warning(
            "[Permission] Request %s timed out after %ss", request_id, timeout
        )
        return False
    except Exception as e:
        logger.error("[Permission] Error waiting for permission: %s", e)
        return False
    finally:
        permission_futures.pop(request_id, None)


def handle_permission_response(
    request_id: str,
    approved: bool,
    *,
    session_id: Optional[str] = None,
) -> bool:
    """Handle a permission response from the client.

    If ``session_id`` is provided, response handling is restricted to matching
    pending requests from the same session.
    """
    pending = permission_futures.get(request_id)
    if pending is None:
        logger.warning(
            "[Permission] Received response for unknown/expired request: %s",
            request_id,
        )
        return False

    if session_id is not None and pending.session_id != session_id:
        logger.warning(
            "[Permission] Session mismatch for request %s (expected %s, got %s)",
            request_id,
            pending.session_id,
            session_id,
        )
        return False

    if pending.future.done():
        logger.warning("[Permission] Request already resolved: %s", request_id)
        return False

    pending.future.set_result(bool(approved))
    logger.info("[Permission] Handled response for %s: %s", request_id, approved)
    return True
