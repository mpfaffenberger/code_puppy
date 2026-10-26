"""Phase B feature 1: history — store format, navigation, reverse search."""

import io

import pytest

from code_puppy.messaging.editor_history import (
    HistoryNavigator,
    HistoryStore,
    ReverseSearch,
)
from code_puppy.messaging.line_editor import RunningLineEditor
from code_puppy.messaging.pause_controller import PauseController


class FakeBar(io.StringIO):
    def set_prompt_text(self, *a):
        pass


@pytest.fixture
def store(tmp_path):
    return HistoryStore(str(tmp_path / "history.txt"))


def make_editor(store, pause_controller=None):
    controller = (
        pause_controller or type("C", (), {"request_steer": lambda *a, **k: None})()
    )
    return RunningLineEditor(
        bar=FakeBar(),
        pause_controller=controller,
        history=HistoryNavigator(store),
        reverse_search=ReverseSearch(store),
    )


# =========================================================================
# File format round-trip (prompt_toolkit FileHistory compatible)
# =========================================================================


def test_store_round_trip(store):
    store.append("first command")
    store.append("second command")
    assert store.load() == ["first command", "second command"]


def test_store_multiline_entry_round_trip(store):
    store.append("line one\nline two\nline three")
    assert store.load() == ["line one\nline two\nline three"]


def test_store_format_matches_prompt_toolkit(store, tmp_path):
    """The on-disk format must be readable by prompt_toolkit itself."""
    store.append("shared entry")
    pytest.importorskip(
        "prompt_toolkit",
        reason="format-compat check against the original implementation",
    )
    from prompt_toolkit.history import FileHistory

    pt = FileHistory(str(tmp_path / "history.txt"))
    assert list(pt.load_history_strings()) == ["shared entry"]


def test_store_reads_prompt_toolkit_writes(store, tmp_path):
    pytest.importorskip(
        "prompt_toolkit",
        reason="format-compat check against the original implementation",
    )
    from prompt_toolkit.history import FileHistory

    pt = FileHistory(str(tmp_path / "history.txt"))
    pt.store_string("classic entry")
    assert store.load() == ["classic entry"]


def test_store_load_missing_file_is_empty(tmp_path):
    assert HistoryStore(str(tmp_path / "nope.txt")).load() == []


# =========================================================================
# Navigator: up/down + working entry
# =========================================================================


def test_navigator_up_walks_backwards(store):
    for entry in ("one", "two", "three"):
        store.append(entry)
    nav = HistoryNavigator(store)
    assert nav.up("") == "three"
    assert nav.up("") == "two"
    assert nav.up("") == "one"
    assert nav.up("") is None  # oldest — stays put


def test_navigator_preserves_working_entry(store):
    store.append("old command")
    nav = HistoryNavigator(store)
    assert nav.up("draft in progress") == "old command"
    assert nav.down("old command") == "draft in progress"


def test_navigator_down_without_browsing_is_noop(store):
    nav = HistoryNavigator(store)
    assert nav.down("anything") is None


def test_navigator_record_submit_appends_and_resets(store):
    nav = HistoryNavigator(store)
    nav.record_submit("new entry")
    assert store.load() == ["new entry"]
    assert nav.up("") == "new entry"  # fresh snapshot sees it


# =========================================================================
# Editor-level arrows
# =========================================================================


def test_editor_up_down_recalls_history(store):
    store.append("previous task")
    editor = make_editor(store)
    for ch in "half typed":
        editor.feed(ch)
    editor.feed("\x1b[A")  # Up
    assert editor.buffer == "previous task"
    editor.feed("\x1b[B")  # Down -> working entry restored
    assert editor.buffer == "half typed"


def test_editor_submit_appends_to_history(store):
    editor = make_editor(store)
    for ch in "do the thing":
        editor.feed(ch)
    editor.feed("\r")
    assert store.load() == ["do the thing"]


def test_editing_exits_history_browsing(store):
    store.append("recalled")
    editor = make_editor(store)
    editor.feed("\x1b[A")
    assert editor.buffer == "recalled"
    editor.feed("!")  # edit -> browsing reset; text stays
    assert editor.buffer == "recalled!"
    editor.feed("\x1b[B")  # Down: no longer browsing -> no-op
    assert editor.buffer == "recalled!"


def test_queued_turns_are_editable_before_regular_history(store):
    for entry in ("older history", "first queued", "second queued"):
        store.append(entry)
    controller = PauseController()
    controller.request_steer("first queued", mode="queue")
    controller.request_steer("second queued", mode="queue")
    editor = make_editor(store, controller)

    editor.feed("\x1b[A")
    assert editor.buffer == "second queued"
    editor.feed("!")
    editor.feed("\x1b[A")
    assert editor.buffer == "first queued"
    editor.feed("\x1b[A")
    assert editor.buffer == "older history"
    assert controller.peek_pending_steer_queued() == [
        "first queued",
        "second queued!",
    ]


def test_down_from_queued_turn_restores_working_draft(store):
    controller = PauseController()
    controller.request_steer("queued", mode="queue")
    editor = make_editor(store, controller)
    editor.feed("draft")

    editor.feed("\x1b[A")
    editor.feed("!")
    editor.feed("\x1b[B")

    assert editor.buffer == "draft"
    assert controller.peek_pending_steer_queued() == ["queued!"]


def test_enter_updates_recalled_queue_item_without_duplication(store):
    controller = PauseController()
    controller.request_steer("first", mode="queue")
    controller.request_steer("second", mode="queue")
    editor = make_editor(store, controller)

    editor.feed("\x1b[A")
    editor.feed(" edited")
    editor.feed("\r")

    assert editor.buffer == ""
    assert controller.peek_pending_steer_queued() == ["first", "second edited"]
    assert controller.drain_pending_steer_now() == []


def test_ctrl_enter_submits_buffer_as_immediate_steer(store):
    controller = PauseController()
    editor = make_editor(store, controller)

    editor.feed("steer immediately")
    editor.feed("\x1b[13;5u")

    assert controller.drain_pending_steer_now() == ["steer immediately"]
    assert controller.peek_pending_steer_queued() == []


def test_ctrl_enter_converts_recalled_queue_item_to_immediate_steer(store):
    controller = PauseController()
    controller.request_steer("later", mode="queue")
    controller.request_steer("steer me", mode="queue")
    editor = make_editor(store, controller)

    editor.feed("\x1b[A")
    editor.feed(" now")
    editor.feed("\x1b[13;5u")

    assert controller.peek_pending_steer_queued() == ["later"]
    assert controller.drain_pending_steer_now() == ["steer me now"]


def test_clearing_recalled_queue_item_restores_original(store):
    controller = PauseController()
    controller.request_steer("keep original", mode="queue")
    editor = make_editor(store, controller)

    editor.feed("\x1b[A")
    editor.feed(" changed")
    editor.clear_buffer()

    assert editor.buffer == ""
    assert controller.peek_pending_steer_queued() == ["keep original"]


def test_reverse_search_restores_recalled_queue_item(store):
    store.append("history match")
    controller = PauseController()
    controller.request_steer("keep queued", mode="queue")
    editor = make_editor(store, controller)

    editor.feed("\x1b[A")
    editor.feed(" changed")
    editor.feed("\x12")

    assert editor._rsearch.active is True
    assert controller.peek_pending_steer_queued() == ["keep queued"]


# =========================================================================
# Ctrl+R reverse search
# =========================================================================


def test_reverse_search_finds_and_walks_older(store):
    for entry in ("git status", "git push", "ls -la", "git pull"):
        store.append(entry)
    rs = ReverseSearch(store)
    rs.start()
    for ch in "git":
        rs.feed_char(ch)
    assert rs.current_match() == "git pull"
    rs.next_older()
    assert rs.current_match() == "git push"
    rs.next_older()
    assert rs.current_match() == "git status"


def test_reverse_search_prompt_text(store):
    store.append("make tests")
    rs = ReverseSearch(store)
    rs.start()
    for ch in "tes":
        rs.feed_char(ch)
    assert rs.prompt_text() == "(reverse-i-search)`tes': make tests"


def test_editor_ctrl_r_flow_accept(store):
    store.append("cargo build")
    editor = make_editor(store)
    editor.feed("\x12")  # Ctrl+R
    for ch in "cargo":
        editor.feed(ch)
    editor.feed("\r")  # accept into buffer WITHOUT submitting
    assert editor.buffer == "cargo build"
    assert store.load() == ["cargo build"]  # nothing new appended


def test_editor_ctrl_r_esc_cancels(store, monkeypatch):
    store.append("secret command")
    editor = make_editor(store)
    for ch in "kept":
        editor.feed(ch)
    editor.feed("\x12")
    editor.feed("s")
    editor.feed("\x1b")  # Esc cancels the search
    fake_now = [1000.0]
    editor._now = lambda: fake_now[0]
    fake_now[0] += 1
    editor.check_timeout()  # resolve the bare ESC
    assert editor._rsearch.active is False
    assert editor.buffer == "kept"  # original buffer untouched
