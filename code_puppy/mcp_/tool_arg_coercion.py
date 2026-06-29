"""Coercion of MCP tool-call arguments against their JSON Schema.

Why this exists
---------------
code-puppy delegates MCP tool calls to pydantic-ai. pydantic-ai's MCP toolset
validates incoming tool-call args with a *passthrough* validator
(``SchemaValidator(schema=core_schema.any_schema())``) that performs **zero**
coercion against each tool's real JSON ``inputSchema``. Whatever the model /
gateway emits is forwarded raw to the MCP server.

In practice some model layers emit arrays / booleans / numbers **encoded as
JSON strings** (e.g. ``"[\\"public\\"]"``, ``"false"``, ``"100"``). Because
nothing coerces them back to their schema types, the downstream MCP server's
strict validation rejects them with errors like ``"string found, array
expected"`` or Zod's ``"expected boolean, received string"``.

This module coerces such stringified scalars/containers back to the types
declared by the tool's own JSON Schema *before* the call is forwarded. It is
deliberately defensive: anything it cannot confidently coerce is passed through
unchanged. It never raises and never drops data.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

__all__ = ["coerce_tool_args"]

# JSON Schema "type" keywords we know how to coerce a string *into*.
_COERCIBLE_TYPES = frozenset({"array", "object", "number", "integer", "boolean"})


def coerce_tool_args(
    tool_args: Dict[str, Any],
    input_schema: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Coerce ``tool_args`` against an MCP tool's JSON ``input_schema``.

    For every argument whose value is a ``str`` but whose schema declares a
    non-string type (array/object/number/integer/boolean), attempt to parse the
    string into that type. If the parse fails or yields the wrong type, the
    original value is kept untouched.

    Args:
        tool_args: The raw arguments emitted for the tool call.
        input_schema: The tool's JSON Schema (typically
            ``ToolDefinition.parameters_json_schema`` / ``mcp_tool.inputSchema``).
            May be ``None`` or malformed; in that case args are returned as-is.

    Returns:
        A new dict with coerced values where possible. The input is never mutated.
    """
    if not isinstance(tool_args, dict):
        return tool_args
    if not isinstance(input_schema, dict):
        return tool_args

    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        return tool_args

    coerced: Dict[str, Any] = dict(tool_args)
    for key, value in tool_args.items():
        if not isinstance(value, str):
            # Only stringified values are ever ambiguous; leave the rest alone.
            continue
        prop_schema = properties.get(key)
        if not isinstance(prop_schema, dict):
            continue
        coerced[key] = _coerce_value(value, prop_schema)
    return coerced


def _schema_types(prop_schema: Dict[str, Any]) -> List[str]:
    """Extract the candidate JSON Schema types for a property.

    Handles ``{"type": "array"}``, ``{"type": ["array", "null"]}`` and the
    ``anyOf`` / ``oneOf`` union shapes. Returns an ordered, de-duplicated list of
    coercion-relevant type names.
    """
    found: List[str] = []

    def _add(raw_type: Any) -> None:
        if isinstance(raw_type, str) and raw_type in _COERCIBLE_TYPES:
            if raw_type not in found:
                found.append(raw_type)

    raw = prop_schema.get("type")
    if isinstance(raw, str):
        _add(raw)
    elif isinstance(raw, list):
        for entry in raw:
            _add(entry)

    for union_key in ("anyOf", "oneOf"):
        union = prop_schema.get(union_key)
        if isinstance(union, list):
            for sub in union:
                if isinstance(sub, dict):
                    for t in _schema_types(sub):
                        if t not in found:
                            found.append(t)

    return found


def _coerce_value(value: str, prop_schema: Dict[str, Any]) -> Any:
    """Coerce a single stringified ``value`` toward one of its schema types.

    Tries each candidate type in declaration order and returns the first
    successful coercion. Falls back to the original string if none apply.
    """
    for schema_type in _schema_types(prop_schema):
        coerced, ok = _coerce_to_type(value, schema_type)
        if ok:
            return coerced
    return value


def _coerce_to_type(value: str, schema_type: str) -> tuple[Any, bool]:
    """Attempt to coerce ``value`` to ``schema_type``.

    Returns a ``(coerced_value, success)`` tuple. On failure the second element
    is ``False`` and the first should be ignored.
    """
    if schema_type == "boolean":
        return _coerce_boolean(value)
    if schema_type == "integer":
        return _coerce_integer(value)
    if schema_type == "number":
        return _coerce_number(value)
    if schema_type == "array":
        return _coerce_json_container(value, list)
    if schema_type == "object":
        return _coerce_json_container(value, dict)
    return value, False


def _coerce_boolean(value: str) -> tuple[Any, bool]:
    lowered = value.strip().lower()
    if lowered == "true":
        return True, True
    if lowered == "false":
        return False, True
    return value, False


def _coerce_integer(value: str) -> tuple[Any, bool]:
    text = value.strip()
    try:
        return int(text), True
    except (TypeError, ValueError):
        # Allow integral floats like "100.0" -> 100.
        try:
            parsed = float(text)
        except (TypeError, ValueError):
            return value, False
        if parsed.is_integer():
            return int(parsed), True
        return value, False


def _coerce_number(value: str) -> tuple[Any, bool]:
    text = value.strip()
    try:
        return float(text), True
    except (TypeError, ValueError):
        return value, False


def _coerce_json_container(value: str, expected: type) -> tuple[Any, bool]:
    """Parse ``value`` as JSON and accept it only if it is an ``expected`` type."""
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return value, False
    if isinstance(parsed, expected):
        return parsed, True
    return value, False
