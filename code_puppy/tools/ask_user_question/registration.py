"""Tool registration for ask_user_question."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic_ai import RunContext

from .handler import ask_user_question as _ask_user_question_impl
from .models import AskUserQuestionOutput

if TYPE_CHECKING:
    from pydantic_ai import Agent


def register_ask_user_question(agent: Agent) -> None:
    """Register the ask_user_question tool with the given agent."""

    @agent.tool
    def ask_user_question(
        context: RunContext,  # noqa: ARG001 - Required by framework
        questions: list[dict[str, Any]],
    ) -> AskUserQuestionOutput:
        """Ask the user multiple related questions in an interactive TUI.

        Args:
            questions: Array of 1-10 questions to ask. Keep it minimal! Each:
                - question (str): The full question text to display
                - header (str): Short label (max 12 chars) for left panel
                - multi_select (bool, optional): Allow multiple selections
                - options (list): 2-6 options, each with:
                    - label (str): Short option name (1-5 words)
                    - description (str, optional): Brief explanation
        """
        # Handler returns AskUserQuestionOutput directly - no revalidation needed
        return _ask_user_question_impl(questions)
