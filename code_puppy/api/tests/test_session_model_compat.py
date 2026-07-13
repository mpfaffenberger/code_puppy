from __future__ import annotations

from datetime import datetime, timezone

import pytest

from code_puppy.api.session_context import (
    SessionContext,
    SessionManager,
    _apply_session_model,
)


class LegacyAgentWithoutSetter:
    def __init__(self) -> None:
        self._session_model_name = None
        self.reload_count = 0

    def reload_code_generation_agent(self) -> None:
        self.reload_count += 1


class ModernAgentWithSetter(LegacyAgentWithoutSetter):
    def __init__(self) -> None:
        super().__init__()
        self.via_method = None

    def set_session_model(self, model_name):
        self.via_method = model_name


@pytest.mark.parametrize(
    "agent_cls,expected_attr,expected_via_method",
    [
        (LegacyAgentWithoutSetter, "gpt-5.1", None),
        (ModernAgentWithSetter, None, "gpt-5.1"),
    ],
)
def test_apply_session_model_compat(agent_cls, expected_attr, expected_via_method):
    agent = agent_cls()
    _apply_session_model(agent, "gpt-5.1")

    if expected_attr is not None:
        assert getattr(agent, "_session_model_name") == expected_attr
    if expected_via_method is not None:
        assert getattr(agent, "via_method") == expected_via_method


@pytest.mark.asyncio
async def test_switch_model_supports_legacy_agent_without_setter():
    mgr = SessionManager()
    agent = LegacyAgentWithoutSetter()
    ctx = SessionContext(
        session_id="legacy-session",
        agent=agent,
        agent_name="code-puppy",
        model_name="synthetic-GLM-5.1",
        working_directory="",
        created_at=datetime.now(timezone.utc),
    )

    mgr._sessions[ctx.session_id] = ctx

    await mgr.switch_model(ctx.session_id, "gpt-5.1")

    assert ctx.model_name == "gpt-5.1"
    assert agent._session_model_name == "gpt-5.1"
    assert agent.reload_count == 1
