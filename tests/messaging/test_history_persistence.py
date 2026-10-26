"""Canonical history persistence at capture, never a second write at dispatch."""

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from code_puppy import config
from code_puppy.messaging.editor_actions import apply_action
from code_puppy.messaging.editor_history import (
    HistoryNavigator,
    HistoryStore,
    ReverseSearch,
)
from code_puppy.messaging.line_editor import RunningLineEditor
from code_puppy.messaging.pause_controller import PauseController


class Bar(io.StringIO):
    def set_prompt_text(self, *args):
        pass


@pytest.fixture
def history(monkeypatch, tmp_path):
    path = tmp_path / "history.txt"
    monkeypatch.setattr(config, "COMMAND_HISTORY_FILE", str(path))
    return HistoryStore(str(path))


def editor_for(history, controller=None):
    return RunningLineEditor(
        bar=Bar(),
        pause_controller=controller or PauseController(),
        history=HistoryNavigator(history),
        reverse_search=ReverseSearch(history),
    )


@pytest.mark.parametrize(
    "text",
    [
        "ordinary prompt",
        "+literal",
        "++literal",
        "line one\n+literal",
        "line one\n\n+literal\n",
        "  spaced prompt  ",
    ],
)
def test_capture_round_trip_and_prompt_toolkit(history, text):
    editor = editor_for(history)
    editor.set_submit_router(lambda *_: None)
    editor._buffer = text
    editor._cursor = len(text)
    editor._submit("now")
    assert history.load() == [text]
    assert editor._history.up("draft") == text
    assert editor._history.down(text) == "draft"
    pytest.importorskip("prompt_toolkit", reason="FileHistory compatibility check")
    from prompt_toolkit.history import FileHistory

    assert list(FileHistory(history._path).load_history_strings()) == [text]


@pytest.mark.parametrize("text", ["ordinary", "+literal", "++literal", "one\n\n+two\n"])
def test_config_writer_is_canonical(history, text):
    config.save_command_to_history(text)
    assert history.load() == [text]


def test_formatted_legacy_entries_are_not_rewritten(history):
    from pathlib import Path

    original = b"\n# 2025-01-01 00:00:00.123456\n++literal\n+\n+tail\n+\n"
    Path(history._path).write_bytes(original)
    assert history.load() == ["+literal\n\ntail\n"]
    config.save_command_to_history("new")
    assert Path(history._path).read_bytes().startswith(original)
    assert history.load() == ["+literal\n\ntail\n", "new"]


def test_deliberate_repeats_are_distinct(history):
    editor = editor_for(history)
    editor.set_submit_router(lambda *_: None)
    for _ in range(2):
        editor._buffer = "+literal"
        editor._submit("now")
    assert history.load() == ["+literal", "+literal"]


@pytest.mark.parametrize("mode", ["now", "queue"])
def test_editor_steering_persists_once_even_when_deferred(history, mode):
    controller = PauseController()
    editor = editor_for(history, controller)
    editor._buffer = "line one\n+literal"
    editor._submit(mode)
    assert history.load() == ["line one\n+literal"]
    if mode == "now":
        controller.defer_pending_steer_now()
    assert controller.pop_next_steer_queued() == "line one\n+literal"
    assert history.load() == ["line one\n+literal"]


def test_editor_steer_command_records_raw_input_once(history):
    controller = PauseController()
    editor = editor_for(history, controller)
    editor._buffer = "/steer +literal"
    editor._submit("now")
    assert controller.drain_pending_steer_now() == ["+literal"]
    assert history.load() == ["/steer +literal"]


def test_completion_and_multiline_take_precedence(history):
    history.append("old command")
    editor = editor_for(history)
    editor._buffer = "one\ntwo"
    editor._cursor = len(editor._buffer)
    apply_action(editor, "up")
    assert editor.buffer == "one\ntwo"
    assert not editor._history.browsing
    moves = []
    editor._completion = SimpleNamespace(move=moves.append)
    editor._completion_open = lambda: True
    apply_action(editor, "up")
    apply_action(editor, "down")
    assert moves == [-1, 1]
    assert not editor._history.browsing


def test_blank_inputs_and_surrogates(history):
    config.save_command_to_history(" \n ")
    assert history.load() == []
    config.save_command_to_history("bad\ud800")
    assert history.load() == ["bad\ufffd\ufffd\ufffd"]


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["persistent", "classic", "queued", "transformed"])
@pytest.mark.parametrize(
    "text", ["ordinary", "+literal", "++literal", "line one\n+literal", "one\n\n+two\n"]
)
async def test_actual_interactive_loop_persists_each_input_once(
    monkeypatch, history, source, text
):
    import code_puppy.cli_runner as cli
    from code_puppy.messaging import pause_controller, run_ui

    controller = PauseController()
    monkeypatch.setattr(pause_controller, "get_pause_controller", lambda: controller)
    monkeypatch.setattr(cli, "_use_persistent_prompt", lambda: source != "classic")
    monkeypatch.setattr(cli, "_persistent_prompt_parts", lambda: (">>> ", []))
    monkeypatch.setattr(run_ui, "start_persistent_ui", lambda **_: True)
    monkeypatch.setattr(run_ui, "set_idle_prompt_prefix", lambda *_: None)
    monkeypatch.setattr(run_ui, "stop_persistent_ui", lambda: None)
    monkeypatch.setattr(cli, "print_truecolor_warning", lambda *_: None)
    monkeypatch.setattr(cli, "record_terminal_session", lambda *_, **__: None)
    monkeypatch.setattr("code_puppy.agents.get_current_agent", lambda: MagicMock())
    tasks = []

    async def fake_run(_agent, task, **_kwargs):
        tasks.append(task)
        return SimpleNamespace(output="synthetic response"), None

    monkeypatch.setattr(cli, "run_prompt_with_attachments", fake_run)
    if source == "queued":
        controller.request_steer(text, mode="queue")
        inputs = []
    else:
        inputs = ["/expand" if source == "transformed" else text]
    inputs.extend(["/handled", "!synthetic", "/exit"])
    monkeypatch.setattr(
        "code_puppy.command_line.shell_passthrough.execute_shell_passthrough",
        lambda _: None,
    )
    editor = editor_for(history)
    editor.set_submit_router(lambda *_: None)

    def next_input():
        value = inputs.pop(0)
        if source != "classic":
            editor._buffer = value
            editor._submit("now")
        return value

    async def wait():
        return next_input()

    monkeypatch.setattr(run_ui, "wait_for_idle_submission", wait)
    monkeypatch.setattr("builtins.input", lambda *_: next_input())
    monkeypatch.setattr(
        "code_puppy.command_line.command_handler.handle_command",
        lambda text: "++expanded" if text == "/expand" else True,
    )
    await asyncio.wait_for(cli.interactive_mode(MagicMock(), initial_command=None), 5)
    expected = (
        ["/expand", "++expanded", "/handled", "!synthetic", "/exit"]
        if source == "transformed"
        else [text, "/handled", "!synthetic", "/exit"]
    )
    assert history.load() == expected
    assert tasks == ["++expanded" if source == "transformed" else text]


def test_actual_runtime_requeues_leftovers_without_recording_again(
    monkeypatch, history
):
    from code_puppy.agents import _run_signals
    from code_puppy.messaging import pause_controller

    controller = PauseController()
    monkeypatch.setattr(pause_controller, "get_pause_controller", lambda: controller)
    monkeypatch.setattr(
        "code_puppy.agent_completion_inbox.pop_completion", lambda _: None
    )
    monkeypatch.setattr(
        _run_signals, "resolve_steer_content", lambda text: (text, text)
    )
    controller.request_steer("+first", mode="queue")
    controller.request_steer("++second", mode="queue")
    assert (
        _run_signals.prepare_queued_steer_injection(
            SimpleNamespace(), SimpleNamespace()
        )
        == "+first"
    )
    assert controller.pop_next_steer_queued() == "++second"
    assert history.load() == ["+first", "++second"]


def test_midrun_command_expansion_is_a_distinct_canonical_prompt(monkeypatch, history):
    from code_puppy.messaging import pause_controller, run_ui

    controller = PauseController()
    monkeypatch.setattr(pause_controller, "get_pause_controller", lambda: controller)
    editor = editor_for(history, controller)
    editor._buffer = "/expand"
    editor._submit("now")
    assert editor.get_pending_command() == "/expand"
    run_ui._handle_command_result("/expand", "++expanded")
    assert controller.pop_next_steer_queued() == "++expanded"
    assert history.load() == ["/expand", "++expanded"]


@pytest.mark.parametrize("mode", ["queue", "now"])
@pytest.mark.parametrize("changed", [False, True])
def test_actual_queue_edit_records_only_changed_capture(history, mode, changed):
    controller = PauseController()
    controller.request_steer("+original", mode="queue")
    editor = editor_for(history, controller)
    editor.feed("\x1b[A")
    assert editor.buffer == "+original"
    if changed:
        editor._buffer = "++edited\n+tail"
    editor._submit(mode)
    expected = ["+original", "++edited\n+tail"] if changed else ["+original"]
    assert history.load() == expected
    if mode == "queue":
        assert controller.pop_next_steer_queued() == expected[-1]
    else:
        assert controller.drain_pending_steer_now() == [expected[-1]]


def test_actual_queue_navigation_and_fallback_restore_do_not_recapture(history):
    controller = PauseController()
    controller.request_steer("+one", mode="queue")
    controller.request_steer("++two", mode="queue")
    editor = editor_for(history, controller)
    editor.feed("\x1b[A")
    assert editor.buffer == "++two"
    # Exercise fallback restoration against a controller missing the restore API.
    controller.restore_pending_steer_queued = None
    editor.feed("\x1b[B")
    assert history.load() == ["+one", "++two"]
    assert controller.drain_pending_steer_queued() == ["+one", "++two"]


def test_history_write_failure_is_debug_only(monkeypatch, history, caplog):
    import logging
    from code_puppy import messaging

    def fail(*args, **kwargs):
        raise OSError("unwritable history")

    error = MagicMock()
    monkeypatch.setattr(messaging, "emit_error", error)
    monkeypatch.setattr("builtins.open", fail)
    with caplog.at_level(logging.DEBUG):
        config.save_command_to_history("+literal")
    error.assert_not_called()
    assert "history append failed" in caplog.text


def test_queue_navigation_commits_changed_draft_once(history):
    controller = PauseController()
    controller.request_steer("+original", mode="queue")
    editor = editor_for(history, controller)
    editor.feed("\x1b[A")
    editor._buffer = "++edited"
    editor._cursor = len(editor._buffer)
    editor.feed("\x1b[B")
    assert controller.pop_next_steer_queued() == "++edited"
    assert history.load() == ["+original", "++edited"]
