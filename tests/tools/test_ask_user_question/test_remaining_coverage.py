"""Tests targeting remaining uncovered lines in code_puppy/tools/ask_user_question/."""

import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# handler.py - lines 40, 55-56, 134-161, 174-188, 220, 230
# ---------------------------------------------------------------------------


def test_is_interactive_non_tty():
    """Cover is_interactive when stdin is not a TTY."""
    from code_puppy.tools.ask_user_question.handler import is_interactive

    with patch("sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = False
        assert is_interactive() is False


def test_is_interactive_attribute_error():
    """Cover is_interactive when stdin has no isatty."""
    from code_puppy.tools.ask_user_question.handler import is_interactive

    with patch("sys.stdin") as mock_stdin:
        mock_stdin.isatty.side_effect = AttributeError
        assert is_interactive() is False


def test_is_interactive_ci_env():
    """Cover is_interactive in CI environment."""
    from code_puppy.tools.ask_user_question.handler import is_interactive

    with patch("sys.stdin") as mock_stdin:
        mock_stdin.isatty.return_value = True
        with patch.dict(os.environ, {"CI": "true"}):
            assert is_interactive() is False


def test_ask_user_question_validation_error():
    """Cover validation error path."""
    from code_puppy.tools.ask_user_question.handler import ask_user_question

    # Missing required fields
    result = ask_user_question([{"bad": "data"}])
    assert result.error is not None


def test_ask_user_question_type_error():
    """Cover TypeError/ValueError in validation."""
    from code_puppy.tools.ask_user_question.handler import ask_user_question

    with patch(
        "code_puppy.tools.ask_user_question.handler._validate_input",
        side_effect=TypeError("bad type"),
    ):
        result = ask_user_question([{}])
        assert result.error is not None


def _mock_interactive(fn):
    """Helper to patch is_interactive to True."""
    return patch(
        "code_puppy.tools.ask_user_question.handler.is_interactive", return_value=True
    )(fn)


@_mock_interactive
def test_ask_user_question_timeout(_):
    """Cover timeout response."""
    from code_puppy.tools.ask_user_question.handler import ask_user_question
    from code_puppy.tools.ask_user_question.models import (
        AskUserQuestionInput,
        Question,
        QuestionOption,
    )

    q = Question(
        question="test?",
        header="Test",
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    validated = AskUserQuestionInput(questions=[q])

    with (
        patch(
            "code_puppy.tools.ask_user_question.handler._validate_input",
            return_value=validated,
        ),
        patch(
            "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
            return_value=([], False, True),
        ),
    ):
        result = ask_user_question([{}], timeout=5)
        assert result.timed_out is True


@_mock_interactive
def test_ask_user_question_cancelled(_):
    """Cover cancelled response."""
    from code_puppy.tools.ask_user_question.handler import ask_user_question
    from code_puppy.tools.ask_user_question.models import (
        AskUserQuestionInput,
        Question,
        QuestionOption,
    )

    q = Question(
        question="test?",
        header="Test",
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    validated = AskUserQuestionInput(questions=[q])

    with (
        patch(
            "code_puppy.tools.ask_user_question.handler._validate_input",
            return_value=validated,
        ),
        patch(
            "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
            return_value=([], True, False),
        ),
    ):
        result = ask_user_question([{}])
        assert result.cancelled is True


@_mock_interactive
def test_ask_user_question_keyboard_interrupt(_):
    """Cover KeyboardInterrupt path."""
    from code_puppy.tools.ask_user_question.handler import ask_user_question
    from code_puppy.tools.ask_user_question.models import (
        AskUserQuestionInput,
        Question,
        QuestionOption,
    )

    q = Question(
        question="test?",
        header="Test",
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    validated = AskUserQuestionInput(questions=[q])

    with (
        patch(
            "code_puppy.tools.ask_user_question.handler._validate_input",
            return_value=validated,
        ),
        patch(
            "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
            side_effect=KeyboardInterrupt,
        ),
    ):
        result = ask_user_question([{}])
        assert result.cancelled is True


@_mock_interactive
def test_ask_user_question_os_error(_):
    """Cover OSError path."""
    from code_puppy.tools.ask_user_question.handler import ask_user_question
    from code_puppy.tools.ask_user_question.models import (
        AskUserQuestionInput,
        Question,
        QuestionOption,
    )

    q = Question(
        question="test?",
        header="Test",
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    validated = AskUserQuestionInput(questions=[q])

    with (
        patch(
            "code_puppy.tools.ask_user_question.handler._validate_input",
            return_value=validated,
        ),
        patch(
            "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
            side_effect=OSError("terminal error"),
        ),
    ):
        result = ask_user_question([{}])
        assert result.error is not None


@_mock_interactive
def test_ask_user_question_success(_):
    """Cover successful answer collection."""
    from code_puppy.tools.ask_user_question.handler import ask_user_question
    from code_puppy.tools.ask_user_question.models import (
        AskUserQuestionInput,
        Question,
        QuestionAnswer,
        QuestionOption,
    )

    q = Question(
        question="test?",
        header="Test",
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    validated = AskUserQuestionInput(questions=[q])
    answer = QuestionAnswer(question_header="Test", selected_options=["A"])

    with (
        patch(
            "code_puppy.tools.ask_user_question.handler._validate_input",
            return_value=validated,
        ),
        patch(
            "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
            return_value=([answer], False, False),
        ),
    ):
        result = ask_user_question([{}])
        assert len(result.answers) == 1


def test_async_context_error_is_runtime_error():
    """Verify AsyncContextError is a RuntimeError subclass."""
    from code_puppy.tools.ask_user_question.handler import AsyncContextError

    assert issubclass(AsyncContextError, RuntimeError)


def test_format_validation_error():
    """Cover _format_validation_error (lines 220, 230)."""
    from pydantic import BaseModel, ValidationError

    from code_puppy.tools.ask_user_question.handler import _format_validation_error

    class Dummy(BaseModel):
        x: int

    try:
        Dummy(x="not_an_int")
    except ValidationError as e:
        msg = _format_validation_error(e)
        assert "Validation error" in msg


def test_format_validation_error_empty():
    """Cover empty errors list."""
    from code_puppy.tools.ask_user_question.handler import _format_validation_error

    mock_err = MagicMock()
    mock_err.errors.return_value = []
    result = _format_validation_error(mock_err)
    assert result == "Validation error"


def test_format_validation_error_many():
    """Cover truncation of many errors."""
    from code_puppy.tools.ask_user_question.handler import (
        MAX_VALIDATION_ERRORS_SHOWN,
        _format_validation_error,
    )

    mock_err = MagicMock()
    mock_err.errors.return_value = [
        {"loc": ("field",), "msg": f"error {i}"}
        for i in range(MAX_VALIDATION_ERRORS_SHOWN + 5)
    ]
    result = _format_validation_error(mock_err)
    assert "and " in result
    assert "more" in result


# ---------------------------------------------------------------------------
# models.py - lines 57-59
# ---------------------------------------------------------------------------


def test_sanitizer_none_not_allowed():
    """Cover sanitizer when None is not allowed."""
    from code_puppy.tools.ask_user_question.models import _make_sanitizer

    sanitizer = _make_sanitizer(allow_none=False)
    with pytest.raises(ValueError, match="cannot be None"):
        sanitizer(None)


def test_sanitizer_none_allowed():
    """Cover sanitizer when None is allowed."""
    from code_puppy.tools.ask_user_question.models import _make_sanitizer

    sanitizer = _make_sanitizer(allow_none=True, default="default_val")
    result = sanitizer(None)
    assert result == "default_val"


# ---------------------------------------------------------------------------
# registration.py - lines 19-87
# ---------------------------------------------------------------------------


def test_register_ask_user_question():
    """Cover the registration function."""
    from code_puppy.tools.ask_user_question.registration import (
        register_ask_user_question,
    )

    mock_agent = MagicMock()
    # The decorator should be called
    mock_agent.tool = lambda f: f  # identity decorator
    register_ask_user_question(mock_agent)


# ---------------------------------------------------------------------------
# terminal_ui.py - uncovered lines
# ---------------------------------------------------------------------------


def test_question_ui_state_is_question_answered():
    """Cover is_question_answered for multi-select."""
    from code_puppy.tools.ask_user_question.models import Question, QuestionOption
    from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState

    q1 = Question(
        question="test?",
        header="Test",
        multi_select=True,
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    q2 = Question(
        question="test2?",
        header="T2",
        multi_select=False,
        options=[QuestionOption(label="X"), QuestionOption(label="Y")],
    )
    state = QuestionUIState([q1, q2])

    # Not answered yet
    assert state.is_question_answered(0) is False
    assert state.is_question_answered(1) is False

    # Multi-select: add an option
    state.selected_options[0].add(0)
    assert state.is_question_answered(0) is True

    # Multi-select: other text
    state.selected_options[0].clear()
    state.other_texts[0] = "custom"
    assert state.is_question_answered(0) is True

    # Single select
    state.single_selections[1] = 0
    assert state.is_question_answered(1) is True


def test_question_ui_state_other_text():
    """Cover enter_other_text_mode and commit_other_text."""
    from code_puppy.tools.ask_user_question.models import Question, QuestionOption
    from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState

    q = Question(
        question="test?",
        header="Test",
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    state = QuestionUIState([q])

    state.enter_other_text_mode()
    assert state.entering_other_text is True

    # Empty text - should not save
    state.other_text_buffer = "   "
    state.commit_other_text()
    assert state.other_texts[0] is None

    # Valid text
    state.enter_other_text_mode()
    state.other_text_buffer = "custom answer"
    state.commit_other_text()
    assert state.other_texts[0] == "custom answer"


def test_question_ui_state_select_all_none():
    """Cover select_all_options and select_no_options."""
    from code_puppy.tools.ask_user_question.models import Question, QuestionOption
    from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState

    q = Question(
        question="test?",
        header="Test",
        multi_select=True,
        options=[
            QuestionOption(label="A"),
            QuestionOption(label="B"),
            QuestionOption(label="C"),
        ],
    )
    state = QuestionUIState([q])

    state.select_all_options()
    assert len(state.selected_options[0]) == 3

    state.select_no_options()
    assert len(state.selected_options[0]) == 0

    # Single-select - should be no-ops
    q2 = Question(
        question="t?",
        header="T",
        multi_select=False,
        options=[QuestionOption(label="X"), QuestionOption(label="Y")],
    )
    state2 = QuestionUIState([q2])
    state2.select_all_options()  # no-op
    state2.select_no_options()  # no-op


def test_question_ui_state_navigation():
    """Cover next_question and prev_question."""
    from code_puppy.tools.ask_user_question.models import Question, QuestionOption
    from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState

    q1 = Question(
        question="q1?",
        header="Q1",
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    q2 = Question(
        question="q2?",
        header="Q2",
        options=[QuestionOption(label="B"), QuestionOption(label="C")],
    )
    state = QuestionUIState([q1, q2])

    assert state.current_question_index == 0
    state.next_question()
    assert state.current_question_index == 1
    state.next_question()  # should not go past end
    assert state.current_question_index == 1
    state.prev_question()
    assert state.current_question_index == 0
    state.prev_question()  # should not go below 0
    assert state.current_question_index == 0


def test_question_ui_state_toggle_select():
    """Cover toggle_current_option and select_current_option."""
    from code_puppy.tools.ask_user_question.models import Question, QuestionOption
    from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState

    q1 = Question(
        question="q?",
        header="Q",
        multi_select=True,
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    q2 = Question(
        question="q2?",
        header="Q2",
        multi_select=False,
        options=[QuestionOption(label="X"), QuestionOption(label="Y")],
    )
    state = QuestionUIState([q1, q2])

    # Multi-select toggle
    state.toggle_current_option()  # select 0
    assert 0 in state.selected_options[0]
    state.toggle_current_option()  # deselect 0
    assert 0 not in state.selected_options[0]

    # Single-select toggle is no-op
    state.current_question_index = 1
    state.toggle_current_option()  # no-op for single select

    # select_current_option
    state.select_current_option()
    assert state.single_selections[1] == 0

    # select_current_option on multi-select is no-op
    state.current_question_index = 0
    state.select_current_option()  # no-op


def test_question_ui_state_get_answers():
    """Cover get_answers with multi and single select."""
    from code_puppy.tools.ask_user_question.models import Question, QuestionOption
    from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState

    q1 = Question(
        question="q1?",
        header="Q1",
        multi_select=True,
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    q2 = Question(
        question="q2?",
        header="Q2",
        multi_select=False,
        options=[QuestionOption(label="X"), QuestionOption(label="Y")],
    )
    state = QuestionUIState([q1, q2])

    state.selected_options[0].add(0)
    state.selected_options[0].add(1)
    state.single_selections[1] = 0

    answers = state.build_answers()
    assert len(answers) == 2
    assert answers[0].selected_options == ["A", "B"]
    assert answers[1].selected_options == ["X"]


def test_question_ui_state_is_option_selected():
    """Cover is_option_selected."""
    from code_puppy.tools.ask_user_question.models import Question, QuestionOption
    from code_puppy.tools.ask_user_question.terminal_ui import QuestionUIState

    q = Question(
        question="q?",
        header="Q",
        multi_select=False,
        options=[QuestionOption(label="A"), QuestionOption(label="B")],
    )
    state = QuestionUIState([q])
    state.single_selections[0] = 1
    assert state.is_option_selected(1) is True
    assert state.is_option_selected(0) is False


# ---------------------------------------------------------------------------
# demo_tui.py - line 55
# ---------------------------------------------------------------------------


def test_demo_tui_main():
    """Cover demo_tui main function."""
    from code_puppy.tools.ask_user_question import demo_tui

    # The if __name__ == '__main__' guard won't fire on import
    assert hasattr(demo_tui, "main")


# ---------------------------------------------------------------------------
# tui_loop.py - line 338
# ---------------------------------------------------------------------------


def test_tui_loop_module_import():
    """Cover tui_loop module import."""
    from code_puppy.tools.ask_user_question import tui_loop

    assert hasattr(tui_loop, "run_question_tui")
