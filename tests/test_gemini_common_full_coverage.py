"""Full coverage tests for code_puppy/gemini_common.py."""

import uuid

from pydantic_ai import ModelSettings
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.messages import TextPart, ThinkingPart, ToolCallPart

from code_puppy.gemini_common import (
    _flatten_union_to_object_gemini,
    _sanitize_schema_for_gemini,
    _build_tools,
    _build_generation_config,
    generate_tool_call_id,
    _parse_candidate_parts,
)
from code_puppy.gemini_model import BYPASS_THOUGHT_SIGNATURE


# --- Utility functions. ---


class TestUtilities:
    def test_generate_tool_call_id(self):
        result = generate_tool_call_id()
        uuid.UUID(result)  # should not raise

    def test_bypass_thought_signature(self):
        assert isinstance(BYPASS_THOUGHT_SIGNATURE, str)


class TestFlattenUnion:
    def test_all_null_types(self):
        result = _flatten_union_to_object_gemini(
            [{"type": "null"}, {"type": "null"}], {}, lambda x: x
        )
        assert result == {"type": "object"}

    def test_string_only(self):
        result = _flatten_union_to_object_gemini(
            [{"type": "string"}, {"type": "null"}], {}, lambda x: x
        )
        assert result == {"type": "string"}

    def test_non_dict_items_ignored(self):
        result = _flatten_union_to_object_gemini(
            ["not a dict", {"type": "string"}], {}, lambda x: x
        )
        assert result == {"type": "string"}

    def test_unresolvable_ref_in_union(self):
        result = _flatten_union_to_object_gemini(
            [{"$ref": "#/$defs/Missing"}], {}, lambda x: x
        )
        assert result == {"type": "object"}

    def test_ref_with_definitions_prefix(self):
        defs = {"Foo": {"type": "object", "properties": {"x": {"type": "string"}}}}

        result = _flatten_union_to_object_gemini(
            [{"$ref": "#/definitions/Foo"}], defs, lambda x: x
        )
        assert "x" in result["properties"]


# --- Schema sanitization. ---


class TestSanitizeSchema:
    def test_non_dict_passthrough(self):
        assert _sanitize_schema_for_gemini("hello") == "hello"
        assert _sanitize_schema_for_gemini(42) == 42

    def test_removes_defs_and_additional_properties(self):
        schema = {
            "type": "object",
            "$defs": {"Foo": {"type": "string"}},
            "additionalProperties": False,
            "properties": {"x": {"type": "string"}},
        }

        result = _sanitize_schema_for_gemini(schema)
        assert "$defs" not in result
        assert "additionalProperties" not in result
        assert result["properties"]["x"]["type"] == "string"

    def test_resolves_ref(self):
        schema = {
            "$defs": {"Foo": {"type": "string", "description": "a foo"}},
            "$ref": "#/$defs/Foo",
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "string"

    def test_resolves_ref_definitions(self):
        schema = {
            "definitions": {"Bar": {"type": "integer"}},
            "$ref": "#/definitions/Bar",
        }
        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "integer"

    def test_unresolvable_ref(self):
        schema = {"$ref": "#/$defs/Missing"}
        result = _sanitize_schema_for_gemini(schema)
        assert result == {"type": "object"}

    def test_unknown_ref_format(self):
        schema = {"$ref": "http://example.com/schema"}
        result = _sanitize_schema_for_gemini(schema)
        assert result == {"type": "object"}

    def test_anyof_simple_nullable(self):
        schema = {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ],
            "description": "nullable string",
        }

        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "string"
        assert result["description"] == "nullable string"

    def test_oneof_simple(self):
        schema = {
            "oneOf": [
                {"type": "integer"},
                {"type": "null"},
            ],
        }

        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "integer"

    def test_anyof_complex_union_with_refs(self):
        schema = {
            "$defs": {
                "TypeA": {
                    "type": "object",
                    "properties": {"a": {"type": "string"}},
                },
                "TypeB": {
                    "type": "object",
                    "properties": {"b": {"type": "integer"}},
                },
            },
            "anyOf": [
                {"$ref": "#/$defs/TypeA"},
                {"$ref": "#/$defs/TypeB"},
            ],
            "description": "union type",
        }

        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "object"
        assert "a" in result["properties"]
        assert "b" in result["properties"]
        assert result["description"] == "union type"

    def test_anyof_with_string_and_objects(self):
        schema = {
            "anyOf": [
                {"type": "string"},
                {"type": "object", "properties": {"x": {"type": "string"}}},
                {"type": "object", "properties": {"y": {"type": "integer"}}},
            ],
        }

        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "object"
        assert "x" in result["properties"]
        assert "y" in result["properties"]

    def test_allof_merges(self):
        schema = {
            "allOf": [
                {"type": "object", "properties": {"a": {"type": "string"}}},
                {"properties": {"b": {"type": "integer"}}},
            ],
            "description": "merged",
        }

        result = _sanitize_schema_for_gemini(schema)
        assert "a" in result["properties"]
        assert "b" in result["properties"]
        assert result["description"] == "merged"

    def test_removes_default_examples_const(self):
        schema = {
            "type": "string",
            "default": "foo",
            "examples": ["a", "b"],
            "const": "fixed",
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "test",
        }

        result = _sanitize_schema_for_gemini(schema)
        assert "default" not in result
        assert "examples" not in result
        assert "const" not in result
        assert "$schema" not in result
        assert "$id" not in result

    def test_scalar_value_passthrough(self):
        """Test that scalar values in schema are returned as-is."""
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 0},
            },
        }

        result = _sanitize_schema_for_gemini(schema)
        # minimum is a scalar that goes through resolve_refs else branch.
        assert result["properties"]["count"]["type"] == "integer"

    def test_recursive_list_processing(self):
        schema = {
            "type": "array",
            "items": {"type": "string"},
        }

        result = _sanitize_schema_for_gemini(schema)
        assert result["type"] == "array"
        assert result["items"]["type"] == "string"

    def test_ref_with_extra_props(self):
        schema = {
            "$defs": {
                "Foo": {"type": "object", "properties": {"x": {"type": "string"}}}
            },
            "$ref": "#/$defs/Foo",
            "description": "extra desc",
        }

        result = _sanitize_schema_for_gemini(schema)
        assert result["description"] == "extra desc"
        assert "x" in result["properties"]


# --- Build tools. ---


class TestBuildTools:
    def test_build_tools(self):
        tools = [
            ToolDefinition(
                name="fn", description="desc", parameters_json_schema={"type": "object"}
            ),
            ToolDefinition(name="fn2", description="", parameters_json_schema=None),
        ]

        result = _build_tools(tools)
        assert len(result) == 1
        decls = result[0]["functionDeclarations"]

        assert len(decls) == 2
        assert "parameters" in decls[0]
        assert "parameters" not in decls[1]


# --- Build generation config. ---


class TestBuildGenerationConfig:
    def test_none_settings(self):
        assert _build_generation_config(None) == {}

    def test_with_temperature(self):
        s = {"temperature": 0.5}
        result = _build_generation_config(s)
        assert result["temperature"] == 0.5

    def test_with_top_p(self):
        result = _build_generation_config({"top_p": 0.9})
        assert result["topP"] == 0.9

    def test_with_max_tokens(self):
        result = _build_generation_config({"max_tokens": 100})
        assert result["maxOutputTokens"] == 100

    def test_thinking_disabled(self):
        result = _build_generation_config({"thinking_enabled": False})
        assert "thinkingConfig" not in result

    def test_thinking_level(self):
        result = _build_generation_config({"thinking_level": "high"})
        assert result["thinkingConfig"]["thinkingLevel"] == "high"
        assert result["thinkingConfig"]["includeThoughts"] is True

    def test_build_generation_config_none(self):
        assert _build_generation_config(None) == {}

    def test_build_generation_config_empty(self):
        settings = ModelSettings()
        result = _build_generation_config(settings)
        # No fields set -> None or empty.
        assert result is None or result == {}

    def test_build_generation_config_with_values(self):
        settings = ModelSettings(temperature=0.5, top_p=0.9, max_tokens=100)
        result = _build_generation_config(settings)

        assert result["temperature"] == 0.5
        assert result["topP"] == 0.9
        assert result["maxOutputTokens"] == 100


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
