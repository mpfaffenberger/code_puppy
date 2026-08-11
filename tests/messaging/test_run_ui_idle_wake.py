"""Tests for the idle-prompt wake-on-queued-steer path.

Regression: a queue-mode steer (for example a message routed in by the
``cp_discord`` plugin) that arrived while the REPL was parked at the idle
prompt used to sit unseen until the user typed something at the terminal --
nothing woke the blocked ``wait_for_idle_submission``. The pause-queue
listener now nudges the idle prompt so the message runs as a fresh turn.
"""

from __future__ import annotations

import asyncio

import pytest

from code_puppy.messaging import run_ui
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_pause_controller()
    yield
    reset_pause_controller()


# =============================================================================
# _on_steer_queue_change: when to wake the idle prompt
# =============================================================================


def test_queued_steer_wakes_idle_prompt(monkeypatch):
    """A pending queue-mode steer at idle wakes the parked prompt."""
    woke: list[int] = []
    monkeypatch.setattr(run_ui, "is_run_active", lambda: False)
    monkeypatch.setattr(run_ui, "wake_idle_for_queued_steer", lambda: woke.append(1))

    get_pause_controller().request_steer("discord msg", mode="queue")
    run_ui._on_steer_queue_change(1)

    assert woke == [1]


def test_now_steer_does_not_wake_idle_prompt(monkeypatch):
    """now-mode steers are drained by the run's history processor, not the
    idle loop -- so with only a now-mode steer pending we must NOT wake.
    """
    woke: list[int] = []
    monkeypatch.setattr(run_ui, "is_run_active", lambda: False)
    monkeypatch.setattr(run_ui, "wake_idle_for_queued_steer", lambda: woke.append(1))

    get_pause_controller().request_steer("now msg", mode="now")
    run_ui._on_steer_queue_change(1)

    assert woke == []


def test_no_wake_while_run_active(monkeypatch):
    """A run in flight drains queued steers via _runtime's between-turns
    loop; the idle wake must stay out of its way.
    """
    woke: list[int] = []
    monkeypatch.setattr(run_ui, "is_run_active", lambda: True)
    monkeypatch.setattr(run_ui, "wake_idle_for_queued_steer", lambda: woke.append(1))

    get_pause_controller().request_steer("mid-run queued", mode="queue")
    run_ui._on_steer_queue_change(1)

    assert woke == []


def test_listener_swallows_errors(monkeypatch):
    """The listener runs on the steer-producer thread and must never raise."""

    def _boom() -> bool:
        raise RuntimeError("state boom")

    monkeypatch.setattr(run_ui, "is_run_active", _boom)

    # Must not propagate.
    run_ui._on_steer_queue_change(1)


# =============================================================================
# wait_for_idle_submission: the wake sentinel round-trips
# =============================================================================


async def test_wait_for_idle_submission_returns_wake_sentinel(monkeypatch):
    """When the wake sentinel is pushed, the blocked wait returns IDLE_WAKE
    so the REPL loop can re-check ``pop_next_steer_queued``.
    """
    q: asyncio.Queue = asyncio.Queue()
    monkeypatch.setattr(run_ui, "_idle_queue", q)
    await q.put(run_ui._WAKE)

    result = await run_ui.wait_for_idle_submission()

    assert result is run_ui.IDLE_WAKE


async def test_wait_for_idle_submission_still_returns_plain_text(monkeypatch):
    """A normal submission is unaffected by the new sentinel handling."""
    q: asyncio.Queue = asyncio.Queue()
    monkeypatch.setattr(run_ui, "_idle_queue", q)
    await q.put("hello puppy")

    result = await run_ui.wait_for_idle_submission()

    assert result == "hello puppy"
