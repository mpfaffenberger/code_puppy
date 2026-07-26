"""Tests for the Phase 5 mid-run slash-command consumer in run_ui.

Covers: submit-listener scheduling, pause→execute→resume ordering,
denylist rejection, exception safety, multi-command drain in one pause
window, the pause-timeout skip path, and string-result → queued steer.
"""

import asyncio
import io

import pytest

import code_puppy.messaging.run_ui as run_ui_mod
from code_puppy.messaging import bottom_bar as bottom_bar_mod
from code_puppy.messaging.line_editor import RunningLineEditor
from code_puppy.messaging.commands import PauseAgentCommand, ResumeAgentCommand
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class FakeBus:
    """Records commands and mirrors the real bus's pause routing."""

    def __init__(self):
        self.commands = []

    def provide_response(self, command):
        self.commands.append(type(command).__name__)
        if isinstance(command, PauseAgentCommand):
            get_pause_controller().pause()
        elif isinstance(command, ResumeAgentCommand):
            get_pause_controller().resume()


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    run_ui_mod.stop_run_ui()
    reset_pause_controller()
    # Nothing parks in unit tests — don't burn 2s per drain on the
    # best-effort park wait.
    monkeypatch.setattr(run_ui_mod, "_PARK_TIMEOUT_S", 0.01)
    yield
    run_ui_mod.stop_run_ui()
    reset_pause_controller()


@pytest.fixture
def bus(monkeypatch):
    fake = FakeBus()
    monkeypatch.setattr("code_puppy.messaging.bus.get_message_bus", lambda: fake)
    return fake


@pytest.fixture
def transcript(monkeypatch):
    lines = {"info": [], "warning": []}
    monkeypatch.setattr(
        "code_puppy.messaging.message_queue.emit_info",
        lambda text, **kw: lines["info"].append(str(text)),
    )
    monkeypatch.setattr(
        "code_puppy.messaging.message_queue.emit_warning",
        lambda text, **kw: lines["warning"].append(str(text)),
    )
    return lines


def make_editor(*commands):
    """A bare editor with commands pre-queued (bypasses key feeding)."""
    editor = RunningLineEditor(
        bar=type("B", (), {"set_prompt_text": staticmethod(lambda *a: None)})()
    )
    for cmd in commands:
        editor._command_queue.put(cmd)
    return editor


# =========================================================================
# Scheduling: slash submit → consumer on the captured loop
# =========================================================================


async def test_slash_submit_schedules_consumer(monkeypatch):
    drained = []

    async def fake_drain(editor):
        drained.append(editor)

    monkeypatch.setattr(run_ui_mod, "_drain_pending_commands", fake_drain)
    bottom_bar_mod.reset_bottom_bar()
    tty = FakeTTY()
    bottom_bar_mod._bottom_bar = bottom_bar_mod.BottomBar(
        stream=tty, get_size=lambda: (80, 24)
    )
    try:
        editor = run_ui_mod.start_run_ui()
        assert editor is not None
        for ch in "/help":
            editor.feed(ch)
        editor.feed("\r")
        await asyncio.sleep(0.02)  # let the scheduled coroutine run
        assert drained == [editor]
    finally:
        run_ui_mod.stop_run_ui()
        bottom_bar_mod.reset_bottom_bar()


async def test_non_slash_submit_schedules_nothing(monkeypatch):
    drained = []

    async def fake_drain(editor):
        drained.append(editor)

    monkeypatch.setattr(run_ui_mod, "_drain_pending_commands", fake_drain)
    bottom_bar_mod.reset_bottom_bar()
    bottom_bar_mod._bottom_bar = bottom_bar_mod.BottomBar(
        stream=FakeTTY(), get_size=lambda: (80, 24)
    )
    try:
        editor = run_ui_mod.start_run_ui()
        for ch in "steer text":
            editor.feed(ch)
        editor.feed("\r")
        await asyncio.sleep(0.02)
        assert drained == []
    finally:
        run_ui_mod.stop_run_ui()
        bottom_bar_mod.reset_bottom_bar()


# =========================================================================
# Pause → execute → resume ordering
# =========================================================================


async def test_pause_execute_resume_order(bus, transcript, monkeypatch):
    order = []

    def fake_exec(cmd):
        # The agent must be paused while the command runs.
        assert get_pause_controller().is_paused() is True
        order.append(cmd)
        return True

    monkeypatch.setattr(run_ui_mod, "_execute_command", fake_exec)
    editor = make_editor()
    await run_ui_mod._run_paused_commands(editor, "/help")

    assert order == ["/help"]
    assert bus.commands == ["PauseAgentCommand", "ResumeAgentCommand"]
    assert get_pause_controller().is_paused() is False
    assert any("running /help" in line for line in transcript["info"])
    assert any("resumed" in line for line in transcript["info"])


async def test_multiple_commands_one_pause_window(bus, transcript, monkeypatch):
    order = []
    monkeypatch.setattr(
        run_ui_mod, "_execute_command", lambda cmd: order.append(cmd) or True
    )
    editor = make_editor("/second", "/third")
    await run_ui_mod._run_paused_commands(editor, "/first")

    assert order == ["/first", "/second", "/third"]
    # ONE pause + ONE resume for the whole window.
    assert bus.commands == ["PauseAgentCommand", "ResumeAgentCommand"]


# =========================================================================
# Denylist
# =========================================================================


async def test_denylisted_command_is_rejected(bus, transcript, monkeypatch):
    executed = []
    monkeypatch.setattr(
        run_ui_mod, "_execute_command", lambda cmd: executed.append(cmd) or True
    )
    editor = make_editor()
    await run_ui_mod._run_paused_commands(editor, "/clear")

    assert executed == []
    assert any("finish the run first" in w for w in transcript["warning"])
    # Still resumes cleanly.
    assert bus.commands == ["PauseAgentCommand", "ResumeAgentCommand"]


async def test_denylist_matches_command_with_args(bus, transcript, monkeypatch):
    executed = []
    monkeypatch.setattr(
        run_ui_mod, "_execute_command", lambda cmd: executed.append(cmd) or True
    )
    editor = make_editor()
    await run_ui_mod._run_paused_commands(editor, "/agent qa-kitten")
    assert executed == []
    assert any("/agent" in w for w in transcript["warning"])


async def test_denied_command_does_not_block_allowed_ones(bus, transcript, monkeypatch):
    executed = []
    monkeypatch.setattr(
        run_ui_mod, "_execute_command", lambda cmd: executed.append(cmd) or True
    )
    editor = make_editor("/help")
    await run_ui_mod._run_paused_commands(editor, "/exit")
    assert executed == ["/help"]


# =========================================================================
# Exception safety
# =========================================================================


async def test_exception_during_execution_still_resumes(bus, transcript, monkeypatch):
    def boom(cmd):
        raise RuntimeError("command exploded")

    monkeypatch.setattr(run_ui_mod, "_execute_command", boom)
    editor = make_editor()
    with pytest.raises(RuntimeError):
        await run_ui_mod._run_paused_commands(editor, "/help")

    # The finally block resumed the agent regardless.
    assert bus.commands[-1] == "ResumeAgentCommand"
    assert get_pause_controller().is_paused() is False
    assert any("resumed" in line for line in transcript["info"])


def test_execute_command_swallows_handler_errors(monkeypatch, transcript):
    monkeypatch.setattr(
        "code_puppy.command_line.command_handler.handle_command",
        lambda cmd: (_ for _ in ()).throw(RuntimeError("bad handler")),
    )
    result = run_ui_mod._execute_command("/help")
    assert result is True  # treated as handled; error surfaced, not raised


# =========================================================================
# Pause-timeout (force-resume) path
# =========================================================================


async def test_expired_pause_skips_remaining_commands(bus, transcript, monkeypatch):
    executed = []

    def exec_and_expire(cmd):
        executed.append(cmd)
        # Simulate event_stream_handler's wait_if_paused timeout firing
        # while this command was running: the controller force-resumes.
        get_pause_controller().resume()
        return True

    monkeypatch.setattr(run_ui_mod, "_execute_command", exec_and_expire)
    editor = make_editor("/second")
    await run_ui_mod._run_paused_commands(editor, "/first")

    assert executed == ["/first"]  # second skipped
    assert any("pause expired" in w for w in transcript["warning"])


# =========================================================================
# handle_command return-value mapping
# =========================================================================


async def test_string_result_becomes_queued_steer(bus, transcript, monkeypatch):
    monkeypatch.setattr(run_ui_mod, "_execute_command", lambda cmd: "expanded prompt")
    editor = make_editor()
    await run_ui_mod._run_paused_commands(editor, "/mycustom")

    pc = get_pause_controller()
    assert pc.drain_pending_steer_queued() == ["expanded prompt"]
    assert any("queued as the next turn" in line for line in transcript["info"])


async def test_autosave_sentinel_is_refused(bus, transcript, monkeypatch):
    monkeypatch.setattr(run_ui_mod, "_execute_command", lambda cmd: "__AUTOSAVE_LOAD__")
    editor = make_editor()
    await run_ui_mod._run_paused_commands(editor, "/plugincmd")

    assert get_pause_controller().drain_pending_steer_queued() == []
    assert any("idle prompt" in w for w in transcript["warning"])


# =========================================================================
# Phase 6: park rendezvous (pause is a flag, not a rendezvous)
# =========================================================================


async def test_await_parked_returns_when_waiter_parks():
    pc = get_pause_controller()
    pc.pause()
    waiter = asyncio.create_task(pc.wait_if_paused())
    try:
        assert await run_ui_mod._await_parked(pc, timeout=2.0) is True
        assert pc.is_parked() is True
    finally:
        pc.resume()
        await waiter
    assert pc.is_parked() is False  # cleared on resume


async def test_await_parked_times_out_without_waiter():
    pc = get_pause_controller()
    pc.pause()
    try:
        assert await run_ui_mod._await_parked(pc, timeout=0.1) is False
    finally:
        pc.resume()


# =========================================================================
# Phase 6: dropped-command warning (loop gone)
# =========================================================================


def test_command_dropped_after_run_end_warns(transcript):
    editor = make_editor()
    listener = run_ui_mod._make_slash_listener(editor)
    with run_ui_mod._lock:
        run_ui_mod._loop = None  # run just ended; loop reference cleared
    listener("/help", "now")
    assert any("Retype it at the prompt" in w for w in transcript["warning"])


def test_non_slash_never_warns_when_loop_gone(transcript):
    editor = make_editor()
    listener = run_ui_mod._make_slash_listener(editor)
    with run_ui_mod._lock:
        run_ui_mod._loop = None
    listener("plain steer", "now")
    assert transcript["warning"] == []


# =========================================================================
# Phase 6: is_draining()
# =========================================================================


async def test_is_draining_true_only_during_drain(monkeypatch):
    seen = []

    async def probe(editor, first):
        seen.append(run_ui_mod.is_draining())

    monkeypatch.setattr(run_ui_mod, "_run_paused_commands", probe)
    editor = make_editor()
    editor._command_queue.put("/x")
    assert run_ui_mod.is_draining() is False
    await run_ui_mod._drain_pending_commands(editor)
    assert seen == [True]
    assert run_ui_mod.is_draining() is False


# =========================================================================
# Drain guard
# =========================================================================


async def test_concurrent_drains_collapse(bus, monkeypatch):
    """A second scheduled drain while one is active returns immediately."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_run(editor, first):
        started.set()
        await release.wait()

    monkeypatch.setattr(run_ui_mod, "_run_paused_commands", slow_run)
    editor = make_editor()
    editor._command_queue.put("/one")
    editor._command_queue.put("/two")

    task1 = asyncio.create_task(run_ui_mod._drain_pending_commands(editor))
    await started.wait()
    # Second drain: guard is held -> returns without touching the queue.
    await run_ui_mod._drain_pending_commands(editor)
    assert editor.get_pending_command() == "/two"  # untouched by drain #2
    release.set()
    await task1
