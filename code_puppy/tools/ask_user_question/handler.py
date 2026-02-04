"""Main handler for ask_user_question tool."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

from pydantic import ValidationError

from code_puppy.command_line.wiggum_state import is_wiggum_active
from code_puppy.tools.subagent_context import is_subagent

from .constants import CI_ENV_VARS, DEFAULT_TIMEOUT_SECONDS, MAX_VALIDATION_ERRORS_SHOWN
from .models import (
    AskUserQuestionInput,
    AskUserQuestionOutput,
    Question,
    QuestionAnswer,
)
from .terminal_ui import CancelledException, interactive_question_picker

logger = logging.getLogger(__name__)


class AsyncContextError(RuntimeError):
    """Raised when TUI is called from async context without await."""

    pass


def _cancelled_response() -> AskUserQuestionOutput:
    """Create a standardized cancelled response.

    Note: cancelled=True means intentional user action, not an error.
    The error field is left None since cancellation is expected behavior.
    """
    return AskUserQuestionOutput.cancelled_response()


def is_interactive() -> bool:
    """
    Check if we're running in an interactive terminal.

    Returns:
        True if stdin is a TTY and we're not in a CI environment.
    """
    # stdin might be replaced with a non-file object in some embedding scenarios
    # (e.g., Jupyter, pytest capture, or custom wrappers), so we catch AttributeError
    try:
        if not sys.stdin.isatty():
            return False
    except (AttributeError, OSError):
        return False

    return not any(os.environ.get(var) for var in CI_ENV_VARS)


def ask_user_question(
    questions: list[dict[str, Any]],
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> AskUserQuestionOutput:
    """
    Ask the user one or more interactive multiple-choice questions.

    This tool displays questions in a split-panel terminal TUI and captures
    user responses through keyboard navigation and selection.

    Args:
        questions: List of question objects, each containing:
            - question (str): The full question text
            - header (str): Short label (max 12 chars)
            - multi_select (bool, optional): Allow multiple selections
            - options (list): 2-6 options, each with label and optional description
        timeout: Inactivity timeout in seconds (default: 300)

    Returns:
        AskUserQuestionOutput containing:
            - answers (list): List of answer objects for each question
            - cancelled (bool): True if user cancelled
            - error (str | None): Error message if failed
            - timed_out (bool): True if timed out

    Example:
        >>> result = ask_user_question([{
        ...     "question": "Which database?",
        ...     "header": "Database",
        ...     "options": [
        ...         {"label": "PostgreSQL", "description": "Relational DB"},
        ...         {"label": "MongoDB", "description": "Document store"}
        ...     ]
        ... }])
        >>> print(result.answers[0].selected_options)
        ['PostgreSQL']
    """
    logger.info("ask_user_question called with %d questions", len(questions))

    # Block interactive tools in sub-agent context
    if is_subagent():
        logger.warning("ask_user_question called from sub-agent context - disabled")
        return AskUserQuestionOutput.error_response(
            "Interactive tools are disabled for sub-agents. "
            "Sub-agents should make reasonable decisions or return to the parent agent "
            "if user input is required."
        )

    # Block interactive tools in wiggum (autonomous loop) mode
    if is_wiggum_active():
        logger.warning("ask_user_question called during wiggum mode - disabled")
        return AskUserQuestionOutput.error_response(
            "Interactive tools are disabled during /wiggum mode. "
            "The agent is running autonomously in a loop. "
            "Make a reasonable decision to proceed, or stop and wait for user input "
            "by completing the current task."
        )

    # Check for interactive environment
    if not is_interactive():
        logger.warning("Non-interactive environment detected")
        return AskUserQuestionOutput.error_response(
            "Cannot ask questions: not running in an interactive terminal. "
            "Please provide configuration through arguments or config files."
        )

    # Validate input
    try:
        validated_input = _validate_input(questions)
    except ValidationError as e:
        error_msg = _format_validation_error(e)
        logger.warning("Validation error: %s", error_msg)
        return AskUserQuestionOutput.error_response(error_msg)
    except (TypeError, ValueError) as e:
        logger.error("Unexpected validation error: %s", e, exc_info=True)
        return AskUserQuestionOutput.error_response(f"Validation error: {e!s}")

    # Run the interactive TUI
    try:
        answers, cancelled, timed_out = _run_interactive_picker(
            validated_input.questions, timeout
        )

        if timed_out:
            logger.info("Interaction timed out after %d seconds", timeout)
            return AskUserQuestionOutput.timeout_response(timeout)

        if cancelled:
            logger.info("User cancelled the interaction")
            return _cancelled_response()

        logger.info("Successfully collected %d answers", len(answers))
        return AskUserQuestionOutput(answers=answers)

    except (CancelledException, KeyboardInterrupt):
        logger.info("User cancelled the interaction")
        return _cancelled_response()

    except OSError as e:
        logger.error("Unexpected error during interaction: %s", e)
        return AskUserQuestionOutput.error_response(f"Interaction error: {e!s}")


def _run_interactive_picker(
    questions: list[Question], timeout: int
) -> tuple[list[QuestionAnswer], bool, bool]:
    """Run the interactive TUI, handling async context detection.

    If called from an async context, raises AsyncContextError with guidance.
    For async callers, use `await interactive_question_picker()` directly.
    """
    # Check for async context BEFORE creating the coroutine to avoid
    # "coroutine was never awaited" warnings on the error path.
    try:
        asyncio.get_running_loop()
        # Already in async context - fail fast with helpful message
        # Note: We avoid nest_asyncio.apply() as it globally patches the event loop,
        # which can break other async code in the process and is not thread-safe.
        raise AsyncContextError(
            "Cannot run interactive TUI from within an async context. "
            "Either call from synchronous code, or use "
            "'await interactive_question_picker()' directly for async callers."
        )
    except RuntimeError:
        # No running loop - safe to proceed with asyncio.run()
        pass

    return asyncio.run(interactive_question_picker(questions, timeout_seconds=timeout))


def _validate_input(questions: list[dict[str, Any]]) -> AskUserQuestionInput:
    """
    Validate and convert input dictionaries to Pydantic models.

    Args:
        questions: Raw question dictionaries from tool invocation

    Returns:
        Validated AskUserQuestionInput model

    Raises:
        ValidationError: If input doesn't match schema
    """
    # Single-pass validation - Pydantic handles nested dict->model conversion
    return AskUserQuestionInput.model_validate({"questions": questions})


def _format_validation_error(error: ValidationError) -> str:
    """
    Format a Pydantic ValidationError into a readable string.

    Args:
        error: The Pydantic ValidationError

    Returns:
        Human-readable error message
    """
    errors = error.errors()
    if not errors:
        return "Validation error"

    messages = []
    for err in errors[:MAX_VALIDATION_ERRORS_SHOWN]:
        loc = ".".join(str(x) for x in err["loc"])
        msg = err["msg"]
        messages.append(f"{loc}: {msg}")

    result = "Validation error: " + "; ".join(messages)
    if len(errors) > MAX_VALIDATION_ERRORS_SHOWN:
        result += f" (and {len(errors) - MAX_VALIDATION_ERRORS_SHOWN} more)"

    return result
