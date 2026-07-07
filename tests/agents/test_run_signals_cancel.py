"""``make_schedule_cancel`` — cancel-agent semantics around running shells.

The kill-then-cancel contract is load-bearing on Windows: the session
strips ENABLE_PROCESSED_INPUT so ^C never becomes a SIGINT — it arrives
as a raw \\x03 via the key listener and lands in ``schedule_agent_cancel``
instead of ``_shell_sigint_handler``. The old guard REFUSED to cancel
while a shell was running ("press Ctrl+X"), which left Ctrl+C dead for
the whole lifetime of every shell command on Windows: the run stayed
active, new submissions queued as steers, and the eventual cancel
discarded them (the "prompt never releases" wedge).
"""

import asyncio

import pytest

from code_puppy.agents._run_signals import make_schedule_cancel


@pytest.fixture
def kill_spy(monkeypatch):
    """Record shell-kill sweeps; keep panel teardown quiet."""
    calls = []
    monkeypatch.setattr(
        "code_puppy.tools.command_runner.kill_all_running_shell_processes",
        lambda: calls.append("kill") or 0,
    )
    monkeypatch.setattr(
        "code_puppy.tools.command_runner._tear_down_live_panels",
        lambda: None,
    )
    return calls


def _shells_running(monkeypatch, running: bool) -> None:
    monkeypatch.setattr(
        "code_puppy.tools.command_runner._RUNNING_PROCESSES",
        {object()} if running else set(),
    )


async def _hanging_task() -> asyncio.Task:
    task = asyncio.create_task(asyncio.sleep(3600))
    await asyncio.sleep(0)  # let it start
    return task


async def test_cancels_even_while_shell_running(monkeypatch, kill_spy):
    """The Windows ^C wedge: shells running must NOT block the cancel."""
    _shells_running(monkeypatch, True)
    task = await _hanging_task()
    cancel = make_schedule_cancel(task, asyncio.get_running_loop())

    cancel()  # force=False — the key-listener hotkey path

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)
    assert kill_spy == ["kill"]  # shells swept BEFORE the cancel


async def test_force_skips_redundant_kill_sweep(monkeypatch, kill_spy):
    """_shell_sigint_handler kills shells itself, then calls force=True."""
    _shells_running(monkeypatch, True)
    task = await _hanging_task()
    cancel = make_schedule_cancel(task, asyncio.get_running_loop())

    cancel(force=True)

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)
    assert kill_spy == []


async def test_no_shells_means_no_sweep(monkeypatch, kill_spy):
    _shells_running(monkeypatch, False)
    task = await _hanging_task()
    cancel = make_schedule_cancel(task, asyncio.get_running_loop())

    cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)
    assert kill_spy == []


async def test_swarm_stop_sweeps_shells_and_subagents(monkeypatch, kill_spy):
    """One press stops the whole tree: shells killed, sub-agents cancelled.

    The old refusal returned early, so a swarm with shells in flight
    could never be stopped by the cancel hotkey at all.
    """
    _shells_running(monkeypatch, True)
    task = await _hanging_task()
    subagent = await _hanging_task()
    monkeypatch.setattr(
        "code_puppy.agents._run_signals._active_subagent_tasks", {subagent}
    )
    cancel = make_schedule_cancel(task, asyncio.get_running_loop())

    cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=2)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(subagent, timeout=2)
    assert kill_spy == ["kill"]


async def test_done_task_is_a_noop(monkeypatch, kill_spy):
    """A stale handler firing after run end must not sweep anyone's shells."""
    _shells_running(monkeypatch, True)
    task = asyncio.create_task(asyncio.sleep(0))
    await task  # completed
    cancel = make_schedule_cancel(task, asyncio.get_running_loop())

    cancel()

    assert kill_spy == []
    assert not task.cancelled()
