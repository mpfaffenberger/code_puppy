"""
Hook Manager plugin – registers callbacks for interactive hook management.

Provides:
  /hooks           – Launch interactive TUI menu (shows global + project hooks)
  /hooks list      – Quick text listing of all configured hooks
  /hooks enable    – Enable all hooks (both global and project)
  /hooks disable   – Disable all hooks (both global and project)
  /hooks status    – Show summary counts per event type
"""

import logging
from typing import Any, List, Optional, Tuple

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

_COMMAND_NAME = "hooks"
_ALIASES = ("hook",)


# ---------------------------------------------------------------------------
# /help entry
# ---------------------------------------------------------------------------


def _hooks_command_help() -> List[Tuple[str, str]]:
    """Advertise /hooks in the /help menu."""
    return [
        (
            "hooks",
            "Manage Claude Code hooks (global + project) – browse, enable/disable, inspect",
        ),
        ("hook", "Alias for /hooks"),
    ]


# ---------------------------------------------------------------------------
# /hooks command handler
# ---------------------------------------------------------------------------


def _handle_hooks_command(command: str, name: str) -> Optional[Any]:
    """Handle /hooks (and /hook) slash commands.

    Sub-commands
    ------------
    /hooks           Launch interactive TUI menu (shows both global and project hooks)
    /hooks list      Print all hooks as text
    /hooks enable    Enable every hook (both global and project)
    /hooks disable   Disable every hook (both global and project)
    /hooks status    Show counts per event type
    """
    if name not in (_COMMAND_NAME, *_ALIASES):
        return None  # Not our command – pass through
    import copy

    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    from .config import (
        _load_global_hooks_config,
        _load_project_hooks_config,
        flatten_all_hooks,
        save_global_hooks_config,
        save_hooks_config,
    )

    tokens = command.split()
    subcommand = tokens[1].lower() if len(tokens) > 1 else ""

    # ------------------------------------------------------------------ list
    if subcommand == "list":
        entries = flatten_all_hooks()
        if not entries:
            emit_info("No hooks configured.")
            emit_info("Add hooks to .claude/settings.json (project):")
            emit_info('  { "hooks": { "PreToolUse": [ ... ] } }')
            emit_info("Or to ~/.code_puppy/hooks.json (global)")
            return True
        emit_info(f"\U0001f3a3 Hooks ({len(entries)} total)\n")

        # Group by source for clarity
        project_hooks = [e for e in entries if e.source == "project"]
        global_hooks = [e for e in entries if e.source == "global"]

        if project_hooks:
            emit_info("📁 PROJECT HOOKS (.claude/settings.json):")
            for entry in project_hooks:
                status = (
                    "\U0001f7e2 enabled " if entry.enabled else "\U0001f534 disabled"
                )
                emit_info(
                    f"  {status}  [{entry.event_type}]  matcher={entry.display_matcher}"
                )
                emit_info(f"      {entry.display_command}")
                emit_info("")

        if global_hooks:
            emit_info("🌍 GLOBAL HOOKS (~/.code_puppy/hooks.json):")
            for entry in global_hooks:
                status = (
                    "\U0001f7e2 enabled " if entry.enabled else "\U0001f534 disabled"
                )
                emit_info(
                    f"  {status}  [{entry.event_type}]  matcher={entry.display_matcher}"
                )
                emit_info(f"      {entry.display_command}")
                emit_info("")

        return True
    # --------------------------------------------------------------- enable
    if subcommand == "enable":
        count = 0

        # Enable all project hooks
        project_config = _load_project_hooks_config()
        project_cfg = copy.deepcopy(project_config)
        for groups in project_cfg.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                for hook in group.get("hooks", []):
                    hook["enabled"] = True
                    count += 1
        if project_config:
            save_hooks_config(project_cfg)

        # Enable all global hooks
        global_config = _load_global_hooks_config()
        global_cfg = copy.deepcopy(global_config)
        for groups in global_cfg.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                for hook in group.get("hooks", []):
                    hook["enabled"] = True
                    count += 1
        if global_config:
            save_global_hooks_config(global_cfg)

        emit_success(f"\u2705 Enabled {count} hook(s).")
        return True
    # -------------------------------------------------------------- disable
    if subcommand == "disable":
        count = 0

        # Disable all project hooks
        project_config = _load_project_hooks_config()
        project_cfg = copy.deepcopy(project_config)
        for groups in project_cfg.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                for hook in group.get("hooks", []):
                    hook["enabled"] = False
                    count += 1
        if project_config:
            save_hooks_config(project_cfg)

        # Disable all global hooks
        global_config = _load_global_hooks_config()
        global_cfg = copy.deepcopy(global_config)
        for groups in global_cfg.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                for hook in group.get("hooks", []):
                    hook["enabled"] = False
                    count += 1
        if global_config:
            save_global_hooks_config(global_cfg)

        emit_warning(f"\U0001f534 Disabled {count} hook(s).")
        return True
    # --------------------------------------------------------------- status
    if subcommand == "status":
        entries = flatten_all_hooks()
        if not entries:
            emit_info("No hooks configured.")
            return True
        from collections import Counter

        by_event: Counter = Counter()
        enabled_by_event: Counter = Counter()
        by_source: Counter = Counter()

        for entry in entries:
            by_event[entry.event_type] += 1
            by_source[entry.source] += 1
            if entry.enabled:
                enabled_by_event[entry.event_type] += 1

        emit_info(
            f"\U0001f4ca Hook status  "
            f"({sum(enabled_by_event.values())}/{len(entries)} enabled)\n"
        )
        for event_type, total in sorted(by_event.items()):
            enabled = enabled_by_event[event_type]
            bar = "\u2588" * enabled + "\u2591" * (total - enabled)
            emit_info(f"  {event_type:<20} {bar} {enabled}/{total}")

        emit_info(
            f"\nSources: {by_source['project']} project, {by_source['global']} global"
        )
        emit_info("")
        return True
    # ----------------------------------------------- unknown sub-command
    if subcommand and subcommand not in ("", "tui"):
        emit_error(f"Unknown sub-command: {subcommand}")
        emit_info("Usage: /hooks [list|enable|disable|status]")
        return True
    # --------------------------------------------------- default: TUI menu
    from .hooks_menu import show_hooks_menu

    show_hooks_menu()
    return True


# ---------------------------------------------------------------------------
# Register callbacks
# ---------------------------------------------------------------------------

register_callback("custom_command_help", _hooks_command_help)
register_callback("custom_command", _handle_hooks_command)

logger.info("Hook Manager plugin loaded")
