"""Safety status plugin — concise /safety and /status slash commands.

Shows the current risk posture without exposing secret values.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from rich.panel import Panel

from code_puppy.callbacks import count_callbacks, register_callback
from code_puppy.messaging import emit_info


def _custom_help() -> List[Tuple[str, str]]:
    return [
        ("safety", "Show safety and trust status (risk posture)"),
        ("status", "Alias for /safety"),
    ]


def _get_status_lines() -> List[str]:
    """Build a list of safety-status lines. All values are redacted or safe."""
    lines: List[str] = []

    # Yolo mode
    try:
        from code_puppy.config import get_yolo_mode

        yolo = get_yolo_mode()
    except Exception:
        yolo = False
    lines.append(f"Yolo mode      : {'on' if yolo else 'off'}")

    # Shell safety
    try:
        from code_puppy.config import get_safety_permission_level

        level = get_safety_permission_level()
    except Exception:
        level = "unknown"
    lines.append(f"Shell safety   : {level}")

    # Workspace root
    try:
        from code_puppy.tools.path_policy import get_workspace_root

        ws = get_workspace_root()
    except Exception:
        ws = Path.cwd()
    lines.append(f"Workspace      : {ws}")

    # Sensitive-file policy
    try:
        from code_puppy.tools.path_policy import SENSITIVE_PATHS

        policy = f"{len(SENSITIVE_PATHS)} sensitive patterns"
    except Exception:
        policy = "active"
    lines.append(f"Sensitive policy: {policy}")

    # Hook trust
    try:
        from code_puppy.hook_engine.trust import _load_trust_db

        db = _load_trust_db()
        hook_count = len(db)
    except Exception:
        hook_count = 0
    lines.append(f"Hook trust     : {hook_count} trusted project(s)")

    # Plugin / callback activity
    try:
        total_callbacks = count_callbacks()
    except Exception:
        total_callbacks = 0
    lines.append(f"Callbacks active: {total_callbacks}")

    # Universal Constructor
    try:
        from code_puppy.config import get_universal_constructor_enabled

        uc = get_universal_constructor_enabled()
    except Exception:
        uc = True
    lines.append(f"UC enabled     : {'yes' if uc else 'no'}")

    # MCP
    try:
        from code_puppy.config import get_mcp_disabled

        mcp = get_mcp_disabled()
    except Exception:
        mcp = False
    lines.append(f"MCP disabled   : {'yes' if mcp else 'no'}")

    # Environment redaction hint
    lines.append("")
    lines.append("Secret values are redacted in logs and status displays.")

    return lines


def _render_panel(lines: List[str]) -> Panel:
    body = "\n".join(lines)
    return Panel(body, title="Safety Status", border_style="cyan")


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if not name:
        return None

    if name in ("safety", "status"):
        lines = _get_status_lines()
        panel = _render_panel(lines)
        emit_info(panel)
        return True

    return None


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
