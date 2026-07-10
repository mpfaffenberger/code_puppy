"""Pydantic models for the ask_user_question tool."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Callable

from .constants import (
    MAX_DESCRIPTION_LENGTH,
    MAX_HEADER_LENGTH,
    MAX_LABEL_LENGTH,
    MAX_OPTIONS_PER_QUESTION,
    MAX_OTHER_TEXT_LENGTH,
    MAX_QUESTION_LENGTH,
    MAX_QUESTIONS_PER_CALL,
    MIN_OPTIONS_PER_QUESTION,
)

__all__ = [
    "AskUserQuestionInput",
    "AskUserQuestionOutput",
    "Question",
    "QuestionAnswer",
    "QuestionOption",
    "sanitize_text",
]

# Regex to match ANSI escape codes
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def sanitize_text(text: str) -> str:
    """Remove ANSI escape codes and strip whitespace."""
    return ANSI_ESCAPE_PATTERN.sub("", text).strip()


def _make_sanitizer(
    *, allow_none: bool = False, default: str = ""
) -> "Callable[[Any], str]":
    """Create a sanitizer with configurable None handling.

    Args:
        allow_none: If True, None returns default. If False, raises ValueError.
        default: Value to return when allow_none=True and input is None.

    Returns:
        A sanitizer function for use with BeforeValidator.
    """

    def sanitize(v: Any) -> str:
        if v is None:
            if allow_none:
                return default
            raise ValueError("Value cannot be None")
        return sanitize_text(str(v))

    return sanitize


# Pre-built sanitizers for common cases
_sanitize_required = _make_sanitizer(allow_none=False)
_sanitize_optional = _make_sanitizer(allow_none=True, default="")

# Legacy direct-construction guard used by unit tests and terminal-oriented callers.
# Tool payload dictionaries (validated through AskUserQuestionInput) can carry
# up to MAX_OPTIONS_PER_QUESTION options for browser-first workflows.
_DIRECT_MODEL_MAX_OPTIONS = 6


def _sanitize_header(v: Any) -> str:
    """Sanitize header: remove ANSI, strip, replace spaces with hyphens."""
    return _sanitize_required(v).replace(" ", "-")


def _check_unique(items: list[str], field_name: str) -> None:
    """Raise ValueError if items has duplicates (case-insensitive)."""
    lowered = [i.lower() for i in items]
    if len(lowered) != len(set(lowered)):
        raise ValueError(f"{field_name} must be unique")


class QuestionOption(BaseModel):
    """
    A single selectable option for a question.

    Attributes:
        label: Short, descriptive name for the option (1-5 words recommended)
        description: Longer explanation of what selecting this option means
    """

    label: Annotated[
        str,
        BeforeValidator(_sanitize_required),
        Field(
            min_length=1,
            max_length=MAX_LABEL_LENGTH,
            description="Short option name (1-5 words)",
        ),
    ]
    description: Annotated[
        str,
        BeforeValidator(_sanitize_optional),
        Field(
            default="",
            max_length=MAX_DESCRIPTION_LENGTH,
            description="Explanation of what this option means",
        ),
    ]


class Question(BaseModel):
    """
    A single question with multiple-choice options.

    Attributes:
        question: The full question text displayed to the user
        header: Short label used for compact display and response mapping
        multi_select: Whether user can select multiple options
        options: List of selectable options. Usually 2-12 choices; may be empty
            when ``input_mode`` is ``"text"``.
        input_mode: Whether the answer is option-based, free-form text, or both
    """

    question: Annotated[
        str,
        BeforeValidator(_sanitize_required),
        Field(
            min_length=1,
            max_length=MAX_QUESTION_LENGTH,
            description="The full question text to display",
        ),
    ]
    header: Annotated[
        str,
        BeforeValidator(_sanitize_header),
        Field(
            min_length=1,
            max_length=MAX_HEADER_LENGTH,
            description="Short label for compact display (max 60 chars)",
        ),
    ]
    multi_select: Annotated[
        bool,
        Field(
            default=False,
            description="If true, user can select multiple options",
        ),
    ]
    options: Annotated[
        list[QuestionOption],
        Field(
            default_factory=list,
            min_length=0,
            max_length=MAX_OPTIONS_PER_QUESTION,
            description=(
                f"Array of 0-{MAX_OPTIONS_PER_QUESTION} selectable options. "
                f"Use at least {MIN_OPTIONS_PER_QUESTION} unless input_mode='text'."
            ),
        ),
    ]
    input_mode: Annotated[
        Literal["select", "text", "select_or_text"],
        Field(
            default="select",
            description=(
                "Answer mode: select from options, enter free-form text, "
                "or allow either."
            ),
        ),
    ]
    input_placeholder: Annotated[
        str,
        BeforeValidator(_sanitize_optional),
        Field(
            default="Type your answer...",
            max_length=MAX_DESCRIPTION_LENGTH,
            description="Placeholder for free-form user input modes",
        ),
    ]

    @model_validator(mode="before")
    @classmethod
    def validate_direct_model_option_limit(cls, values: Any) -> Any:
        """Keep direct ``Question(...)`` construction capped for terminal ergonomics.

        Backward-compat nuance: legacy tests instantiate ``Question`` with pre-built
        ``QuestionOption`` objects and expect >6 options to fail. Browser/tool payloads
        arrive as dicts via ``AskUserQuestionInput`` and are allowed up to
        ``MAX_OPTIONS_PER_QUESTION``.
        """
        if isinstance(values, dict):
            options = values.get("options")
            if (
                isinstance(options, list)
                and len(options) > _DIRECT_MODEL_MAX_OPTIONS
                and options
                and all(isinstance(opt, QuestionOption) for opt in options)
            ):
                raise ValueError(
                    f"options must include at most {_DIRECT_MODEL_MAX_OPTIONS} items"
                )
        return values

    @property
    def allows_text_input(self) -> bool:
        """Return True when this question accepts free-form text."""
        return self.input_mode in {"text", "select_or_text"}

    @model_validator(mode="after")
    def validate_question_shape(self) -> Question:
        """Ensure labels are unique and options are present when required."""
        if self.options:
            _check_unique([opt.label for opt in self.options], "Option labels")
        if self.input_mode == "select" and len(self.options) < MIN_OPTIONS_PER_QUESTION:
            raise ValueError(
                f"options must include at least {MIN_OPTIONS_PER_QUESTION} items "
                "when input_mode='select'"
            )
        return self


class AskUserQuestionInput(BaseModel):
    """
    Input schema for the ask_user_question tool.

    Attributes:
        questions: List of 1-10 questions to ask the user
    """

    questions: Annotated[
        list[Question],
        Field(
            min_length=1,
            max_length=MAX_QUESTIONS_PER_CALL,
            description="Array of 1-10 questions to ask",
        ),
    ]

    @model_validator(mode="after")
    def validate_unique_headers(self) -> AskUserQuestionInput:
        """Ensure all question headers are unique."""
        _check_unique([q.header for q in self.questions], "Question headers")
        return self


class QuestionAnswer(BaseModel):
    """
    Answer to a single question.

    Attributes:
        question_header: The header of the question being answered
        selected_options: List of labels for selected options
        other_text: Custom text if user selected "Other" option
    """

    question_header: Annotated[
        str,
        Field(description="Header of the answered question"),
    ]
    selected_options: Annotated[
        list[str],
        Field(
            default_factory=list,
            description="Labels of selected options",
        ),
    ]
    other_text: Annotated[
        str | None,
        Field(
            default=None,
            max_length=MAX_OTHER_TEXT_LENGTH,
            description="Custom text if 'Other' was selected",
        ),
    ]
    user_input: Annotated[
        str | None,
        Field(
            default=None,
            max_length=MAX_OTHER_TEXT_LENGTH,
            description="Free-form text answer for input-enabled questions",
        ),
    ]

    @property
    def has_other(self) -> bool:
        """Check if user provided custom 'Other' input."""
        return self.other_text is not None

    @property
    def is_empty(self) -> bool:
        """Check if no options were selected."""
        return (
            not self.selected_options
            and self.other_text is None
            and self.user_input is None
        )


class AskUserQuestionOutput(BaseModel):
    """
    Output schema for the ask_user_question tool.

    Attributes:
        answers: List of answers to all questions
        cancelled: Whether user cancelled the interaction
        error: Error message if something went wrong
        timed_out: Whether the interaction timed out
    """

    answers: Annotated[
        list[QuestionAnswer],
        Field(
            default_factory=list,
            description="Answers to all questions",
        ),
    ]
    cancelled: Annotated[
        bool,
        Field(
            default=False,
            description="True if user cancelled (Esc/Ctrl+C)",
        ),
    ]
    error: Annotated[
        str | None,
        Field(
            default=None,
            description="Error message if interaction failed",
        ),
    ]
    timed_out: Annotated[
        bool,
        Field(
            default=False,
            description="True if interaction timed out",
        ),
    ]

    @property
    def success(self) -> bool:
        """Check if interaction completed successfully."""
        return not self.cancelled and self.error is None and not self.timed_out

    @classmethod
    def error_response(cls, error: str) -> AskUserQuestionOutput:
        """Create an error response."""
        return cls(error=error)

    @classmethod
    def cancelled_response(cls) -> AskUserQuestionOutput:
        """Create a cancelled response (intentional user action, not an error)."""
        return cls(answers=[], cancelled=True, error=None)

    @classmethod
    def timeout_response(cls, timeout: int) -> AskUserQuestionOutput:
        """Create a timeout response."""
        return cls(
            answers=[],
            cancelled=False,
            timed_out=True,
            error=f"Interaction timed out after {timeout} seconds of inactivity",
        )

    def get_answer(self, header: str) -> QuestionAnswer | None:
        """Get answer by question header (case-insensitive)."""
        header_lower = header.lower()
        return next(
            (a for a in self.answers if a.question_header.lower() == header_lower),
            None,
        )

    def get_selected(self, header: str) -> list[str]:
        """Get selected options for a question by header."""
        answer = self.get_answer(header)
        return answer.selected_options if answer else []
