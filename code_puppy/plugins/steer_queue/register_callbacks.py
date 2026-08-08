"""Register callbacks for the ``steer_queue`` plugin.

Mid-run Enter now QUEUES by default (see ``line_editor``); this plugin
supplies the rest of the feature:

* ``/steer <text>`` -- inject guidance mid-turn, interrupting the
  agent's current train of thought ASAP (the old Enter default). At
  idle it's a no-op with a hint: just type at the prompt.
* ``/queue`` -- full-screen queue manager with prompt preview, multiline
  add/edit, guarded delete, and reordering. Works at idle and mid-run: both
  paths already release the terminal around command execution.
* Status suffix -- a ``(N queued)`` tag rides the bottom bar's status
  row, updated live via the PauseController's steer-queue listeners
  (submit, drain, TUI edits -- every mutation fires them).
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

_STEER = "steer"
_QUEUE = "queue"


def _emit_info(message: str) -> None:
    from code_puppy.messaging import emit_info

    emit_info(message)


def _emit_warning(message: str) -> None:
    from code_puppy.messaging import emit_warning

    emit_warning(message)


# ---------------------------------------------------------------------------
# /steer
# ---------------------------------------------------------------------------
def _handle_steer(command: str) -> bool:
    text = command.split(" ", 1)[1].strip() if " " in command else ""
    if not text:
        _emit_info("Usage: /steer <message> \u2014 inject guidance mid-turn")
        return True

    from code_puppy.messaging.run_ui import is_run_active

    if not is_run_active():
        _emit_warning(
            "No agent run in flight \u2014 just type your prompt; "
            "/steer only makes sense while the agent is working."
        )
        return True

    from code_puppy.messaging.pause_controller import get_pause_controller

    # mode='now': drained by the steer history processor at the next
    # model call. The processor announces the injection in the
    # transcript, so no ack here (acking twice was the old bug).
    get_pause_controller().request_steer(text, mode="now")
    return True


# ---------------------------------------------------------------------------
# /queue
# ---------------------------------------------------------------------------
def _handle_queue(command: str) -> bool:
    from .queue_menu import open_queue_menu_blocking

    open_queue_menu_blocking()
    _emit_queue_summary()
    return True


def _emit_queue_summary() -> None:
    from code_puppy.messaging.pause_controller import get_pause_controller

    count = len(get_pause_controller().peek_pending_steer_queued())
    if count:
        _emit_info(f"\u23ed {count} prompt(s) queued")
    else:
        _emit_info("Queue is empty")


# ---------------------------------------------------------------------------
# Status suffix: '(N queued)'
# ---------------------------------------------------------------------------
def _update_status_suffix(count: int) -> None:
    """Steer-queue listener: paint/clear the pending-count tag.

    ``count`` is the TOTAL across both queues (now + queued), so the
    suffix is on whenever EITHER queue holds something. ``/steer`` uses
    ``mode="now"``; that steer sits in the now-queue until the history
    processor drains it, so the suffix tags the whole window between
    submit and injection.
    """
    try:
        from code_puppy.messaging.bottom_bar import get_bottom_bar

        get_bottom_bar().set_status_suffix(f" ({count} pending)" if count else "")
    except Exception:
        logger.debug("pending-count paint failed", exc_info=True)


def _on_startup() -> None:
    try:
        from code_puppy.messaging.pause_controller import get_pause_controller

        get_pause_controller().add_steer_queue_listener(_update_status_suffix)
    except Exception:
        logger.debug("steer_queue startup failed", exc_info=True)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if name == _STEER:
        return _handle_steer(command)
    if name == _QUEUE:
        return _handle_queue(command)
    return None


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (_STEER, "Inject guidance mid-turn while the agent is running"),
        (_QUEUE, "Manage queued prompts in a full-screen TUI"),
    ]


# ── Textual TUI integration ─────────────────────────────────────────
# The prompt_toolkit queue menu (arrow_select_async / PromptSession) assumes
# suspended_run_ui handed it the terminal; there's no run-UI to suspend in the
# Textual app, so it no-ops / corrupts the screen. The TUI opens a native
# ModalScreen over the same PauseController steer-queue instead. register_screen
# is consumed only by the Textual UI; classic mode is unaffected.
def _register_queue_screen():
    from .queue_tui import open_queue

    return [{"command": "queue", "open": open_queue}]


register_callback("startup", _on_startup)
register_callback("custom_command", _handle_custom_command)
register_callback("custom_command_help", _custom_help)
register_callback("register_screen", _register_queue_screen)


__all__ = [
    "_handle_custom_command",
    "_handle_queue",
    "_handle_steer",
    "_on_startup",
    "_register_queue_screen",
    "_update_status_suffix",
]
