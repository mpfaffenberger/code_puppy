"""Schema tests for browser/user-input ask_user_question support."""

import pytest
from pydantic import ValidationError

from code_puppy.tools.ask_user_question.models import (
    AskUserQuestionInput,
    QuestionAnswer,
)
from code_puppy.tools.ask_user_question.registration import _QUESTIONS_ARRAY_SCHEMA


def _options(count: int):
    return [{"label": f"Option {i}"} for i in range(count)]


def test_accepts_more_than_six_options_up_to_twelve():
    payload = {
        "questions": [
            {
                "question": "Pick any option",
                "header": "choices",
                "options": _options(11),
            }
        ]
    }

    validated = AskUserQuestionInput.model_validate(payload)

    assert len(validated.questions[0].options) == 11


def test_rejects_more_than_twelve_options():
    payload = {
        "questions": [
            {
                "question": "Pick any option",
                "header": "choices",
                "options": _options(13),
            }
        ]
    }

    with pytest.raises(ValidationError):
        AskUserQuestionInput.model_validate(payload)


def test_text_input_mode_allows_no_options():
    payload = {
        "questions": [
            {
                "question": "What should the UI say?",
                "header": "copy",
                "input_mode": "text",
                "input_placeholder": "Type copy...",
            }
        ]
    }

    validated = AskUserQuestionInput.model_validate(payload)

    assert validated.questions[0].options == []
    assert validated.questions[0].allows_text_input is True


def test_select_mode_still_requires_two_options():
    payload = {
        "questions": [
            {
                "question": "Pick one",
                "header": "one",
                "options": [{"label": "Only"}],
            }
        ]
    }

    with pytest.raises(ValidationError, match="at least 2"):
        AskUserQuestionInput.model_validate(payload)


def test_tool_schema_advertises_twelve_options_and_input_mode():
    question_schema = _QUESTIONS_ARRAY_SCHEMA["items"]

    assert question_schema["properties"]["options"]["maxItems"] == 12
    assert "input_mode" in question_schema["properties"]
    assert "options" not in question_schema["required"]


def test_question_answer_can_carry_free_form_user_input():
    answer = QuestionAnswer(question_header="copy", user_input="Use a compact card")

    assert answer.user_input == "Use a compact card"
    assert answer.is_empty is False
