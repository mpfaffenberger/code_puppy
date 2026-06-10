"""Regression tests for tool_group_id consistency in websocket lifecycle frames.

These tests enforce the backend invariant introduced by Option C:
all emitted ``ServerToolResult`` payloads must include ``tool_group_id``.
After modularization, the constructors may live outside ``chat_handler.py``, so
we scan the known WebSocket emitter modules.
"""

from __future__ import annotations

import ast
from pathlib import Path

WS_DIR = Path(__file__).resolve().parents[1]
EMITTER_PATHS = [
    WS_DIR / "chat_handler.py",
    WS_DIR / "chat_tool_lifecycle.py",
    WS_DIR / "ws_turn_finalization.py",
]


def _get_server_tool_result_calls(source: str) -> list[ast.Call]:
    """Return every ``ServerToolResult(...)`` call in source."""
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
    missing: list[str] = []
    total_calls = 0

    for source_path in EMITTER_PATHS:
        source = source_path.read_text(encoding="utf-8")
        calls = _get_server_tool_result_calls(source)
        total_calls += len(calls)
        for call in calls:
            keyword_names = {kw.arg for kw in call.keywords if kw.arg is not None}
            if "tool_group_id" not in keyword_names:
                missing.append(f"{source_path.name}:{call.lineno}")

    assert total_calls, "Expected at least one ServerToolResult(...) call"
    assert not missing, (
        f"ServerToolResult(...) calls missing tool_group_id keyword at: {missing}"
    )


def test_server_tool_result_calls_never_pass_explicit_none_for_tool_group_id() -> None:
    """Guard against explicit ``tool_group_id=None`` regressions."""
    explicit_none_locations: list[str] = []

    for source_path in EMITTER_PATHS:
        source = source_path.read_text(encoding="utf-8")
        calls = _get_server_tool_result_calls(source)
        for call in calls:
            for keyword in call.keywords:
                if keyword.arg != "tool_group_id":
                    continue
                if (
                    isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is None
                ):
                    explicit_none_locations.append(f"{source_path.name}:{call.lineno}")

    assert not explicit_none_locations, (
        "ServerToolResult(...) calls pass explicit tool_group_id=None at: "
        f"{explicit_none_locations}"
    )
