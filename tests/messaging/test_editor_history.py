"""Phase B feature 1: history — store format, navigation, reverse search."""

import io

import pytest

from code_puppy.messaging.editor_history import (
    HistoryNavigator,
    HistoryStore,
    ReverseSearch,
)
from code_puppy.messaging.line_editor import RunningLineEditor


class FakeBar(io.StringIO):
    def set_prompt_text(self, *a):
        pass


@pytest.fixture
def store(tmp_path):
    return HistoryStore(str(tmp_path / "history.txt"))


def make_editor(store):
    return RunningLineEditor(
        bar=FakeBar(),
        pause_controller=type("C", (), {"request_steer": lambda *a, **k: None})(),
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
    from prompt_toolkit.history import FileHistory

    pt = FileHistory(str(tmp_path / "history.txt"))
    assert list(pt.load_history_strings()) == ["shared entry"]


def test_store_reads_prompt_toolkit_writes(store, tmp_path):
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
