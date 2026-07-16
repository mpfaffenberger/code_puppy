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


class TestSessionBindings:
    """Session-only bindings (in-memory overlay used by /mcp start)."""

    def test_set_session_binding_is_not_persisted(self, tmp_bindings):
        ab.set_session_binding("python", "serena")
        assert ab.is_bound("python", "serena") is True
        # Crucial: nothing should have hit disk.
        assert not tmp_bindings.exists()
        assert ab.load_bindings() == {}

    def test_session_binding_visible_via_get_bound_servers(self, tmp_bindings):
        ab.set_session_binding("python", "serena")
        assert ab.get_bound_servers("python") == {"serena": {"auto_start": True}}

    def test_session_overrides_file_for_same_server(self, tmp_bindings):
        ab.set_binding("python", "serena", auto_start=False)
        ab.set_session_binding("python", "serena", auto_start=True)
        # Session wins — most recent user intent.
        assert ab.get_auto_start("python", "serena") is True

    def test_clear_session_bindings_wipes_overlay(self, tmp_bindings):
        ab.set_session_binding("python", "serena")
        ab.clear_session_bindings()
        assert ab.is_bound("python", "serena") is False

    def test_remove_session_binding_returns_false_when_absent(self, tmp_bindings):
        assert ab.remove_session_binding("python", "nope") is False

    def test_remove_binding_also_clears_session_ghost(self, tmp_bindings):
        # If a user explicitly unbinds via the menu, the session overlay must
        # not silently re-enable the server.
        ab.set_session_binding("python", "serena")
        ab.set_binding("python", "serena")
        assert ab.remove_binding("python", "serena") is True
        assert ab.is_bound("python", "serena") is False


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


class TestUnboundOrphanWarning:
    """Hand-edited mcp_servers.json should produce a visible orphan warning.

    Covers CPUP-6ym: a server registered via mcp_servers.json but with no
    binding for the current agent used to be silently dropped on every
    agent build with a logger.debug call no one would see. We now emit a
    visible warning once per ``(server, agent)`` pair per process.
    """

    def _fresh_manager(self):
        from code_puppy.mcp_ import manager as mgr_mod
        from code_puppy.mcp_.manager import MCPManager

        with (
            patch.object(MCPManager, "sync_from_config"),
            patch.object(MCPManager, "_initialize_servers"),
        ):
            manager = MCPManager()
        mgr_mod._reset_unbound_warning_cache()
        return manager, mgr_mod

    def test_unbound_orphan_emits_warning(self, tmp_bindings):
        manager, mgr_mod = self._fresh_manager()
        manager._managed_servers = {"a": _fake_managed("nu")}

        with patch.object(mgr_mod, "emit_warning") as mock_warn:
            servers = manager.get_servers_for_agent(agent_name="python")

        assert servers == []
        assert mock_warn.call_count == 1
        msg = mock_warn.call_args.args[0]
        # Terse one-liner: count + agent + how to act. Individual server names
        # are intentionally omitted (run `/mcp` to see them).
        assert "1 MCP server" in msg
        assert "'python'" in msg
        # The warning must advertise its own off-switch, otherwise users have
        # no idea this is silenceable.
        assert "/mcp silence-warning" in msg

    def test_warning_deduped_per_pair_per_process(self, tmp_bindings):
        manager, mgr_mod = self._fresh_manager()
        manager._managed_servers = {"a": _fake_managed("nu")}

        with patch.object(mgr_mod, "emit_warning") as mock_warn:
            for _ in range(5):
                manager.get_servers_for_agent(agent_name="python")

        assert mock_warn.call_count == 1

    def test_distinct_pairs_each_warn_once(self, tmp_bindings):
        manager, mgr_mod = self._fresh_manager()
        manager._managed_servers = {
            "a": _fake_managed("nu"),
            "b": _fake_managed("mu"),
        }

        with patch.object(mgr_mod, "emit_warning") as mock_warn:
            manager.get_servers_for_agent(agent_name="python")
            manager.get_servers_for_agent(agent_name="python")
            manager.get_servers_for_agent(agent_name="rust")

        # One consolidated warning per fresh (agent, set-of-unbound-servers)
        # batch: python's first build emits one block listing nu+mu, rust's
        # first build emits one block listing nu+mu, python's second build
        # is fully deduped. Total: 2 warning blocks.
        assert mock_warn.call_count == 2
        # Each emitted message reports the count of unbound servers and the
        # specific agent it was built for (names are omitted by design).
        for call in mock_warn.call_args_list:
            msg = call.args[0]
            assert "2 MCP servers" in msg
        agents_warned_about = [
            "python" if "'python'" in call.args[0] else "rust"
            for call in mock_warn.call_args_list
        ]
        assert sorted(agents_warned_about) == ["python", "rust"]
        # Multi-server variant must also mention the silence command.
        for call in mock_warn.call_args_list:
            assert "/mcp silence-warning" in call.args[0]

    def test_disabled_or_quarantined_does_not_warn(self, tmp_bindings):
        manager, mgr_mod = self._fresh_manager()

        disabled = _fake_managed("disabled-srv")
        disabled.is_enabled.return_value = False
        quarantined = _fake_managed("quar-srv")
        quarantined.is_quarantined.return_value = True
        manager._managed_servers = {"d": disabled, "q": quarantined}

        with patch.object(mgr_mod, "emit_warning") as mock_warn:
            manager.get_servers_for_agent(agent_name="python")

        mock_warn.assert_not_called()

    def test_bound_server_does_not_warn(self, tmp_bindings):
        manager, mgr_mod = self._fresh_manager()
        manager._managed_servers = {"a": _fake_managed("nu")}

        ab.set_binding("python", "nu")

        with patch.object(mgr_mod, "emit_warning") as mock_warn:
            servers = manager.get_servers_for_agent(agent_name="python")

        assert len(servers) == 1
        mock_warn.assert_not_called()

    def test_silence_flag_suppresses_warning(self, tmp_bindings):
        """`/mcp silence-warning` (i.e. the config flag) kills the warning."""
        manager, mgr_mod = self._fresh_manager()
        manager._managed_servers = {"a": _fake_managed("nu")}

        with (
            patch.object(mgr_mod, "emit_warning") as mock_warn,
            patch(
                "code_puppy.config.get_mcp_unbound_warning_silenced",
                return_value=True,
            ),
        ):
            servers = manager.get_servers_for_agent(agent_name="python")

        assert servers == []
        mock_warn.assert_not_called()

    def test_silence_flag_does_not_pollute_dedupe_cache(self, tmp_bindings):
        """Silencing should not mark pairs as 'already warned' — unsilencing
        later must restore the warning on the next build."""
        manager, mgr_mod = self._fresh_manager()
        manager._managed_servers = {"a": _fake_managed("nu")}

        # First call: silenced, no warn, cache untouched.
        with (
            patch.object(mgr_mod, "emit_warning") as mock_warn,
            patch(
                "code_puppy.config.get_mcp_unbound_warning_silenced",
                return_value=True,
            ),
        ):
            manager.get_servers_for_agent(agent_name="python")
        mock_warn.assert_not_called()

        # Second call: un-silenced — warning must fire because the silenced
        # path bailed before touching _WARNED_UNBOUND.
        with (
            patch.object(mgr_mod, "emit_warning") as mock_warn,
            patch(
                "code_puppy.config.get_mcp_unbound_warning_silenced",
                return_value=False,
            ),
        ):
            manager.get_servers_for_agent(agent_name="python")
        assert mock_warn.call_count == 1


def _fake_managed(name: str):
    """Tiny mock for ManagedMCPServer satisfying get_servers_for_agent."""
    from unittest.mock import MagicMock

    fake = MagicMock()
    fake.config.name = name
    fake.is_enabled.return_value = True
    fake.is_quarantined.return_value = False
    fake.get_pydantic_server.return_value = MagicMock(name=f"pydantic-{name}")
    return fake
