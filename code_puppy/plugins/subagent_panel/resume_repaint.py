"""Repaint the sub-agent panel after Ctrl+T steering resumes.

The status panel lives inside the main ConsoleSpinner Rich Live. Michael's
raw steer intentionally tears that Live down while collecting input. During a
sub-agent swarm the main agent is blocked inside the invoke_agent tool await,
so the normal event_stream_handler PartEndEvent path cannot rebuild the Live.
This module gives subagent_panel its own tiny wake-up path, without touching
steer itself.
"""

from __future__ import annotations

import threading
from typing import Callable, Protocol


class _State(Protocol):
    def has_active(self) -> bool: ...


_runtime_enabled: Callable[[], bool] | None = None
_state: _State | None = None
_install_lock = threading.Lock()
_repaint_lock = threading.RLock()
_installed = False


def install(runtime_enabled: Callable[[], bool], state: _State) -> None:
    """Install resume/repaint hooks. Safe to call repeatedly."""
    global _installed, _runtime_enabled, _state
    with _install_lock:
        _runtime_enabled = runtime_enabled
        _state = state
        if _installed:
            return
        _installed = True
    _install_resume_listener()
    _install_bus_resume_hook()


def _active_swarm() -> bool:
    try:
        if _runtime_enabled is None or _state is None:
            return False
        if not _runtime_enabled():
            return False
        if not _state.has_active():
            return False
        from code_puppy.messaging.pause_controller import get_pause_controller
        from code_puppy.tools.command_runner import is_awaiting_user_input

        return not get_pause_controller().is_paused() and not is_awaiting_user_input()
    except Exception:
        return False


def _request_repaint(_reason: str = "resume") -> None:
    """Try now and retry shortly after prompt teardown/renderer flush races."""
    if not _active_swarm():
        return
    _repaint_once()
    for delay in (0.05, 0.20, 0.50):
        timer = threading.Timer(delay, _repaint_once)
        timer.daemon = True
        timer.start()


def _repaint_once() -> None:
    if not _active_swarm():
        return
    with _repaint_lock:
        if not _active_swarm():
            return
        try:
            from code_puppy.messaging.spinner import resume_all_spinners

            resume_all_spinners()
        except Exception:
            pass
        _force_refresh_active_spinners()


def _force_refresh_active_spinners() -> None:
    try:
        from code_puppy.messaging.spinner import _active_spinners
    except Exception:
        return
    for spinner in list(_active_spinners):
        try:
            _force_refresh_spinner(spinner)
        except Exception:
            pass


def _force_refresh_spinner(spinner) -> None:
    if not getattr(spinner, "_is_spinning", False):
        return
    # If ConsoleSpinner.resume() missed its moment, force the same invariant:
    # an unpaused spinner with a live Rich surface containing our patched panel.
    try:
        spinner._paused = False
    except Exception:
        pass

    live = getattr(spinner, "_live", None)
    if live is None:
        _start_live(spinner)
        return

    try:
        live.update(spinner._generate_spinner_panel())
        live.refresh()
    except Exception:
        pass


def _start_live(spinner) -> None:
    try:
        from rich.live import Live

        console = getattr(spinner, "console", None)
        if console is None:
            return
        console.print()
        live = Live(
            spinner._generate_spinner_panel(),
            console=console,
            refresh_per_second=20,
            transient=True,
            auto_refresh=False,
        )
        spinner._live = live
        live.start()
    except Exception:
        pass


def _install_resume_listener() -> None:
    try:
        from code_puppy.messaging.pause_controller import get_pause_controller

        get_pause_controller().add_resume_listener(_request_repaint)
    except Exception:
        pass


def _install_bus_resume_hook() -> None:
    try:
        from code_puppy.messaging.bus import MessageBus
    except Exception:
        return

    current = MessageBus.provide_response
    if getattr(current, "_subagent_panel_resume_repaint", False):
        return

    def _wrapped(self, command):
        result = current(self, command)
        try:
            if type(command).__name__ == "ResumeAgentCommand":
                _request_repaint("resume-command")
        except Exception:
            pass
        return result

    _wrapped._subagent_panel_resume_repaint = True
    MessageBus.provide_response = _wrapped
