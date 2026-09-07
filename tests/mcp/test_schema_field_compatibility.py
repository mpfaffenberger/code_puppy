"""Schema access must work without touching a deprecated alias when available."""

from types import SimpleNamespace

import pytest
from mcp.types import Tool

from code_puppy.mcp_.managed_server import _input_schema_for_tool
from code_puppy.mcp_.tool_arg_coercion import coerce_tool_args
from code_puppy.mcp_.toolset_utils import iter_cached_tool_defs

SCHEMA = {"type": "object", "properties": {"items": {"type": "array"}}}


class ModernTool:
    name = "test"
    description = "test tool"
    input_schema = SCHEMA

    @property
    def inputSchema(self):
        raise AssertionError("deprecated alias accessed")


class Server:
    def __init__(self, tool):
        self._cached_tools = [tool]

    async def list_tools(self):
        return self._cached_tools

    async def call_tool(self):
        pass


@pytest.mark.parametrize(
    ("tool", "expected"),
    [
        (ModernTool(), SCHEMA),
        (SimpleNamespace(name="test", input_schema=SCHEMA), SCHEMA),
        (SimpleNamespace(name="test", inputSchema=SCHEMA), SCHEMA),
        (SimpleNamespace(name="test", input_schema=None, inputSchema=SCHEMA), SCHEMA),
        (SimpleNamespace(name="test", input_schema=SCHEMA, inputSchema={}), SCHEMA),
        (SimpleNamespace(name="test", input_schema={}, inputSchema=SCHEMA), {}),
        (SimpleNamespace(name="test", input_schema={}), {}),
        (SimpleNamespace(name="test"), None),
        (Tool(name="test", inputSchema=SCHEMA), SCHEMA),
        (Tool(name="test", inputSchema={}), {}),
    ],
)
async def test_live_and_cached_schema_reads_agree(tool, expected):
    server = Server(tool)
    schema = await _input_schema_for_tool(server.call_tool, "test")
    assert schema == expected
    assert list(iter_cached_tool_defs(server))[0][2] == expected
    if schema == SCHEMA:
        assert coerce_tool_args({"items": '["one"]'}, schema) == {"items": ["one"]}
