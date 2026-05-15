"""Tests for code_puppy.mcp_.agent_bindings."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.mcp_ import agent_bindings as ab


@pytest.fixture
def tmp_bindings(tmp_path: Path, monkeypatch):
    """Redirect BINDINGS_FILE at runtime to a temp file."""
    target = tmp_path / "mcp_agent_bindings.json"
    monkeypatch.setattr(ab, "BINDINGS_FILE", str(target))
    return target


class TestBindingsRoundTrip:
    def test_empty_when_missing(self, tmp_bindings):
        assert ab.load_bindings() == {}
        assert ab.get_bound_servers("anybody") == {}
        assert ab.is_bound("anybody", "anything") is False
        assert ab.get_auto_start("anybody", "anything") is False

    def test_set_and_get_binding(self, tmp_bindings):
        ab.set_binding("python", "filesystem", auto_start=True)
        assert ab.is_bound("python", "filesystem") is True
        assert ab.get_auto_start("python", "filesystem") is True
        assert ab.get_bound_servers("python") == {"filesystem": {"auto_start": True}}
        assert ab.get_agents_for_server("filesystem") == ["python"]

    def test_set_binding_default_is_auto_start_true(self, tmp_bindings):
        # Locks in the "binding implies auto-start" UX default. If you ever
        # need to flip this back, make sure you also update toggle_binding
        # and the post-install bind menu.
        ab.set_binding("python", "fs")
        assert ab.get_auto_start("python", "fs") is True

    def test_toggle_binding_on_defaults_to_auto_start(self, tmp_bindings):
        assert ab.toggle_binding("python", "fs") is True
        assert ab.get_auto_start("python", "fs") is True

    def test_set_overwrites_options(self, tmp_bindings):
        ab.set_binding("python", "fs", auto_start=True)
        ab.set_binding("python", "fs", auto_start=False)
        assert ab.get_auto_start("python", "fs") is False

    def test_remove_binding(self, tmp_bindings):
        ab.set_binding("python", "fs")
        assert ab.remove_binding("python", "fs") is True
        assert ab.is_bound("python", "fs") is False
        # Removing again is a no-op
        assert ab.remove_binding("python", "fs") is False

    def test_remove_last_binding_drops_agent_block(self, tmp_bindings):
        ab.set_binding("python", "fs")
        ab.remove_binding("python", "fs")
        data = json.loads(tmp_bindings.read_text())
        assert "python" not in data["bindings"]

    def test_toggle_binding(self, tmp_bindings):
        assert ab.toggle_binding("python", "fs") is True
        assert ab.is_bound("python", "fs") is True
        assert ab.toggle_binding("python", "fs") is False
        assert ab.is_bound("python", "fs") is False

    def test_toggle_auto_start_requires_binding(self, tmp_bindings):
        assert ab.toggle_auto_start("python", "fs") is None
        ab.set_binding("python", "fs", auto_start=False)
        assert ab.toggle_auto_start("python", "fs") is True
        assert ab.toggle_auto_start("python", "fs") is False

    def test_remove_server_from_all_agents(self, tmp_bindings):
        # Default auto_start is now True — see set_binding() docstring.
        ab.set_binding("python", "fs")
        ab.set_binding("qa", "fs", auto_start=True)
        ab.set_binding("qa", "github")
        removed = ab.remove_server_from_all_agents("fs")
        assert removed == 2
        assert ab.get_bound_servers("python") == {}
        assert ab.get_bound_servers("qa") == {"github": {"auto_start": True}}

    def test_rename_server_in_bindings(self, tmp_bindings):
        ab.set_binding("python", "fs", auto_start=True)
        ab.set_binding("qa", "fs")
        affected = ab.rename_server_in_bindings("fs", "filesystem")
        assert affected == 2
        assert ab.is_bound("python", "filesystem")
        assert ab.is_bound("qa", "filesystem")
        assert not ab.is_bound("python", "fs")

    def test_rename_noop(self, tmp_bindings):
        ab.set_binding("python", "fs")
        assert ab.rename_server_in_bindings("fs", "fs") == 0


class TestCorruptionResilience:
    def test_invalid_json_returns_empty(self, tmp_bindings):
        tmp_bindings.write_text("{not json")
        assert ab.load_bindings() == {}

    def test_wrong_shape_returns_empty(self, tmp_bindings):
        tmp_bindings.write_text(json.dumps({"oops": []}))
        assert ab.load_bindings() == {}


class TestManagerFilter:
    """get_servers_for_agent should respect bindings (strict opt-in)."""

    def test_unbound_agent_gets_nothing(self, tmp_bindings):
        from code_puppy.mcp_.manager import MCPManager

        with (
            patch.object(MCPManager, "sync_from_config"),
            patch.object(MCPManager, "_initialize_servers"),
        ):
            manager = MCPManager()

        # Build two fake managed servers
        fake_a = _fake_managed("alpha")
        fake_b = _fake_managed("beta")
        manager._managed_servers = {"a": fake_a, "b": fake_b}

        # No bindings → strict opt-in returns nothing
        assert manager.get_servers_for_agent(agent_name="ghost-agent") == []

    def test_bound_agent_gets_only_bound(self, tmp_bindings):
        from code_puppy.mcp_.manager import MCPManager

        with (
            patch.object(MCPManager, "sync_from_config"),
            patch.object(MCPManager, "_initialize_servers"),
        ):
            manager = MCPManager()

        fake_a = _fake_managed("alpha")
        fake_b = _fake_managed("beta")
        manager._managed_servers = {"a": fake_a, "b": fake_b}

        ab.set_binding("python", "alpha")
        servers = manager.get_servers_for_agent(agent_name="python")
        assert servers == [fake_a.get_pydantic_server.return_value]

    def test_legacy_no_agent_name_returns_all(self, tmp_bindings):
        from code_puppy.mcp_.manager import MCPManager

        with (
            patch.object(MCPManager, "sync_from_config"),
            patch.object(MCPManager, "_initialize_servers"),
        ):
            manager = MCPManager()

        fake_a = _fake_managed("alpha")
        fake_b = _fake_managed("beta")
        manager._managed_servers = {"a": fake_a, "b": fake_b}

        servers = manager.get_servers_for_agent()
        assert len(servers) == 2


def _fake_managed(name: str):
    """Tiny mock for ManagedMCPServer satisfying get_servers_for_agent."""
    from unittest.mock import MagicMock

    fake = MagicMock()
    fake.config.name = name
    fake.is_enabled.return_value = True
    fake.is_quarantined.return_value = False
    fake.get_pydantic_server.return_value = MagicMock(name=f"pydantic-{name}")
    return fake
