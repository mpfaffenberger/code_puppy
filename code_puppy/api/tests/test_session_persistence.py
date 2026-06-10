"""Focused tests for session persistence payload builders (Phase 3)."""

from __future__ import annotations

from code_puppy.api.ws.session_persistence import (
    build_session_meta_payload,
    build_session_update_payload,
    resolve_agent_model_meta,
)

# ---------------------------------------------------------------------------
# resolve_agent_model_meta
# ---------------------------------------------------------------------------


class _FakeAgent:
    def __init__(self, name: str = "", model_name: str = ""):
        self.name = name
        self._model_name = model_name

    def get_model_name(self) -> str:
        return self._model_name


class _FakeCtx:
    def __init__(self, agent_name: str = "", model_name: str = ""):
        self.agent_name = agent_name
        self.model_name = model_name


def test_resolve_uses_agent_when_available():
    agent = _FakeAgent(name="husky", model_name="gpt-5")
    name, model = resolve_agent_model_meta(agent=agent)
    assert name == "husky"
    assert model == "gpt-5"


def test_resolve_falls_back_to_ctx():
    agent = _FakeAgent(name="", model_name="")
    ctx = _FakeCtx(agent_name="shepherd", model_name="claude-4")
    name, model = resolve_agent_model_meta(agent=agent, ctx=ctx)
    assert name == "shepherd"
    assert model == "claude-4"


def test_resolve_falls_back_to_defaults():
    name, model = resolve_agent_model_meta()
    assert name == "code-puppy"
    assert model == "unknown"


def test_resolve_prefers_agent_over_ctx():
    agent = _FakeAgent(name="terrier", model_name="gpt-5")
    ctx = _FakeCtx(agent_name="shepherd", model_name="claude-4")
    name, model = resolve_agent_model_meta(agent=agent, ctx=ctx)
    assert name == "terrier"
    assert model == "gpt-5"


def test_resolve_agent_none_uses_ctx():
    ctx = _FakeCtx(agent_name="watchdog", model_name="o3")
    name, model = resolve_agent_model_meta(agent=None, ctx=ctx)
    assert name == "watchdog"
    assert model == "o3"


# ---------------------------------------------------------------------------
# build_session_meta_payload
# ---------------------------------------------------------------------------


def test_session_meta_payload_contains_all_fields():
    payload = build_session_meta_payload(
        session_id="WS_session_001",
        session_name="WS_session_001",
        total_tokens=42,
        message_count=3,
        title="test chat",
        working_directory="/tmp",
        agent_name="code-puppy",
        model_name="gpt-5",
    )
    assert payload["type"] == "session_meta"
    assert payload["session_id"] == "WS_session_001"
    assert payload["total_tokens"] == 42
    assert payload["message_count"] == 3
    assert payload["title"] == "test chat"
    assert payload["working_directory"] == "/tmp"
    assert payload["agent_name"] == "code-puppy"
    assert payload["model_name"] == "gpt-5"


def test_session_meta_payload_has_no_extra_keys():
    payload = build_session_meta_payload(
        session_id="s1",
        session_name="s1",
        total_tokens=0,
        message_count=0,
        title="",
        working_directory="",
        agent_name="",
        model_name="",
    )
    expected_keys = {
        "type",
        "session_id",
        "session_name",
        "total_tokens",
        "message_count",
        "title",
        "working_directory",
        "agent_name",
        "model_name",
    }
    assert set(payload.keys()) == expected_keys


# ---------------------------------------------------------------------------
# build_session_update_payload
# ---------------------------------------------------------------------------


def test_session_update_action_created_for_first_message():
    payload = build_session_update_payload(
        session_id="s1",
        session_name="s1",
        title="new chat",
        working_directory="/home",
        message_count=1,
        total_tokens=10,
        timestamp="2026-01-01T00:00:00",
    )
    assert payload["action"] == "created"
    assert payload["auto_saved"] is True
    assert payload["timestamp"] == "2026-01-01T00:00:00"


def test_session_update_action_updated_for_subsequent_messages():
    payload = build_session_update_payload(
        session_id="s1",
        session_name="s1",
        title="chat",
        working_directory="",
        message_count=5,
        total_tokens=100,
    )
    assert payload["action"] == "updated"
    # timestamp auto-generated when not provided
    assert "timestamp" in payload and payload["timestamp"]


def test_session_update_payload_has_expected_keys():
    payload = build_session_update_payload(
        session_id="s1",
        session_name="s1",
        title="",
        working_directory="",
        message_count=2,
        total_tokens=0,
    )
    expected_keys = {
        "session_id",
        "session_name",
        "title",
        "working_directory",
        "timestamp",
        "message_count",
        "total_tokens",
        "auto_saved",
        "action",
    }
    assert set(payload.keys()) == expected_keys
