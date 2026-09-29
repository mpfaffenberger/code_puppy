"""Phase 4 residuals: tool banners never hit raw stdout in the TUI."""

from io import StringIO
from types import SimpleNamespace

import pytest
from rich.console import Console


@pytest.mark.asyncio
async def test_mcp_tool_call_line_uses_streaming_console(monkeypatch, capsys):
    """The compact MCP call line goes to the streaming console the TUI installs
    (its quiet console), never straight to stdout where it would corrupt the
    Textual screen."""
    from code_puppy.agents import event_stream_handler
    from code_puppy.mcp_ import managed_server

    sink = StringIO()
    monkeypatch.setattr(
        event_stream_handler,
        "_streaming_console",
        Console(file=sink, force_terminal=False, width=120),
    )

    async def no_schema(_call_tool, _name):
        return None

    monkeypatch.setattr(managed_server, "_input_schema_for_tool", no_schema)
    called = {}

    async def fake_call_tool(name, args, metadata=None):
        called["name"] = name
        called["metadata"] = metadata
        return "ok"

    ctx = SimpleNamespace(deps={"x": 1})
    result = await managed_server.process_tool_call(
        ctx, fake_call_tool, "mytool", {"a": 1}
    )

    assert result == "ok"
    assert called == {"name": "mytool", "metadata": {"deps": {"x": 1}}}
    assert "mytool" in sink.getvalue()
    assert "mytool" not in capsys.readouterr().out
