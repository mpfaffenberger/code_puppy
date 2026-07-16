"""Tests for the runtime enable/disable toggle.

Covers:
* default state is enabled
* set_enabled persists across reads
* recorder no-ops when disabled
* retriever returns None when disabled
* every agent-facing tool returns the disabled error when disabled
* /kennel enable / disable / status slash commands flip and report state
* /kennel stats and /kennel wings still work when disabled (human inspection)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def kennel_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # ``PUPPY_KENNEL_ROOT`` now ONLY controls where the SQLite DB lives;
    # it has nothing to do with the on/off toggle, which lives in
    # puppy.cfg (isolated to a temp file by the root tests/conftest.py).
    root = tmp_path / "kennel"
    monkeypatch.setenv("PUPPY_KENNEL_ROOT", str(root))

    import importlib

    from code_puppy.plugins.puppy_kennel import commands as commands_mod
    from code_puppy.plugins.puppy_kennel import config as kennel_config
    from code_puppy.plugins.puppy_kennel import kennel as kennel_mod
    from code_puppy.plugins.puppy_kennel import recorder as recorder_mod
    from code_puppy.plugins.puppy_kennel import retriever as retriever_mod
    from code_puppy.plugins.puppy_kennel import state as state_mod
    from code_puppy.plugins.puppy_kennel import tools as tools_mod

    importlib.reload(kennel_config)
    importlib.reload(state_mod)
    importlib.reload(kennel_mod)
    importlib.reload(recorder_mod)
    importlib.reload(retriever_mod)
    importlib.reload(tools_mod)
    importlib.reload(commands_mod)
    kennel_mod.initialize()
    return root


class _FakeAgent:
    def __init__(self) -> None:
        self.registered: dict[str, Any] = {}

    def tool(self, fn):
        self.registered[fn.__name__] = fn
        return fn


def _ctx(agent_name: str = "code-puppy") -> Any:
    return SimpleNamespace(agent_name=agent_name, deps=None)


# --------------------------------------------------------------------------- #
# State module
# --------------------------------------------------------------------------- #


def test_default_state_is_enabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import state

    assert state.is_enabled() is True


def test_set_enabled_persists(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import state

    state.set_enabled(False)
    assert state.is_enabled() is False
    state.set_enabled(True)
    assert state.is_enabled() is True


def test_garbage_cfg_value_falls_back_to_enabled(kennel_root: Path) -> None:
    """Default-on means a typo in puppy.cfg must not silently kill memory."""
    from code_puppy.config import set_config_value
    from code_puppy.plugins.puppy_kennel import state

    set_config_value("kennel_enabled", "banana")
    assert state.is_enabled() is True


# --------------------------------------------------------------------------- #
# Recorder + retriever honour the toggle
# --------------------------------------------------------------------------- #


def test_recorder_skips_when_disabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel, recorder, state

    state.set_enabled(False)
    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        success=True,
        response_text="Should not be recorded.",
    )
    assert kennel.count_drawers() == 0


def test_recorder_resumes_after_re_enable(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel, recorder, state

    state.set_enabled(False)
    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        success=True,
        response_text="Lost.",
    )
    state.set_enabled(True)
    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        success=True,
        response_text="Saved.",
    )
    # Phase 5: single-write to repo wing only.
    assert kennel.count_drawers() == 1


def test_retriever_returns_none_when_disabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import recorder, retriever, state

    # Has to be longer than MIN_DRAWER_CHARS (80) to clear the packer's
    # noise filter; otherwise the block would be empty for unrelated reasons.
    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        success=True,
        response_text=(
            "Something to recall - and importantly, long enough that the "
            "packer doesn't silently drop it as noise below the minimum "
            "drawer-length threshold."
        ),
    )
    # Sanity: enabled returns a block.
    assert retriever.build_recall_block() is not None

    state.set_enabled(False)
    assert retriever.build_recall_block() is None


# --------------------------------------------------------------------------- #
# All five tools return the disabled error
# --------------------------------------------------------------------------- #


def test_all_tools_return_disabled_error_when_off(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import state, tools

    state.set_enabled(False)
    agent = _FakeAgent()
    tools.register_kennel_recall(agent)
    tools.register_kennel_remember(agent)
    tools.register_kennel_recent(agent)
    tools.register_kennel_list_wings(agent)
    tools.register_kennel_stats(agent)

    recall_out = asyncio.run(agent.registered["kennel_recall"](_ctx(), "anything"))
    remember_out = asyncio.run(
        agent.registered["kennel_remember"](_ctx(), "something to write")
    )
    recent_out = asyncio.run(agent.registered["kennel_recent"](_ctx()))
    wings_out = asyncio.run(agent.registered["kennel_list_wings"](_ctx()))
    stats_out = asyncio.run(agent.registered["kennel_stats"](_ctx()))

    for out in (recall_out, remember_out, recent_out, wings_out, stats_out):
        assert out.error is not None
        assert "disabled" in out.error.lower()


def test_tools_resume_after_re_enable(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel, state, tools

    state.set_enabled(False)
    agent = _FakeAgent()
    tools.register_kennel_remember(agent)
    remember = agent.registered["kennel_remember"]

    blocked = asyncio.run(remember(_ctx(), "Will not be saved."))
    assert blocked.error is not None
    assert kennel.count_drawers() == 0

    state.set_enabled(True)
    ok = asyncio.run(remember(_ctx(), "Will be saved."))
    assert ok.error is None
    assert ok.drawer_id > 0
    assert kennel.count_drawers() == 1


# --------------------------------------------------------------------------- #
# Slash commands flip + report state
# --------------------------------------------------------------------------- #


def test_slash_status_when_enabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands

    assert commands.handle("/kennel status", "kennel") is True


def test_slash_status_when_disabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    state.set_enabled(False)
    assert commands.handle("/kennel status", "kennel") is True


def test_slash_disable_then_enable_roundtrip(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    assert state.is_enabled() is True
    assert commands.handle("/kennel disable", "kennel") is True
    assert state.is_enabled() is False
    assert commands.handle("/kennel enable", "kennel") is True
    assert state.is_enabled() is True


def test_slash_off_and_on_aliases(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    commands.handle("/kennel off", "kennel")
    assert state.is_enabled() is False
    commands.handle("/kennel on", "kennel")
    assert state.is_enabled() is True


def test_slash_enable_when_already_enabled_is_noop(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    assert state.is_enabled() is True
    assert commands.handle("/kennel enable", "kennel") is True
    assert state.is_enabled() is True  # still enabled, no flip


def test_slash_disable_when_already_disabled_is_noop(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    state.set_enabled(False)
    assert commands.handle("/kennel disable", "kennel") is True
    assert state.is_enabled() is False


# --------------------------------------------------------------------------- #
# Human inspection commands still work when disabled
# --------------------------------------------------------------------------- #


def test_stats_command_works_when_disabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, recorder, state

    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        success=True,
        response_text="something",
    )
    state.set_enabled(False)
    assert commands.handle("/kennel stats", "kennel") is True


def test_wings_command_works_when_disabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, recorder, state

    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        success=True,
        response_text="something",
    )
    state.set_enabled(False)
    assert commands.handle("/kennel wings", "kennel") is True


def test_search_command_works_when_disabled(kennel_root: Path) -> None:
    """Human-driven search bypasses the toggle — operator can always inspect."""
    from code_puppy.plugins.puppy_kennel import commands, recorder, state

    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        success=True,
        response_text="The pangolin is a scaly mammal.",
    )
    state.set_enabled(False)
    assert commands.handle("/kennel search pangolin", "kennel") is True


# --------------------------------------------------------------------------- #
# register_agent_tools advertisement honours the toggle
# --------------------------------------------------------------------------- #


def test_advertise_tools_returns_full_list_when_enabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import register_callbacks, state

    state.set_enabled(True)
    advertised = register_callbacks._advertise_tools_to_agent("code-puppy")
    assert set(advertised) == set(register_callbacks._KENNEL_TOOL_NAMES)


def test_advertise_tools_returns_empty_when_disabled(kennel_root: Path) -> None:
    """Disabled kennel must not leak its tool names into the agent's surface."""
    from code_puppy.plugins.puppy_kennel import register_callbacks, state

    state.set_enabled(False)
    assert register_callbacks._advertise_tools_to_agent("code-puppy") == []


# --------------------------------------------------------------------------- #
# Toggle commands trigger an agent reload so the tool list refreshes live
# --------------------------------------------------------------------------- #


def test_slash_disable_triggers_agent_reload(
    kennel_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from code_puppy.plugins.puppy_kennel import commands

    calls: list[str] = []

    class _StubAgent:
        def reload_code_generation_agent(self) -> None:
            calls.append("reloaded")

    import code_puppy.agents.agent_manager as agent_manager

    monkeypatch.setattr(agent_manager, "get_current_agent", lambda: _StubAgent())

    assert commands.handle("/kennel disable", "kennel") is True
    assert calls == ["reloaded"]


def test_slash_enable_triggers_agent_reload(
    kennel_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    state.set_enabled(False)
    calls: list[str] = []

    class _StubAgent:
        def reload_code_generation_agent(self) -> None:
            calls.append("reloaded")

    import code_puppy.agents.agent_manager as agent_manager

    monkeypatch.setattr(agent_manager, "get_current_agent", lambda: _StubAgent())

    assert commands.handle("/kennel enable", "kennel") is True
    assert calls == ["reloaded"]


def test_noop_toggle_does_not_reload(
    kennel_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Already-enabled + /kennel enable should NOT churn the agent."""
    from code_puppy.plugins.puppy_kennel import commands

    calls: list[str] = []

    class _StubAgent:
        def reload_code_generation_agent(self) -> None:
            calls.append("reloaded")

    import code_puppy.agents.agent_manager as agent_manager

    monkeypatch.setattr(agent_manager, "get_current_agent", lambda: _StubAgent())

    commands.handle("/kennel enable", "kennel")  # already enabled by default
    assert calls == []


def test_reload_failure_does_not_break_toggle(
    kennel_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reload errors are swallowed; the persisted toggle still flips."""
    from code_puppy.plugins.puppy_kennel import commands, state

    def _boom() -> None:
        raise RuntimeError("agent manager unavailable")

    import code_puppy.agents.agent_manager as agent_manager

    monkeypatch.setattr(agent_manager, "get_current_agent", _boom)

    assert commands.handle("/kennel disable", "kennel") is True
    assert state.is_enabled() is False
