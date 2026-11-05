"""Prompt undo/redo: UndoHistory unit tests + RunningLineEditor key paths."""

import pytest

from code_puppy.messaging import editor_keys as ek
from code_puppy.messaging.editor_undo import UndoHistory
from code_puppy.messaging.line_editor import RunningLineEditor

CTRL_Z, CTRL_Y = "\x1a", "\x19"
CMD_Z, CMD_SHIFT_Z = "\x1b[122;9u", "\x1b[122;10u"
BACKSPACE, LEFT = "\x7f", "\x1b[D"


class FakeBar:
    def set_prompt_text(self, *a):
        pass


class FakeHistory:
    def up(self, _t):
        return "recalled from history"

    def down(self, _t):
        return None

    def reset(self):
        pass

    def record_submit(self, _t):
        pass


class FakeRSearch:
    active = False

    def cancel(self):
        pass


@pytest.fixture
def ed():
    editor = RunningLineEditor(
        prompt_prefix="> ",
        bar=FakeBar(),
        now=lambda: 100.0,
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )
    editor.set_submit_router(lambda _text, _mode: None)
    return editor


def state(editor):
    return editor.buffer, editor.cursor


# --- UndoHistory ------------------------------------------------------------


def test_history_empty_stacks_return_none():
    h = UndoHistory()
    assert h.undo("x", 1) is None
    assert h.redo("x", 1) is None
    assert not h.can_undo and not h.can_redo


def test_history_caps_size_dropping_oldest():
    h = UndoHistory(limit=3)
    for i in range(5):
        h.record("kill", str(i), i)
    assert [h.undo("now", 0) for _ in range(4)] == [("4", 4), ("3", 3), ("2", 2), None]


def test_history_coalesces_only_when_untouched_since_last_edit():
    h = UndoHistory()
    h.record("type", "", 0)
    h.settle("a", 1)
    h.record("type", "a", 1)  # contiguous: same step
    h.settle("ab", 2)
    h.record("type", "ab", 0)  # cursor moved: new step
    assert h.undo("xab", 1) == ("ab", 0)
    assert h.undo("ab", 0) == ("", 0)
    assert h.undo("", 0) is None


def test_history_skips_snapshots_equal_to_current_state():
    h = UndoHistory()
    h.record("kill", "abc", 3)
    h.record("complete", "same", 4)  # a rewrite that changed nothing
    assert h.undo("same", 4) == ("abc", 3)


def test_history_new_edit_clears_redo_and_reset_clears_all():
    h = UndoHistory()
    h.record("kill", "abc", 3)
    assert h.undo("", 0) == ("abc", 3)
    assert h.can_redo
    h.record("kill", "abc", 3)
    assert not h.can_redo
    h.reset()
    assert not h.can_undo and not h.can_redo


# --- Single undo per deletion kind --------------------------------------------


@pytest.mark.parametrize(
    ("setup", "keys", "after"),
    [
        ("hello", BACKSPACE, "hell"),
        ("hello", BACKSPACE * 3, "he"),  # a run of backspaces = one step
        ("hello big world", "\x17", "hello big "),  # Ctrl+W
        ("hello big world", "\x1b\x7f", "hello big "),  # Alt+Backspace
        ("hello world", "\x01\x0b", ""),  # Ctrl+A, Ctrl+K
        ("hello world", "\x15", ""),  # Ctrl+U
        ("hello", "\x01\x1b[3~\x1b[3~", "llo"),  # Delete x2 = one step
    ],
)
def test_single_undo_restores_deleted_text(ed, setup, keys, after):
    ed.insert_paste_text(setup)
    ed.feed("\x05")  # Ctrl+E: break the paste step, cursor to end
    ed.feed(keys)
    assert ed.buffer == after
    ed.feed(CTRL_Z)
    assert ed.buffer == setup


def test_undo_restores_cursor_position(ed):
    ed.insert_paste_text("hello world")
    ed.feed(LEFT * 6 + "\x0b")  # kill " world" from mid-line
    assert state(ed) == ("hello", 5)
    ed.feed(CTRL_Z)
    assert state(ed) == ("hello world", 5)


def test_clear_buffer_is_undoable(ed):
    ed.insert_paste_text("precious prompt")
    ed.clear_buffer()  # Ctrl+C at idle / buffer-first absorb
    assert ed.buffer == ""
    ed.feed(CTRL_Z)
    assert ed.buffer == "precious prompt"


def test_paste_is_one_undo_step(ed):
    ed.feed("ab")
    ed.feed("\x1b[200~pasted text\x1b[201~")
    assert ed.buffer == "abpasted text"
    ed.feed(CTRL_Z)
    assert ed.buffer == "ab"


def test_external_editor_replace_and_history_recall_are_undoable(ed):
    ed.feed("draft")
    ed.replace_buffer_text("from $EDITOR")
    ed.feed("\x1b[A")  # Up: history recall
    assert ed.buffer == "recalled from history"
    ed.feed(CTRL_Z)
    assert ed.buffer == "from $EDITOR"
    ed.feed(CTRL_Z)
    assert ed.buffer == "draft"


def test_completion_is_undoable(ed):
    ed.feed("/mo")
    ed.apply_completion(0, 3, "/model ")
    ed.feed(CTRL_Z)
    assert ed.buffer == "/mo"


# --- Multi-step undo, coalescing, redo ----------------------------------------


def test_typing_coalesces_per_word(ed):
    ed.feed("hello world")
    ed.feed(CTRL_Z)
    assert ed.buffer == "hello "
    ed.feed(CTRL_Z)
    assert ed.buffer == ""


def test_multi_step_undo_walks_back_through_edits(ed):
    ed.feed("one")
    ed.feed(BACKSPACE * 2)  # "o"
    ed.feed("\x15")  # Ctrl+U -> ""
    ed.feed(CTRL_Z)
    assert ed.buffer == "o"
    ed.feed(CTRL_Z)
    assert ed.buffer == "one"
    ed.feed(CTRL_Z)
    assert ed.buffer == ""


def test_cursor_move_breaks_typing_group(ed):
    ed.feed("ac")
    ed.feed(LEFT + "b")
    assert ed.buffer == "abc"
    ed.feed(CTRL_Z)
    assert ed.buffer == "ac"


def test_redo_reapplies_and_new_edit_drops_redo(ed):
    ed.feed("keep")
    ed.feed("\x15")
    ed.feed(CTRL_Z)
    assert ed.buffer == "keep"
    ed.feed(CTRL_Y)
    assert ed.buffer == ""
    ed.feed(CTRL_Z + "!")  # back to "keep", then a fresh edit
    ed.feed(CTRL_Y)  # nothing to redo any more
    assert ed.buffer == "keep!"


def test_typing_after_undo_starts_a_new_step(ed):
    ed.feed("ab")
    ed.feed(BACKSPACE)
    ed.feed(CTRL_Z)  # "ab"
    ed.feed("c")
    ed.feed(CTRL_Z)
    assert ed.buffer == "ab"


def test_empty_stack_is_noop(ed):
    ed.feed(BACKSPACE + "\x17\x0b\x15")  # no-op deletes record nothing
    ed.feed(CTRL_Z + CTRL_Y)
    assert state(ed) == ("", 0)
    ed.feed("x")
    ed.feed(CTRL_Z + CTRL_Z + CTRL_Z)
    assert state(ed) == ("", 0)
    ed.feed(CTRL_Y + CTRL_Y)
    assert state(ed) == ("x", 1)


def test_submit_resets_the_stack(ed):
    ed.feed("first prompt")
    ed.feed("\r")
    assert ed.buffer == ""
    ed.feed(CTRL_Z)
    assert ed.buffer == ""  # the submitted text is not resurrected
    ed.feed(CTRL_Y)
    assert ed.buffer == ""


# --- Key delivery: Ctrl+Z, Cmd+Z (CSI-u), modifyOtherKeys -----------------------


def test_ctrl_z_never_inserts_a_control_char(ed):
    ed.feed(CTRL_Z)
    ed.feed("a" + CTRL_Z)
    assert "\x1a" not in ed.buffer
    assert ed.buffer == ""


@pytest.mark.parametrize(
    "undo_seq",
    [CMD_Z, "\x1b[122;5u", "\x1b[90;9u", "\x1b[122;9:1u", "\x1b[27;5;122~"],
)
def test_csi_undo_sequences(ed, undo_seq):
    ed.feed("text")
    ed.feed(undo_seq)
    assert ed.buffer == ""


@pytest.mark.parametrize(
    "redo_seq",
    [CMD_SHIFT_Z, "\x1b[122;6u", "\x1b[121;5u", "\x1b[121;9u", "\x1b[90;10u"],
)
def test_csi_redo_sequences(ed, redo_seq):
    ed.feed("text" + CMD_Z)
    ed.feed(redo_seq)
    assert ed.buffer == "text"


@pytest.mark.parametrize(
    "seq",
    [
        "122;9:3u",  # key release
        "122;3u",  # Alt+Z
        "122;13u",  # Ctrl+Cmd+Z
        "122;11u",  # Alt+Cmd+Z
        "121;10u",  # Cmd+Shift+Y
        "97;9u",  # Cmd+A
        "122u",  # no modifiers field
        "x;9u",  # malformed
        "27;5;x~",
    ],
)
def test_non_undo_csi_sequences_are_ignored(seq):
    assert ek.classify_undo_csi(seq) is None


def test_caps_lock_bit_does_not_block_undo():
    assert ek.classify_undo_csi("122;73u") == "undo"  # super + caps lock


def test_unrelated_csi_sequences_keep_their_meaning():
    assert ek.classify_csi("13;5u") == "submit_now"
    assert ek.classify_csi("1;5D") == "word_left"


def test_classify_control_maps_undo_keys():
    assert ek.classify_control(CTRL_Z) == "undo"
    assert ek.classify_control(CTRL_Y) == "redo"
    assert ek.classify_control("a") is None
