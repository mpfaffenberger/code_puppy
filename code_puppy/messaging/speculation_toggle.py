"""Ctrl+X Ctrl+S: toggle speculative execution for every agent.

Flips ``enable_speculative_code_mode`` in config and rebuilds the current
agent so the very next turn honours the new setting; a run already in
flight keeps the agent it started with. The pinned speculation row is
refreshed as visible feedback (it collapses while speculation is off), and
a one-line notice lands in the transcript.

Same threading contract as the ``$EDITOR`` chord: the key-listener thread
only schedules a coroutine on the captured loop; config I/O and the agent
rebuild run there, never on the listener.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from code_puppy.config import (
    get_speculative_code_mode_enabled,
    set_speculative_code_mode_enabled,
)
from code_puppy.i18n import t

logger = logging.getLogger(__name__)

#: Same LoopGetter contract as run_ui_wiring.
LoopGetter = Callable[[], Optional[asyncio.AbstractEventLoop]]

CHORD_KEY = "\x13"  # Ctrl+S
CHORD_HINT = "Ctrl+S toggle speculation"


def toggle_speculation() -> bool:
    """Flip the switch, rebuild the current agent, report. Returns the new state."""
    enabled = not get_speculative_code_mode_enabled()
    set_speculative_code_mode_enabled(enabled)
    _rebuild_current_agent()
    _refresh_row()
    from .message_queue import emit_info

    emit_info(t("speculation.enabled" if enabled else "speculation.disabled"))
    return enabled


def make_speculation_toggle_handler(get_loop: LoopGetter) -> Callable[[], None]:
    """Ctrl+X Ctrl+S: hop the toggle onto the loop; never block the listener."""

    def _handler() -> None:
        loop = get_loop()
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(_toggle_session(), loop)
        except RuntimeError:
            pass  # loop shut down between check and call

    return _handler


async def _toggle_session() -> None:
    try:
        toggle_speculation()
    except Exception:
        logger.debug("speculation toggle failed", exc_info=True)


def _rebuild_current_agent() -> None:
    """Best-effort: the config write already stuck, a failed rebuild only
    delays the switch until the next reload."""
    try:
        from code_puppy.agents.agent_manager import get_current_agent

        get_current_agent().reload_code_generation_agent()
    except Exception:
        logger.debug("agent rebuild after speculation toggle failed", exc_info=True)


def _refresh_row() -> None:
    from .speculation_stats import refresh_speculation_status

    refresh_speculation_status()


__all__ = [
    "CHORD_HINT",
    "CHORD_KEY",
    "make_speculation_toggle_handler",
    "toggle_speculation",
]
