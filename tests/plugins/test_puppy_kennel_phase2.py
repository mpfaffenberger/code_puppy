"""Phase 2 tests: multi-wing search, kennel_recall tool, /kennel commands."""

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

    importlib.reload(kennel_config)
    importlib.reload(state_mod)
    importlib.reload(kennel_mod)
    kennel_mod.initialize()
    # Storage/search tests operate on an enabled kennel; the default-off
    # behavior is covered by test_puppy_kennel_toggle.
    state_mod.set_enabled(True)
    return root


# --------------------------------------------------------------------------- #
# Multi-wing search + dedup
# --------------------------------------------------------------------------- #


def test_search_drawers_multi_dedupes_same_content(kennel_root: Path) -> None:
    """Multi-wing search dedupes by content even when the same text appears
    in more than one wing (e.g. autosaved in repo, then echoed via
    ``kennel_remember`` into another wing).
    """
    from code_puppy.plugins.puppy_kennel import kennel, recorder, wings

    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        session_id="s1",
        success=True,
        response_text="Distinctive verbatim text about porcupines.",
    )
    repo_w = wings.repo_wing()
    agent_w = wings.agent_wing("code-puppy")
    # Echo the same content into the agent wing via the storage layer,
    # mimicking what an explicit ``kennel_remember(wing="agent")`` would do.
    agent_wing_id = kennel.ensure_wing(agent_w)
    agent_room_id = kennel.ensure_room(agent_wing_id, "notes")
    kennel.add_drawer(
        agent_room_id,
        content="Distinctive verbatim text about porcupines.",
        role="note",
        session_id="s1",
        metadata={"agent": "code-puppy"},
    )
    # Sanity: same content now lives in both wings.
    assert kennel.count_drawers() == 2

    # Multi-wing search across BOTH wings must dedupe to ONE result.
    hits = kennel.search_drawers_multi(
        "porcupines", wing_names=[repo_w, agent_w], limit=5
    )
    assert len(hits) == 1
    assert "porcupines" in hits[0].content.lower()


def test_search_drawers_multi_all_wings_when_none(kennel_root: Path) -> None:
    """Passing None for wings = search every wing."""
    from code_puppy.plugins.puppy_kennel import kennel, recorder

    recorder.record_run_end(
        agent_name="agent-a",
        model_name="m",
        success=True,
        response_text="Whales communicate via ultrasound.",
    )
    hits = kennel.search_drawers_multi("whales", wing_names=None, limit=5)
    assert len(hits) == 1


def test_search_drawers_multi_empty_query(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import kennel

    assert kennel.search_drawers_multi("", wing_names=None) == []
    assert kennel.search_drawers_multi("   ", wing_names=None) == []


# --------------------------------------------------------------------------- #
# kennel_recall tool
# --------------------------------------------------------------------------- #


class _FakeAgent:
    """Minimal stand-in for a pydantic_ai Agent — captures the tool fn."""

    def __init__(self) -> None:
        self.registered: dict[str, Any] = {}

    def tool(self, fn):  # mimics @agent.tool
        self.registered[fn.__name__] = fn
        return fn


def _make_context(agent_name: str = "code-puppy") -> Any:
    return SimpleNamespace(agent_name=agent_name, deps=None)


def test_kennel_recall_returns_hits(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import recorder, tools

    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        session_id="s1",
        success=True,
        response_text="The dingo ate my SQL homework yesterday.",
    )
    agent = _FakeAgent()
    tools.register_kennel_recall(agent)
    recall = agent.registered["kennel_recall"]

    out = asyncio.run(recall(_make_context(), "dingo homework"))
    assert out.total_hits >= 1
    assert any("dingo" in d.content.lower() for d in out.drawers)


def test_kennel_recall_empty_query_returns_error(kennel_root: Path) -> None:
    from code_puppy.plugins.puppy_kennel import tools

    agent = _FakeAgent()
    tools.register_kennel_recall(agent)
    recall = agent.registered["kennel_recall"]

    out = asyncio.run(recall(_make_context(), ""))
    assert out.error is not None
    assert out.total_hits == 0


def test_kennel_recall_scope_repo_only(kennel_root: Path) -> None:
    """scope='repo' should restrict to the repo wing."""
    from code_puppy.plugins.puppy_kennel import recorder, tools

    # Autosaved content lives in the repo wing now (no dual-write).
    recorder.record_run_end(
        agent_name="code-puppy",
        model_name="m",
        session_id="s1",
        success=True,
        response_text="Aardvarks are nocturnal.",
    )
    agent = _FakeAgent()
    tools.register_kennel_recall(agent)
    recall = agent.registered["kennel_recall"]

    out = asyncio.run(recall(_make_context(), "aardvarks", scope="repo"))
    assert len(out.wings_searched) == 1
    assert out.wings_searched[0].startswith("repo:")
    assert out.total_hits >= 1


def test_register_tools_callback_shape() -> None:
    """The callback contract: list of dicts with name + register_func.

    The full surface assertion lives in test_puppy_kennel_tools; this one
    just sanity-checks that kennel_recall is in the set.
    """
    from code_puppy.plugins.puppy_kennel import tools

    result = tools.register_tools_callback()
    assert isinstance(result, list) and len(result) >= 1
    names = {s["name"] for s in result}
    assert "kennel_recall" in names
    for spec in result:
        assert callable(spec["register_func"])


# --------------------------------------------------------------------------- #
# /kennel slash commands
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "cmd, name, record_text, expected",
    [
        ("/notkennel", "notkennel", None, None),
        ("/kennel help", "kennel", None, True),
        ("/kennel ?", "kennel", None, True),
        ("/kennel wings", "kennel", "Some wisdom.", True),
        ("/kennel wings", "kennel", None, True),
        ("/kennel stats", "kennel", None, True),
        ("/kennel search", "kennel", None, True),
        (
            "/kennel search octopi",
            "kennel",
            "Octopi have nine brains, technically.",
            True,
        ),
        ("/kennel", "kennel", None, True),
        # Should not return None — we own /kennel, we handle it.
        ("/kennel bogus", "kennel", None, True),
    ],
    ids=[
        "ignores_other_names",
        "help",
        "question_mark",
        "wings_with_data",
        "wings_empty",
        "stats",
        "search_no_query",
        "search_with_hits",
        "default_overview",
        "unknown_subcommand",
    ],
)
def test_kennel_commands(
    kennel_root: Path, cmd: str, name: str, record_text: str | None, expected
) -> None:
    from code_puppy.plugins.puppy_kennel import commands, recorder

    if record_text:
        recorder.record_run_end(
            agent_name="code-puppy",
            model_name="m",
            success=True,
            response_text=record_text,
        )
    assert commands.handle(cmd, name) is expected


def test_help_entries_advertised() -> None:
    from code_puppy.plugins.puppy_kennel import commands

    entries = commands.help_entries()
    assert any(name == "kennel" for name, _desc in entries)
