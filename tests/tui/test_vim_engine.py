"""Unit tests for the pure (Textual-free) vim engine."""

from __future__ import annotations

from code_puppy.tui.vim import (
    INSERT,
    NORMAL,
    Editor,
    VimState,
    feed,
    offset_to_rowcol,
    rowcol_to_offset,
)


def run(
    text: str, cursor: int, keys, mode: str = NORMAL, state: VimState | None = None
):
    """Feed a sequence of keys and return (state, editor)."""
    state = state or VimState(mode=mode)
    ed = Editor(text=text, cursor=cursor)
    for key in keys:
        feed(state, ed, key)
    return state, ed


# --- coordinate helpers ---------------------------------------------------
def test_offset_rowcol_roundtrip():
    text = "abc\ndef\nghij"
    for off in range(len(text) + 1):
        r, c = offset_to_rowcol(text, off)
        assert rowcol_to_offset(text, r, c) == off


# --- mode switching -------------------------------------------------------
def test_escape_enters_normal_and_moves_left():
    state = VimState(mode=INSERT)
    ed = Editor("hello", cursor=5)
    feed(state, ed, "escape")
    assert state.mode == NORMAL
    assert ed.cursor == 4


def test_i_enters_insert():
    state, ed = run("hello", 2, ["i"])
    assert state.mode == INSERT
    assert ed.cursor == 2


def test_a_appends_after_cursor():
    state, ed = run("hello", 0, ["a"])
    assert state.mode == INSERT
    assert ed.cursor == 1


def test_A_appends_at_line_end():
    state, ed = run("hello\nworld", 0, ["A"])
    assert ed.cursor == 5


def test_I_inserts_at_first_non_blank():
    state, ed = run("  hi", 3, ["I"])
    assert ed.cursor == 2


def test_o_opens_line_below():
    state, ed = run("ab\ncd", 0, ["o"])
    assert ed.text == "ab\n\ncd"
    assert state.mode == INSERT
    assert ed.cursor == 3


def test_O_opens_line_above():
    state, ed = run("ab\ncd", 3, ["O"])
    assert ed.text == "ab\n\ncd"
    assert ed.cursor == 3


# --- navigation -----------------------------------------------------------
def test_h_l_clamped_to_line():
    _, ed = run("abc", 0, ["h"])
    assert ed.cursor == 0
    _, ed = run("abc", 2, ["l"])
    assert ed.cursor == 2  # cannot pass last char


def test_word_forward():
    _, ed = run("foo bar baz", 0, ["w"])
    assert ed.cursor == 4


def test_word_end():
    _, ed = run("foo bar", 0, ["e"])
    assert ed.cursor == 2


def test_word_back():
    _, ed = run("foo bar", 4, ["b"])
    assert ed.cursor == 0


def test_line_start_end():
    _, ed = run("foo bar", 3, ["0"])
    assert ed.cursor == 0
    _, ed = run("foo bar", 0, ["$"])
    assert ed.cursor == 6


def test_first_non_blank():
    _, ed = run("   foo", 5, ["^"])
    assert ed.cursor == 3


def test_gg_and_G():
    _, ed = run("a\nb\nc", 4, ["g", "g"])
    assert ed.cursor == 0
    _, ed = run("a\nb\nc", 0, ["G"])
    assert ed.cursor == 4


def test_count_motion():
    _, ed = run("foo bar baz qux", 0, ["3", "w"])
    assert ed.cursor == 12


def test_find_char_forward_and_repeat():
    _, ed = run("a.b.c.d", 0, ["f", "."])
    assert ed.cursor == 1
    state, ed = run("a.b.c.d", 0, ["f", "."])
    feed(state, ed, ";")
    assert ed.cursor == 3


def test_till_char():
    _, ed = run("a.b.c", 0, ["t", "."])
    assert ed.cursor == 0


def test_find_backward():
    _, ed = run("a.b.c", 4, ["F", "."])
    assert ed.cursor == 3


# --- editing --------------------------------------------------------------
def test_x_deletes_char():
    _, ed = run("hello", 0, ["x"])
    assert ed.text == "ello"


def test_count_x():
    _, ed = run("hello", 0, ["3", "x"])
    assert ed.text == "lo"


def test_D_deletes_to_eol():
    _, ed = run("hello world", 5, ["D"])
    assert ed.text == "hello"


def test_C_changes_to_eol():
    state, ed = run("hello world", 5, ["C"])
    assert ed.text == "hello"
    assert state.mode == INSERT


def test_r_replaces():
    _, ed = run("cat", 0, ["r", "b"])
    assert ed.text == "bat"


def test_tilde_toggles_case():
    _, ed = run("abc", 0, ["~"])
    assert ed.text == "Abc"


def test_J_joins_lines():
    _, ed = run("foo\nbar", 0, ["J"])
    assert ed.text == "foo bar"


def test_indent_dedent():
    _, ed = run("foo", 0, [">", ">"])
    assert ed.text == "  foo"
    _, ed = run("    foo", 0, ["<", "<"])
    assert ed.text == "  foo"


# --- operators ------------------------------------------------------------
def test_dw():
    _, ed = run("foo bar", 0, ["d", "w"])
    assert ed.text == "bar"


def test_de():
    _, ed = run("foo bar", 0, ["d", "e"])
    assert ed.text == " bar"


def test_dd():
    _, ed = run("a\nb\nc", 2, ["d", "d"])
    assert ed.text == "a\nc"


def test_d_dollar():
    _, ed = run("hello world", 5, ["d", "$"])
    assert ed.text == "hello"


def test_df_char():
    _, ed = run("hello.world", 0, ["d", "f", "."])
    assert ed.text == "world"


def test_dt_char():
    _, ed = run("hello.world", 0, ["d", "t", "."])
    assert ed.text == ".world"


def test_cw_enters_insert():
    state, ed = run("foo bar", 0, ["c", "w"])
    assert state.mode == INSERT
    assert ed.text == "bar"


def test_yw_then_paste():
    state = VimState(mode=NORMAL)
    ed = Editor("foo bar", 0)
    for k in ["y", "w"]:
        feed(state, ed, k)
    assert state.register == "foo "
    feed(state, ed, "$")
    feed(state, ed, "p")
    assert "foo " in ed.text


def test_yy_and_paste_linewise():
    state = VimState(mode=NORMAL)
    ed = Editor("line1\nline2", 0)
    feed(state, ed, "y")
    feed(state, ed, "y")
    assert state.register == "line1"
    assert state.register_linewise
    feed(state, ed, "p")
    assert ed.text == "line1\nline1\nline2"


def test_count_operator():
    _, ed = run("a b c d", 0, ["d", "2", "w"])
    assert ed.text == "c d"


# --- text objects ---------------------------------------------------------
def test_diw():
    _, ed = run("foo bar baz", 4, ["d", "i", "w"])
    assert ed.text == "foo  baz"


def test_daw():
    _, ed = run("foo bar baz", 4, ["d", "a", "w"])
    assert ed.text == "foo baz"


def test_di_quote():
    _, ed = run('say "hello" now', 6, ["d", "i", '"'])
    assert ed.text == 'say "" now'


def test_da_paren():
    _, ed = run("f(x + y)", 3, ["d", "a", "("])
    assert ed.text == "f"


def test_ci_bracket():
    state, ed = run("[1, 2, 3]", 4, ["c", "i", "["])
    assert ed.text == "[]"
    assert state.mode == INSERT


# --- visual mode ----------------------------------------------------------
def test_visual_select_and_delete():
    state, ed = run("hello", 0, ["v", "l", "l", "d"])
    assert ed.text == "lo"
    assert state.mode == NORMAL


def test_visual_yank():
    state = VimState(mode=NORMAL)
    ed = Editor("hello", 0)
    for k in ["v", "l", "l", "y"]:
        feed(state, ed, k)
    assert state.register == "hel"
    assert state.mode == NORMAL


def test_visual_escape_exits():
    state, ed = run("hello", 0, ["v", "l", "escape"])
    assert state.mode == NORMAL
    assert ed.anchor is None


def test_visual_change():
    state, ed = run("hello", 0, ["v", "l", "c"])
    assert ed.text == "llo"
    assert state.mode == INSERT


# --- undo & dot-repeat ----------------------------------------------------
def test_undo_restores():
    state = VimState(mode=NORMAL)
    ed = Editor("hello", 0)
    feed(state, ed, "x")
    assert ed.text == "ello"
    feed(state, ed, "u")
    assert ed.text == "hello"


def test_dot_repeat_x():
    state = VimState(mode=NORMAL)
    ed = Editor("hello", 0)
    feed(state, ed, "x")
    feed(state, ed, ".")
    assert ed.text == "llo"


def test_dot_repeat_dw():
    state = VimState(mode=NORMAL)
    ed = Editor("a b c d", 0)
    feed(state, ed, "d")
    feed(state, ed, "w")
    feed(state, ed, ".")
    assert ed.text == "c d"


def test_dot_repeat_insert():
    state = VimState(mode=NORMAL)
    ed = Editor("X", 0)
    # i + type "ab" + escape
    feed(state, ed, "i")
    ed.text = "abX"
    ed.cursor = 2
    feed(state, ed, "escape")
    assert ed.text == "abX"
    # dot repeats the insert at cursor
    feed(state, ed, ".")
    assert "ab" in ed.text


# --- ctrl / enter fall-through -------------------------------------------
def test_enter_not_consumed_in_normal():
    state = VimState(mode=NORMAL)
    ed = Editor("hi", 0)
    assert feed(state, ed, "enter") is False


def test_ctrl_combo_not_consumed():
    state = VimState(mode=NORMAL)
    ed = Editor("hi", 0)
    assert feed(state, ed, "ctrl+c") is False
