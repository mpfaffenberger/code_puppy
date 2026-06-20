"""Core permission boundary for shell execution and file mutation."""

from __future__ import annotations

from enum import Enum
from typing import Any


class PermissionMode(str, Enum):
    ASK = "ask"
    ACCEPT_EDITS = "acceptEdits"
    AUTO = "auto"


def get_permission_mode() -> PermissionMode:
    """Resolve explicit mode, falling back to the legacy YOLO setting."""
    from code_puppy.config import get_value, get_yolo_mode

    configured = get_value("permission_mode")
    if configured:
        normalized = str(configured).strip().lower()
        mapping = {
            "ask": PermissionMode.ASK,
            "acceptedits": PermissionMode.ACCEPT_EDITS,
            "accept_edits": PermissionMode.ACCEPT_EDITS,
            "auto": PermissionMode.AUTO,
        }
        if normalized in mapping:
            return mapping[normalized]
    # Compatibility for existing installations. New configs explicitly set
    # permission_mode=ask in ensure_config_exists().
    return PermissionMode.AUTO if get_yolo_mode() else PermissionMode.ASK


def has_explicit_permission_mode() -> bool:
    from code_puppy.config import get_value

    return bool(get_value("permission_mode"))


def authorize_file_operation(path: str, operation: str) -> bool:
    mode = get_permission_mode()
    if mode in {PermissionMode.AUTO, PermissionMode.ACCEPT_EDITS}:
        return True

    from code_puppy.tools.common import get_user_approval

    approved, _ = get_user_approval(
        "File Operation",
        f"Requesting permission to {operation}:\n{path}",
    )
    return approved


async def authorize_shell_command(
    command: str, cwd: str | None = None, *, force_prompt: bool = False
) -> tuple[bool, str | None]:
    if not force_prompt and get_permission_mode() is PermissionMode.AUTO:
        return True, None

    from code_puppy.tools.common import get_user_approval_async

    location = f"\nWorking directory: {cwd}" if cwd else ""
    return await get_user_approval_async(
        "Shell Command",
        f"Requesting permission to run:\n$ {command}{location}",
    )


def permission_denied_result(path: str) -> dict[str, Any]:
    return {
        "success": False,
        "path": path,
        "message": "Operation denied by core permission policy.",
        "changed": False,
        "user_rejection": True,
        "user_feedback": None,
    }
