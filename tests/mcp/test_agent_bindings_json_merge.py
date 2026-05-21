"""Tests for the JSON-declared bindings merge in ``get_bound_servers``.

Locks in the contract:

* JSON-declared bindings are visible to all consumers (autostart,
  manager filtering, the bindings menu) without anyone having to call
  the agent loader directly.
* The runtime bindings file (``mcp_agent_bindings.json``) **wins** on
  per-server conflict so the menu can still override declarations.
* If the agent loader fails, the merge degrades gracefully to file-only
  bindings instead of breaking MCP filtering for healthy agents.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.mcp_ import agent_bindings


@pytest.fixture
def tmp_bindings_file(tmp_path, monkeypatch):
    """Point the bindings module at a throwaway JSON file."""
    path = tmp_path / "mcp_agent_bindings.json"
    monkeypatch.setattr(agent_bindings, "BINDINGS_FILE", str(path))
    return path


def _write_file_bindings(path: Path, data: dict) -> None:
    path.write_text(json.dumps({"bindings": data}), encoding="utf-8")


def _stub_json_agent(declared: dict):
    """Return a context that makes ``load_agent`` yield a JSONAgent stub."""
    from code_puppy.agents.json_agent import JSONAgent

    fake_agent = MagicMock(spec=JSONAgent)
    fake_agent.get_declared_mcp_bindings.return_value = declared
    return patch("code_puppy.agents.agent_manager.load_agent", return_value=fake_agent)


class TestJsonOnly:
    def test_json_declared_bindings_show_up(self, tmp_bindings_file):
        with _stub_json_agent({"serena": {"auto_start": True}}):
            result = agent_bindings.get_bound_servers("clone-1")
        assert result == {"serena": {"auto_start": True}}

    def test_no_declarations_no_file_yields_empty(self, tmp_bindings_file):
        with _stub_json_agent({}):
            assert agent_bindings.get_bound_servers("ghost") == {}


class TestFileOnly:
    def test_file_bindings_when_no_json(self, tmp_bindings_file):
        _write_file_bindings(
            tmp_bindings_file, {"code-puppy": {"sqlite": {"auto_start": True}}}
        )
        # Non-JSON agent: load_agent returns something that isn't a JSONAgent.
        with patch(
            "code_puppy.agents.agent_manager.load_agent", return_value=MagicMock()
        ):
            result = agent_bindings.get_bound_servers("code-puppy")
        assert result == {"sqlite": {"auto_start": True}}


class TestMergeFileWins:
    def test_file_overrides_declared_auto_start(self, tmp_bindings_file):
        _write_file_bindings(
            tmp_bindings_file, {"clone-1": {"serena": {"auto_start": False}}}
        )
        with _stub_json_agent({"serena": {"auto_start": True}}):
            result = agent_bindings.get_bound_servers("clone-1")
        # File's auto_start=False wins over JSON's auto_start=True.
        assert result == {"serena": {"auto_start": False}}

    def test_union_of_servers(self, tmp_bindings_file):
        _write_file_bindings(
            tmp_bindings_file, {"clone-1": {"sqlite": {"auto_start": True}}}
        )
        with _stub_json_agent({"serena": {"auto_start": True}}):
            result = agent_bindings.get_bound_servers("clone-1")
        # Both servers visible; neither source is dropped.
        assert result == {
            "serena": {"auto_start": True},
            "sqlite": {"auto_start": True},
        }


class TestDefensiveDegradation:
    """When the agent loader misbehaves, file bindings still work."""

    def test_load_agent_raises_falls_back_to_file(self, tmp_bindings_file):
        _write_file_bindings(
            tmp_bindings_file, {"clone-1": {"sqlite": {"auto_start": True}}}
        )
        with patch(
            "code_puppy.agents.agent_manager.load_agent",
            side_effect=RuntimeError("boom"),
        ):
            result = agent_bindings.get_bound_servers("clone-1")
        assert result == {"sqlite": {"auto_start": True}}

    def test_get_declared_raises_falls_back_to_file(self, tmp_bindings_file):
        from code_puppy.agents.json_agent import JSONAgent

        _write_file_bindings(
            tmp_bindings_file, {"clone-1": {"sqlite": {"auto_start": True}}}
        )
        bad_agent = MagicMock(spec=JSONAgent)
        bad_agent.get_declared_mcp_bindings.side_effect = RuntimeError("kaboom")
        with patch(
            "code_puppy.agents.agent_manager.load_agent", return_value=bad_agent
        ):
            result = agent_bindings.get_bound_servers("clone-1")
        assert result == {"sqlite": {"auto_start": True}}


class TestDownstreamConsumersSeeMerge:
    """Spot-check: consumers using ``get_bound_servers`` get the merged view."""

    def test_is_bound_sees_declared(self, tmp_bindings_file):
        with _stub_json_agent({"serena": {"auto_start": True}}):
            assert agent_bindings.is_bound("clone-1", "serena") is True
            assert agent_bindings.is_bound("clone-1", "ghost") is False

    def test_get_auto_start_uses_merged_value(self, tmp_bindings_file):
        _write_file_bindings(
            tmp_bindings_file, {"clone-1": {"serena": {"auto_start": False}}}
        )
        with _stub_json_agent({"serena": {"auto_start": True}}):
            # File wins -> False, despite JSON saying True.
            assert agent_bindings.get_auto_start("clone-1", "serena") is False
