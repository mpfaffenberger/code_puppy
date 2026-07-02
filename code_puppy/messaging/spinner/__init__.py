"""DEPRECATED compat shim — the Rich Live puppy spinner is gone.

Phase 3 of the bottom-bar rewrite replaced the spinner with a persistent
bottom prompt: a DECSTBM scroll region managed by
``code_puppy.messaging.bottom_bar``, with the old spinner "context info"
(token usage etc.) now riding the bottom bar's status line.

This package survives purely so out-of-tree plugins that import it don't
crash:

* ``pause_all_spinners`` / ``resume_all_spinners`` /
  ``register_spinner`` / ``unregister_spinner`` — no-ops.
* ``update_spinner_context(info)`` — forwards to
  ``get_bottom_bar().set_status(info)``.
* ``clear_spinner_context()`` — clears the status line.
* ``format_context_info(...)`` — the token-summary formatter that used
  to live on ``SpinnerBase``.
* ``ConsoleSpinner`` — an inert stub (context-manager compatible).

New code should use ``code_puppy.messaging.bottom_bar`` directly.
"""

import logging
from typing import Any, List

logger = logging.getLogger(__name__)

#: Always empty now. Kept because a few call sites (and out-of-tree
#: plugins) import it to poke at active spinners.
_active_spinners: List[Any] = []


def register_spinner(spinner: Any) -> None:
    """No-op (deprecated): there are no spinners to register."""


def unregister_spinner(spinner: Any) -> None:
    """No-op (deprecated): there are no spinners to unregister."""


def pause_all_spinners() -> None:
    """No-op (deprecated): the bottom bar lives outside the scroll region.

    Code that takes over the whole terminal should use
    ``code_puppy.messaging.run_ui.suspended_run_ui()`` instead.
    """


def resume_all_spinners() -> None:
    """No-op (deprecated): see :func:`pause_all_spinners`."""


def _compact_count(n: int) -> str:
    """1234 -> '1.2k', 500000 -> '500k', 1500000 -> '1.5M'."""
    for threshold, suffix in ((1_000_000, "M"), (1_000, "k")):
        if n >= threshold:
            text = f"{n / threshold:.1f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return str(n)


def format_context_info(total_tokens: int, capacity: int, proportion: float) -> str:
    """Create a compact context summary for the status line.

    e.g. ``150.3k/500k tokens (30%)`` — the old long form
    (``Tokens: 150,329/500,000 (30.1% used)``) ate half the row.
    """
    if capacity <= 0:
        return ""
    return (
        f"{_compact_count(total_tokens)}/{_compact_count(capacity)} "
        f"tokens ({proportion * 100:.0f}%)"
    )


def update_spinner_context(info: str) -> None:
    """Forward the old spinner context line to the bottom-bar status row.

    Sub-agent writes are dropped: sub-agents run their own compaction
    (which calls this), and letting them win the single status row would
    stomp the MAIN agent's token summary mid-turn. Unlike the old
    ``pause_all_spinners`` gate there is no high-output-mode exception —
    that exception existed for inline stream/Live coordination, which
    doesn't apply to a status row that describes the main context.
    (Sub-agent status lives on the panel rows via ``set_panel_lines``.)
    """
    try:
        from code_puppy.tools.subagent_context import is_subagent
    except ImportError:
        is_subagent = None
    if is_subagent is not None and is_subagent():
        return
    try:
        from code_puppy.messaging.bottom_bar import get_bottom_bar

        get_bottom_bar().set_status(info or "")
    except Exception:
        # Deprecated shim — must never take the app down.
        logger.debug("status forward failed", exc_info=True)


def clear_spinner_context() -> None:
    """Clear the bottom-bar status row (formerly the spinner context)."""
    update_spinner_context("")


class ConsoleSpinner:
    """Inert stub of the old Rich Live spinner (deprecated).

    Exists only so out-of-tree plugins that instantiate or patch it keep
    importing. Every method is a no-op; the context-manager protocol is
    preserved.
    """

    def __init__(self, console: Any = None) -> None:
        self.console = console

    def start(self) -> None:
        """No-op."""

    def stop(self) -> None:
        """No-op."""

    def pause(self) -> None:
        """No-op."""

    def resume(self) -> None:
        """No-op."""

    def __enter__(self) -> "ConsoleSpinner":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False


__all__ = [
    "ConsoleSpinner",
    "register_spinner",
    "unregister_spinner",
    "pause_all_spinners",
    "resume_all_spinners",
    "format_context_info",
    "update_spinner_context",
    "clear_spinner_context",
]
