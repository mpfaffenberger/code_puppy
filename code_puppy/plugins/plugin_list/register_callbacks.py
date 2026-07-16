"""``/plugins`` slash command -- manage plugins interactively or via subcommands.

Usage::

    /plugins                   -- open interactive TUI
    /plugins list              -- print loaded plugins with status
    /plugins disable <name>    -- disable a plugin (callbacks are skipped)
    /plugins enable <name>     -- enable a plugin; untrusted project plugins
                                  open the TUI trust ceremony directly
    /plugins revoke <name>     -- revoke trust for a project plugin

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


_PROJECT_STATUS_LABELS = {
    "untrusted": "(not enabled -- review & enable in the /plugins TUI)",
    "changed": "(changed since accepted -- re-review in the /plugins TUI)",
    "disabled": "(disabled)",
    "error": "(failed to load -- see logs)",
}


def _format_project_plugin_list(
    loaded_names: list[str],
    statuses: dict[str, str],
    disabled: set[str],
) -> str:
    """Project tier listing: loaded plugins plus skipped-by-trust ones.

    Project plugins are disabled by default; unlike other tiers we also
    show plugins that were discovered but NOT imported, with the reason.
    """
    names = sorted(set(loaded_names) | set(statuses))
    if not names:
        return "  (none)"
    lines = []
    for name in names:
        status = statuses.get(name, "loaded" if name in loaded_names else "untrusted")
        if status == "loaded":
            suffix = "  (disabled)" if name in disabled else ""
        else:
            suffix = "  " + _PROJECT_STATUS_LABELS.get(status, f"({status})")
        lines.append(f"   {name}{suffix}")
    return "\n".join(lines)


def _build_output() -> str:
    """Build the full /plugins list display string."""
    from code_puppy.plugins import (
        get_loaded_plugins,
        get_project_plugins_directory,
        get_project_plugin_status,
    )
    from code_puppy.plugins.config import get_disabled_plugins

    loaded = get_loaded_plugins()
    disabled = get_disabled_plugins()
    project_status = get_project_plugin_status()

    # Display paths with forward slashes regardless of OS so the output is
    # consistent across Windows / POSIX (and easier to copy-paste).
    builtin_path = Path(__file__).parent.parent.as_posix() + "/"
    user_path = "~/.code_puppy/plugins/"
    project_dir = get_project_plugins_directory()
    project_path = (
        project_dir.as_posix() + "/" if project_dir else "<CWD>/.code_puppy/plugins/"
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
        _format_project_plugin_list(loaded["project"], project_status, disabled),
    ]

    if disabled:
        lines.extend(
            [
                "",
                f"Disabled: {', '.join(sorted(disabled))}",
                "Re-enable it in the /plugins TUI.",
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


def _handle_toggle(plugin_name: str, *, disabled: bool) -> bool:
    """Flip *plugin_name*'s disabled state to *disabled*.

    One implementation handles both ``enable`` and ``disable`` — the only
    difference is the target state and the success-message verb.
    """
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
    from code_puppy.plugins.config import set_plugin_disabled

    if plugin_name not in _all_loaded_plugin_names():
        emit_error(
            f"Plugin '{plugin_name}' is not loaded. "
            f"Use /plugins to see available plugins."
        )
        return True

    verb = "disabled" if disabled else "re-enabled"
    state = "disabled" if disabled else "enabled"
    if set_plugin_disabled(plugin_name, disabled):
        emit_success(f"Plugin '{plugin_name}' {verb}.")
        emit_warning("Restart Code Puppy for this change to take effect.")
    else:
        emit_info(f"Plugin '{plugin_name}' is already {state}.")
    return True


# -- startup hook ----------------------------------------------------------


def _on_startup() -> None:
    """Surface project plugins held back by the trust gate.

    Runs via the ``startup`` callback, which fires after the renderers are
    live — so the orange banner lands inline with the other startup
    messages instead of rotting in the legacy queue's startup buffer
    (which SynchronousInteractiveRenderer never replays).
    """
    try:
        from code_puppy.plugins import get_project_plugin_status
        from code_puppy.plugins.trust_notice import emit_skipped_plugin_notice

        emit_skipped_plugin_notice(get_project_plugin_status())
    except Exception as exc:
        logger.debug(f"Trust-notice startup hook failed: {exc}")


# -- custom_command hooks --------------------------------------------------


def _custom_help() -> list[tuple[str, str]]:
    return [("plugins", "List, enable/disable, or trust project plugins")]


def _run_interactive_menu() -> None:
    """Open the TUI; fall back to a plain-text list if it blows up."""
    from code_puppy.messaging import emit_info

    try:
        from code_puppy.plugins.plugin_list.plugins_menu import run_plugins_menu

        run_plugins_menu()
    except Exception as exc:
        logger.warning(f"Plugins TUI failed, falling back to list: {exc}")
        emit_info(_build_output())


def _sub_list(_tokens: list[str]) -> bool:
    from code_puppy.messaging import emit_info

    emit_info(_build_output())
    return True


def _sub_disable(tokens: list[str]) -> bool:
    return _sub_toggle(tokens, disabled=True)


def _sub_enable(tokens: list[str]) -> bool:
    from code_puppy.messaging import emit_error

    if len(tokens) < 3:
        emit_error("Usage: /plugins enable <plugin-name>")
        return True

    # Project plugins get the trust/risk-acceptance flow; anything else
    # falls through to the regular enable toggle.
    from code_puppy.plugins.plugin_list.project_trust_flow import (
        try_enable_project_plugin,
    )

    if try_enable_project_plugin(tokens[2]):
        return True
    return _handle_toggle(tokens[2], disabled=False)


def _sub_revoke(tokens: list[str]) -> bool:
    from code_puppy.messaging import emit_error

    if len(tokens) < 3:
        emit_error("Usage: /plugins revoke <plugin-name>")
        return True

    from code_puppy.plugins.plugin_list.project_trust_flow import (
        revoke_project_plugin,
    )

    return revoke_project_plugin(tokens[2])


def _sub_toggle(tokens: list[str], *, disabled: bool) -> bool:
    from code_puppy.messaging import emit_error

    action = "disable" if disabled else "enable"
    if len(tokens) < 3:
        emit_error(f"Usage: /plugins {action} <plugin-name>")
        return True
    return _handle_toggle(tokens[2], disabled=disabled)


_SUBCOMMANDS = {
    "list": _sub_list,
    "disable": _sub_disable,
    "enable": _sub_enable,
    "revoke": _sub_revoke,
}


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name != "plugins":
        return None

    tokens = command.strip().split()

    if len(tokens) <= 1:
        _run_interactive_menu()
        return True

    handler = _SUBCOMMANDS.get(tokens[1].lower())
    if handler is None:
        from code_puppy.messaging import emit_error

        emit_error(
            f"Unknown subcommand: '{tokens[1]}'. "
            "Usage: /plugins [list | enable <name> | disable <name> | revoke <name>]"
        )
        return True
    return handler(tokens)


register_callback("startup", _on_startup)
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
