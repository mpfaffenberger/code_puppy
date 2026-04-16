"""Tool registration for ask_user_question."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field
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
        questions: Annotated[
            list[dict[str, Any]],
            Field(
                description=(
                    "Array of question objects. Each question should include: "
                    "'question' (string), 'header' (short string), "
                    "optional 'multi_select' (boolean), and 'options' "
                    "(array of option objects with 'label' and optional "
                    "'description')."
                )
            ),
        ],
    ) -> AskUserQuestionOutput:
        """Ask the user multiple related questions in an interactive TUI."""
        # Keep the external tool schema simple for provider compatibility.
        # The handler performs the real nested validation and normalization.
        return _ask_user_question_impl(questions)
