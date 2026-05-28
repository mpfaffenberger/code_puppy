"""
Permission System for Tool Call Execution

This module provides a permission request system that integrates with the WebSocket API
to request user approval before executing potentially dangerous operations.

Features:
- WebSocket-based permission requests with in-chat action buttons
- 5-minute timeout on permission waits
- Automatic approval in yolo mode
- CLI mode support via WebSocket

Usage:
    from code_puppy.api.permissions import request_permission

    approved = await request_permission(
        websocket=ws,
        session_id="session-123",
        request_type="shell_command",
        title="Execute Shell Command",
        description="Run: ls -la",
        details={"command": "ls -la", "cwd": "/home/user"}
    )
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import WebSocket

from code_puppy.api.ws.schemas import ServerPermissionRequest

logger = logging.getLogger(__name__)

# Global dictionary to track pending permission requests
# This is managed by the WebSocket API module
permission_futures: Dict[str, asyncio.Future] = {}


async def request_permission(
    websocket: Optional[WebSocket],
    session_id: str,
    request_type: str,
    title: str,
    description: str,
    details: Dict[str, Any],
    timeout: int = 300,
) -> bool:
    """
    Request permission from user via WebSocket.

    Args:
        websocket: WebSocket connection to send request through
        session_id: Current session ID
        request_type: Type of permission (e.g., 'shell_command')
        title: Permission dialog title
        description: Human-readable description
        details: Additional context (command, args, etc.)
        timeout: Timeout in seconds (default 5 minutes)

    Returns:
        bool: True if approved, False if denied or timeout
    """
    # Check if yolo mode is enabled (auto-approve everything)
    try:
        import json
        import os

        from code_puppy.config import CONFIG_FILE

        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                yolo_mode = str(config.get("yolo_mode", "false")).lower() == "true"
                if yolo_mode:
                    logger.info(
                        f"[Permission] YOLO mode enabled, auto-approving {request_type}"
                    )
                    return True
            except Exception:
                pass  # If config read fails, continue to request permission
    except Exception:
        pass  # If we can't check, require permission

    # If no WebSocket connection, deny by default (fail-safe)
    if websocket is None:
        logger.warning("[Permission] No WebSocket connection, denying %s", request_type)
        return False

    request_id = str(uuid.uuid4())

    # Send permission request to frontend
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
        logger.error("[Permission] Failed to send request: %s", e)
        return False

    # Create a future to wait for the response
    future = asyncio.Future()
    permission_futures[request_id] = future

    try:
        # Wait for user response with timeout
        approved = await asyncio.wait_for(future, timeout=timeout)
        logger.info(
            f"[Permission] ✅ Got response for {request_id}: {'APPROVED' if approved else 'DENIED'}"
        )
        return approved
    except asyncio.TimeoutError:
        logger.warning(
            "[Permission] Request %s timed out after %ss", request_id, timeout
        )
        return False
    except Exception as e:
        logger.error("[Permission] Error waiting for permission: %s", e)
        return False
    finally:
        # Clean up the future
        permission_futures.pop(request_id, None)


def handle_permission_response(request_id: str, approved: bool) -> bool:
    """
    Handle a permission response from the client.

    Args:
        request_id: The request ID from the permission_request
        approved: True if approved, False if denied

    Returns:
        bool: True if the response was handled, False if request_id not found
    """
    logger.info(
        f"[Permission] handle_permission_response called: request_id={request_id}, approved={approved}"
    )
    logger.info(
        f"[Permission] Current permission_futures keys: {list(permission_futures.keys())}"
    )

    future = permission_futures.get(request_id)
    logger.info(
        f"[Permission] Future found: {future is not None}, done: {future.done() if future else 'N/A'}"
    )

    if future and not future.done():
        logger.info("[Permission] Setting future result to: %s", approved)
        future.set_result(approved)
        logger.info("[Permission] Handled response for %s: %s", request_id, approved)
        return True
    else:
        logger.warning(
            f"[Permission] Received response for unknown/expired request: {request_id}"
        )
        logger.warning(
            f"[Permission] Future exists: {future is not None}, Future done: {future.done() if future else 'N/A'}"
        )
        return False
