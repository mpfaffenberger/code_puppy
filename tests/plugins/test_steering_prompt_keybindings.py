"""Unit tests for the raw-terminal steering prompt key handling + rendering.

No prompt_toolkit here — on purpose. The steering prompt is stdlib-only and
single-line, so these tests exercise the pure key handler, the incremental
line-editor renderer, and the fallback path without putting pytest's terminal
into raw mode. Good dog, no TTY crimes.
"""

from __future__ import annotations

import builtins
import io

import pytest

from code_puppy.plugins.agent_steering import line_editor
from code_puppy.plugins.agent_steering import steering_prompt as prompt


@pytest.fixture
def buffer() -> list[str]:
    return []


# =============================================================================
# Pure key handling
# =============================================================================


def test_printable_chars_insert_at_cursor(buffer):
    action, pos, mode = prompt._handle_key("h", buffer, 0, "now")
    assert (action, pos, mode) == ("continue", 1, "now")
    action, pos, mode = prompt._handle_key("i", buffer, pos, mode)
    assert (action, pos, mode) == ("continue", 2, "now")
    assert buffer == ["h", "i"]


def test_printable_chars_insert_mid_line():
    buffer = list("hd")
    action, pos, mode = prompt._handle_key("a", buffer, 1, "now")
    assert (action, pos) == ("continue", 2)
    assert buffer == list("had")


def test_tab_toggles_mode_now_to_queue_to_now(buffer):
    action, pos, mode = prompt._handle_key("\t", buffer, 0, "now")
    assert (action, mode) == ("continue", "queue")
    action, pos, mode = prompt._handle_key("\t", buffer, pos, mode)
    assert (action, mode) == ("continue", "now")
    assert buffer == []


@pytest.mark.parametrize("backspace", ["\x7f", "\b"])
def test_backspace_removes_char_before_cursor(backspace):
    buffer = list("abc")
    action, pos, mode = prompt._handle_key(backspace, buffer, 3, "queue")
    assert (action, pos, mode) == ("continue", 2, "queue")
    assert buffer == list("ab")


@pytest.mark.parametrize("backspace", ["\x7f", "\b"])
def test_backspace_mid_line_removes_left_of_cursor(backspace):
    buffer = list("abc")
    action, pos, _ = prompt._handle_key(backspace, buffer, 2, "now")
    assert (action, pos) == ("continue", 1)
    assert buffer == list("ac")


@pytest.mark.parametrize("backspace", ["\x7f", "\b"])
def test_backspace_at_line_start_is_noop(backspace):
    buffer = list("abc")
    action, pos, _ = prompt._handle_key(backspace, buffer, 0, "now")
    assert (action, pos) == ("continue", 0)
    assert buffer == list("abc")


def test_delete_removes_char_at_cursor():
    buffer = list("abc")
    action, pos, _ = prompt._handle_key("delete", buffer, 1, "now")
    assert (action, pos) == ("continue", 1)
    assert buffer == list("ac")


def test_delete_at_end_is_noop():
    buffer = list("abc")
    action, pos, _ = prompt._handle_key("delete", buffer, 3, "now")
    assert (action, pos) == ("continue", 3)
    assert buffer == list("abc")


def test_left_right_move_and_clamp():
    buffer = list("ab")
    _, pos, _ = prompt._handle_key("left", buffer, 1, "now")
    assert pos == 0
    _, pos, _ = prompt._handle_key("left", buffer, pos, "now")
    assert pos == 0  # clamped at start
    _, pos, _ = prompt._handle_key("right", buffer, 2, "now")
    assert pos == 2  # clamped at end


def test_home_and_end_jump():
    buffer = list("hello")
    _, pos, _ = prompt._handle_key("home", buffer, 3, "now")
    assert pos == 0
    _, pos, _ = prompt._handle_key("end", buffer, pos, "now")
    assert pos == 5


@pytest.mark.parametrize("enter", ["\r", "\n"])
def test_enter_submits(enter, buffer):
    buffer.extend(" ship it ")
    action, _, mode = prompt._handle_key(enter, buffer, len(buffer), "queue")
    assert action == "submit"
    assert prompt._finish_submit(buffer, mode) == ("ship it", "queue")


def test_empty_enter_returns_none(buffer):
    buffer.extend("   ")
    action, _, mode = prompt._handle_key("\r", buffer, 3, "now")
    assert action == "submit"
    assert prompt._finish_submit(buffer, mode) is None


@pytest.mark.parametrize("cancel", ["\x1b", "\x03", "\x04", ""])
def test_cancel_keys_return_cancel(cancel, buffer):
    buffer.extend("do not submit")
    action, _, mode = prompt._handle_key(cancel, buffer, 0, "queue")
    assert (action, mode) == ("cancel", "queue")
    assert buffer == list("do not submit")


@pytest.mark.parametrize("control", ["\x00", "\x01", "\x02", "\x1f"])
def test_other_control_chars_are_ignored(control, buffer):
    action, pos, mode = prompt._handle_key(control, buffer, 0, "now")
    assert (action, pos, mode) == ("continue", 0, "now")
    assert buffer == []


# =============================================================================
# Escape-sequence handling (_iter_keys)
# =============================================================================


@pytest.mark.parametrize(
    "sequence, token",
    [
        ("\x1b[D", "left"),
        ("\x1b[C", "right"),
        ("\x1b[H", "home"),
        ("\x1b[F", "end"),
        ("\x1b[1~", "home"),
        ("\x1b[7~", "home"),
        ("\x1b[4~", "end"),
        ("\x1b[8~", "end"),
        ("\x1b[3~", "delete"),
        ("\x1b[1;5D", "left"),  # Ctrl+left → base key, close enough
        ("\x1bOD", "left"),  # SS3 / application mode
        ("\x1bOH", "home"),
    ],
)
def test_iter_keys_translates_nav_sequences(sequence, token):
    assert list(prompt._iter_keys(sequence)) == [token]


@pytest.mark.parametrize(
    "sequence",
    [
        "\x1b[A",  # up arrow — meaningless in a single-line prompt
        "\x1b[B",  # down arrow
        "\x1b[15~",  # F5
        "\x1bx",  # Alt+x chord
        "\x1bOP",  # F1 (SS3)
    ],
)
def test_iter_keys_swallows_unhandled_sequences(sequence):
    """Unknown sequences must be ignored entirely — NOT ESC + garbage."""
    assert list(prompt._iter_keys(sequence)) == []


def test_iter_keys_lone_esc_passes_through():
    """A bare ESC press still reaches the handler (→ cancel)."""
    assert list(prompt._iter_keys("\x1b")) == ["\x1b"]


def test_iter_keys_text_around_sequence_survives():
    assert list(prompt._iter_keys("ab\x1b[Acd")) == ["a", "b", "c", "d"]


def test_iter_keys_plain_text_passes_through():
    assert list(prompt._iter_keys("hello")) == list("hello")


def test_iter_keys_left_arrow_moves_cursor_not_cancel():
    """Regression: left arrow used to read as lone ESC and cancel the steer.

    Now it must actually move the cursor, so '!' lands BETWEEN h and i.
    """
    buffer: list[str] = []
    pos, mode = 0, "now"
    for token in prompt._iter_keys("hi\x1b[D!"):
        action, pos, mode = prompt._handle_key(token, buffer, pos, mode)
        assert action != "cancel"
    assert buffer == list("h!i")
    assert pos == 2


# =============================================================================
# Render math (wrap handling)
# =============================================================================


@pytest.mark.parametrize(
    "text_len, width, expected_row",
    [
        (0, 80, 0),  # empty prompt → row 0
        (1, 80, 0),  # one char → still row 0
        (80, 80, 0),  # exactly fills row 0, cursor pending-wrap → row 0
        (81, 80, 1),  # wrapped one char onto row 1
        (160, 80, 1),  # fills row 1 exactly → still row 1
        (161, 80, 2),  # spilled to row 2
        (500, 80, 6),  # (500-1)//80 == 6
    ],
)
def test_end_row_handles_wrap(text_len, width, expected_row):
    assert line_editor._end_row(text_len, width) == expected_row


def test_end_row_clamps_pathological_width():
    assert line_editor._end_row(10, 0) == 9
    assert line_editor._end_row(0, 0) == 0


@pytest.mark.parametrize(
    "index, length, width, expected",
    [
        (0, 0, 20, (0, 0)),  # empty line
        (5, 10, 20, (0, 5)),  # mid-line, row 0
        (25, 30, 20, (1, 5)),  # mid-line, wrapped
        (20, 30, 20, (1, 0)),  # boundary index mid-line → start of row 1
        (20, 20, 20, (0, 19)),  # boundary index AT end → clamp to last cell
        (40, 40, 20, (1, 19)),  # exact two-row fill → last cell of row 1
    ],
)
def test_visual_pos(index, length, width, expected):
    assert line_editor._visual_pos(index, length, width) == expected


# =============================================================================
# Incremental rendering (line_editor.render_line)
# =============================================================================


def _editor(monkeypatch, width: int = 80) -> tuple[io.StringIO, dict]:
    monkeypatch.setattr(line_editor, "terminal_width", lambda: width)
    return io.StringIO(), line_editor.make_render_state()


def test_first_render_is_full_redraw_without_cursor_up(monkeypatch):
    out, state = _editor(monkeypatch)

    line_editor.render_line("steer [now]> ", 13, state, out)

    written = out.getvalue()
    assert "\r\x1b[J" in written
    assert "steer [now]> " in written
    assert "\x1b[" + "1A" not in written  # no spurious scroll on first paint
    assert written.startswith(line_editor._SYNC_BEGIN)
    assert written.endswith(line_editor._SYNC_END)
    assert state["cursor_row"] == 0


def test_typing_appends_suffix_only(monkeypatch):
    """The common typing case must be a single tiny write — no escapes.

    Legacy Windows consoles ignore DEC 2026, so any wipe-per-keystroke
    flickers there. Appending raw chars can't flicker anywhere.
    """
    out, state = _editor(monkeypatch)
    line_editor.render_line("steer [now]> hi", 15, state, out)
    out.truncate(0), out.seek(0)

    line_editor.render_line("steer [now]> hip", 16, state, out)

    assert out.getvalue() == "p"


def test_unchanged_render_writes_nothing(monkeypatch):
    out, state = _editor(monkeypatch)
    line_editor.render_line("steer [now]> hi", 15, state, out)
    out.truncate(0), out.seek(0)

    line_editor.render_line("steer [now]> hi", 15, state, out)

    assert out.getvalue() == ""


def test_cursor_only_move_emits_column_escape_only(monkeypatch):
    out, state = _editor(monkeypatch)
    line_editor.render_line("steer [now]> hi", 15, state, out)
    out.truncate(0), out.seek(0)

    line_editor.render_line("steer [now]> hi", 14, state, out)  # left arrow

    written = out.getvalue()
    assert written == "\x1b[15G"  # CHA to col 15 (1-based) — nothing else
    assert state["cursor"] == 14


def test_mid_line_insert_rewrites_tail_and_repositions(monkeypatch):
    out, state = _editor(monkeypatch)
    line_editor.render_line("steer [now]> hd", 14, state, out)  # cursor on 'd'
    out.truncate(0), out.seek(0)

    line_editor.render_line("steer [now]> had", 15, state, out)

    written = out.getvalue()
    assert "ad" in written  # rewrote from the edit point
    assert "\x1b[J" not in written and "\x1b[K" not in written  # no clears
    assert line_editor._SYNC_BEGIN not in written


def test_backspace_at_end_clears_to_eol_only(monkeypatch):
    out, state = _editor(monkeypatch)
    line_editor.render_line("steer [now]> hip", 16, state, out)
    out.truncate(0), out.seek(0)

    line_editor.render_line("steer [now]> hi", 15, state, out)

    written = out.getvalue()
    assert "\x1b[K" in written
    assert "\x1b[J" not in written


def test_shrink_across_wrap_clears_only_stale_rows(monkeypatch):
    out, state = _editor(monkeypatch, width=20)
    line_editor.render_line("x" * 30, 30, state, out)  # rows 0-1
    assert state["cursor_row"] == 1
    out.truncate(0), out.seek(0)

    line_editor.render_line("x" * 10, 10, state, out)  # back to row 0

    written = out.getvalue()
    assert "\x1b[B\r\x1b[J" in written  # wipes ONLY the rows below
    assert line_editor._SYNC_BEGIN not in written  # not a full redraw
    assert state["cursor_row"] == 0


def test_append_at_exact_wrap_boundary_enters_row_explicitly(monkeypatch):
    """Exact-fill append must \\r\\n into the next row, never trust the
    terminal's pending-wrap flag (explicit positioning clears it)."""
    out, state = _editor(monkeypatch, width=20)
    line_editor.render_line("x" * 20, 20, state, out)  # exactly fills row 0
    out.truncate(0), out.seek(0)

    line_editor.render_line("x" * 21, 21, state, out)

    written = out.getvalue()
    assert "\r\n" in written
    assert written.endswith("x")
    assert state["cursor_row"] == 1


def test_resize_forces_full_redraw(monkeypatch):
    out, state = _editor(monkeypatch, width=80)
    line_editor.render_line("steer [now]> hi", 15, state, out)
    out.truncate(0), out.seek(0)

    monkeypatch.setattr(line_editor, "terminal_width", lambda: 40)
    line_editor.render_line("steer [now]> hip", 16, state, out)

    written = out.getvalue()
    assert "\r\x1b[J" in written
    assert line_editor._SYNC_BEGIN in written
    assert state["width"] == 40


def test_cursor_is_clamped_to_line_bounds(monkeypatch):
    out, state = _editor(monkeypatch)

    line_editor.render_line("ab", 99, state, out)

    assert state["cursor"] == 2


def test_full_redraw_repositions_mid_line_cursor(monkeypatch):
    out, state = _editor(monkeypatch, width=80)
    line_editor.render_line("steer [now]> hello", 14, state, out)

    # Cursor parked at col 14 (0-based) → CHA 15, on row 0.
    assert state["cursor_row"] == 0
    assert "\x1b[15G" in out.getvalue()


# =============================================================================
# Prompt wrapper (mode prefix + cursor offset)
# =============================================================================


def test_render_prompt_offsets_cursor_by_prefix(monkeypatch):
    captured: dict = {}

    def fake_render(line, cursor, state, out=None):
        captured["line"], captured["cursor"] = line, cursor

    monkeypatch.setattr(prompt, "render_line", fake_render)

    prompt._render_prompt(list("hello"), 2, "queue", {})

    assert captured["line"] == "steer [queue]> hello"
    assert captured["cursor"] == len("steer [queue]> ") + 2


def test_mode_toggle_rerenders_incrementally(monkeypatch):
    """Tab toggling the prefix must not wipe the screen (conhost flicker)."""
    out, state = _editor(monkeypatch)
    line_editor.render_line("steer [now]> hi", 15, state, out)
    out.truncate(0), out.seek(0)

    line_editor.render_line("steer [queue]> hi", 17, state, out)

    written = out.getvalue()
    assert "queue]> hi" in written  # rewrote from the first diff
    assert line_editor._SYNC_BEGIN not in written
    assert "\x1b[J" not in written


# =============================================================================
# input() fallback
# =============================================================================


def test_input_fallback_returns_text_in_now_mode(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt_text: "  hello  ")

    assert prompt._collect_via_input_fallback() == ("hello", "now")


def test_input_fallback_returns_none_on_empty(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt_text: "   ")

    assert prompt._collect_via_input_fallback() is None
