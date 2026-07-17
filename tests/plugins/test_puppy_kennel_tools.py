"""Tests for the full puppy_kennel tool surface.

Covers ``kennel_remember``, ``kennel_recent``, ``kennel_list_wings``,
``kennel_stats``, plus the shared wing/scope resolution helpers.
The original ``kennel_recall`` tests live in ``test_puppy_kennel_phase2``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def kennel_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Throwaway kennel dir, isolated per test."""
    root = tmp_path / "kennel"
    monkeypatch.setenv("PUPPY_KENNEL_ROOT", str(root))

    import importlib

    from code_puppy.plugins.puppy_kennel import config as kennel_config
    from code_puppy.plugins.puppy_kennel import kennel as kennel_mod
    from code_puppy.plugins.puppy_kennel import state as state_mod
    from code_puppy.plugins.puppy_kennel import tools as tools_mod

    importlib.reload(kennel_config)
    importlib.reload(state_mod)
    importlib.reload(kennel_mod)
    importlib.reload(tools_mod)
    kennel_mod.initialize()
    return root


class _FakeAgent:
    """Captures @agent.tool-decorated functions for direct invocation."""

    def __init__(self) -> None:
        self.registered: dict[str, Any] = {}

    def tool(self, fn):
        self.registered[fn.__name__] = fn
        return fn


def _ctx(agent_name: str = "mist") -> Any:
    return SimpleNamespace(agent_name=agent_name, deps=None)


# --------------------------------------------------------------------------- #
# Wing/scope resolution helpers (DRY-checked)
# --------------------------------------------------------------------------- #


def test_resolve_wing_shortcuts(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    cwd = Path.cwd()
    # Phase 5: blank default now routes to repo, not agent.
    assert tools._resolve_wing("", "mist", cwd).startswith("repo:")
    assert tools._resolve_wing("repo", "mist", cwd).startswith("repo:")
    assert tools._resolve_wing("agent", "mist", cwd) == "agent:mist"
    assert tools._resolve_wing("user", "mist", cwd) == "user:default"
    assert tools._resolve_wing("custom:name", "mist", cwd) == "custom:name"


def test_resolve_scope_combinations(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    cwd = Path.cwd()
    # Explicit wing wins over scope.
    assert tools._resolve_scope("user", "repo", "a", cwd) == ["user:default"]
    # scope='all' returns empty list (no filter)
    assert tools._resolve_scope("", "all", "a", cwd) == []
    # scope='default' returns three-wing set
    assert len(tools._resolve_scope("", "default", "a", cwd)) == 3
    # scope='user' single wing
    assert tools._resolve_scope("", "user", "a", cwd) == ["user:default"]


# --------------------------------------------------------------------------- #
# kennel_remember
# --------------------------------------------------------------------------- #


def test_kennel_remember_writes_to_repo_wing_by_default(kennel_root: Path) -> None:
    """Phase 5: default wing flipped from 'agent' to 'repo'.

    Project-scoped notes are by far the most common use case for
    ``kennel_remember``, so the default should match.
    """
    from code_puppy.plugins.puppy_kennel import kennel, tools

    agent = _FakeAgent()
    tools.register_kennel_remember(agent)
    remember = agent.registered["kennel_remember"]

    out = asyncio.run(remember(_ctx(), "Quagga is an extinct subspecies of zebra."))
    assert out.error is None
    assert out.drawer_id > 0
    assert out.wing.startswith("repo:")
    assert out.room == "notes"
    assert out.bytes_stored > 0
    assert kennel.count_drawers() == 1


def test_kennel_remember_wing_shortcuts(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    agent = _FakeAgent()
    tools.register_kennel_remember(agent)
    remember = agent.registered["kennel_remember"]

    out_user = asyncio.run(
        remember(
            _ctx(), "Mike prefers vim keybindings.", wing="user", room="preferences"
        )
    )
    assert out_user.wing == "user:default"
    assert out_user.room == "preferences"

    out_repo = asyncio.run(remember(_ctx(), "Auth uses JWT.", wing="repo"))
    assert out_repo.wing.startswith("repo:")


def test_kennel_remember_explicit_wing_passes_through(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    agent = _FakeAgent()
    tools.register_kennel_remember(agent)
    remember = agent.registered["kennel_remember"]

    out = asyncio.run(remember(_ctx(), "Custom note.", wing="team:platform"))
    assert out.wing == "team:platform"


def test_kennel_remember_empty_content_returns_error(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel, tools

    agent = _FakeAgent()
    tools.register_kennel_remember(agent)
    remember = agent.registered["kennel_remember"]

    out = asyncio.run(remember(_ctx(), ""))
    assert out.error is not None
    assert out.drawer_id == 0
    assert kennel.count_drawers() == 0


def test_kennel_remember_blank_room_falls_back_to_notes(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    agent = _FakeAgent()
    tools.register_kennel_remember(agent)
    remember = agent.registered["kennel_remember"]

    out = asyncio.run(remember(_ctx(), "Hello.", room="   "))
    assert out.error is None


# --------------------------------------------------------------------------- #
# kennel_recent
# --------------------------------------------------------------------------- #


def test_kennel_recent_returns_newest_first(kennel_root: Path) -> None:
    import time

    from code_puppy.plugins.puppy_kennel import recorder, tools

    recorder.record_run_end(
        agent_name="mist",
        model_name="m",
        session_id="s1",
        success=True,
        response_text="First memory.",
    )
    time.sleep(1.01)  # Distinct timestamps (we store seconds-precision).
    recorder.record_run_end(
        agent_name="mist",
        model_name="m",
        session_id="s2",
        success=True,
        response_text="Second memory.",
    )

    agent = _FakeAgent()
    tools.register_kennel_recent(agent)
    recent = agent.registered["kennel_recent"]

    out = asyncio.run(recent(_ctx(), top_k=5))
    assert out.total == 2
    assert out.drawers[0].content == "Second memory."
    assert out.drawers[1].content == "First memory."


def test_kennel_recent_scope_user(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    agent = _FakeAgent()
    tools.register_kennel_remember(agent)
    tools.register_kennel_recent(agent)
    remember = agent.registered["kennel_remember"]
    recent = agent.registered["kennel_recent"]

    asyncio.run(remember(_ctx(), "User pref A", wing="user"))
    asyncio.run(remember(_ctx(), "User pref B", wing="user"))
    asyncio.run(remember(_ctx(), "Agent diary entry", wing="agent"))

    out = asyncio.run(recent(_ctx(), scope="user"))
    assert out.wings_searched == ["user:default"]
    assert out.total == 2
    for d in out.drawers:
        assert d.content.startswith("User pref")


def test_kennel_recent_top_k_clamped(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    agent = _FakeAgent()
    tools.register_kennel_recent(agent)
    recent = agent.registered["kennel_recent"]

    out = asyncio.run(recent(_ctx(), top_k=9999))
    assert isinstance(out.drawers, list)


def test_kennel_recent_empty_kennel(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    agent = _FakeAgent()
    tools.register_kennel_recent(agent)
    recent = agent.registered["kennel_recent"]

    out = asyncio.run(recent(_ctx()))
    assert out.total == 0
    assert out.drawers == []


# --------------------------------------------------------------------------- #
# kennel_list_wings
# --------------------------------------------------------------------------- #


def test_list_wings_empty_kennel(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    agent = _FakeAgent()
    tools.register_kennel_list_wings(agent)
    fn = agent.registered["kennel_list_wings"]

    out = asyncio.run(fn(_ctx()))
    assert out.total_wings == 0
    assert out.wings == []


def test_list_wings_with_counts(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import recorder, tools

    recorder.record_run_end(
        agent_name="mist",
        model_name="m",
        session_id="s1",
        success=True,
        response_text="hello",
    )
    agent = _FakeAgent()
    tools.register_kennel_list_wings(agent)
    fn = agent.registered["kennel_list_wings"]

    out = asyncio.run(fn(_ctx()))
    # Phase 5: single-write to repo wing only.
    assert out.total_wings == 1
    names = {w.name for w in out.wings}
    assert any(n.startswith("repo:") for n in names)
    assert "agent:mist" not in names
    for w in out.wings:
        assert w.drawer_count == 1


# --------------------------------------------------------------------------- #
# kennel_stats
# --------------------------------------------------------------------------- #


def test_kennel_stats_basic(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import recorder, tools

    recorder.record_run_end(
        agent_name="mist",
        model_name="m",
        success=True,
        response_text="x",
    )
    agent = _FakeAgent()
    tools.register_kennel_stats(agent)
    fn = agent.registered["kennel_stats"]

    out = asyncio.run(fn(_ctx()))
    assert out.error is None
    # Phase 5: single-write to repo wing only.
    assert out.total_drawers == 1
    assert out.total_wings == 1
    assert out.db_size_bytes > 0
    assert out.db_path.endswith("kennel.db")


# --------------------------------------------------------------------------- #
# register_tools_callback contract
# --------------------------------------------------------------------------- #


def test_register_tools_callback_exposes_full_surface() -> None:
    from code_puppy.plugins.puppy_kennel import tools

    specs = tools.register_tools_callback()
    names = {s["name"] for s in specs}
    assert names == {
        "kennel_recall",
        "kennel_remember",
        "kennel_recent",
        "kennel_list_wings",
        "kennel_stats",
    }
    for spec in specs:
        assert callable(spec["register_func"])
