"""Tests for the optional ``mcp_servers`` field on JSON sub-agent configs.

This is the declarative path: a sub-agent author can ship a JSON file
with ``mcp_servers`` set so the agent's bindings work out of the box,
without requiring users to manually run ``/agents \u2192 B`` first.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_puppy.agents.json_agent import JSONAgent


# ---------- helpers ----------------------------------------------------------


def _write_agent(
    tmp_path: Path,
    *,
    name: str = "test-agent",
    mcp_servers=None,  # noqa: ANN001 - intentionally permissive for invalid-shape tests
    **extra,
) -> str:
    """Write a minimally-valid JSON agent config and return its path.

    ``mcp_servers`` is included only when explicitly provided so we can
    distinguish "field absent" from "field present but empty".
    """
    config = {
        "name": name,
        "description": "test agent",
        "system_prompt": "you are a test agent",
        "tools": [],
    }
    if mcp_servers is not None:
        config["mcp_servers"] = mcp_servers
    config.update(extra)

    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return str(path)


# ---------- absence ----------------------------------------------------------


class TestNoMcpServers:
    def test_absent_field_means_empty_bindings(self, tmp_path):
        agent = JSONAgent(_write_agent(tmp_path))
        assert agent.get_declared_mcp_bindings() == {}


# ---------- list shorthand ---------------------------------------------------


class TestListShorthand:
    def test_list_entries_default_to_auto_start_true(self, tmp_path):
        agent = JSONAgent(_write_agent(tmp_path, mcp_servers=["serena", "puppeteer"]))
        assert agent.get_declared_mcp_bindings() == {
            "serena": {"auto_start": True},
            "puppeteer": {"auto_start": True},
        }

    def test_empty_list_yields_empty_bindings(self, tmp_path):
        agent = JSONAgent(_write_agent(tmp_path, mcp_servers=[]))
        assert agent.get_declared_mcp_bindings() == {}

    def test_non_string_entry_rejected(self, tmp_path):
        path = _write_agent(tmp_path, mcp_servers=["serena", 42])
        with pytest.raises(ValueError, match="must be strings"):
            JSONAgent(path)


# ---------- dict form --------------------------------------------------------


class TestDictForm:
    def test_dict_with_auto_start_options(self, tmp_path):
        agent = JSONAgent(
            _write_agent(
                tmp_path,
                mcp_servers={
                    "serena": {"auto_start": True},
                    "puppeteer": {"auto_start": False},
                },
            )
        )
        assert agent.get_declared_mcp_bindings() == {
            "serena": {"auto_start": True},
            "puppeteer": {"auto_start": False},
        }

    def test_dict_missing_auto_start_defaults_to_true(self, tmp_path):
        """Empty options dict still means 'bound', and bound implies auto_start."""
        agent = JSONAgent(_write_agent(tmp_path, mcp_servers={"serena": {}}))
        assert agent.get_declared_mcp_bindings() == {"serena": {"auto_start": True}}

    def test_dict_value_must_be_dict(self, tmp_path):
        path = _write_agent(tmp_path, mcp_servers={"serena": "true"})
        with pytest.raises(ValueError, match="must be a dict of options"):
            JSONAgent(path)


# ---------- invalid shapes ---------------------------------------------------


class TestInvalidShapes:
    def test_string_top_level_rejected(self, tmp_path):
        path = _write_agent(tmp_path, mcp_servers="serena")
        with pytest.raises(ValueError, match="must be a list of names or a dict"):
            JSONAgent(path)

    def test_int_top_level_rejected(self, tmp_path):
        path = _write_agent(tmp_path, mcp_servers=42)
        with pytest.raises(ValueError, match="must be a list of names or a dict"):
            JSONAgent(path)


# ---------- coexists with existing fields ------------------------------------


class TestCoexistence:
    """Make sure the new field doesn't disturb the rest of the schema."""

    def test_other_fields_still_validate(self, tmp_path):
        agent = JSONAgent(
            _write_agent(
                tmp_path,
                mcp_servers=["serena"],
                user_prompt="hi",
                model="claude-haiku",
            )
        )
        assert agent.name == "test-agent"
        assert agent.get_user_prompt() == "hi"
        assert agent.get_model_name() == "claude-haiku"
        assert agent.get_declared_mcp_bindings() == {"serena": {"auto_start": True}}
