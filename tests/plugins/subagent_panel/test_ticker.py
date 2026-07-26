"""Tests for the 1 Hz elapsed-clock ticker (eyeball-test bug #2).

The panel repaint is event-driven; the ticker keeps mm:ss advancing
during long silent model calls. Zero new threads — it's an asyncio task.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from code_puppy.plugins.subagent_panel import register_callbacks as rc
from code_puppy.plugins.subagent_panel import state


class FakeBar:
    def __init__(self):
        self.calls: list[list[str]] = []

    def set_panel_lines(self, lines):
        self.calls.append(list(lines))


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    state.clear()
    rc._stop_ticker()
    rc._push_state["t"] = 0.0
    rc._push_state["count"] = -1
    # Fast ticks so tests don't sleep for real seconds. The production
    # 1 Hz tick clears the 0.1s same-shape throttle by design; the fast
    # test ticks would NOT, so shrink the throttle proportionally.
    monkeypatch.setattr(rc, "_TICK_INTERVAL_S", 0.01)
    monkeypatch.setattr(rc, "_PUSH_MIN_INTERVAL", 0.0)
    yield
    rc._stop_ticker()
    state.clear()


@pytest.fixture
def bar(monkeypatch):
    fake = FakeBar()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: fake)
    return fake


# =========================================================================
# Start / idempotency / no-loop contexts
# =========================================================================


async def test_start_ticker_creates_task():
    rc._start_ticker()
    assert rc._ticker_task is not None
    assert not rc._ticker_task.done()


async def test_start_ticker_is_idempotent():
    rc._start_ticker()
    first = rc._ticker_task
    rc._start_ticker()
    assert rc._ticker_task is first  # no double-start


def test_start_ticker_without_loop_is_noop():
    """Outside an event loop the ticker degrades to event-driven only."""
    rc._start_ticker()  # must not raise
    assert rc._ticker_task is None


# =========================================================================
# Ticks repaint with advancing elapsed time
# =========================================================================


async def test_tick_pushes_updated_elapsed(bar):
    state.register("sid-1", "slow-worker", "gpt-5.4")
    # Backdate the start so the clock reads ~01:05 on the next tick.
    with state._LOCK:
        state._AGENTS["sid-1"]["start"] = time.time() - 65
    rc._start_ticker()
    await asyncio.sleep(0.05)  # several fast ticks
    assert bar.calls, "ticker never pushed"
    line = bar.calls[-1][0]
    assert "slow-worker" in line
    assert "01:0" in line  # elapsed re-derived from wall clock


async def test_ticks_keep_advancing_the_clock(bar):
    state.register("sid-1", "worker", "gpt-5.4")
    rc._start_ticker()
    await asyncio.sleep(0.03)
    first_count = len(bar.calls)
    # Backdate further — the NEXT tick must re-render with the new value.
    with state._LOCK:
        state._AGENTS["sid-1"]["start"] = time.time() - 30
    await asyncio.sleep(0.03)
    assert len(bar.calls) > first_count
    assert "00:30" in bar.calls[-1][0]


# =========================================================================
# Lifecycle: stop on completion / cancel / run end / self-termination
# =========================================================================


async def test_ticker_self_terminates_with_no_agents(bar):
    rc._start_ticker()
    task = rc._ticker_task
    await asyncio.sleep(0.05)  # first tick finds zero agents -> break
    assert task.done()
    assert rc._ticker_task is None  # cleared its own reference


async def test_last_completion_flush_stops_ticker(bar):
    class FakeConsole:
        def print(self, *a, **k):
            pass

    state.register("sid-1", "worker", "gpt-5.4")
    rc._start_ticker()
    task = rc._ticker_task
    state.mark_done("sid-1")
    rc._maybe_flush_group(FakeConsole())  # whole swarm idle -> flush + stop
    assert rc._ticker_task is None
    await asyncio.sleep(0)  # let the cancellation land
    assert task.done()
    assert bar.calls[-1] == []  # panel collapsed


async def test_agent_run_cancel_stops_ticker_and_collapses(bar):
    state.register("sid-1", "worker", "gpt-5.4")
    rc._start_ticker()
    task = rc._ticker_task
    await rc._on_agent_run_cancel("group-1")
    assert rc._ticker_task is None
    await asyncio.sleep(0)
    assert task.done()
    assert bar.calls[-1] == []
    assert state.snapshot() == []


async def test_agent_run_end_stops_ticker(bar):
    state.register("sid-1", "worker", "gpt-5.4")
    rc._start_ticker()
    task = rc._ticker_task
    await rc._on_agent_run_end(agent_name="main")
    assert rc._ticker_task is None
    await asyncio.sleep(0)
    assert task.done()


async def test_no_orphan_task_after_stop_ticker():
    rc._start_ticker()
    task = rc._ticker_task
    rc._stop_ticker()
    rc._stop_ticker()  # idempotent
    await asyncio.sleep(0)
    assert task.done()
    assert rc._ticker_task is None
