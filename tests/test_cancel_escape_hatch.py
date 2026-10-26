"""Escape hatches for zombie cancellations (Discord "death spiral" freeze).

A cancelled run with sub-agents/MCP servers can wedge mid-unwind, leaving
``is_run_active()`` True forever and gating every quit gesture. Coverage:

- the detach seam (install/request/clear) in agents._run_signals
- schedule_agent_cancel escalating a repeat cancel gesture to a detach
- cli_runner._shutdown_agent_task never hanging on a stuck task
"""

import asyncio
from types import SimpleNamespace

import pytest

from code_puppy import cli_runner
from code_puppy.agents import _run_signals


@pytest.fixture(autouse=True)
def clean_detach_seam():
    _run_signals.clear_detach_event()
    yield
    _run_signals.clear_detach_event()


def _make_stubborn(flag):
    """A task that swallows cancellation until ``flag['stop']`` — simulates
    a run whose unwind is stuck (the bug being escaped from)."""

    async def stubborn():
        while not flag["stop"]:
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                pass

    return stubborn


# ---------------------------------------------------------------------------
# Detach seam
# ---------------------------------------------------------------------------


async def test_request_detach_without_event_is_noop():
    assert _run_signals.request_run_detach() is False


async def test_request_detach_fires_installed_event():
    event = asyncio.Event()
    _run_signals.install_detach_event(event)
    assert _run_signals.request_run_detach() is True
    assert event.is_set()
    _run_signals.clear_detach_event()
    assert _run_signals.request_run_detach() is False


# ---------------------------------------------------------------------------
# schedule_agent_cancel escalation
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_clock(monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr(
        _run_signals, "time", SimpleNamespace(monotonic=lambda: clock["now"])
    )
    return clock


async def test_repeat_cancel_after_window_escalates_to_detach(monkeypatch, fake_clock):
    monkeypatch.setattr(_run_signals, "emit_warning", lambda *a, **k: None)
    monkeypatch.setattr(
        "code_puppy.tools.command_runner._tear_down_live_panels", lambda: None
    )
    flag = {"stop": False}
    task = asyncio.create_task(_make_stubborn(flag)())
    loop = asyncio.get_running_loop()
    event = asyncio.Event()
    _run_signals.install_detach_event(event)

    cancel = _run_signals.make_schedule_cancel(task, loop)
    cancel()  # first gesture: plain cancel
    await asyncio.sleep(0.05)  # deliver it — stubborn task shrugs it off
    assert not task.done()

    fake_clock["now"] += _run_signals.CANCEL_ESCALATE_AFTER_S
    cancel()  # second gesture on a wedged unwind: escalate
    await asyncio.sleep(0)  # run the call_soon_threadsafe callback
    assert event.is_set()

    flag["stop"] = True
    await task


async def test_repeat_cancel_within_window_does_not_escalate(monkeypatch, fake_clock):
    monkeypatch.setattr(_run_signals, "emit_warning", lambda *a, **k: None)
    flag = {"stop": False}
    task = asyncio.create_task(_make_stubborn(flag)())
    loop = asyncio.get_running_loop()
    event = asyncio.Event()
    _run_signals.install_detach_event(event)

    cancel = _run_signals.make_schedule_cancel(task, loop)
    cancel()
    await asyncio.sleep(0.05)
    fake_clock["now"] += _run_signals.CANCEL_ESCALATE_AFTER_S / 2
    cancel()  # impatient double-tap: still just a cancel, never a detach
    await asyncio.sleep(0)
    assert not event.is_set()

    flag["stop"] = True
    await task


async def test_cancel_on_done_task_never_escalates(fake_clock):
    task = asyncio.create_task(asyncio.sleep(0))
    await task
    loop = asyncio.get_running_loop()
    event = asyncio.Event()
    _run_signals.install_detach_event(event)

    cancel = _run_signals.make_schedule_cancel(task, loop)
    cancel()
    fake_clock["now"] += _run_signals.CANCEL_ESCALATE_AFTER_S * 2
    cancel()
    await asyncio.sleep(0)
    assert not event.is_set()


# ---------------------------------------------------------------------------
# _shutdown_agent_task (quit paths: double Ctrl+C / Ctrl+D / exit)
# ---------------------------------------------------------------------------


async def test_shutdown_agent_task_bounded_on_stuck_task(monkeypatch):
    monkeypatch.setattr(cli_runner, "_QUIT_CANCEL_TIMEOUT_S", 0.05)
    warnings = []
    monkeypatch.setattr(
        "code_puppy.messaging.emit_warning",
        lambda msg, **k: warnings.append(str(msg)),
    )
    flag = {"stop": False}
    task = asyncio.create_task(_make_stubborn(flag)())
    await asyncio.sleep(0)

    # The whole point: this must return, not freeze the quit path.
    await asyncio.wait_for(cli_runner._shutdown_agent_task(task), 2.0)
    assert warnings  # the abandon was announced

    flag["stop"] = True
    await task


async def test_shutdown_agent_task_with_cooperative_task():
    task = asyncio.create_task(asyncio.sleep(60))
    await asyncio.sleep(0)
    await asyncio.wait_for(cli_runner._shutdown_agent_task(task), 2.0)
    assert task.done()


async def test_shutdown_agent_task_handles_none_and_done():
    await cli_runner._shutdown_agent_task(None)
    task = asyncio.create_task(asyncio.sleep(0))
    await task
    await cli_runner._shutdown_agent_task(task)  # no-op, no raise
