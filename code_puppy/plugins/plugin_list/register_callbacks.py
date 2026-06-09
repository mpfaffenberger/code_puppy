"""``/plugins`` slash command -- manage plugins interactively or via subcommands.

Usage::

    /plugins                   -- open interactive TUI
    /plugins list              -- print loaded plugins with status
    /plugins disable <name>    -- disable a plugin (callbacks are skipped)
    /plugins enable <name>     -- re-enable a disabled plugin

Dogfoods the plugin system by implementing itself as a builtin plugin that
hooks into ``custom_command`` and ``custom_command_help``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)


def _format_plugin_list(names: list[str], disabled: set[str]) -> str:
    """Return a bullet list of plugin names with status indicators."""
    if not names:
        return "  (none)"
    lines = []
    for name in sorted(names):
        if name in disabled:
            lines.append(f"   {name}  (disabled)")
        else:
            lines.append(f"   {name}")
    return "\n".join(lines)


def _build_output() -> str:
    """Build the full /plugins list display string."""
    from code_puppy.plugins import (
        get_loaded_plugins,
        get_project_plugins_directory,
    )
    from code_puppy.plugins.config import get_disabled_plugins

    loaded = get_loaded_plugins()
    disabled = get_disabled_plugins()

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
        _format_plugin_list(loaded["builtin"], disabled),
        "",
        f"User ({user_path}):",
        _format_plugin_list(loaded["user"], disabled),
        "",
        f"Project ({project_path}):",
        _format_plugin_list(loaded["project"], disabled),
    ]

    if disabled:
        lines.extend(
            [
                "",
                f"Disabled: {', '.join(sorted(disabled))}",
                "Use /plugins enable <name> to re-enable.",
            ]
        )

    return "\n".join(lines)


def _all_loaded_plugin_names() -> set[str]:
    """Return the set of all loaded plugin names across all tiers."""
    from code_puppy.plugins import get_loaded_plugins

    loaded = get_loaded_plugins()
    names: set[str] = set()
    for tier_names in loaded.values():
        names.update(tier_names)
    return names


def _handle_disable(plugin_name: str) -> bool:
    """Disable a plugin by name."""
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
    from code_puppy.plugins.config import set_plugin_disabled

    all_names = _all_loaded_plugin_names()
    if plugin_name not in all_names:
        emit_error(
            f"Plugin '{plugin_name}' is not loaded. "
            f"Use /plugins to see available plugins."
        )
        return True

    if set_plugin_disabled(plugin_name, disabled=True):
        emit_success(f"Plugin '{plugin_name}' disabled.")
        emit_warning("Restart Code Puppy for this change to take effect.")
    else:
        emit_info(f"Plugin '{plugin_name}' is already disabled.")
    return True


def _handle_enable(plugin_name: str) -> bool:
    """Enable a previously disabled plugin."""
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
    from code_puppy.plugins.config import set_plugin_disabled

    all_names = _all_loaded_plugin_names()
    if plugin_name not in all_names:
        emit_error(
            f"Plugin '{plugin_name}' is not loaded. "
            f"Use /plugins to see available plugins."
        )
        return True

    if set_plugin_disabled(plugin_name, disabled=False):
        emit_success(f"Plugin '{plugin_name}' re-enabled.")
        emit_warning("Restart Code Puppy for this change to take effect.")
    else:
        emit_info(f"Plugin '{plugin_name}' is already enabled.")
    return True


# -- custom_command hooks --------------------------------------------------


def _custom_help() -> list[tuple[str, str]]:
    return [("plugins", "List, enable, or disable plugins")]


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name != "plugins":
        return None  # Not our command.

    from code_puppy.messaging import emit_error, emit_info

    tokens = command.strip().split()

    # Bare /plugins -> interactive TUI
    if len(tokens) <= 1:
        try:
            from code_puppy.plugins.plugin_list.plugins_menu import run_plugins_menu

            run_plugins_menu()
        except Exception as exc:
            logger.warning(f"Plugins TUI failed, falling back to list: {exc}")
            emit_info(_build_output())
        return True

    subcommand = tokens[1].lower()

    if subcommand == "list":
        emit_info(_build_output())
        return True

    if subcommand == "disable":
        if len(tokens) < 3:
            emit_error("Usage: /plugins disable <plugin-name>")
            return True
        return _handle_disable(tokens[2])

    if subcommand == "enable":
        if len(tokens) < 3:
            emit_error("Usage: /plugins enable <plugin-name>")
            return True
        return _handle_enable(tokens[2])

    emit_error(
        f"Unknown subcommand: '{subcommand}'. "
        "Usage: /plugins [list | enable <name> | disable <name>]"
    )
    return True


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
