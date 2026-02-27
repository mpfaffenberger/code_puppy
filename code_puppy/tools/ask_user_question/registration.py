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

        IMPORTANT - WHEN TO USE THIS TOOL:
            - Use ONLY when you need answers to 2+ related questions together
            - Do NOT use for simple yes/no questions - just ask in conversation
            - Do NOT use for single questions unless user explicitly requests it
            - Do NOT use when you can make reasonable assumptions instead
            - ALWAYS prefer fewer questions over more - respect user's time

        MINIMALISM PRINCIPLES:
            - Ask only what you MUST know to proceed
            - Prefer 2-3 questions over 4+ whenever possible
            - Use 2-3 options per question, not 5-6
            - Omit options that are rarely chosen
            - If in doubt, make a reasonable default choice and mention it

        Displays a split-panel TUI with questions on the left and options on
        the right. Each question can have 2-6 options with descriptions.
        Users can select single or multiple options, and can always provide
        custom 'Other' input.

        Args:
            questions: Array of 1-10 questions to ask. Keep it minimal! Each:
                - question (str): The full question text to display
                - header (str): Short label (max 12 chars) for left panel
                - multi_select (bool, optional): Allow multiple selections
                - options (list): 2-6 options, each with:
                    - label (str): Short option name (1-5 words)
                    - description (str, optional): Brief explanation

        Returns:
            AskUserQuestionOutput containing:
                - answers (list): Answer for each question with:
                    - question_header (str): The header of the question
                    - selected_options (list[str]): Labels of selected options
                    - other_text (str | None): Custom text if 'Other' selected
                - cancelled (bool): True if user pressed Esc/Ctrl+C
                - error (str | None): Error message if failed
                - timed_out (bool): True if interaction timed out

        Navigation:
            - ←→: Switch questions  |  ↑↓: Navigate options
            - Space: Select option  |  Enter: Next/Submit
            - Ctrl+S: Submit all    |  Esc: Cancel

        Example - Good (minimal, focused):
            >>> ask_user_question(ctx, questions=[
            ...     {"question": "Which database?", "header": "DB",
            ...      "options": [{"label": "Postgres"}, {"label": "SQLite"}]},
            ...     {"question": "Include auth?", "header": "Auth",
            ...      "options": [{"label": "Yes"}, {"label": "No"}]}
            ... ])

        Example - Bad (too many questions/options):
            >>> # DON'T DO THIS - ask only what's essential
            >>> ask_user_question(ctx, questions=[
            ...     {"question": "...", "options": [6 options]},  # Too many!
            ...     {"question": "...", "options": [...]},
            ...     {"question": "...", "options": [...]},
            ...     {"question": "...", "options": [...]},  # 4+ = overwhelming
            ... ])
        """
        # Handler returns AskUserQuestionOutput directly - no revalidation needed
        return _ask_user_question_impl(questions)
