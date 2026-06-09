"""``/plugins`` slash command — lists loaded plugins grouped by source tier.

Dogfoods the plugin system by implementing itself as a builtin plugin that
hooks into ``custom_command`` and ``custom_command_help``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)


def _format_plugin_list(names: list[str]) -> str:
    """Return a bullet list of plugin names, or a placeholder when empty."""
    if not names:
        return "  (none)"
    return "\n".join(f"  • {name}" for name in sorted(names))


def _build_output() -> str:
    """Build the full /plugins display string."""
    # Lazy import to avoid circular-import at registration time.
    from code_puppy.plugins import (
        get_loaded_plugins,
        get_project_plugins_directory,
    )

    loaded = get_loaded_plugins()

    builtin_path = str(Path(__file__).parent.parent) + "/"
    user_path = "~/.code_puppy/plugins/"
    project_dir = get_project_plugins_directory()
    project_path = (
        str(project_dir) + "/" if project_dir else "<CWD>/.code_puppy/plugins/"
    )

    lines = [
        "Loaded Plugins",
        "",
        f"Builtin ({builtin_path}):",
        _format_plugin_list(loaded["builtin"]),
        "",
        f"User ({user_path}):",
        _format_plugin_list(loaded["user"]),
        "",
        f"Project ({project_path}):",
        _format_plugin_list(loaded["project"]),
    ]

    return "\n".join(lines)


# ── custom_command hooks ──────────────────────────────────────────────────


def _custom_help() -> list[tuple[str, str]]:
    return [("plugins", "Show loaded plugins grouped by source tier")]


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name != "plugins":
        return None  # Not our command — let other plugins try.

    from code_puppy.messaging import emit_info

    emit_info(_build_output())
    return True  # Fully handled.


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
