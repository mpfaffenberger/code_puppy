"""Ask User Question tool for code-puppy.

This tool allows agents to ask users interactive multiple-choice questions
through a terminal TUI interface. Uses prompt_toolkit for the split-panel
UI similar to the /colors command.
"""

from .handler import ask_user_question
from .models import (
    AskUserQuestionInput,
    AskUserQuestionOutput,
    Question,
    QuestionAnswer,
    QuestionOption,
)
from .registration import register_ask_user_question

__all__ = [
    "ask_user_question",
    "register_ask_user_question",
    "AskUserQuestionInput",
    "AskUserQuestionOutput",
    "Question",
    "QuestionAnswer",
    "QuestionOption",
]
