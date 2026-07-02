"""Tests for the puppy_spinner plugin (the resurrected bouncing pup).

The spinner rides the bottom bar's status-PREFIX slot, refcounted by
agent_run_start/agent_run_end so nested (sub-agent) runs keep it alive
until the last run finishes.
"""

from __future__ import annotations

import asyncio

import pytest

from code_puppy.plugins.puppy_spinner import register_callbacks as rc


class FakeBar:
    def __init__(self, active: bool = True):
        self.active = active
        self.prefixes: list[str] = []

    def is_active(self) -> bool:
        return self.active

    def set_status_prefix(self, text: str) -> None:
        self.prefixes.append(text)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    rc._stop_ticker()
    rc._active_runs = 0
    monkeypatch.setattr(rc, "_TICK_INTERVAL_S", 0.01)
    yield
    rc._stop_ticker()
    rc._active_runs = 0


@pytest.fixture
def bar(monkeypatch):
    fake = FakeBar()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: fake)
    return fake


# =========================================================================
# Frames
# =========================================================================


def test_frames_bounce_there_and_back():
    """Eight frames: pup walks cells 0..4 then back, kennel width fixed."""
    assert len(rc.FRAMES) == 8
    positions = [frame.index(rc._PUPPY) for frame in rc.FRAMES]
    assert positions == [1, 2, 3, 4, 5, 4, 3, 2]  # offset by the '('
    # Every frame has the same shape: parens + 4 pad cells + trailing space.
    assert all(f.startswith("(") and f.endswith(") ") for f in rc.FRAMES)
    assert len({len(f) for f in rc.FRAMES}) == 1


# =========================================================================
# Lifecycle: start / paint / end / clear
# =========================================================================


async def test_run_start_spins_and_run_end_clears(bar):
    await rc._on_run_start(agent_name="a", model_name="m")
    assert rc._ticker_task is not None

    await asyncio.sleep(0.05)  # a few ticks
    painted = [p for p in bar.prefixes if p]
    assert painted, "ticker never painted a frame"
    assert all(rc._PUPPY in p for p in painted)
    # Frames only -- no "<puppy> is thinking..." chatter on the status row.
    assert all(p in rc.FRAMES for p in painted)

    await rc._on_run_end(agent_name="a", model_name="m", success=True)
    await asyncio.sleep(0.02)  # let the cancelled task run its finally
    assert bar.prefixes[-1] == ""  # slot cleared for the idle prompt
    assert rc._ticker_task is None


async def test_frames_advance_between_ticks(bar):
    await rc._on_run_start(agent_name="a", model_name="m")
    await asyncio.sleep(0.06)
    await rc._on_run_end(agent_name="a", model_name="m")
    painted = [p for p in bar.prefixes if p]
    assert len(set(painted)) > 1, "puppy never moved"


async def test_refcount_survives_nested_runs(bar):
    """Sub-agent start/end must NOT kill the main run's spinner."""
    await rc._on_run_start(agent_name="main", model_name="m")
    await rc._on_run_start(agent_name="sub", model_name="m")
    await rc._on_run_end(agent_name="sub", model_name="m")
    assert rc._ticker_task is not None and not rc._ticker_task.done()

    await rc._on_run_end(agent_name="main", model_name="m")
    await asyncio.sleep(0.02)
    assert rc._ticker_task is None
    assert bar.prefixes[-1] == ""


async def test_handlers_accept_dispatcher_positional_args(bar):
    """The callback dispatcher passes hook args POSITIONALLY (7 of them
    for agent_run_end) -- the live '_on_run_end() takes from 0 to 3
    positional arguments but 7 were given' bug. Call the handlers the
    exact way ``on_agent_run_start``/``on_agent_run_end`` do.
    """
    await rc._on_run_start("agent", "model", "session-id")
    assert rc._active_runs == 1
    await rc._on_run_end(
        "agent", "model", "session-id", True, None, "response", {"model": "m"}
    )
    assert rc._active_runs == 0
    await asyncio.sleep(0.02)
    assert rc._ticker_task is None
    assert bar.prefixes[-1] == ""  # idle prompt reclaimed the slot


async def test_run_end_never_goes_negative(bar):
    """A stray extra end (double-fire) must not corrupt the refcount."""
    await rc._on_run_end(agent_name="a", model_name="m")
    assert rc._active_runs == 0
    await rc._on_run_start(agent_name="a", model_name="m")
    assert rc._active_runs == 1
    await rc._on_run_end(agent_name="a", model_name="m")


# =========================================================================
# Degraded contexts: headless / no loop / broken bar
# =========================================================================


async def test_inactive_bar_means_no_ticker(monkeypatch):
    """Headless -p mode: the bar refuses to activate, so no animation."""
    fake = FakeBar(active=False)
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: fake)
    await rc._on_run_start(agent_name="a", model_name="m")
    assert rc._ticker_task is None
    assert fake.prefixes == []
    await rc._on_run_end(agent_name="a", model_name="m")


def test_start_ticker_without_loop_is_noop(bar):
    rc._active_runs = 1
    rc._start_ticker()  # must not raise outside an event loop
    assert rc._ticker_task is None


async def test_broken_bar_never_kills_the_ticker(monkeypatch):
    """A bar that raises on paint must not crash the tick loop."""

    class ExplodingBar(FakeBar):
        def set_status_prefix(self, text):
            raise RuntimeError("boom")

    fake = ExplodingBar()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: fake)
    await rc._on_run_start(agent_name="a", model_name="m")
    await asyncio.sleep(0.03)
    assert rc._ticker_task is not None and not rc._ticker_task.done()
    await rc._on_run_end(agent_name="a", model_name="m")
