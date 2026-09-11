"""Full coverage tests for code_puppy/gemini_common.py."""

from pydantic_ai.tools import ToolDefinition

from code_puppy.gemini_common import (
    _flatten_union_to_object_gemini,
    _sanitize_schema_for_gemini,
    _build_tools,
)


# --- Flatten union. ---


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
