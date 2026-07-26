"""Tests for MCP tool-argument coercion.

These cover the bug where models emit arrays/booleans/numbers encoded as JSON
strings, which pydantic-ai forwards raw (it uses an ``any_schema`` passthrough
validator), causing downstream MCP servers to reject them. Confirmed in the
wild against both the SonarQube and Supabase MCP servers.
"""

from types import SimpleNamespace

import pytest

from code_puppy.mcp_.managed_server import (
    _input_schema_for_tool,
    process_tool_call,
)
from code_puppy.mcp_.tool_arg_coercion import coerce_tool_args


def _schema(properties: dict) -> dict:
    return {"type": "object", "properties": properties}


def test_stringified_array_becomes_array():
    schema = _schema({"schemas": {"type": "array", "items": {"type": "string"}}})
    args = {"schemas": '["public"]'}
    assert coerce_tool_args(args, schema) == {"schemas": ["public"]}


def test_stringified_object_becomes_object():
    schema = _schema({"filters": {"type": "object"}})
    args = {"filters": '{"status": "open"}'}
    assert coerce_tool_args(args, schema) == {"filters": {"status": "open"}}


def test_false_string_becomes_bool():
    schema = _schema({"verbose": {"type": "boolean"}})
    assert coerce_tool_args({"verbose": "false"}, schema) == {"verbose": False}


def test_true_string_case_insensitive_becomes_bool():
    schema = _schema({"verbose": {"type": "boolean"}})
    assert coerce_tool_args({"verbose": "TRUE"}, schema) == {"verbose": True}


def test_numeric_string_becomes_int():
    schema = _schema({"limit": {"type": "integer"}})
    assert coerce_tool_args({"limit": "100"}, schema) == {"limit": 100}


def test_numeric_string_becomes_float():
    schema = _schema({"ratio": {"type": "number"}})
    assert coerce_tool_args({"ratio": "1.5"}, schema) == {"ratio": 1.5}


def test_integral_float_string_for_integer():
    schema = _schema({"limit": {"type": "integer"}})
    assert coerce_tool_args({"limit": "100.0"}, schema) == {"limit": 100}


def test_already_correct_values_pass_through_untouched():
    schema = _schema(
        {
            "schemas": {"type": "array"},
            "verbose": {"type": "boolean"},
            "limit": {"type": "integer"},
        }
    )
    args = {"schemas": ["public"], "verbose": True, "limit": 100}
    assert coerce_tool_args(args, schema) == args


def test_string_arg_with_string_schema_is_left_alone():
    schema = _schema({"name": {"type": "string"}})
    # A genuine JSON-looking string for a string field must NOT be parsed.
    args = {"name": "[1, 2, 3]"}
    assert coerce_tool_args(args, schema) == {"name": "[1, 2, 3]"}


def test_uncoercible_junk_passes_through_without_crashing():
    schema = _schema(
        {
            "schemas": {"type": "array"},
            "limit": {"type": "integer"},
            "verbose": {"type": "boolean"},
        }
    )
    args = {"schemas": "not json at all", "limit": "abc", "verbose": "maybe"}
    # Nothing coercible -> everything passes through verbatim, no exception.
    assert coerce_tool_args(args, schema) == args


def test_json_parses_but_wrong_type_passes_through():
    # Value parses as an int but schema wants an array -> keep the original.
    schema = _schema({"schemas": {"type": "array"}})
    assert coerce_tool_args({"schemas": "5"}, schema) == {"schemas": "5"}


def test_nullable_union_type_list_is_coerced():
    schema = _schema({"schemas": {"type": ["array", "null"]}})
    assert coerce_tool_args({"schemas": '["a","b"]'}, schema) == {"schemas": ["a", "b"]}


def test_anyof_union_is_coerced():
    schema = _schema({"limit": {"anyOf": [{"type": "integer"}, {"type": "null"}]}})
    assert coerce_tool_args({"limit": "42"}, schema) == {"limit": 42}


def test_missing_schema_returns_args_unchanged():
    args = {"schemas": '["public"]'}
    assert coerce_tool_args(args, None) == args
    assert coerce_tool_args(args, {}) == args
    assert coerce_tool_args(args, {"type": "object"}) == args


def test_unknown_property_left_alone():
    schema = _schema({"known": {"type": "array"}})
    args = {"unknown": '["x"]'}
    assert coerce_tool_args(args, schema) == {"unknown": '["x"]'}


def test_input_is_not_mutated():
    schema = _schema({"limit": {"type": "integer"}})
    args = {"limit": "100"}
    coerce_tool_args(args, schema)
    assert args == {"limit": "100"}


def test_non_dict_args_returned_as_is():
    assert coerce_tool_args("nope", _schema({})) == "nope"  # type: ignore[arg-type]


# --- Integration: the process_tool_call wiring -----------------------------


class _FakeServer:
    """Stands in for a pydantic-ai MCP server exposing list_tools()."""

    def __init__(self, tools):
        self._tools = tools
        self.list_tools_calls = 0

    async def list_tools(self):
        self.list_tools_calls += 1
        return self._tools

    async def direct_call_tool(self, name, args, metadata=None):
        return {"name": name, "args": args, "metadata": metadata}


def _tool(name: str, input_schema: dict) -> SimpleNamespace:
    return SimpleNamespace(name=name, inputSchema=input_schema)


@pytest.mark.asyncio
async def test_input_schema_for_tool_resolves_via_bound_server():
    server = _FakeServer([_tool("search", _schema({"q": {"type": "string"}}))])
    schema = await _input_schema_for_tool(server.direct_call_tool, "search")
    assert schema == _schema({"q": {"type": "string"}})


@pytest.mark.asyncio
async def test_input_schema_for_tool_missing_returns_none():
    server = _FakeServer([_tool("search", _schema({}))])
    assert await _input_schema_for_tool(server.direct_call_tool, "nope") is None


@pytest.mark.asyncio
async def test_input_schema_for_tool_handles_non_server_callable():
    async def plain_callable(name, args, metadata=None):
        return None

    assert await _input_schema_for_tool(plain_callable, "whatever") is None


@pytest.mark.asyncio
async def test_process_tool_call_coerces_before_forwarding():
    schema = _schema(
        {
            "schemas": {"type": "array"},
            "verbose": {"type": "boolean"},
            "limit": {"type": "integer"},
        }
    )
    server = _FakeServer([_tool("list_tables", schema)])
    ctx = SimpleNamespace(deps="DEPS")
    raw_args = {"schemas": '["public"]', "verbose": "false", "limit": "100"}

    result = await process_tool_call(
        ctx, server.direct_call_tool, "list_tables", raw_args
    )

    assert result["args"] == {
        "schemas": ["public"],
        "verbose": False,
        "limit": 100,
    }
    assert result["metadata"] == {"deps": "DEPS"}
