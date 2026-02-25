"""Full coverage tests for tools/ask_user_question/handler.py."""

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.ask_user_question.handler import (
    _cancelled_response,
    _format_validation_error,
    _run_interactive_picker,
    ask_user_question,
    is_interactive,
)


class TestIsInteractive:
    def test_tty(self):
        with (
            patch.object(sys, "stdin") as mock_stdin,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_stdin.isatty.return_value = True
            assert is_interactive() is True

    def test_not_tty(self):
        with patch.object(sys, "stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            assert is_interactive() is False

    def test_attribute_error(self):
        with patch.object(sys, "stdin", new=None):
            assert is_interactive() is False

    def test_ci_env(self):
        with (
            patch.object(sys, "stdin") as mock_stdin,
            patch.dict(os.environ, {"CI": "true"}),
        ):
            mock_stdin.isatty.return_value = True
            assert is_interactive() is False


class TestCancelledResponse:
    def test_returns_cancelled(self):
        result = _cancelled_response()
        assert result.cancelled is True
        assert result.error is None


class TestAskUserQuestion:
    def test_subagent_blocked(self):
        with patch(
            "code_puppy.tools.ask_user_question.handler.is_subagent", return_value=True
        ):
            result = ask_user_question(
                [{"question": "q", "header": "h", "options": [{"label": "a"}]}]
            )
            assert result.error is not None
            assert "sub-agent" in result.error

    def test_wiggum_blocked(self):
        with (
            patch(
                "code_puppy.tools.ask_user_question.handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_wiggum_active",
                return_value=True,
            ),
        ):
            result = ask_user_question(
                [{"question": "q", "header": "h", "options": [{"label": "a"}]}]
            )
            assert "wiggum" in result.error.lower()

    def test_non_interactive(self):
        with (
            patch(
                "code_puppy.tools.ask_user_question.handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_wiggum_active",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_interactive",
                return_value=False,
            ),
        ):
            result = ask_user_question(
                [{"question": "q", "header": "h", "options": [{"label": "a"}]}]
            )
            assert "not running" in result.error

    def test_validation_error(self):
        with (
            patch(
                "code_puppy.tools.ask_user_question.handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_wiggum_active",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_interactive",
                return_value=True,
            ),
        ):
            result = ask_user_question([{"bad": "data"}])
            assert result.error is not None

    def test_type_error(self):
        with (
            patch(
                "code_puppy.tools.ask_user_question.handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_wiggum_active",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_interactive",
                return_value=True,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler._validate_input",
                side_effect=TypeError("bad"),
            ),
        ):
            result = ask_user_question([])
            assert "Validation error" in result.error

    def test_keyboard_interrupt(self):
        with (
            patch(
                "code_puppy.tools.ask_user_question.handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_wiggum_active",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_interactive",
                return_value=True,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler._validate_input"
            ) as mock_val,
            patch(
                "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
                side_effect=KeyboardInterrupt,
            ),
        ):
            mock_val.return_value = MagicMock(questions=[MagicMock()])
            result = ask_user_question(
                [
                    {
                        "question": "q",
                        "header": "h",
                        "options": [{"label": "a"}, {"label": "b"}],
                    }
                ]
            )
            assert result.cancelled is True

    def test_os_error(self):
        with (
            patch(
                "code_puppy.tools.ask_user_question.handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_wiggum_active",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_interactive",
                return_value=True,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler._validate_input"
            ) as mock_val,
            patch(
                "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
                side_effect=OSError("fail"),
            ),
        ):
            mock_val.return_value = MagicMock(questions=[MagicMock()])
            result = ask_user_question(
                [
                    {
                        "question": "q",
                        "header": "h",
                        "options": [{"label": "a"}, {"label": "b"}],
                    }
                ]
            )
            assert "error" in result.error.lower()

    def test_timeout(self):
        with (
            patch(
                "code_puppy.tools.ask_user_question.handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_wiggum_active",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_interactive",
                return_value=True,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler._validate_input"
            ) as mock_val,
            patch(
                "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
                return_value=([], False, True),
            ),
        ):
            mock_val.return_value = MagicMock(questions=[MagicMock()])
            result = ask_user_question(
                [
                    {
                        "question": "q",
                        "header": "h",
                        "options": [{"label": "a"}, {"label": "b"}],
                    }
                ]
            )
            assert result.timed_out is True

    def test_cancelled(self):
        with (
            patch(
                "code_puppy.tools.ask_user_question.handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_wiggum_active",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_interactive",
                return_value=True,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler._validate_input"
            ) as mock_val,
            patch(
                "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
                return_value=([], True, False),
            ),
        ):
            mock_val.return_value = MagicMock(questions=[MagicMock()])
            result = ask_user_question(
                [
                    {
                        "question": "q",
                        "header": "h",
                        "options": [{"label": "a"}, {"label": "b"}],
                    }
                ]
            )
            assert result.cancelled is True

    def test_success(self):
        from code_puppy.tools.ask_user_question.models import QuestionAnswer

        answer = QuestionAnswer(
            question_index=0, question_header="h", selected_options=["a"]
        )
        with (
            patch(
                "code_puppy.tools.ask_user_question.handler.is_subagent",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_wiggum_active",
                return_value=False,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler.is_interactive",
                return_value=True,
            ),
            patch(
                "code_puppy.tools.ask_user_question.handler._validate_input"
            ) as mock_val,
            patch(
                "code_puppy.tools.ask_user_question.handler._run_interactive_picker",
                return_value=([answer], False, False),
            ),
        ):
            mock_val.return_value = MagicMock(questions=[MagicMock()])
            result = ask_user_question(
                [
                    {
                        "question": "q",
                        "header": "h",
                        "options": [{"label": "a"}, {"label": "b"}],
                    }
                ]
            )
            assert len(result.answers) == 1


class TestRunInteractivePicker:
    def test_async_context_raises(self):
        """When in async context, should raise RuntimeError."""

        async def in_async():
            with pytest.raises(RuntimeError):
                _run_interactive_picker([], 10)

        asyncio.run(in_async())


class TestFormatValidationError:
    def test_no_errors(self):
        mock_err = MagicMock()
        mock_err.errors.return_value = []
        result = _format_validation_error(mock_err)
        assert result == "Validation error"

    def test_with_errors(self):
        mock_err = MagicMock()
        mock_err.errors.return_value = [
            {"loc": ("field",), "msg": "is required"},
        ]
        result = _format_validation_error(mock_err)
        assert "field" in result

    def test_truncated_errors(self):
        mock_err = MagicMock()
        mock_err.errors.return_value = [
            {"loc": (f"field{i}",), "msg": f"error{i}"} for i in range(20)
        ]
        result = _format_validation_error(mock_err)
        assert "more" in result
