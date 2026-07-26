"""Register callbacks for the ``puppy_spinner`` plugin.

Resurrects the classic bouncing-puppy spinner on the persistent bottom
bar. The old Rich ``Live`` spinner died in the bottom-bar rewrite (its
compat shim in ``messaging.spinner`` forwards context text only); this
plugin animates the bar's dedicated status-PREFIX slot instead, so the
token-context info written via ``BottomBar.set_status`` is never
stomped -- two writers, two slots, one row.

Lifecycle:

* ``agent_run_start`` -- refcount +1; first active run starts a ~5 fps
  asyncio ticker task (same zero-thread pattern as ``subagent_panel``).
  Sub-agent runs fire these hooks too; the refcount naturally keeps the
  puppy running until the LAST run finishes.
* ``agent_run_end`` -- refcount -1 (fired from ``_runtime``'s ``finally``,
  so cancels/exceptions never leak a spin); at zero the ticker stops and
  the prefix slot is cleared.

Headless (``-p`` / non-TTY) runs never start the ticker: the bar is
inactive and output must stay byte-identical.

Customization (``/spinner``): the tick loop reads the active spinner
from ``spinners`` each iteration, so picking a new style in the TUI
(or simply editing ``spinners.json`` -- its mtime is watched) takes
effect on the very next frame, even mid-run.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from code_puppy.callbacks import register_callback

from . import commands, spinners

logger = logging.getLogger(__name__)

_PUPPY = spinners.PUPPY  # DOG FACE emoji, escape-spelled (repo emoji filter)

#: The classic kennel-bounce (the ``puppy`` entry in the spinner catalogue).
FRAMES = spinners.BUILTIN_SPINNERS[spinners.DEFAULT_SPINNER].frames

#: Sourced from the catalogue so the stock puppy's speed has exactly one
#: home; kept as a module constant so tests can monkeypatch the tempo.
_TICK_INTERVAL_S = spinners.BUILTIN_SPINNERS[spinners.DEFAULT_SPINNER].interval

_lock = threading.Lock()
_active_runs = 0
_ticker_task: Optional["asyncio.Task"] = None


def _bar():
    from code_puppy.messaging.bottom_bar import get_bottom_bar

    return get_bottom_bar()


# NOTE: the callback dispatcher passes hook arguments POSITIONALLY
# (``callback(*args, **kwargs)`` -- agent_run_end sends 7 of them), and
# this plugin uses none of them. Swallow everything, stay signature-proof.
async def _on_run_start(*_args, **_kw):
    global _active_runs
    with _lock:
        _active_runs += 1
    _start_ticker()


async def _on_run_end(*_args, **_kw):
    global _active_runs
    with _lock:
        _active_runs = max(0, _active_runs - 1)
        last_one_out = _active_runs == 0
    if last_one_out:
        _stop_ticker()
        _clear_prefix()


def _start_ticker() -> None:
    """Start the ticker task (idempotent; no loop or no bar = no puppy)."""
    global _ticker_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # sync/odd context: skip the animation entirely
    try:
        if not _bar().is_active():
            return  # headless / non-TTY: nothing to paint on
    except Exception:
        return
    with _lock:
        if _ticker_task is not None and not _ticker_task.done():
            return
        _ticker_task = loop.create_task(_tick_loop())


def _stop_ticker() -> None:
    """Cancel the ticker task if it's running. Idempotent."""
    global _ticker_task
    with _lock:
        task = _ticker_task
        _ticker_task = None
    if task is not None and not task.done():
        task.cancel()


async def _tick_loop() -> None:
    """Advance the puppy one cell per tick until no run is active.

    Just the animation -- no "<puppy> is thinking..." chatter. The
    status row is prime real estate; the token summary needs it more.
    """
    global _ticker_task
    frame = 0
    try:
        while True:
            with _lock:
                if _active_runs <= 0:
                    break  # belt-and-braces: never outlive the run
            frames, interval = _current_frames_and_interval()
            _paint_prefix(frames[frame % len(frames)])
            frame += 1
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
    finally:
        _clear_prefix()
        with _lock:
            if _ticker_task is asyncio.current_task():
                _ticker_task = None


def _current_frames_and_interval():
    """The active spinner's frames + interval, re-read every tick.

    The stock builtin puppy routes through the module constants so tests
    (and nostalgic monkeypatchers) can tweak ``_TICK_INTERVAL_S``; any
    other choice -- including a user-file override of "puppy" -- uses
    the catalogue values. A broken catalogue degrades to the classic.
    """
    try:
        active = spinners.get_active_spinner()
        is_stock_puppy = (
            active.name == spinners.DEFAULT_SPINNER
            and active.source == "builtin"
            and active.interval
            == spinners.BUILTIN_SPINNERS[
                spinners.DEFAULT_SPINNER
            ].interval  # a speed override on the puppy still counts as custom
        )
        if not is_stock_puppy:
            return active.frames, active.interval
    except Exception:
        logger.debug("active spinner lookup failed", exc_info=True)
    return FRAMES, _TICK_INTERVAL_S


#: Breathing room between the spinner frame and whatever the status bar
#: renders next. Applied at paint time so every spinner -- builtin or
#: user-authored -- gets the same gap without baking spaces into frames.
_PREFIX_GAP = "  "


def _paint_prefix(text: str) -> None:
    """Best-effort paint -- a broken bar must never kill the ticker.

    Non-empty frames get ``_PREFIX_GAP`` appended; clearing stays a
    true empty string so nothing lingers in the prefix slot.
    """
    try:
        _bar().set_status_prefix(text + _PREFIX_GAP if text else "")
    except Exception:
        logger.debug("puppy spinner paint failed", exc_info=True)


def _clear_prefix() -> None:
    _paint_prefix("")


register_callback("agent_run_start", _on_run_start)
register_callback("agent_run_end", _on_run_end)
register_callback("custom_command", commands.handle_spinner)
register_callback("custom_command_help", commands.help_entries)


__all__ = [
    "FRAMES",
    "_on_run_end",
    "_on_run_start",
    "_start_ticker",
    "_stop_ticker",
    "_tick_loop",
]
