"""Tests for the key-listener suspend/resume contract.

When ``ask_user_question`` opens its prompt_toolkit TUI, the agent-runtime
key listener (which holds stdin in cbreak mode for Ctrl+T / Ctrl+X / etc.)
must be suspended for the duration of the TUI — otherwise the two readers
race for every keystroke and the user has to press keys multiple times.

This module locks in that contract by mocking the listener handle and the
TUI loop, then asserting suspend/resume are called in the right order.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.ask_user_question.models import Question, QuestionOption
from code_puppy.tools.ask_user_question.terminal_ui import interactive_question_picker


def _make_questions() -> list[Question]:
    return [
        Question(
            question="Pick one?",
            header="Test",
            multi_select=False,
            options=[
                QuestionOption(label="Alpha", description="A"),
                QuestionOption(label="Beta", description="B"),
            ],
        )
    ]


@pytest.mark.asyncio
async def test_suspends_and_resumes_key_listener_when_present():
    """When an active listener exists, it is suspended before and resumed
    after the TUI runs — regardless of how the TUI exits."""
    fake_handle = MagicMock()
    fake_handle.suspend.return_value = True  # listener acknowledged

    fake_run = AsyncMock(return_value=([], False, False))

    with (
        patch(
            "code_puppy.agents._key_listeners.get_active_handle",
            return_value=fake_handle,
        ),
        patch(
            "code_puppy.tools.ask_user_question.tui_loop.run_question_tui",
            fake_run,
        ),
    ):
        await interactive_question_picker(_make_questions(), timeout_seconds=5)

    fake_handle.suspend.assert_called_once()
    fake_handle.resume.assert_called_once()


@pytest.mark.asyncio
async def test_no_listener_handle_is_a_noop():
    """If no listener is registered (e.g. non-TTY / tests), we don't blow up."""
    fake_run = AsyncMock(return_value=([], False, False))

    with (
        patch(
            "code_puppy.agents._key_listeners.get_active_handle",
            return_value=None,
        ),
        patch(
            "code_puppy.tools.ask_user_question.tui_loop.run_question_tui",
            fake_run,
        ),
    ):
        result = await interactive_question_picker(_make_questions(), timeout_seconds=5)

    assert result == ([], False, False)


@pytest.mark.asyncio
async def test_resume_called_when_suspend_succeeds_even_if_tui_raises():
    """Listener must be resumed even when the TUI raises — otherwise the
    next agent turn would still have the listener parked on suspend_event
    and stdin would stay dead."""
    fake_handle = MagicMock()
    fake_handle.suspend.return_value = True

    fake_run = AsyncMock(side_effect=RuntimeError("tui exploded"))

    with (
        patch(
            "code_puppy.agents._key_listeners.get_active_handle",
            return_value=fake_handle,
        ),
        patch(
            "code_puppy.tools.ask_user_question.tui_loop.run_question_tui",
            fake_run,
        ),
        pytest.raises(RuntimeError, match="tui exploded"),
    ):
        await interactive_question_picker(_make_questions(), timeout_seconds=5)

    fake_handle.suspend.assert_called_once()
    fake_handle.resume.assert_called_once()


@pytest.mark.asyncio
async def test_no_resume_when_suspend_timed_out():
    """If suspend() returned False (listener didn't ack within the timeout),
    we deliberately skip resume() — calling resume() on a listener that
    never paused would just clear an already-clear event, which is
    harmless, but the underlying problem (rogue listener) is something the
    user should see, not get silently masked by a spurious resume call."""
    fake_handle = MagicMock()
    fake_handle.suspend.return_value = False  # didn't ack in time

    fake_run = AsyncMock(return_value=([], False, False))

    with (
        patch(
            "code_puppy.agents._key_listeners.get_active_handle",
            return_value=fake_handle,
        ),
        patch(
            "code_puppy.tools.ask_user_question.tui_loop.run_question_tui",
            fake_run,
        ),
    ):
        await interactive_question_picker(_make_questions(), timeout_seconds=5)

    fake_handle.suspend.assert_called_once()
    fake_handle.resume.assert_not_called()
