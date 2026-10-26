"""Tests for MCP toolset introspection helpers.

Covers the ``Tool.inputSchema`` -> ``Tool.input_schema`` rename (MCP SDK v2),
which otherwise spews ``FastMCPDeprecationWarning`` at every startup when the
importer reads the deprecated camelCase attribute.
"""

from types import SimpleNamespace

import pytest

from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerConfig
from code_puppy.mcp_.toolset_utils import tool_input_schema, toolset_init_timeout


def test_reads_new_snake_case_field():
    """SDK v2: ``input_schema`` is authoritative."""
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    tool = SimpleNamespace(name="search", input_schema=schema)
    assert tool_input_schema(tool) == schema


def test_falls_back_to_legacy_camel_case_field():
    """SDK v1: only ``inputSchema`` exists; still resolves."""
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    tool = SimpleNamespace(name="search", inputSchema=schema)
    assert tool_input_schema(tool) == schema


def test_new_field_wins_when_both_present():
    """If both are set, prefer the non-deprecated snake_case attribute."""
    new = {"type": "object", "properties": {"new": {"type": "string"}}}
    old = {"type": "object", "properties": {"old": {"type": "string"}}}
    tool = SimpleNamespace(name="search", input_schema=new, inputSchema=old)
    assert tool_input_schema(tool) == new


def test_returns_none_when_no_schema_attribute():
    """Tools without either field resolve to ``None`` (callers skip coercion)."""
    assert tool_input_schema(SimpleNamespace(name="bare")) is None


def test_explicit_none_schema_falls_through_to_legacy():
    """An explicit ``input_schema=None`` must not mask a legacy value."""
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    tool = SimpleNamespace(name="search", input_schema=None, inputSchema=schema)
    assert tool_input_schema(tool) == schema


def test_does_not_touch_deprecated_field_when_new_present():
    """Reading the deprecated attribute is what triggers the warning.

    fastmcp's SDK v2 bridge installs a warn-once ``inputSchema`` property on
    ``mcp.types.Tool`` (``fastmcp/_compat.py``), so *any* read of the
    camelCase name emits ``FastMCPDeprecationWarning``. Make the deprecated
    attribute actively hostile: if the helper probes it first — or in
    addition — the property raises and this test fails.
    """
    schema = {"type": "object"}

    class StrictTool:
        input_schema = schema

        @property
        def inputSchema(self):  # camelCase mirrors the SDK's field name
            raise AssertionError("deprecated `inputSchema` was read")

    assert tool_input_schema(StrictTool()) == schema


# --- toolset_init_timeout ---------------------------------------------------
# Regression: MCPToolset has no ``init_timeout`` attribute, so the lifecycle's
# old ``getattr(leaf, "init_timeout", 10.0)`` silently cut every configured
# deadline (330s OAuth, 60s stdio) to 10s. Build REAL toolsets here: the
# duck-typed fakes in test_async_lifecycle.py are exactly what hid the bug.


def _real_toolset(server_type, **config):
    managed = ManagedMCPServer(
        ServerConfig(id="t", name="t", type=server_type, config=config)
    )
    return managed._pydantic_server  # wrapped, exactly as the lifecycle sees it


@pytest.mark.parametrize(
    ("server_type", "config", "expected"),
    [
        ("http", {"url": "https://example.com/mcp", "auth": "oauth"}, 330),
        ("http", {"url": "https://example.com/mcp", "timeout": 45}, 45),
        ("http", {"url": "https://example.com/mcp"}, 5),
        ("sse", {"url": "https://example.com/sse", "timeout": 0}, None),
        ("stdio", {"command": "python"}, 60),
    ],
)
def test_real_toolset_timeout_is_read(server_type, config, expected):
    assert toolset_init_timeout(_real_toolset(server_type, **config), 10.0) == expected


def test_leaf_attribute_wins_and_unknown_falls_back():
    assert toolset_init_timeout(SimpleNamespace(init_timeout=None), 10.0) is None
    assert toolset_init_timeout(SimpleNamespace(), 10.0) == 10.0
