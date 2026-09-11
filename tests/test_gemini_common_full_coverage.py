"""Full coverage tests for code_puppy/gemini_common.py."""

import uuid

from pydantic_ai.messages import TextPart, ThinkingPart, ToolCallPart

from code_puppy.gemini_common import generate_tool_call_id, _parse_candidate_parts
from code_puppy.gemini_model import BYPASS_THOUGHT_SIGNATURE


# --- Utility functions. ---


class TestUtilities:
    def test_generate_tool_call_id(self):
        result = generate_tool_call_id()
        uuid.UUID(result)  # should not raise

    def test_bypass_thought_signature(self):
        assert isinstance(BYPASS_THOUGHT_SIGNATURE, str)


# --- Parse candidate parts. ---


class TestParseCandidateParts:
    def test_text_part(self):
        data = {"usageMetadata": {}}
        candidates = [{"content": {"parts": [{"text": "hello"}]}}]
        usage, parts = _parse_candidate_parts(data, candidates)

        assert len(parts) == 1
        assert isinstance(parts[0], TextPart)
        assert parts[0].content == "hello"

    def test_thinking_part_with_signature(self):
        data = {"usageMetadata": {}}
        candidates = [
            {
                "content": {
                    "parts": [
                        {
                            "thought": True,
                            "text": "reasoning...",
                            "thoughtSignature": "sig123",
                        }
                    ]
                }
            }
        ]
        usage, parts = _parse_candidate_parts(data, candidates)

        assert len(parts) == 1
        assert isinstance(parts[0], ThinkingPart)
        assert parts[0].content == "reasoning..."
        assert parts[0].signature == "sig123"

    def test_thinking_part_without_signature(self):
        data = {"usageMetadata": {}}
        candidates = [
            {"content": {"parts": [{"thought": True, "text": "reasoning..."}]}}
        ]

        usage, parts = _parse_candidate_parts(data, candidates)
        assert parts[0].signature is None

    def test_function_call_with_api_supplied_id(self):
        data = {"usageMetadata": {}}

        candidates = [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "my_tool",
                                "args": {"x": 1},
                                "id": "call_abc123",
                            }
                        }
                    ]
                }
            }
        ]

        usage, parts = _parse_candidate_parts(data, candidates)
        assert isinstance(parts[0], ToolCallPart)
        assert parts[0].tool_name == "my_tool"
        assert parts[0].args == {"x": 1}
        assert parts[0].tool_call_id == "call_abc123"

    def test_function_call_without_api_supplied_id_generates_one(self):
        data = {"usageMetadata": {}}

        candidates = [
            {"content": {"parts": [{"functionCall": {"name": "my_tool", "args": {}}}]}}
        ]
        usage, parts = _parse_candidate_parts(data, candidates)

        # Should fall back to generate_tool_call_id(), not crash / not be None.
        assert parts[0].tool_call_id is not None
        assert parts[0].tool_call_id != ""

    def test_function_call_without_args_defaults_to_empty_dict(self):
        data = {"usageMetadata": {}}
        candidates = [{"content": {"parts": [{"functionCall": {"name": "my_tool"}}]}}]

        usage, parts = _parse_candidate_parts(data, candidates)
        assert parts[0].args == {}

    def test_mixed_parts_in_order(self):
        data = {"usageMetadata": {}}

        candidates = [
            {
                "content": {
                    "parts": [
                        {"thought": True, "text": "thinking"},
                        {"text": "answer"},
                        {"functionCall": {"name": "tool", "args": {}}},
                    ]
                }
            }
        ]
        usage, parts = _parse_candidate_parts(data, candidates)

        assert len(parts) == 3
        assert isinstance(parts[0], ThinkingPart)
        assert isinstance(parts[1], TextPart)
        assert isinstance(parts[2], ToolCallPart)

    def test_usage_extraction(self):
        data = {
            "usageMetadata": {
                "promptTokenCount": 42,
                "candidatesTokenCount": 17,
            }
        }
        candidates = [{"content": {"parts": [{"text": "x"}]}}]

        usage, _ = _parse_candidate_parts(data, candidates)
        assert usage.input_tokens == 42
        assert usage.output_tokens == 17

    def test_usage_defaults_to_zero_when_missing(self):
        data = {}
        candidates = [{"content": {"parts": [{"text": "x"}]}}]

        usage, _ = _parse_candidate_parts(data, candidates)
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0

    def test_empty_parts_list(self):
        data = {"usageMetadata": {}}
        candidates = [{"content": {"parts": []}}]

        usage, parts = _parse_candidate_parts(data, candidates)
        assert parts == []

    def test_missing_content_key_defaults_to_empty(self):
        data = {"usageMetadata": {}}
        candidates = [{}]  # No "content" key at all.

        usage, parts = _parse_candidate_parts(data, candidates)
        assert parts == []

    def test_empty_candidates_list_does_not_crash(self):
        data = {"usageMetadata": {}}
        candidates = []

        usage, parts = _parse_candidate_parts(data, candidates)
        assert parts == []
