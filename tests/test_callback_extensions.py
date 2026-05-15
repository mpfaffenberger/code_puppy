"""Tests for the Phase-1 callback extensions in ``code_puppy.callbacks``.

Covers four new hook phases added for the DBOS-extraction refactor:

* ``wrap_pydantic_agent``       — sync, last-non-None wins
* ``agent_run_context``         — sync, returns list of async CMs
* ``agent_run_cancel``          — async dispatch
* ``should_skip_fallback_render`` — sync, any-True wins
"""

import asyncio
from contextlib import asynccontextmanager

import pytest

from code_puppy.callbacks import (
    clear_callbacks,
    on_agent_run_cancel,
    on_agent_run_context,
    on_should_skip_fallback_render,
    on_wrap_pydantic_agent,
    register_callback,
)


class TestWrapPydanticAgent:
    def setup_method(self):
        clear_callbacks()

    def teardown_method(self):
        clear_callbacks()

    def test_no_callbacks_returns_input(self):
        agent = object()
        pyd = object()
        assert on_wrap_pydantic_agent(agent, pyd) is pyd

    def test_last_non_none_wins(self):
        sentinel = object()

        def first(agent, pyd, **kwargs):
            return None

        def second(agent, pyd, **kwargs):
            return sentinel

        register_callback("wrap_pydantic_agent", first)
        register_callback("wrap_pydantic_agent", second)

        result = on_wrap_pydantic_agent(object(), object())
        assert result is sentinel

    def test_kwargs_are_forwarded(self):
        captured = {}

        def cb(
            agent, pyd, *, event_stream_handler=None, message_group=None, kind="main"
        ):
            captured["esh"] = event_stream_handler
            captured["mg"] = message_group
            captured["kind"] = kind
            return None

        register_callback("wrap_pydantic_agent", cb)
        on_wrap_pydantic_agent(
            object(),
            object(),
            event_stream_handler="esh",
            message_group="mg",
            kind="subagent",
        )
        assert captured == {"esh": "esh", "mg": "mg", "kind": "subagent"}


class TestAgentRunContext:
    def setup_method(self):
        clear_callbacks()

    def teardown_method(self):
        clear_callbacks()

    def test_empty_when_no_callbacks(self):
        assert on_agent_run_context(object(), object(), "gid", []) == []

    def test_collects_async_cms_and_skips_none(self):
        @asynccontextmanager
        async def my_cm():
            yield "in"

        cm_instance = my_cm()

        def returns_cm(agent, pyd, group_id, mcp_servers):
            return cm_instance

        def returns_none(agent, pyd, group_id, mcp_servers):
            return None

        register_callback("agent_run_context", returns_cm)
        register_callback("agent_run_context", returns_none)

        result = on_agent_run_context(object(), object(), "gid-123", [])
        assert result == [cm_instance]

        # Sanity check: it really is an async CM.
        async def _enter():
            async with cm_instance as v:
                return v

        assert asyncio.run(_enter()) == "in"


class TestAgentRunCancel:
    def setup_method(self):
        clear_callbacks()

    def teardown_method(self):
        clear_callbacks()

    def test_async_dispatch_sync_callback(self):
        seen = []

        def cb(group_id):
            seen.append(group_id)
            return "sync-ok"

        register_callback("agent_run_cancel", cb)
        results = asyncio.run(on_agent_run_cancel("gid-1"))
        assert seen == ["gid-1"]
        assert results == ["sync-ok"]

    def test_async_dispatch_async_callback(self):
        seen = []

        async def cb(group_id):
            seen.append(group_id)
            return "async-ok"

        register_callback("agent_run_cancel", cb)
        results = asyncio.run(on_agent_run_cancel("gid-2"))
        assert seen == ["gid-2"]
        assert results == ["async-ok"]


class TestShouldSkipFallbackRender:
    def setup_method(self):
        clear_callbacks()

    def teardown_method(self):
        clear_callbacks()

    def test_no_callbacks_returns_false(self):
        assert on_should_skip_fallback_render(object()) is False

    def test_all_none_returns_false(self):
        register_callback("should_skip_fallback_render", lambda agent: None)
        register_callback("should_skip_fallback_render", lambda agent: None)
        assert on_should_skip_fallback_render(object()) is False

    def test_any_true_returns_true(self):
        register_callback("should_skip_fallback_render", lambda agent: None)
        register_callback("should_skip_fallback_render", lambda agent: False)
        register_callback("should_skip_fallback_render", lambda agent: True)
        assert on_should_skip_fallback_render(object()) is True

    def test_only_false_returns_false(self):
        register_callback("should_skip_fallback_render", lambda agent: False)
        assert on_should_skip_fallback_render(object()) is False


# Standalone pytest-style sanity check for callbacks present in registry.
def test_new_phases_registered():
    from code_puppy.callbacks import _callbacks

    for phase in (
        "wrap_pydantic_agent",
        "agent_run_context",
        "agent_run_cancel",
        "should_skip_fallback_render",
    ):
        assert phase in _callbacks, f"Phase {phase!r} missing from _callbacks"


# Guard: registering an unknown phase still raises.
def test_unknown_phase_still_rejected():
    with pytest.raises(ValueError):
        register_callback("definitely_not_a_phase", lambda: None)  # type: ignore[arg-type]
