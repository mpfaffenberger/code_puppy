"""Tests for code_puppy/messaging/spinner/__init__.py module.

Tests the global spinner management functions including registration,
pausing/resuming, and context info updates.
"""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.messaging.spinner import (
    _active_spinners,
    clear_spinner_context,
    pause_all_spinners,
    register_spinner,
    resume_all_spinners,
    unregister_spinner,
    update_spinner_context,
)
from code_puppy.messaging.spinner.spinner_base import SpinnerBase


@pytest.fixture(autouse=True)
def clear_spinners():
    """Clear active spinners before and after each test."""
    _active_spinners.clear()
    yield
    _active_spinners.clear()


@pytest.fixture
def mock_spinner():
    """Create a mock spinner with pause and resume methods."""
    spinner = MagicMock()
    spinner.pause = MagicMock()
    spinner.resume = MagicMock()
    return spinner


class TestRegisterSpinner:
    """Tests for register_spinner function."""

    def test_register_adds_spinner_to_active_list(self, mock_spinner):
        """Test that registering a spinner adds it to the active list."""
        assert mock_spinner not in _active_spinners

        register_spinner(mock_spinner)

        assert mock_spinner in _active_spinners

    def test_register_does_not_add_duplicate(self, mock_spinner):
        """Test that registering the same spinner twice only adds it once."""
        register_spinner(mock_spinner)
        register_spinner(mock_spinner)

        assert _active_spinners.count(mock_spinner) == 1

    def test_register_multiple_different_spinners(self):
        """Test that multiple different spinners can be registered."""
        spinner1 = MagicMock()
        spinner2 = MagicMock()

        register_spinner(spinner1)
        register_spinner(spinner2)

        assert spinner1 in _active_spinners
        assert spinner2 in _active_spinners
        assert len(_active_spinners) == 2


class TestUnregisterSpinner:
    """Tests for unregister_spinner function."""

    def test_unregister_removes_spinner_from_active_list(self, mock_spinner):
        """Test that unregistering removes the spinner from active list."""
        register_spinner(mock_spinner)
        assert mock_spinner in _active_spinners

        unregister_spinner(mock_spinner)

        assert mock_spinner not in _active_spinners

    def test_unregister_nonexistent_spinner_is_safe(self, mock_spinner):
        """Test that unregistering a non-registered spinner doesn't raise."""
        assert mock_spinner not in _active_spinners

        # Should not raise
        unregister_spinner(mock_spinner)

        assert mock_spinner not in _active_spinners

    def test_unregister_only_removes_target_spinner(self):
        """Test that unregistering one spinner leaves others untouched."""
        spinner1 = MagicMock()
        spinner2 = MagicMock()
        register_spinner(spinner1)
        register_spinner(spinner2)

        unregister_spinner(spinner1)

        assert spinner1 not in _active_spinners
        assert spinner2 in _active_spinners


class TestPauseAllSpinners:
    """Tests for pause_all_spinners function."""

    @patch("code_puppy.tools.subagent_context.is_subagent", return_value=False)
    def test_pause_calls_pause_on_all_spinners(self, mock_is_subagent, mock_spinner):
        """Test that pause_all_spinners calls pause on each active spinner."""
        spinner2 = MagicMock()
        register_spinner(mock_spinner)
        register_spinner(spinner2)

        pause_all_spinners()

        mock_spinner.pause.assert_called_once()
        spinner2.pause.assert_called_once()

    @patch("code_puppy.tools.subagent_context.is_subagent", return_value=True)
    def test_pause_is_noop_when_subagent(self, mock_is_subagent, mock_spinner):
        """Test that pause_all_spinners is a no-op in subagent context."""
        register_spinner(mock_spinner)

        pause_all_spinners()

        mock_spinner.pause.assert_not_called()

    @patch("code_puppy.tools.subagent_context.is_subagent", return_value=False)
    def test_pause_handles_spinner_exception(self, mock_is_subagent):
        """Test that exceptions during pause are caught and ignored."""
        failing_spinner = MagicMock()
        failing_spinner.pause.side_effect = Exception("Pause failed!")
        working_spinner = MagicMock()

        register_spinner(failing_spinner)
        register_spinner(working_spinner)

        # Should not raise, and should continue to next spinner
        pause_all_spinners()

        failing_spinner.pause.assert_called_once()
        working_spinner.pause.assert_called_once()

    @patch("code_puppy.tools.subagent_context.is_subagent", return_value=False)
    def test_pause_with_empty_spinner_list(self, mock_is_subagent):
        """Test that pause_all_spinners works with no active spinners."""
        assert len(_active_spinners) == 0

        # Should not raise
        pause_all_spinners()


class TestResumeAllSpinners:
    """Tests for resume_all_spinners function."""

    @patch("code_puppy.tools.subagent_context.is_subagent", return_value=False)
    def test_resume_calls_resume_on_all_spinners(self, mock_is_subagent, mock_spinner):
        """Test that resume_all_spinners calls resume on each active spinner."""
        spinner2 = MagicMock()
        register_spinner(mock_spinner)
        register_spinner(spinner2)

        resume_all_spinners()

        mock_spinner.resume.assert_called_once()
        spinner2.resume.assert_called_once()

    @patch("code_puppy.tools.subagent_context.is_subagent", return_value=True)
    def test_resume_is_noop_when_subagent(self, mock_is_subagent, mock_spinner):
        """Test that resume_all_spinners is a no-op in subagent context."""
        register_spinner(mock_spinner)

        resume_all_spinners()

        mock_spinner.resume.assert_not_called()

    @patch("code_puppy.tools.subagent_context.is_subagent", return_value=False)
    def test_resume_handles_spinner_exception(self, mock_is_subagent):
        """Test that exceptions during resume are caught and ignored."""
        failing_spinner = MagicMock()
        failing_spinner.resume.side_effect = Exception("Resume failed!")
        working_spinner = MagicMock()

        register_spinner(failing_spinner)
        register_spinner(working_spinner)

        # Should not raise, and should continue to next spinner
        resume_all_spinners()

        failing_spinner.resume.assert_called_once()
        working_spinner.resume.assert_called_once()

    @patch("code_puppy.tools.subagent_context.is_subagent", return_value=False)
    def test_resume_with_empty_spinner_list(self, mock_is_subagent):
        """Test that resume_all_spinners works with no active spinners."""
        assert len(_active_spinners) == 0

        # Should not raise
        resume_all_spinners()


class TestSpinnerContext:
    """Tests for update_spinner_context and clear_spinner_context."""

    def test_update_spinner_context_sets_info(self):
        """Test that update_spinner_context sets context info."""
        test_info = "Processing file.py"

        update_spinner_context(test_info)

        assert SpinnerBase.get_context_info() == test_info

    def test_clear_spinner_context_clears_info(self):
        """Test that clear_spinner_context clears the context info."""
        update_spinner_context("Some info")
        assert SpinnerBase.get_context_info() != ""

        clear_spinner_context()

        assert SpinnerBase.get_context_info() == ""

    def test_update_context_with_empty_string(self):
        """Test updating context with empty string."""
        update_spinner_context("Initial info")

        update_spinner_context("")

        assert SpinnerBase.get_context_info() == ""

    def test_update_context_overwrites_previous(self):
        """Test that updating context overwrites previous value."""
        update_spinner_context("First")
        update_spinner_context("Second")

        assert SpinnerBase.get_context_info() == "Second"
