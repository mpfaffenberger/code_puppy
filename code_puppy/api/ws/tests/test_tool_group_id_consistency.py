"""Regression tests for tool_group_id consistency in websocket lifecycle frames.

These tests enforce the backend invariant introduced by Option C:
all emitted ``ServerToolResult`` payloads must include ``tool_group_id``.
"""

from __future__ import annotations

import ast
from pathlib import Path

CHAT_HANDLER_PATH = Path(__file__).resolve().parents[1] / "chat_handler.py"


def _get_server_tool_result_calls(source: str) -> list[ast.Call]:
    """Return every ``ServerToolResult(...)`` call in chat_handler source."""
    tree = ast.parse(source)
    calls: list[ast.Call] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "ServerToolResult":
            calls.append(node)

    return calls


def test_server_tool_result_calls_always_include_tool_group_id_keyword() -> None:
    """Every ServerToolResult constructor call must include tool_group_id.

    This protects against regressions where a new emission path forgets to
    include the grouping field and breaks frontend tool-message grouping.
    """
    source = CHAT_HANDLER_PATH.read_text(encoding="utf-8")
    calls = _get_server_tool_result_calls(source)

    assert calls, "Expected at least one ServerToolResult(...) call"

    missing = []
    for call in calls:
        keyword_names = {kw.arg for kw in call.keywords if kw.arg is not None}
        if "tool_group_id" not in keyword_names:
            missing.append(call.lineno)

    assert not missing, (
        f"ServerToolResult(...) calls missing tool_group_id keyword at lines: {missing}"
    )


def test_server_tool_result_calls_never_pass_explicit_none_for_tool_group_id() -> None:
    """Guard against explicit ``tool_group_id=None`` regressions."""
    source = CHAT_HANDLER_PATH.read_text(encoding="utf-8")
    calls = _get_server_tool_result_calls(source)

    explicit_none_lines: list[int] = []
    for call in calls:
        for keyword in call.keywords:
            if keyword.arg != "tool_group_id":
                continue
            if isinstance(keyword.value, ast.Constant) and keyword.value.value is None:
                explicit_none_lines.append(call.lineno)

    assert not explicit_none_lines, (
        "ServerToolResult(...) calls pass explicit tool_group_id=None at lines: "
        f"{explicit_none_lines}"
    )
