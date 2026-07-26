"""Tests for the /btw quick-side-question plugin."""

from unittest.mock import patch

from code_puppy.plugins.btw import inline_view, side_query
from code_puppy.plugins.btw.register_callbacks import (
    COMMAND_NAME,
    _custom_help,
    _handle_custom_command,
    _parse_question,
)


# ---------------------------------------------------------------------------
# Help + dispatch basics
# ---------------------------------------------------------------------------
def test_help_lists_btw():
    entries = _custom_help()
    assert any(name == COMMAND_NAME for name, _ in entries)


def test_other_commands_are_not_ours():
    assert _handle_custom_command("/woof hi", "woof") is None


def test_bare_btw_shows_usage_and_is_handled():
    with patch("code_puppy.messaging.emit_info") as emit:
        assert _handle_custom_command("/btw", "btw") is True
    assert emit.called
    assert "Usage" in str(emit.call_args)


def test_help_flag_shows_usage():
    with patch("code_puppy.messaging.emit_info"):
        assert _parse_question("/btw --help") is None


def test_parse_question_extracts_text():
    assert _parse_question("/btw why is the sky blue?") == "why is the sky blue?"


# ---------------------------------------------------------------------------
# Happy path, TTY: inline render + dismiss wait (model call mocked out)
# ---------------------------------------------------------------------------
def test_tty_happy_path_renders_inline_and_waits():
    with (
        patch.object(side_query, "resolve_model_name", return_value="gpt-5"),
        patch.object(side_query, "ask_blocking", return_value="a monoid, obviously"),
        patch.object(inline_view, "is_tty", return_value=True),
        patch.object(inline_view, "show_asking") as asking,
        patch.object(inline_view, "show_answer") as answer,
        patch.object(inline_view, "wait_for_dismiss") as wait,
        patch.object(inline_view, "emit_fallback") as fallback,
    ):
        assert _handle_custom_command("/btw what is a monad?", "btw") is True
    asking.assert_called_once_with("what is a monad?", "gpt-5")
    answer.assert_called_once_with("a monoid, obviously")
    wait.assert_called_once()
    fallback.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path, no TTY: transcript fallback, no key wait
# ---------------------------------------------------------------------------
def test_non_tty_happy_path_uses_fallback():
    with (
        patch.object(side_query, "resolve_model_name", return_value="gpt-5"),
        patch.object(side_query, "ask_blocking", return_value="42"),
        patch.object(inline_view, "is_tty", return_value=False),
        patch.object(inline_view, "wait_for_dismiss") as wait,
        patch.object(inline_view, "emit_fallback") as fallback,
        patch("code_puppy.messaging.emit_info"),
    ):
        assert _handle_custom_command("/btw meaning of life?", "btw") is True
    fallback.assert_called_once_with("meaning of life?", "42")
    wait.assert_not_called()


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------
def test_no_model_resolved_emits_error():
    with (
        patch.object(side_query, "resolve_model_name", return_value=None),
        patch("code_puppy.messaging.emit_error") as err,
    ):
        assert _handle_custom_command("/btw hi", "btw") is True
    assert err.called


def test_query_failure_is_swallowed_with_error():
    with (
        patch.object(side_query, "resolve_model_name", return_value="gpt-5"),
        patch.object(side_query, "ask_blocking", side_effect=RuntimeError("boom")),
        patch.object(inline_view, "is_tty", return_value=False),
        patch.object(inline_view, "emit_fallback") as fallback,
        patch("code_puppy.messaging.emit_info"),
        patch("code_puppy.messaging.emit_error") as err,
    ):
        assert _handle_custom_command("/btw hi", "btw") is True
    assert err.called
    fallback.assert_not_called()


# ---------------------------------------------------------------------------
# inline_view unit behavior
# ---------------------------------------------------------------------------
def test_is_tty_respects_no_tui_env(monkeypatch):
    monkeypatch.setenv("CODE_PUPPY_NO_TUI", "1")
    assert inline_view.is_tty() is False


def test_wait_for_dismiss_noop_without_tty(monkeypatch):
    monkeypatch.setenv("CODE_PUPPY_NO_TUI", "1")
    inline_view.wait_for_dismiss(timeout_s=0.01)  # must return instantly, no raise


def test_emit_fallback_includes_question_and_answer():
    with patch("code_puppy.messaging.emit_info") as emit:
        inline_view.emit_fallback("q?", "a.")
    text = str(emit.call_args)
    assert "q?" in text
    assert "a." in text


# ---------------------------------------------------------------------------
# Model resolution order: agent pin wins, global is fallback
# ---------------------------------------------------------------------------
def test_resolve_model_prefers_agent_pin():
    class FakeAgent:
        def get_model_name(self):
            return "pinned-model"

    with patch(
        "code_puppy.agents.agent_manager.get_current_agent",
        return_value=FakeAgent(),
    ):
        assert side_query.resolve_model_name() == "pinned-model"


def test_resolve_model_falls_back_to_global():
    class FakeAgent:
        def get_model_name(self):
            return None

    with (
        patch(
            "code_puppy.agents.agent_manager.get_current_agent",
            return_value=FakeAgent(),
        ),
        patch(
            "code_puppy.config.get_global_model_name",
            return_value="global-model",
        ),
    ):
        assert side_query.resolve_model_name() == "global-model"
