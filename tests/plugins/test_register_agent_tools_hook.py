"""Tests for the new ``register_agent_tools`` core callback hook.

Covers:
* the hook exists and accepts callbacks
* ``on_register_agent_tools`` returns a flat, deduplicated list
* the hook receives the ``agent_name`` argument so plugins can scope
* ``register_tools_for_agent`` unions plugin extras into the agent's list
* ``None`` results from a callback are tolerated (skipped)
"""

from __future__ import annotations

import pytest

from code_puppy import callbacks


@pytest.fixture(autouse=True)
def _clear_register_agent_tools_callbacks():
    """Snapshot + restore the hook's callback list so tests don't leak."""
    saved = list(callbacks._callbacks.get("register_agent_tools", []))
    callbacks._callbacks["register_agent_tools"] = []
    try:
        yield
    finally:
        callbacks._callbacks["register_agent_tools"] = saved


def test_phase_registered_in_callbacks() -> None:
    """The new hook must appear in the central callbacks registry."""
    assert "register_agent_tools" in callbacks._callbacks


def test_on_register_agent_tools_empty() -> None:
    assert callbacks.on_register_agent_tools() == []
    assert callbacks.on_register_agent_tools("mist") == []


def test_on_register_agent_tools_collects_and_dedupes() -> None:
    callbacks.register_callback("register_agent_tools", lambda agent_name: ["a", "b"])
    callbacks.register_callback("register_agent_tools", lambda agent_name: ["b", "c"])

    result = callbacks.on_register_agent_tools("any-agent")
    assert result == ["a", "b", "c"]


def test_on_register_agent_tools_passes_agent_name_through() -> None:
    seen: list[str | None] = []

    def cb(agent_name):
        seen.append(agent_name)
        return ["x"]

    callbacks.register_callback("register_agent_tools", cb)
    callbacks.on_register_agent_tools("wiggum")
    callbacks.on_register_agent_tools("mist")
    callbacks.on_register_agent_tools(None)

    assert seen == ["wiggum", "mist", None]


def test_on_register_agent_tools_supports_per_agent_scoping() -> None:
    """Plugins can return different tools per agent."""

    def cb(agent_name):
        if agent_name == "mist":
            return ["only_for_puppy"]
        if agent_name == "wiggum":
            return ["only_for_wiggum"]
        return []

    callbacks.register_callback("register_agent_tools", cb)
    assert callbacks.on_register_agent_tools("mist") == ["only_for_puppy"]
    assert callbacks.on_register_agent_tools("wiggum") == ["only_for_wiggum"]
    assert callbacks.on_register_agent_tools("nobody") == []


def test_on_register_agent_tools_tolerates_none() -> None:
    callbacks.register_callback("register_agent_tools", lambda agent_name: None)
    callbacks.register_callback("register_agent_tools", lambda agent_name: ["kept"])
    assert callbacks.on_register_agent_tools() == ["kept"]


def test_on_register_agent_tools_filters_non_strings() -> None:
    callbacks.register_callback(
        "register_agent_tools", lambda agent_name: ["valid", 42, None, "", "also_valid"]
    )
    assert callbacks.on_register_agent_tools() == ["valid", "also_valid"]


def test_register_tools_for_agent_unions_plugin_extras() -> None:
    """End-to-end: a plugin advertising a tool sees it on the agent."""
    from code_puppy.tools import TOOL_REGISTRY, register_tools_for_agent

    # Register a fake tool in the registry the way a plugin would.
    registered_targets: list[object] = []

    def fake_register_func(agent):
        registered_targets.append(agent)

    TOOL_REGISTRY["test_plugin_tool"] = fake_register_func
    try:
        callbacks.register_callback(
            "register_agent_tools", lambda agent_name: ["test_plugin_tool"]
        )

        class FakeAgent:
            def __init__(self):
                self._tools: dict = {}

        agent = FakeAgent()
        # Agent's hardcoded list is empty — the only way the tool ends up
        # registered is via the new hook.
        register_tools_for_agent(agent, [], agent_name="test-agent")
        assert registered_targets == [agent]
    finally:
        TOOL_REGISTRY.pop("test_plugin_tool", None)


def test_register_tools_for_agent_dedupes_hardcoded_and_extras() -> None:
    """If the agent already lists the tool, the hook shouldn't double-register."""
    from code_puppy.tools import TOOL_REGISTRY, register_tools_for_agent

    call_count = {"n": 0}

    def fake_register_func(agent):
        call_count["n"] += 1

    TOOL_REGISTRY["double_tool"] = fake_register_func
    try:
        callbacks.register_callback(
            "register_agent_tools", lambda agent_name: ["double_tool"]
        )

        class FakeAgent:
            def __init__(self):
                self._tools: dict = {}

        register_tools_for_agent(FakeAgent(), ["double_tool"], agent_name="x")
        assert call_count["n"] == 1
    finally:
        TOOL_REGISTRY.pop("double_tool", None)
