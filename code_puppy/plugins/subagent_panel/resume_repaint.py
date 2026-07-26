"""Repaint the sub-agent panel after a pause -> resume transition.

During a sub-agent swarm the main agent is blocked inside the
invoke_agent tool await, so no stream events arrive to trigger the
normal event-driven ``_push_panel`` repaint. If the PauseController
paused and then resumed in that window (renderer buffering may have
scrolled output over the bar), this module gives subagent_panel its own
tiny wake-up path: force-push the panel lines to the bottom bar on every
resume, plus on ``ResumeAgentCommand`` from the message bus.
"""

from __future__ import annotations

import threading
from typing import Callable, Protocol


class _State(Protocol):
    def has_active(self) -> bool: ...


_runtime_enabled: Callable[[], bool] | None = None
_state: _State | None = None
_repaint: Callable[..., None] | None = None
_install_lock = threading.Lock()
_installed = False


def install(
    runtime_enabled: Callable[[], bool],
    state: _State,
    repaint: Callable[..., None],
) -> None:
    """Install resume/repaint hooks. Safe to call repeatedly.

    Args:
        runtime_enabled: The plugin's runtime on/off switch.
        state: The sub-agent registry (for the active-swarm guard).
        repaint: Callable pushing the panel to the bottom bar; invoked
            with ``force=True``.
    """
    global _installed, _runtime_enabled, _state, _repaint
    with _install_lock:
        _runtime_enabled = runtime_enabled
        _state = state
        _repaint = repaint
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
    """Force-push the panel now; no retries needed — set_panel_lines is a
    direct synchronous paint on the reserved rows, not a Live rebuild."""
    if not _active_swarm():
        return
    if _repaint is None:
        return
    try:
        _repaint(force=True)
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
