"""Tests for ask_user_question handler."""

import os
from unittest.mock import patch

import pytest

from code_puppy.tools.ask_user_question.handler import (
    ask_user_question,
    is_interactive,
)


class TestIsInteractive:
    """Tests for is_interactive() detection."""

    def test_non_tty_stdin(self) -> None:
        """Non-TTY stdin should return False."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            assert is_interactive() is False

    def test_ci_environment_github_actions(self) -> None:
        """GitHub Actions CI should return False."""
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                assert is_interactive() is False

    def test_ci_environment_gitlab(self) -> None:
        """GitLab CI should return False."""
        with patch.dict(os.environ, {"GITLAB_CI": "true"}):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                assert is_interactive() is False

    def test_ci_environment_jenkins(self) -> None:
        """Jenkins should return False."""
        with patch.dict(os.environ, {"JENKINS_URL": "http://jenkins.example.com"}):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                assert is_interactive() is False

    def test_ci_environment_generic(self) -> None:
        """Generic CI env var should return False."""
        with patch.dict(os.environ, {"CI": "true"}):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                assert is_interactive() is False


class TestAskUserQuestionValidation:
    """Tests for input validation in ask_user_question.

    These tests mock is_interactive to bypass the non-interactive check
    so we can test the validation logic directly.
    """

    @pytest.fixture(autouse=True)
    def mock_interactive(self):
        """Mock is_interactive to return True for all validation tests."""
        with patch(
            "code_puppy.tools.ask_user_question.handler.is_interactive",
            return_value=True,
        ):
            yield

    def test_empty_questions_array(self) -> None:
        """Empty questions array should return validation error."""
        result = ask_user_question([])
        assert result.error is not None
        assert "questions" in result.error.lower()
        assert result.answers == []

    def test_too_many_questions(self) -> None:
        """More than 10 questions should return validation error."""
        questions = [
            {
                "question": f"Q{i}?",
                "header": f"H{i}",
                "options": [{"label": "A"}, {"label": "B"}],
            }
            for i in range(11)  # MAX_QUESTIONS_PER_CALL is 10
        ]
        result = ask_user_question(questions)
        assert result.error is not None
        assert result.answers == []

    def test_header_too_long(self) -> None:
        """Header over 12 chars should return validation error."""
        result = ask_user_question(
            [
                {
                    "question": "Which database?",
                    "header": "TooLongHeader!",  # 14 chars
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ]
        )
        assert result.error is not None
        # The error message includes the constraint info
        assert "12" in result.error or "header" in result.error.lower()

    def test_too_few_options(self) -> None:
        """Less than 2 options should return validation error."""
        result = ask_user_question(
            [
                {
                    "question": "Which database?",
                    "header": "Database",
                    "options": [{"label": "Only one"}],
                }
            ]
        )
        assert result.error is not None

    def test_too_many_options(self) -> None:
        """More than 6 options should return validation error."""
        result = ask_user_question(
            [
                {
                    "question": "Which database?",
                    "header": "Database",
                    "options": [{"label": f"Opt{i}"} for i in range(7)],
                }
            ]
        )
        assert result.error is not None

    def test_duplicate_headers(self) -> None:
        """Duplicate question headers should return validation error."""
        result = ask_user_question(
            [
                {
                    "question": "First?",
                    "header": "Same",
                    "options": [{"label": "A"}, {"label": "B"}],
                },
                {
                    "question": "Second?",
                    "header": "Same",
                    "options": [{"label": "C"}, {"label": "D"}],
                },
            ]
        )
        assert result.error is not None
        # Error should mention headers or uniqueness
        assert (
            "header" in result.error.lower() or "unique" in result.error.lower()
        )

    def test_duplicate_option_labels(self) -> None:
        """Duplicate option labels should return validation error."""
        result = ask_user_question(
            [
                {
                    "question": "Which?",
                    "header": "Choices",
                    "options": [{"label": "Same"}, {"label": "Same"}],
                }
            ]
        )
        assert result.error is not None

    def test_missing_required_field(self) -> None:
        """Missing required field should return validation error."""
        result = ask_user_question(
            [
                {
                    "question": "Which?",
                    # missing "header"
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ]
        )
        assert result.error is not None


class TestAskUserQuestionNonInteractive:
    """Tests for non-interactive environment handling."""

    def test_returns_error_when_non_interactive(self) -> None:
        """Should return error when not in interactive terminal."""
        with patch(
            "code_puppy.tools.ask_user_question.handler.is_interactive",
            return_value=False,
        ):
            result = ask_user_question(
                [
                    {
                        "question": "Which database?",
                        "header": "Database",
                        "options": [{"label": "A"}, {"label": "B"}],
                    }
                ]
            )
        assert result.error is not None
        assert "interactive" in result.error.lower()
        assert result.answers == []
        assert result.cancelled is False
        assert result.timed_out is False
