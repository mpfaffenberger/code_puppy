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
