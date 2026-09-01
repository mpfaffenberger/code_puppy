"""Regression tests for JSONAgent's config-load corruption resilience.

Part of the PUP-605 follow-up (Andrew Tilson's review on #757 flagged
``~/.code_puppy/agents/*.json`` reads at startup as another unbounded-read
site). ``_load_config`` now delegates to :mod:`code_puppy.atomic_json`,
which bounds the read before parsing and raises ``ValueError`` (matching
the pre-existing public contract) instead of letting a pathological file
balloon memory.
"""

import json

import pytest

from code_puppy.agents.json_agent import JSONAgent

VALID_CONFIG = {
    "name": "test-agent",
    "description": "A test agent",
    "system_prompt": "You are a helpful test agent.",
    "tools": ["list_files"],
}


@pytest.fixture
def agent_path(tmp_path):
    return tmp_path / "agent.json"


def test_loads_valid_config(agent_path):
    agent_path.write_text(json.dumps(VALID_CONFIG))

    agent = JSONAgent(str(agent_path))

    assert agent._config["name"] == "test-agent"


def test_missing_file_raises_value_error(agent_path):
    # agent_path was never created.
    with pytest.raises(ValueError, match="Failed to load JSON agent config"):
        JSONAgent(str(agent_path))


def test_malformed_json_raises_value_error(agent_path):
    agent_path.write_text("{not valid json at all")

    with pytest.raises(ValueError, match="Failed to load JSON agent config"):
        JSONAgent(str(agent_path))


def test_oversized_file_raises_value_error_without_full_parse(agent_path, monkeypatch):
    """Pins the actual field-report shape this closes off: a pathologically
    large agent file dropped in the agents directory must never reach a
    full in-memory JSON parse."""
    from code_puppy import atomic_json

    monkeypatch.setattr(atomic_json, "MAX_JSON_BYTES", 1024)
    agent_path.write_text(json.dumps({**VALID_CONFIG, "padding": "x" * 4096}))

    with pytest.raises(ValueError, match="Failed to load JSON agent config"):
        JSONAgent(str(agent_path))


def test_discover_json_agents_skips_corrupt_files_without_raising(
    tmp_path, monkeypatch
):
    """The existing discover_json_agents contract: one bad file must not
    prevent the others from loading."""
    from code_puppy.agents.json_agent import discover_json_agents

    good = tmp_path / "good.json"
    good.write_text(json.dumps(VALID_CONFIG))
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")

    monkeypatch.setattr(
        "code_puppy.config.get_user_agents_directory", lambda: str(tmp_path)
    )
    monkeypatch.setattr("code_puppy.config.get_project_agents_directory", lambda: None)

    agents = discover_json_agents()

    assert agents.get("test-agent") == str(good)
    assert len(agents) == 1


def test_mcp_servers_null_is_accepted(agent_path):
    """Explicit JSON ``null`` for ``mcp_servers`` must be treated as "no
    bindings declared", not rejected. This is the shape the marketplace
    backend emits for agents with no MCP servers bound (see
    ``AgentPublish.mcp_servers: dict[str, dict] | None`` in puppy-frontend),
    so a downloaded agent with no bindings must load cleanly rather than
    raising during ``_validate_config()``.
    """
    agent_path.write_text(json.dumps({**VALID_CONFIG, "mcp_servers": None}))

    agent = JSONAgent(str(agent_path))

    assert agent._config["name"] == "test-agent"
    assert agent.get_declared_mcp_bindings() == {}


def test_mcp_servers_null_agent_is_discoverable(tmp_path, monkeypatch):
    """Before the fix, ``mcp_servers: null`` raised a ``ValueError`` from
    ``_validate_config()`` that ``discover_json_agents()`` silently
    swallowed, so the agent vanished from the registry entirely
    (presenting to the user as "agent not found"). Confirm the agent now
    survives discovery.
    """
    from code_puppy.agents.json_agent import discover_json_agents

    agent_file = tmp_path / "no-bindings.json"
    agent_file.write_text(json.dumps({**VALID_CONFIG, "mcp_servers": None}))

    monkeypatch.setattr(
        "code_puppy.config.get_user_agents_directory", lambda: str(tmp_path)
    )
    monkeypatch.setattr("code_puppy.config.get_project_agents_directory", lambda: None)

    agents = discover_json_agents()

    assert agents.get("test-agent") == str(agent_file)
