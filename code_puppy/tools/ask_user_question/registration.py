"""Tool registration for ask_user_question."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai import RunContext

from .handler import ask_user_question as _ask_user_question_impl
from .models import AskUserQuestionOutput, Question

if TYPE_CHECKING:
    from pydantic_ai import Agent


def register_ask_user_question(agent: Agent) -> None:
    """Register the ask_user_question tool with the given agent."""

    @agent.tool
    def ask_user_question(
        context: RunContext,  # noqa: ARG001 - Required by framework
        questions: list[Question],
    ) -> AskUserQuestionOutput:
        """Ask the user multiple related questions in an interactive TUI."""
        # Handler returns AskUserQuestionOutput directly - no revalidation needed
        return _ask_user_question_impl(questions)
