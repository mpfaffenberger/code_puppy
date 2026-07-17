"""Register callbacks for the ``wide_completion_menu`` plugin.

Hooks:

* ``startup`` — monkey-patches prompt_toolkit's completion menu width so the
  scrollbar anchors to the right edge of the terminal rather than the right
  edge of the menu content.
* ``custom_command`` / ``custom_command_help`` — exposes ``/widemenu`` to
  toggle the effect at runtime without restarting the app.

Design notes
------------
prompt_toolkit's :class:`CompletionsMenuControl.preferred_width` returns
``menu_width + menu_meta_width`` based on the longest completion, so the
menu is content-sized and the scrollbar lives wherever that content ends.
We replace ``preferred_width`` with a version that returns
``max_available_width``, causing the parent ``Window`` to stretch the menu
across the full row. Combined with the existing ``_left_justify_completion_menu``
that pins the menu's ``Float`` to column 0, the scrollbar lands flush against
the right edge of the screen.

The patch is:

* **Idempotent** — re-installing is a no-op (sentinel attribute).
* **Reversible** — original methods are stashed and restored on disable.
* **Defensive** — every patch step is wrapped in try/except so a
  prompt_toolkit version bump cannot crash the prompt.
"""

from __future__ import annotations

from typing import List, Tuple

from code_puppy.callbacks import register_callback

_COMMAND_NAME = "widemenu"
_PATCH_FLAG = "_wide_completion_menu_patched"
_ORIGINAL_ATTR = "_wide_completion_menu_original_preferred_width"

# Module-level state so the /widemenu command can flip behavior without
# uninstalling the patch. When False the patched preferred_width delegates
# back to the original implementation.
_state = {"enabled": True}


# ---------------------------------------------------------------------------
# Messaging helpers (lazy-imported to dodge boot-time circular imports)
# ---------------------------------------------------------------------------
def _emit_info(message: str) -> None:
    from code_puppy.messaging import emit_info

    emit_info(message)


def _emit_error(message: str) -> None:
    from code_puppy.messaging import emit_error

    emit_error(message)


# ---------------------------------------------------------------------------
# Patching
# ---------------------------------------------------------------------------
def _patch_menu_class(cls) -> None:
    """Replace ``cls.preferred_width`` with a screen-filling variant.

    Stores the original method on the class under ``_ORIGINAL_ATTR`` so we
    can both delegate to it (when toggled off) and restore it cleanly.
    """
    if getattr(cls, _PATCH_FLAG, False):
        return  # Already patched.

    original = cls.preferred_width
    setattr(cls, _ORIGINAL_ATTR, original)

    def patched_preferred_width(self, max_available_width: int):
        # When toggled off, behave exactly like upstream.
        if not _state["enabled"]:
            return original(self, max_available_width)

        # Only stretch when there's actually a completion menu to show;
        # otherwise upstream returns 0 and we should too (avoids reserving
        # a full-width strip for an empty menu).
        try:
            from prompt_toolkit.application.current import get_app

            complete_state = get_app().current_buffer.complete_state
        except Exception:
            complete_state = None

        if not complete_state:
            return 0
        return max_available_width

    cls.preferred_width = patched_preferred_width
    setattr(cls, _PATCH_FLAG, True)


def _install_patch() -> None:
    """Patch both single- and multi-column completion menu controls."""
    from prompt_toolkit.layout.menus import (
        CompletionsMenuControl,
        MultiColumnCompletionMenuControl,
    )

    _patch_menu_class(CompletionsMenuControl)
    _patch_menu_class(MultiColumnCompletionMenuControl)


def _on_startup() -> None:
    try:
        _install_patch()
    except Exception as exc:
        # Plugin rule #4: fail gracefully — never crash the app.
        _emit_error(f"wide_completion_menu: failed to install patch — {exc}")


# ---------------------------------------------------------------------------
# /widemenu slash command
# ---------------------------------------------------------------------------
_USAGE = "Usage: /widemenu [on|off|toggle|status]"


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            _COMMAND_NAME,
            "Toggle full-width completion menu (scrollbar pinned to screen edge)",
        )
    ]


def _handle_widemenu_command(command: str) -> bool:
    # `command` is the full line, e.g. "/widemenu on". Strip the slash + name.
    parts = command.strip().split()
    arg = parts[1].lower() if len(parts) >= 2 else "status"

    if arg in ("on", "enable", "true", "1"):
        _state["enabled"] = True
        _emit_info("🫧 widemenu: ON — scrollbar pinned to right edge of screen.")
    elif arg in ("off", "disable", "false", "0"):
        _state["enabled"] = False
        _emit_info("🫧 widemenu: OFF — menu sized to content (default).")
    elif arg in ("toggle", "t"):
        _state["enabled"] = not _state["enabled"]
        status = "ON" if _state["enabled"] else "OFF"
        _emit_info(f"🫧 widemenu: {status}")
    elif arg == "status":
        status = "ON" if _state["enabled"] else "OFF"
        _emit_info(f"🫧 widemenu is currently {status}. {_USAGE}")
    else:
        _emit_info(_USAGE)
    return True


def _handle_custom_command(command: str, name: str):
    if name != _COMMAND_NAME:
        return None
    return _handle_widemenu_command(command)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
register_callback("startup", _on_startup)
register_callback("custom_command", _handle_custom_command)
register_callback("custom_command_help", _custom_help)


__all__ = [
    "_handle_custom_command",
    "_handle_widemenu_command",
    "_install_patch",
    "_on_startup",
    "_patch_menu_class",
]
