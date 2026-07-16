"""Tests for ask_user_question tool registration.

Covers the BeforeValidator that coerces JSON-stringified question arrays to
native lists. LLMs occasionally serialise the questions argument as a JSON
string instead of a native list; pydantic-ai validates arguments before
calling the handler, so the coercion must happen at the registration layer.
"""

from __future__ import annotations

import json


class TestCoerceQuestionsJsonString:
    """_coerce_questions_json_string coerces JSON strings to lists."""

    def test_coerce_valid_json_string_to_list(self):
        """A JSON-stringified array should be parsed to a native list."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )

        questions = [{"question": "q", "header": "h", "options": [{"label": "a"}]}]
        result = _coerce_questions_json_string(json.dumps(questions))
        assert result == questions
        assert isinstance(result, list)

    def test_passthrough_native_list(self):
        """A native list passes through unchanged (exact same object)."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )

        questions = [{"question": "q", "header": "h", "options": [{"label": "a"}]}]
        result = _coerce_questions_json_string(questions)
        assert result is questions

    def test_passthrough_invalid_json_string(self):
        """A non-JSON string passes through unchanged so pydantic can error."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )

        bad = "not-json"
        assert _coerce_questions_json_string(bad) == bad

    def test_passthrough_none(self):
        """None passes through unchanged."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )

        assert _coerce_questions_json_string(None) is None

    def test_passthrough_dict(self):
        """A dict (wrong type but not a string) passes through unchanged."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )

        d = {"question": "q"}
        assert _coerce_questions_json_string(d) is d

    def test_coerce_empty_array_string(self):
        """The string '[]' coerces to an empty list."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )

        assert _coerce_questions_json_string("[]") == []

    def test_coerce_single_element_array_string(self):
        """Single-element JSON array string coerces correctly — the original failing case."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )

        q = [
            {
                "question": "Which theme?",
                "header": "Theme",
                "options": [{"label": "A"}, {"label": "B"}],
            }
        ]
        result = _coerce_questions_json_string(json.dumps(q))
        assert result == q
        assert len(result) == 1


class TestToolSchemaConstraints:
    """Verify the JSON schema includes all constraints for LLM guidance."""

    def test_schema_includes_all_maxlength_constraints(self):
        """Schema should include maxLength for all string fields."""
        from pydantic_ai import Agent

        from code_puppy.tools.ask_user_question.constants import (
            MAX_DESCRIPTION_LENGTH,
            MAX_HEADER_LENGTH,
            MAX_LABEL_LENGTH,
            MAX_OPTIONS_PER_QUESTION,
            MAX_QUESTION_LENGTH,
            MAX_QUESTIONS_PER_CALL,
            MIN_OPTIONS_PER_QUESTION,
        )
        from code_puppy.tools.ask_user_question.registration import (
            register_ask_user_question,
        )

        agent = Agent("test")
        register_ask_user_question(agent)

        # Get the schema from the registered tool
        toolset = agent._function_toolset
        tool = toolset.tools["ask_user_question"]
        schema = tool.function_schema.json_schema

        # Check questions array constraints
        questions_schema = schema["properties"]["questions"]
        assert questions_schema["minItems"] == 1
        assert questions_schema["maxItems"] == MAX_QUESTIONS_PER_CALL

        # Check question object constraints
        question_schema = questions_schema["items"]
        assert (
            question_schema["properties"]["question"]["maxLength"]
            == MAX_QUESTION_LENGTH
        )
        assert question_schema["properties"]["header"]["maxLength"] == MAX_HEADER_LENGTH
        assert "question" in question_schema["required"]
        assert "header" in question_schema["required"]
        assert "options" in question_schema["required"]

        # Check options array constraints
        options_schema = question_schema["properties"]["options"]
        assert options_schema["minItems"] == MIN_OPTIONS_PER_QUESTION
        assert options_schema["maxItems"] == MAX_OPTIONS_PER_QUESTION

        # Check option object constraints
        option_schema = options_schema["items"]
        assert option_schema["properties"]["label"]["maxLength"] == MAX_LABEL_LENGTH
        assert (
            option_schema["properties"]["description"]["maxLength"]
            == MAX_DESCRIPTION_LENGTH
        )
        assert "label" in option_schema["required"]
