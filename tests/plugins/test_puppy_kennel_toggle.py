"""Tests for the runtime enable/disable toggle.

Covers:
* default state is disabled (opt-in)
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
    # ``PUPPY_KENNEL_ROOT`` only sets the SQLite DB location, NOT the on/off
    # toggle (that lives in puppy.cfg, isolated by tests/conftest.py).
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
    state.set_enabled(True)
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


def test_default_is_disabled(kennel_root: Path) -> None:
    """Fresh installs start with the kennel off — memory is opt-in."""
    from code_puppy.plugins.puppy_kennel import state

    assert state.is_enabled() is False


def test_slash_status_when_enabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    state.set_enabled(True)
    assert commands.handle("/kennel status", "kennel") is True


def test_slash_status_when_disabled(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    state.set_enabled(False)
    assert commands.handle("/kennel status", "kennel") is True


def test_slash_disable_then_enable_roundtrip(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    state.set_enabled(True)
    assert state.is_enabled() is True
    assert commands.handle("/kennel disable", "kennel") is True
    assert state.is_enabled() is False
    assert commands.handle("/kennel enable", "kennel") is True
    assert state.is_enabled() is True


def test_slash_off_and_on_aliases(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    state.set_enabled(True)
    assert state.is_enabled() is True
    commands.handle("/kennel off", "kennel")
    assert state.is_enabled() is False
    commands.handle("/kennel on", "kennel")
    assert state.is_enabled() is True


def test_slash_enable_when_already_enabled_is_noop(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import commands, state

    state.set_enabled(True)
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


@pytest.mark.parametrize(
    "command, initial_enabled, reload_raises, expected_calls, final_enabled",
    [
        # Disabling reloads the live agent so the tool list refreshes.
        ("/kennel disable", True, False, ["reloaded"], False),
        # Re-enabling reloads the live agent.
        ("/kennel enable", False, False, ["reloaded"], True),
        # Already-enabled + enable is a no-op that must NOT churn the agent.
        ("/kennel enable", True, False, [], True),
        # Reload errors are swallowed; the persisted toggle still flips.
        ("/kennel disable", True, True, [], False),
    ],
    ids=[
        "disable_reloads",
        "enable_reloads",
        "noop_no_reload",
        "reload_error_still_flips",
    ],
)
def test_toggle_reload_behavior(
    kennel_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    initial_enabled: bool,
    reload_raises: bool,
    expected_calls: list[str],
    final_enabled: bool,
) -> None:
    """Toggle commands trigger a live agent reload so tools refresh; reload
    failures are swallowed without blocking the toggle flip."""
    from code_puppy.plugins.puppy_kennel import commands, state

    state.set_enabled(initial_enabled)
    calls: list[str] = []

    import code_puppy.agents.agent_manager as agent_manager

    if reload_raises:

        def _boom() -> None:
            raise RuntimeError("agent manager unavailable")

        monkeypatch.setattr(agent_manager, "get_current_agent", _boom)
    else:

        class _StubAgent:
            def reload_code_generation_agent(self) -> None:
                calls.append("reloaded")

        monkeypatch.setattr(agent_manager, "get_current_agent", lambda: _StubAgent())

    assert commands.handle(command, "kennel") is True
    assert calls == expected_calls
    assert state.is_enabled() is final_enabled
