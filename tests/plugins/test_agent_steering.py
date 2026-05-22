"""Tests for the agent_steering plugin (Phase 3)."""

from __future__ import annotations

from typing import List

import pytest

from code_puppy.agents import _key_listeners
from code_puppy.callbacks import _callbacks
from code_puppy.messaging import (
    SteerAgentCommand,
    reset_message_bus,
)
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)
from code_puppy.plugins.agent_steering import register_callbacks as plugin


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset bus + controller + active handle; leave ``_callbacks`` alone.

    Earlier versions of this fixture did ``clear_callbacks()`` + restore-from-
    snapshot, but that wiped plugin registrations other tests depend on (the
    suite-wide ``_callbacks`` dict is module-level global state). The plugin
    under test only mutates the bus, the controller, and the active handle;
    reset just those.
    """
    reset_message_bus()
    reset_pause_controller()
    _key_listeners.set_active_handle(None)
    yield
    reset_message_bus()
    reset_pause_controller()
    _key_listeners.set_active_handle(None)


# =============================================================================
# Helpers — spy on bus.provide_response to capture command ordering
# =============================================================================


class _BusSpy:
    """Wraps the global bus to record every command sent via provide_response."""

    def __init__(self) -> None:
        from code_puppy.messaging import get_message_bus

        self.bus = get_message_bus()
        self.commands: List[object] = []
        self._orig = self.bus.provide_response
        self.bus.provide_response = self._recording  # type: ignore[assignment]

    def _recording(self, command: object) -> None:
        self.commands.append(command)
        self._orig(command)

    def restore(self) -> None:
        self.bus.provide_response = self._orig  # type: ignore[assignment]


@pytest.fixture
def bus_spy():
    spy = _BusSpy()
    yield spy
    spy.restore()


# =============================================================================
# _on_pause_requested — submit path
# =============================================================================


@pytest.mark.asyncio
async def test_on_pause_requested_submits_steer_and_resumes(monkeypatch, bus_spy):
    # Editor returns (text, mode); the legacy plain-string return is gone.
    monkeypatch.setattr(
        plugin,
        "collect_steering_message",
        lambda: ("please add error handling", "now"),
    )

    await plugin._on_pause_requested()

    types = [type(c).__name__ for c in bus_spy.commands]
    assert types == [
        "PauseAgentCommand",
        "SteerAgentCommand",
        "ResumeAgentCommand",
    ], f"unexpected command order: {types}"

    steer = bus_spy.commands[1]
    assert isinstance(steer, SteerAgentCommand)
    assert steer.text == "please add error handling"
    assert steer.mode == "now"

    # Final controller state should be resumed, now-queue holds the steer.
    pc = get_pause_controller()
    assert pc.is_paused() is False
    assert pc.drain_pending_steer_now() == ["please add error handling"]


# =============================================================================
# _on_pause_requested — abort path
# =============================================================================


@pytest.mark.asyncio
async def test_on_pause_requested_abort_resumes_without_steer(monkeypatch, bus_spy):
    monkeypatch.setattr(plugin, "collect_steering_message", lambda: None)

    await plugin._on_pause_requested()

    types = [type(c).__name__ for c in bus_spy.commands]
    assert types == ["PauseAgentCommand", "ResumeAgentCommand"]
    pc = get_pause_controller()
    assert pc.is_paused() is False
    assert pc.drain_pending_steer() == []


@pytest.mark.asyncio
async def test_on_pause_requested_whitespace_only_treated_as_abort(
    monkeypatch, bus_spy
):
    # Defensive: even if a malformed editor returns whitespace-only text
    # in a tuple (shouldn't happen — collect_steering_message strips and
    # returns None), the plugin's guard still rejects it.
    monkeypatch.setattr(plugin, "collect_steering_message", lambda: ("   ", "now"))

    await plugin._on_pause_requested()

    types = [type(c).__name__ for c in bus_spy.commands]
    assert types == ["PauseAgentCommand", "ResumeAgentCommand"]


@pytest.mark.asyncio
async def test_on_pause_requested_handles_prompt_exception(monkeypatch, bus_spy):
    def _boom() -> str:
        raise RuntimeError("prompt_toolkit hates us today")

    monkeypatch.setattr(plugin, "collect_steering_message", _boom)

    # Should NOT raise; should still resume.
    await plugin._on_pause_requested()

    types = [type(c).__name__ for c in bus_spy.commands]
    assert types == ["PauseAgentCommand", "ResumeAgentCommand"]


# =============================================================================
# Registration smoke — Ctrl+T is the ONLY entry point (the typed /steer
# slash command was removed because slash commands can only fire at the
# input prompt, which is unavailable while the agent is running).
# =============================================================================


def test_plugin_registers_exactly_one_callback():
    """Importing the plugin module registers ONLY ``agent_pause_requested``."""
    assert plugin._on_pause_requested in _callbacks["agent_pause_requested"]
    # The plugin must not own any custom_command / custom_command_help hooks.
    assert not hasattr(plugin, "_handle_custom_command"), (
        "_handle_custom_command should have been deleted in the cleanup"
    )
    assert not hasattr(plugin, "_custom_help"), (
        "_custom_help should have been deleted in the cleanup"
    )


# =============================================================================
# Key-listener suspend/resume contract (Bug 1 fix-up)
# =============================================================================


class _SpyHandle:
    """Minimal stand-in for KeyListenerHandle that records suspend/resume."""

    def __init__(self, suspend_returns: bool = True) -> None:
        self.suspend_returns = suspend_returns
        self.suspend_calls: list[float] = []
        self.resume_calls: int = 0

    def suspend(self, timeout: float = 1.0) -> bool:
        self.suspend_calls.append(timeout)
        return self.suspend_returns

    def resume(self) -> None:
        self.resume_calls += 1


@pytest.mark.asyncio
async def test_on_pause_requested_suspends_and_resumes_active_handle(
    monkeypatch, bus_spy
):
    """When a handle is published, the plugin must suspend + resume it
    around the editor invocation.
    """
    handle = _SpyHandle()
    _key_listeners.set_active_handle(handle)
    monkeypatch.setattr(plugin, "collect_steering_message", lambda: ("hi", "now"))

    await plugin._on_pause_requested()

    assert len(handle.suspend_calls) == 1
    assert handle.resume_calls == 1


@pytest.mark.asyncio
async def test_on_pause_requested_resumes_handle_even_on_editor_exception(
    monkeypatch, bus_spy
):
    """If the editor blows up, ``handle.resume()`` MUST still fire so we
    don't leave the terminal hung.
    """
    handle = _SpyHandle()
    _key_listeners.set_active_handle(handle)

    def _boom() -> str:
        raise RuntimeError("editor exploded")

    monkeypatch.setattr(plugin, "collect_steering_message", _boom)

    await plugin._on_pause_requested()

    assert handle.resume_calls == 1


@pytest.mark.asyncio
async def test_on_pause_requested_no_handle_path_does_not_crash(monkeypatch, bus_spy):
    """In test/non-TTY contexts, ``get_active_handle()`` returns None — the
    plugin must still complete the pause→steer→resume bus dance.
    """
    _key_listeners.set_active_handle(None)
    monkeypatch.setattr(plugin, "collect_steering_message", lambda: ("hi", "now"))

    # No assertion needed beyond "didn't crash"; the bus_spy invariants
    # already confirm correctness.
    await plugin._on_pause_requested()

    types = [type(c).__name__ for c in bus_spy.commands]
    assert types == ["PauseAgentCommand", "SteerAgentCommand", "ResumeAgentCommand"]


@pytest.mark.asyncio
async def test_on_pause_requested_warns_if_suspend_times_out(monkeypatch, bus_spy):
    """When suspend() returns False, we still proceed but warn the user."""
    handle = _SpyHandle(suspend_returns=False)
    _key_listeners.set_active_handle(handle)
    warnings: list[str] = []
    monkeypatch.setattr(plugin, "emit_warning", lambda msg: warnings.append(msg))
    monkeypatch.setattr(plugin, "collect_steering_message", lambda: ("ok", "now"))

    await plugin._on_pause_requested()

    assert any("Could not suspend" in w for w in warnings), (
        f"expected suspend-timeout warning, got: {warnings!r}"
    )
    # And we still resume the handle (no leak).
    assert handle.resume_calls == 1


# =============================================================================
# Spinner-teardown ordering (Bug fix: spinner litter under steering editor)
# =============================================================================


@pytest.mark.asyncio
async def test_on_pause_requested_calls_pause_all_spinners_before_editor(
    monkeypatch, bus_spy
):
    """Plugin MUST tear down the spinner BEFORE launching the editor.

    Otherwise the Rich Live display + prompt_toolkit fight over the
    terminal, and the editor's cursor lands on top of "Biscuit is
    thinking... 🐶 Tokens: …". Order is captured via a shared list so
    we can lock down the exact sequence.
    """
    call_order: list[str] = []

    def _spy_pause_all_spinners() -> None:
        call_order.append("pause_all_spinners")

    def _spy_collect_steering_message() -> tuple[str, str]:
        call_order.append("collect_steering_message")
        return ("do the thing", "now")

    # Patch where the plugin LOOKS UP each symbol (plugin module re-exports
    # both via its top-level imports).
    monkeypatch.setattr(plugin, "pause_all_spinners", _spy_pause_all_spinners)
    monkeypatch.setattr(
        plugin, "collect_steering_message", _spy_collect_steering_message
    )

    await plugin._on_pause_requested()

    # Spinner MUST go down BEFORE the editor opens.
    assert "pause_all_spinners" in call_order, (
        f"pause_all_spinners was never called: {call_order!r}"
    )
    assert "collect_steering_message" in call_order
    assert call_order.index("pause_all_spinners") < call_order.index(
        "collect_steering_message"
    ), (
        f"pause_all_spinners must fire BEFORE collect_steering_message, "
        f"got: {call_order!r}"
    )


# =============================================================================
# Queue-mode submission path
# =============================================================================


@pytest.mark.asyncio
async def test_on_pause_requested_with_queue_mode_lands_in_queued_queue(
    monkeypatch, bus_spy
):
    """When the user picks ``queue`` mode in the editor, the resulting
    SteerAgentCommand MUST carry mode='queue' so the bus routes it into
    the queued queue (where ``_runtime._do_run`` will drain it between
    turns), not the now queue (owned by the history processor).
    """
    monkeypatch.setattr(
        plugin,
        "collect_steering_message",
        lambda: ("write tests after you're done", "queue"),
    )

    await plugin._on_pause_requested()

    steer = bus_spy.commands[1]
    assert isinstance(steer, SteerAgentCommand)
    assert steer.mode == "queue"
    assert steer.text == "write tests after you're done"

    pc = get_pause_controller()
    assert pc.has_pending_steer_queued() is True
    assert pc.has_pending_steer_now() is False
    assert pc.drain_pending_steer_queued() == ["write tests after you're done"]


@pytest.mark.asyncio
async def test_on_pause_requested_returns_none_treated_as_abort(monkeypatch, bus_spy):
    """The new collect_steering_message returns None on cancel/empty —
    plugin must treat that as abort, not crash on tuple unpacking.
    """
    monkeypatch.setattr(plugin, "collect_steering_message", lambda: None)

    await plugin._on_pause_requested()

    types = [type(c).__name__ for c in bus_spy.commands]
    assert types == ["PauseAgentCommand", "ResumeAgentCommand"]
