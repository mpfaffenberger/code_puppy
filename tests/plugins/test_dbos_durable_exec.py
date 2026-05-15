"""Tests for the dbos_durable_exec plugin.

Covers config, workflow_ids, wrapper, runtime, cancel, commands, and the
register_callbacks wiring. None of these tests require the real `dbos`
package to be installed — `dbos` is monkeypatched in/out of `sys.modules`.
"""

from __future__ import annotations

import importlib
import sys
import types
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from code_puppy.callbacks import (
    clear_callbacks,
    count_callbacks,
    get_callbacks,
)
from code_puppy.plugins.dbos_durable_exec import cancel as cancel_mod
from code_puppy.plugins.dbos_durable_exec import commands as commands_mod
from code_puppy.plugins.dbos_durable_exec import config as config_mod
from code_puppy.plugins.dbos_durable_exec import runtime as runtime_mod
from code_puppy.plugins.dbos_durable_exec import workflow_ids as workflow_ids_mod
from code_puppy.plugins.dbos_durable_exec import wrapper as wrapper_mod

# ─────────────────────── config.is_enabled ────────────────────────────


class TestIsEnabled:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.setattr(config_mod, "get_value", lambda _k: None)
        assert config_mod.is_enabled() is True

    @pytest.mark.parametrize("val", ["true", "TRUE", "1", "yes", "YES", "on", "On"])
    def test_truthy_values(self, monkeypatch, val):
        monkeypatch.setattr(config_mod, "get_value", lambda _k: val)
        assert config_mod.is_enabled() is True

    @pytest.mark.parametrize("val", ["false", "FALSE", "0", "no", "off", "OFF"])
    def test_falsy_values(self, monkeypatch, val):
        monkeypatch.setattr(config_mod, "get_value", lambda _k: val)
        assert config_mod.is_enabled() is False

    def test_set_enabled_writes_string(self, monkeypatch):
        captured = {}

        def fake_set(k, v):
            captured[k] = v

        monkeypatch.setattr(config_mod, "set_config_value", fake_set)
        config_mod.set_enabled(True)
        assert captured["enable_dbos"] == "true"
        config_mod.set_enabled(False)
        assert captured["enable_dbos"] == "false"


# ─────────────────────── workflow_ids ─────────────────────────────────


class TestGenerateDbosWorkflowId:
    def test_consecutive_calls_differ(self):
        a = workflow_ids_mod.generate_dbos_workflow_id("base")
        b = workflow_ids_mod.generate_dbos_workflow_id("base")
        assert a != b

    def test_starts_with_base_prefix(self):
        out = workflow_ids_mod.generate_dbos_workflow_id("my-base")
        assert isinstance(out, str)
        assert out.startswith("my-base")


# ─────────────────────── wrapper.wrap_with_dbos_agent ─────────────────


def _install_fake_pydantic_dbos(monkeypatch):
    """Install a fake pydantic_ai.durable_exec.dbos module with a sentinel DBOSAgent.

    Also forces ``lifecycle.is_launched()`` to True so the wrapper actually
    proceeds (it now bails out when DBOS hasn't been launched, to avoid
    handing back broken DBOSAgents in test environments).
    """
    from code_puppy.plugins.dbos_durable_exec import lifecycle as lifecycle_mod

    monkeypatch.setattr(lifecycle_mod, "_LAUNCHED", True)
    captured = {}

    class FakeDBOSAgent:
        def __init__(self, inner, **kwargs):
            captured["inner"] = inner
            captured["kwargs"] = kwargs
            self.inner = inner
            self.kwargs = kwargs

    pydantic_ai_pkg = types.ModuleType("pydantic_ai")
    durable_pkg = types.ModuleType("pydantic_ai.durable_exec")
    dbos_submod = types.ModuleType("pydantic_ai.durable_exec.dbos")
    dbos_submod.DBOSAgent = FakeDBOSAgent
    monkeypatch.setitem(sys.modules, "pydantic_ai", pydantic_ai_pkg)
    monkeypatch.setitem(sys.modules, "pydantic_ai.durable_exec", durable_pkg)
    monkeypatch.setitem(sys.modules, "pydantic_ai.durable_exec.dbos", dbos_submod)
    return FakeDBOSAgent, captured


class TestWrapWithDbosAgent:
    def test_returns_none_when_dbos_not_launched(self, monkeypatch):
        """Wrapper must bail out when DBOS hasn't been launched.

        Regression: when [durable] extras were installed in CI, dbos became
        importable in pytest's process, so the wrapper produced DBOSAgents
        that were unusable (no DBOS instance running). Test verifies that
        path now passes through unmodified.
        """
        from code_puppy.plugins.dbos_durable_exec import lifecycle as lifecycle_mod

        monkeypatch.setattr(lifecycle_mod, "_LAUNCHED", False)
        # Even with the pydantic_ai dbos submodule available, we must NOT wrap.
        _install_fake_pydantic_dbos(monkeypatch)
        # _install_fake_pydantic_dbos sets _LAUNCHED=True; flip it back.
        monkeypatch.setattr(lifecycle_mod, "_LAUNCHED", False)

        agent = MagicMock(name="agent")
        pydantic_agent = MagicMock(name="pyd")
        pydantic_agent._toolsets = []
        result = wrapper_mod.wrap_with_dbos_agent(agent, pydantic_agent)
        assert result is None

    def test_returns_none_when_import_fails(self, monkeypatch):
        # Force import to fail by setting the submodule to None.
        from code_puppy.plugins.dbos_durable_exec import lifecycle as lifecycle_mod

        monkeypatch.setattr(lifecycle_mod, "_LAUNCHED", True)
        monkeypatch.setitem(sys.modules, "pydantic_ai.durable_exec.dbos", None)
        agent = MagicMock(name="agent")
        pydantic_agent = MagicMock(name="pyd")
        pydantic_agent._toolsets = []
        result = wrapper_mod.wrap_with_dbos_agent(agent, pydantic_agent)
        assert result is None

    def test_main_kind_passes_through_handler(self, monkeypatch):
        FakeDBOSAgent, captured = _install_fake_pydantic_dbos(monkeypatch)

        agent = MagicMock(name="agent")
        agent.name = "main-agent"
        pydantic_agent = MagicMock(name="pyd")
        pydantic_agent._toolsets = ["toolset-1"]
        handler = object()

        result = wrapper_mod.wrap_with_dbos_agent(
            agent,
            pydantic_agent,
            event_stream_handler=handler,
            kind="main",
        )

        assert result is not pydantic_agent
        assert isinstance(result, FakeDBOSAgent)
        assert captured["kwargs"]["event_stream_handler"] is handler
        assert captured["kwargs"]["name"].startswith("main-agent-main-")
        # Toolsets are reset (pickleability fix).
        assert pydantic_agent._toolsets == []

    def test_subagent_kind_forces_handler_none(self, monkeypatch):
        _, captured = _install_fake_pydantic_dbos(monkeypatch)

        agent = MagicMock(name="agent")
        agent.name = "sub"
        pydantic_agent = MagicMock(name="pyd")
        pydantic_agent._toolsets = []
        handler = object()

        wrapper_mod.wrap_with_dbos_agent(
            agent,
            pydantic_agent,
            event_stream_handler=handler,
            kind="subagent",
        )
        assert captured["kwargs"]["event_stream_handler"] is None
        assert captured["kwargs"]["name"].startswith("sub-subagent-")

    def test_no_stash_attribute_left_behind(self, monkeypatch):
        """YAGNI cleanup: the dead _dbos_stashed_mcp_toolsets attr must be gone."""
        _install_fake_pydantic_dbos(monkeypatch)
        agent = MagicMock(name="agent")
        agent.name = "x"
        pydantic_agent = types.SimpleNamespace(_toolsets=["a", "b"])
        wrapper_mod.wrap_with_dbos_agent(agent, pydantic_agent)
        assert not hasattr(pydantic_agent, "_dbos_stashed_mcp_toolsets")


# ─────────────────────── runtime.dbos_run_context ─────────────────────


class _FakeSetWorkflowID:
    """Fake context manager that records the workflow_id it was given."""

    calls: list = []

    def __init__(self, workflow_id):
        self.workflow_id = workflow_id
        _FakeSetWorkflowID.calls.append(workflow_id)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@contextmanager
def _install_fake_dbos(monkeypatch):
    """Stub the dbos module + force is_launched()=True for the runtime tests."""
    from code_puppy.plugins.dbos_durable_exec import lifecycle as lifecycle_mod

    _FakeSetWorkflowID.calls = []
    fake_mod = types.ModuleType("dbos")
    fake_mod.SetWorkflowID = _FakeSetWorkflowID
    monkeypatch.setitem(sys.modules, "dbos", fake_mod)
    monkeypatch.setattr(lifecycle_mod, "_LAUNCHED", True)
    try:
        yield fake_mod
    finally:
        pass


class TestDbosRunContext:
    async def test_no_op_when_dbos_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "dbos", None)
        inner = types.SimpleNamespace(_toolsets=["original"])
        pydantic_agent = types.SimpleNamespace(wrapped=inner)
        async with runtime_mod.dbos_run_context(
            agent=None,
            pydantic_agent=pydantic_agent,
            group_id="invoke_agent_foo",
            mcp_servers=["mcp-1"],
        ):
            # No mutation should occur because dbos is unavailable.
            assert inner._toolsets == ["original"]

    async def test_invoke_agent_appends_counter(self, monkeypatch):
        with _install_fake_dbos(monkeypatch):
            inner = types.SimpleNamespace(_toolsets=[])
            pydantic_agent = types.SimpleNamespace(wrapped=inner)
            ids = []
            for _ in range(2):
                async with runtime_mod.dbos_run_context(
                    None, pydantic_agent, "invoke_agent_foo_123", []
                ) as wid:
                    ids.append(wid)
            assert ids[0] != ids[1]
            assert all(w.startswith("invoke_agent_foo_123") for w in ids)
            assert _FakeSetWorkflowID.calls == ids

    async def test_main_run_uses_group_id_verbatim(self, monkeypatch):
        with _install_fake_dbos(monkeypatch):
            inner = types.SimpleNamespace(_toolsets=[])
            pydantic_agent = types.SimpleNamespace(wrapped=inner)
            async with runtime_mod.dbos_run_context(
                None, pydantic_agent, "main_run_xyz", []
            ) as wid:
                assert wid == "main_run_xyz"
            assert _FakeSetWorkflowID.calls == ["main_run_xyz"]

    async def test_mcp_servers_swap_and_restore_on_success(self, monkeypatch):
        with _install_fake_dbos(monkeypatch):
            inner = types.SimpleNamespace(_toolsets=["orig-a"])
            pydantic_agent = types.SimpleNamespace(wrapped=inner)
            async with runtime_mod.dbos_run_context(
                None, pydantic_agent, "main_run", ["mcp-1", "mcp-2"]
            ):
                assert inner._toolsets == ["orig-a", "mcp-1", "mcp-2"]
            assert inner._toolsets == ["orig-a"]

    async def test_mcp_servers_restored_on_exception(self, monkeypatch):
        with _install_fake_dbos(monkeypatch):
            inner = types.SimpleNamespace(_toolsets=["orig"])
            pydantic_agent = types.SimpleNamespace(wrapped=inner)
            with pytest.raises(RuntimeError, match="boom"):
                async with runtime_mod.dbos_run_context(
                    None, pydantic_agent, "main_run", ["mcp-1"]
                ):
                    assert inner._toolsets == ["orig", "mcp-1"]
                    raise RuntimeError("boom")
            assert inner._toolsets == ["orig"]


# ─────────────────────── cancel.cancel_workflow ───────────────────────


class TestCancelWorkflow:
    async def test_no_op_when_dbos_missing(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "dbos", None)
        # Just make sure it doesn't raise.
        await cancel_mod.cancel_workflow("group-1")

    async def test_calls_cancel_workflow_async(self, monkeypatch):
        fake_mod = types.ModuleType("dbos")
        fake_dbos = MagicMock()
        fake_dbos.cancel_workflow_async = AsyncMock(return_value=None)
        fake_mod.DBOS = fake_dbos
        monkeypatch.setitem(sys.modules, "dbos", fake_mod)

        await cancel_mod.cancel_workflow("group-42")
        fake_dbos.cancel_workflow_async.assert_awaited_once_with("group-42")

    async def test_swallows_exceptions(self, monkeypatch):
        fake_mod = types.ModuleType("dbos")
        fake_dbos = MagicMock()
        fake_dbos.cancel_workflow_async = AsyncMock(side_effect=RuntimeError("nope"))
        fake_mod.DBOS = fake_dbos
        monkeypatch.setitem(sys.modules, "dbos", fake_mod)

        # Should not raise.
        await cancel_mod.cancel_workflow("group-99")


# ─────────────────────── commands.handle_dbos_command ─────────────────


class TestHandleDbosCommand:
    def test_non_dbos_name_returns_none(self):
        assert commands_mod.handle_dbos_command("woof", "woof") is None

    def test_status_path_when_on(self, monkeypatch):
        monkeypatch.setattr(commands_mod, "is_enabled", lambda: True)
        result = commands_mod.handle_dbos_command("/dbos status", "dbos")
        assert "ON" in result

    def test_status_path_when_off(self, monkeypatch):
        monkeypatch.setattr(commands_mod, "is_enabled", lambda: False)
        result = commands_mod.handle_dbos_command("/dbos status", "dbos")
        assert "OFF" in result

    def test_no_subcommand_shows_status_and_usage(self, monkeypatch):
        monkeypatch.setattr(commands_mod, "is_enabled", lambda: True)
        result = commands_mod.handle_dbos_command("/dbos", "dbos")
        assert "ON" in result
        assert "Usage" in result

    def test_on_calls_set_enabled_true(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            commands_mod, "set_enabled", lambda v: captured.setdefault("v", v)
        )
        result = commands_mod.handle_dbos_command("/dbos on", "dbos")
        assert captured["v"] is True
        assert "enabled" in result.lower()

    def test_off_calls_set_enabled_false(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            commands_mod, "set_enabled", lambda v: captured.setdefault("v", v)
        )
        result = commands_mod.handle_dbos_command("/dbos off", "dbos")
        assert captured["v"] is False
        assert "disabled" in result.lower()

    def test_unknown_subcommand(self, monkeypatch):
        monkeypatch.setattr(commands_mod, "is_enabled", lambda: True)
        result = commands_mod.handle_dbos_command("/dbos sideways", "dbos")
        assert "Unknown" in result
        assert "sideways" in result

    def test_help_entries(self):
        entries = commands_mod.dbos_command_help()
        assert any(name == "dbos" for name, _ in entries)


# ─────────────────────── register_callbacks wiring ────────────────────


# Phases owned by this plugin (slash-cmd hooks always, lifecycle behind dbos).
_SLASH_PHASES = ("custom_command", "custom_command_help")
_DBOS_PHASES = (
    "startup",
    "shutdown",
    "wrap_pydantic_agent",
    "agent_run_context",
    "agent_run_cancel",
    "should_skip_fallback_render",
)


@pytest.fixture
def clean_callbacks():
    """Snapshot + restore the global callback registry around each test."""
    saved = {p: get_callbacks(p) for p in _SLASH_PHASES + _DBOS_PHASES}
    for p in saved:
        clear_callbacks(p)
    yield
    for p, funcs in saved.items():
        clear_callbacks(p)
        for f in funcs:
            from code_puppy.callbacks import register_callback as _reg

            _reg(p, f)


def _reload_register_callbacks():
    mod_name = "code_puppy.plugins.dbos_durable_exec.register_callbacks"
    if mod_name in sys.modules:
        return importlib.reload(sys.modules[mod_name])
    return importlib.import_module(mod_name)


class TestRegisterCallbacksWiring:
    def test_disabled_registers_only_slash_commands(self, monkeypatch, clean_callbacks):
        monkeypatch.setattr(config_mod, "is_enabled", lambda: False)
        _reload_register_callbacks()
        # Slash command hooks always register.
        for p in _SLASH_PHASES:
            assert count_callbacks(p) == 1, f"expected slash cmd registered for {p}"
        # DBOS-specific hooks should NOT.
        for p in _DBOS_PHASES:
            assert count_callbacks(p) == 0, f"unexpected callback on phase {p}"

    def test_enabled_but_dbos_missing_skips_lifecycle(
        self, monkeypatch, clean_callbacks
    ):
        monkeypatch.setattr(config_mod, "is_enabled", lambda: True)
        monkeypatch.setitem(sys.modules, "dbos", None)
        _reload_register_callbacks()
        for p in _SLASH_PHASES:
            assert count_callbacks(p) == 1
        for p in _DBOS_PHASES:
            assert count_callbacks(p) == 0

    def test_enabled_and_dbos_present_registers_everything(
        self, monkeypatch, clean_callbacks
    ):
        monkeypatch.setattr(config_mod, "is_enabled", lambda: True)
        fake_mod = types.ModuleType("dbos")
        monkeypatch.setitem(sys.modules, "dbos", fake_mod)
        _reload_register_callbacks()
        for p in _SLASH_PHASES + _DBOS_PHASES:
            assert count_callbacks(p) >= 1, f"missing callback on phase {p}"

    def test_idempotent_reload_does_not_double_register(
        self, monkeypatch, clean_callbacks
    ):
        monkeypatch.setattr(config_mod, "is_enabled", lambda: True)
        fake_mod = types.ModuleType("dbos")
        monkeypatch.setitem(sys.modules, "dbos", fake_mod)
        _reload_register_callbacks()
        counts = {p: count_callbacks(p) for p in _SLASH_PHASES + _DBOS_PHASES}
        _reload_register_callbacks()
        counts_after = {p: count_callbacks(p) for p in _SLASH_PHASES + _DBOS_PHASES}
        assert counts == counts_after, "register_callback should dedupe on reload"
