"""Unit tests for the raw-terminal steering prompt key handling.

No prompt_toolkit here — on purpose. The steering prompt is stdlib-only and
single-line, so these tests exercise the pure key handler and fallback path
without putting pytest's terminal into raw mode. Good dog, no TTY crimes.
"""

from __future__ import annotations

import builtins

import pytest

from code_puppy.plugins.agent_steering import steering_prompt as prompt


@pytest.fixture
def buffer() -> list[str]:
    return []


# =============================================================================
# Pure key handling
# =============================================================================


def test_printable_chars_append(buffer):
    mode = "now"

    action, mode = prompt._handle_key("h", buffer, mode)
    assert action == "continue"
    assert mode == "now"
    assert buffer == ["h"]

    action, mode = prompt._handle_key("i", buffer, mode)
    assert action == "continue"
    assert mode == "now"
    assert buffer == ["h", "i"]


def test_tab_toggles_mode_now_to_queue_to_now(buffer):
    action, mode = prompt._handle_key("\t", buffer, "now")
    assert action == "redraw"
    assert mode == "queue"
    assert buffer == []

    action, mode = prompt._handle_key("\t", buffer, mode)
    assert action == "redraw"
    assert mode == "now"
    assert buffer == []


@pytest.mark.parametrize("backspace", ["\x7f", "\b"])
def test_backspace_removes_one_char(backspace):
    buffer = list("abc")

    action, mode = prompt._handle_key(backspace, buffer, "queue")

    assert action == "redraw"
    assert mode == "queue"
    assert buffer == list("ab")


@pytest.mark.parametrize("backspace", ["\x7f", "\b"])
def test_backspace_on_empty_buffer_is_noop(backspace, buffer):
    action, mode = prompt._handle_key(backspace, buffer, "now")

    assert action == "continue"
    assert mode == "now"
    assert buffer == []


@pytest.mark.parametrize("enter", ["\r", "\n"])
def test_enter_submits(enter, buffer):
    buffer.extend(" ship it ")

    action, mode = prompt._handle_key(enter, buffer, "queue")

    assert action == "submit"
    assert mode == "queue"
    assert prompt._finish_submit(buffer, mode) == ("ship it", "queue")


def test_empty_enter_returns_none(buffer):
    buffer.extend("   ")

    action, mode = prompt._handle_key("\r", buffer, "now")

    assert action == "submit"
    assert prompt._finish_submit(buffer, mode) is None


@pytest.mark.parametrize("cancel", ["\x1b", "\x03", "\x04", ""])
def test_cancel_keys_return_cancel(cancel, buffer):
    buffer.extend("do not submit")

    action, mode = prompt._handle_key(cancel, buffer, "queue")

    assert action == "cancel"
    assert mode == "queue"
    assert buffer == list("do not submit")


@pytest.mark.parametrize("control", ["\x00", "\x01", "\x02", "\x1f"])
def test_other_control_chars_are_ignored(control, buffer):
    action, mode = prompt._handle_key(control, buffer, "now")

    assert action == "continue"
    assert mode == "now"
    assert buffer == []


# =============================================================================
# Escape-sequence handling (_iter_keys)
# =============================================================================


@pytest.mark.parametrize(
    "sequence",
    [
        "\x1b[D",  # left arrow (CSI)
        "\x1b[C",  # right arrow
        "\x1b[A",  # up arrow
        "\x1b[B",  # down arrow
        "\x1b[H",  # Home
        "\x1b[1;5D",  # Ctrl+left (CSI with params)
        "\x1b[3~",  # Delete
        "\x1bOD",  # left arrow (SS3 / application mode)
        "\x1bx",  # Alt+x chord
    ],
)
def test_iter_keys_swallows_escape_sequences(sequence):
    """Nav keys must be ignored entirely — NOT treated as ESC + garbage."""
    assert list(prompt._iter_keys(sequence)) == []


def test_iter_keys_lone_esc_passes_through():
    """A bare ESC press still reaches the handler (→ cancel)."""
    assert list(prompt._iter_keys("\x1b")) == ["\x1b"]


def test_iter_keys_text_around_sequence_survives():
    """Printable chars on either side of a nav key are preserved in order."""
    assert list(prompt._iter_keys("ab\x1b[Dcd")) == ["a", "b", "c", "d"]


def test_iter_keys_plain_text_passes_through():
    assert list(prompt._iter_keys("hello")) == list("hello")


def test_iter_keys_left_arrow_does_not_cancel_prompt():
    """Regression: left arrow used to read as lone ESC and cancel the steer."""
    buffer: list[str] = []
    mode = "now"
    for ch in prompt._iter_keys("hi\x1b[D!"):
        action, mode = prompt._handle_key(ch, buffer, mode)
        assert action != "cancel"
    assert buffer == ["h", "i", "!"]


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
def test_cursor_row_for_length_handles_wrap(text_len, width, expected_row):
    assert prompt._cursor_row_for_length(text_len, width) == expected_row


def test_cursor_row_for_length_clamps_pathological_width():
    # width <= 0 must not blow up division
    assert prompt._cursor_row_for_length(10, 0) == 9
    assert prompt._cursor_row_for_length(0, 0) == 0


def test_render_prompt_jumps_up_then_clears_before_redrawing(monkeypatch):
    """Wrapped redraws must rewind to the prompt's start row, not stamp again."""
    writes: list[str] = []
    monkeypatch.setattr(
        prompt.sys.stdout, "write", lambda s: writes.append(s) or len(s)
    )
    monkeypatch.setattr(prompt.sys.stdout, "flush", lambda: None)
    monkeypatch.setattr(prompt, "_terminal_width", lambda: 20)

    state = prompt._make_render_state()
    # Pretend a previous render landed the cursor 3 rows below its start.
    state["cursor_row"] = 3

    prompt._render_prompt(list("hello"), "now", state)

    joined = "".join(writes)
    # Move up 3 rows, then \r, then clear-to-end-of-screen, then the line.
    assert "\x1b[3A" in joined
    assert "\r\x1b[J" in joined
    assert "steer [now]> hello" in joined
    # Order matters: rewind happens before the wipe, wipe before the redraw.
    assert (
        joined.index("\x1b[3A")
        < joined.index("\r\x1b[J")
        < joined.index("steer [now]>")
    )


def test_render_prompt_skips_cursor_up_on_first_render(monkeypatch):
    """No prior row → no spurious ``\\x1b[NA`` escape (would scroll the term)."""
    writes: list[str] = []
    monkeypatch.setattr(
        prompt.sys.stdout, "write", lambda s: writes.append(s) or len(s)
    )
    monkeypatch.setattr(prompt.sys.stdout, "flush", lambda: None)
    monkeypatch.setattr(prompt, "_terminal_width", lambda: 80)

    state = prompt._make_render_state()
    prompt._render_prompt([], "queue", state)

    joined = "".join(writes)
    # No cursor-up escape on the first render — that would scroll the term.
    import re

    assert re.search(r"\x1b\[\d+A", joined) is None
    assert "steer [queue]> " in joined
    assert state["cursor_row"] == 0


def test_render_prompt_wraps_output_in_synchronized_mode(monkeypatch):
    """DEC 2026 begin/end must bracket the redraw so it commits atomically."""
    writes: list[str] = []
    monkeypatch.setattr(
        prompt.sys.stdout, "write", lambda s: writes.append(s) or len(s)
    )
    monkeypatch.setattr(prompt.sys.stdout, "flush", lambda: None)
    monkeypatch.setattr(prompt, "_terminal_width", lambda: 80)

    state = prompt._make_render_state()
    state["cursor_row"] = 2
    prompt._render_prompt(list("hi"), "now", state)

    joined = "".join(writes)
    begin_idx = joined.index(prompt._SYNC_BEGIN)
    end_idx = joined.index(prompt._SYNC_END)
    # Begin opens the frame, the cursor-up + wipe + line all live strictly
    # inside, and end closes it. Atomic commit → no flicker.
    assert begin_idx < joined.index("\x1b[2A") < joined.index("\r\x1b[J")
    assert joined.index("steer [now]> hi") < end_idx
    # And the END escape is the very last thing written.
    assert joined.endswith(prompt._SYNC_END)


def test_render_prompt_updates_cursor_row_after_wrap(monkeypatch):
    """After redrawing wrapped content, state must reflect the new row."""
    monkeypatch.setattr(prompt.sys.stdout, "write", lambda s: len(s))
    monkeypatch.setattr(prompt.sys.stdout, "flush", lambda: None)
    monkeypatch.setattr(prompt, "_terminal_width", lambda: 20)

    state = prompt._make_render_state()
    # "steer [now]> " is 13 chars; add 50 chars of content → total 63 → row 3 at width 20.
    prompt._render_prompt(list("x" * 50), "now", state)

    assert state["cursor_row"] == (13 + 50 - 1) // 20


# =============================================================================
# input() fallback
# =============================================================================


def test_input_fallback_returns_text_in_now_mode(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt_text: "  hello  ")

    assert prompt._collect_via_input_fallback() == ("hello", "now")


def test_input_fallback_returns_none_on_empty(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt_text: "   ")

    assert prompt._collect_via_input_fallback() is None


@pytest.mark.parametrize("exc", [KeyboardInterrupt, EOFError])
def test_input_fallback_returns_none_on_abort(monkeypatch, exc):
    def _raise(_prompt_text: str):
        raise exc

    monkeypatch.setattr(builtins, "input", _raise)

    assert prompt._collect_via_input_fallback() is None


# =============================================================================
# Public dispatch
# =============================================================================


def test_collect_uses_input_fallback_when_not_tty(monkeypatch):
    monkeypatch.setattr(prompt, "_can_run_full_ui", lambda: False)
    monkeypatch.setattr(prompt, "_collect_via_input_fallback", lambda: ("x", "now"))

    assert prompt.collect_steering_message() == ("x", "now")


def test_collect_uses_raw_terminal_when_tty(monkeypatch):
    monkeypatch.setattr(prompt, "_can_run_full_ui", lambda: True)
    monkeypatch.setattr(prompt, "_collect_via_raw_terminal", lambda: ("x", "queue"))

    assert prompt.collect_steering_message() == ("x", "queue")
