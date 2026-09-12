"""Binding revocation must beat cached toolsets and agent JSON defaults."""

from types import SimpleNamespace

import pytest

from code_puppy.mcp_ import agent_bindings as bindings


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(bindings, "BINDINGS_FILE", str(tmp_path / "bindings.json"))
    monkeypatch.setattr(bindings, "_session_bindings", {})
    monkeypatch.setattr(bindings, "_load_json_declared_bindings", lambda name: {})


def test_unbinding_invalidates_cached_agent(isolated, monkeypatch):
    from code_puppy.agents import agent_manager

    bindings.set_binding("puppy", "remote")
    agent = SimpleNamespace(
        name="puppy",
        _code_generation_agent=object(),
        pydantic_agent=object(),
        _mcp_servers=[object()],
    )
    monkeypatch.setattr(agent_manager, "_CURRENT_AGENT", agent)
    bindings.remove_binding("puppy", "remote")
    assert agent._code_generation_agent is None
    assert agent.pydantic_agent is None
    assert agent._mcp_servers == []
    assert not bindings.is_bound("puppy", "remote")


def test_unbinding_declared_default_survives_reload(isolated, monkeypatch):
    monkeypatch.setattr(
        bindings,
        "_load_json_declared_bindings",
        lambda name: {"remote": {"auto_start": True}},
    )
    assert bindings.remove_binding("puppy", "remote")
    assert not bindings.is_bound("puppy", "remote")
    bindings.clear_session_bindings()
    assert not bindings.is_bound("puppy", "remote")
    bindings.set_binding("puppy", "remote")
    assert bindings.is_bound("puppy", "remote")


def test_persistent_auto_start_change_beats_session_overlay(isolated):
    bindings.set_session_binding("puppy", "remote", auto_start=True)
    bindings.set_binding("puppy", "remote", auto_start=False)
    assert not bindings.get_auto_start("puppy", "remote")


def test_explicit_stop_is_not_an_autostart_target(isolated):
    from unittest.mock import MagicMock

    from code_puppy.agents._builder import _iter_autostart_targets

    bindings.set_binding("puppy", "remote")
    manager = MagicMock()
    manager.get_server_by_name.return_value = SimpleNamespace(id="remote")
    manager.get_server_status.return_value = {"state": "stopped"}
    manager.is_autostart_suppressed.return_value = True
    assert list(_iter_autostart_targets(manager, "puppy")) == []
    manager.is_autostart_suppressed.return_value = False
    assert len(list(_iter_autostart_targets(manager, "puppy"))) == 1


@pytest.mark.asyncio
async def test_unbinding_cancels_pending_start_on_owning_loop(isolated, monkeypatch):
    import asyncio
    from unittest.mock import MagicMock

    from code_puppy.agents import agent_manager
    from code_puppy.mcp_ import manager as manager_module

    bindings.set_binding("puppy", "remote")
    agent = SimpleNamespace(name="puppy")
    monkeypatch.setattr(agent_manager, "_CURRENT_AGENT", agent)
    task = asyncio.create_task(asyncio.Event().wait())
    manager = MagicMock()
    manager._pending_start_tasks = {"remote": task}
    manager.get_server.return_value = SimpleNamespace(
        config=SimpleNamespace(name="remote")
    )
    monkeypatch.setattr(manager_module, "_manager_instance", manager)
    try:
        await asyncio.to_thread(bindings.remove_binding, "puppy", "remote")
        await asyncio.sleep(0)
        manager.stop_server_sync.assert_called_with("remote")
        assert not bindings.is_bound("puppy", "remote")
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
