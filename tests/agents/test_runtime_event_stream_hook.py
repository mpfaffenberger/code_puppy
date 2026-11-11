"""The ``agent_event_stream_start`` seam as wired by ``run_with_mcp``."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.agent_execution_context import get_executing_agent
from code_puppy.agents import _runtime
from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.callbacks import clear_callbacks, register_callback

_PHASES = ("agent_event_stream_start", "agent_run_end")


@pytest.fixture(autouse=True)
def _clean_callbacks():
    for phase in _PHASES:
        clear_callbacks(phase)
    yield
    for phase in _PHASES:
        clear_callbacks(phase)


async def _no_events():
    return
    yield


@pytest.mark.asyncio
async def test_hook_fires_inside_the_run_before_events_are_handled(monkeypatch):
    agent = CodePuppyAgent()
    order: list = []
    ended: list = []

    async def handler(_ctx, events):
        async for _ in events:
            pass
        order.append("handler")

    async def on_end(_agent_name, _model_name, session_id, *_rest):
        ended.append(session_id)

    async def fake_run(*_args, event_stream_handler, **_kwargs):
        await event_stream_handler(MagicMock(), _no_events())
        return MagicMock(data="response")

    monkeypatch.setattr(_runtime, "get_enable_streaming", lambda: True)
    monkeypatch.setattr(_runtime, "event_stream_handler", handler)
    register_callback(
        "agent_event_stream_start",
        lambda group_id: order.append((group_id, get_executing_agent())),
    )
    register_callback("agent_run_end", on_end)

    with patch.object(agent, "_code_generation_agent") as mock_agent:
        mock_agent.run = AsyncMock(side_effect=fake_run)
        await agent.run_with_mcp("hello")

    (group_id, executing_agent), step = order
    assert step == "handler"
    assert executing_agent is agent
    assert group_id and ended == [group_id]
