"""Submission routing and prompt repaint helpers for ``RunningLineEditor``."""

from __future__ import annotations

import logging
from typing import Optional

from .editor_display import to_display

logger = logging.getLogger(__name__)


class QueuedFeedback(str):
    """Marker for feedback that belongs in the dedicated queued renderer."""


def toggle_multiline(editor) -> None:
    editor._multiline = not editor._multiline
    editor._repaint()


def resolve_esc_timeout(editor) -> None:
    """Resolve a bare Esc after the sequence-disambiguation window."""
    if editor._esc_pending_at is None:
        return
    if editor._now() - editor._esc_pending_at <= editor._esc_timeout:
        return
    editor._esc_pending_at = None
    if editor._rsearch.active:
        editor._rsearch.cancel()
        editor._set_completion_suppressed(False)
        editor._repaint()
    elif editor._completion_open():
        editor._close_completion()


def submit_buffer(editor, mode: str) -> Optional[str]:
    """Route the current buffer and return a transcript feedback line, if any."""
    text = editor._buffer
    queue_route = editor._queued_messages.prepare_submit(text, mode)
    editor._buffer = ""
    editor._cursor = 0
    editor._close_completion()
    editor._repaint()

    stripped = text.strip()
    if not stripped:
        return None

    try:
        editor._history.record_submit(text)
    except Exception:
        logger.debug("history record failed", exc_info=True)

    # Plain Enter while editing a queued item updates it in place. There is no
    # second submission to route (which would duplicate the queued turn).
    if queue_route is False:
        return None

    router = editor._router
    if router is not None:
        try:
            feedback = router(text, mode)
        except Exception:
            logger.debug("submit router failed", exc_info=True)
            feedback = None
    else:
        feedback = route_default(editor, text, mode)

    for listener in list(editor._submit_listeners):
        try:
            listener(stripped, mode)
        except Exception:
            logger.debug("submit listener failed", exc_info=True)
    return feedback


def _parse_steer_command(stripped: str) -> Optional[str]:
    """Return /steer content, an empty usage sentinel, or None."""
    if stripped == "/steer":
        return ""
    if stripped.startswith("/steer "):
        return stripped[len("/steer ") :].strip()
    return None


def route_default(editor, text: str, mode: str) -> Optional[str]:
    """Built-in mid-run routing: slash -> command queue, else steer."""
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("/"):
        steer_text = _parse_steer_command(stripped)
        if steer_text is not None:
            if not steer_text:
                return "Usage: /steer <message>"
            try:
                editor._resolve_controller().request_steer(steer_text, mode="now")
            except Exception:
                logger.debug("steer fast path failed", exc_info=True)
            return None
        editor._command_queue.put(stripped)
        return None
    try:
        editor._resolve_controller().request_steer(text, mode=mode)
    except Exception:
        logger.debug("request_steer failed", exc_info=True)
        return None
    if mode == "queue":
        return QueuedFeedback(f"for next turn: {stripped[:60]}")
    return None


def emit_feedback(note: str) -> None:
    """Best-effort transcript line for a successful steer submission."""
    try:
        from code_puppy.messaging.message_queue import emit_info, emit_queued

        if isinstance(note, QueuedFeedback):
            emit_queued(str(note))
        else:
            emit_info(note)
    except Exception:
        logger.debug("feedback emit failed", exc_info=True)


def repaint(editor) -> None:
    """Paint the current editor buffer into the persistent bottom bar."""
    try:
        bar = editor._resolve_bar()
        if editor._rsearch.active:
            text = editor._rsearch.prompt_text()
            bar.set_prompt_text("", text, len(text))
            return
        prefix = editor._prompt_prefix + ("[multiline] " if editor._multiline else "")
        display_text, display_cursor = to_display(editor._buffer, editor._cursor)
        bar.set_prompt_text(
            prefix, display_text, display_cursor, editor._prompt_prefix_sgrs
        )
    except Exception:
        # Painting is best-effort; the buffer state is the truth.
        pass


__all__ = [
    "emit_feedback",
    "repaint",
    "resolve_esc_timeout",
    "route_default",
    "submit_buffer",
    "toggle_multiline",
]
