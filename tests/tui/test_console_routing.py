"""Phase 4 residuals: banners route through the queue (not raw stdout)."""

from types import SimpleNamespace

import pytest


class _FakeQueueConsole:
    def __init__(self, sink):
        self._sink = sink

    def print(self, *values, **kwargs):
        self._sink.append(values[0] if values else "")


@pytest.mark.asyncio
async def test_mcp_tool_call_banner_uses_queue_console(monkeypatch):
    printed = []
    monkeypatch.setattr(
        "code_puppy.messaging.get_queue_console",
        lambda: _FakeQueueConsole(printed),
    )
    called = {}

    async def fake_call_tool(name, args, deps):
        called["name"] = name
        return "ok"

    from code_puppy.mcp_.managed_server import process_tool_call

    ctx = SimpleNamespace(deps={"x": 1})
    result = await process_tool_call(ctx, fake_call_tool, "mytool", {"a": 1})

    assert result == "ok"
    assert called["name"] == "mytool"
    assert any("MCP TOOL CALL" in str(p) for p in printed)


def test_wiggum_banner_routes_to_queue_in_tui(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_ui_mode", lambda: "textual")
    printed = []
    monkeypatch.setattr(
        "code_puppy.messaging.get_queue_console",
        lambda: _FakeQueueConsole(printed),
    )
    from code_puppy.plugins.wiggum.register_callbacks import _display_banner_message

    _display_banner_message("GOAL MODE", "activated", banner_name="llm_judge")
    assert printed  # routed to the queue, not printed straight to stdout
