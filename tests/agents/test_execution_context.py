"""Tests for async-safe executing-agent attribution."""

from __future__ import annotations

import asyncio

import pytest

from code_puppy.agent_execution_context import (
    executing_agent_context,
    get_executing_agent,
)


def test_context_defaults_to_none_and_restores_nested_values():
    outer = object()
    inner = object()

    assert get_executing_agent() is None
    with executing_agent_context(outer):
        assert get_executing_agent() is outer
        with executing_agent_context(inner):
            assert get_executing_agent() is inner
        assert get_executing_agent() is outer
    assert get_executing_agent() is None


@pytest.mark.asyncio
async def test_context_is_isolated_between_concurrent_tasks():
    first = object()
    second = object()
    both_started = asyncio.Event()
    started = 0

    async def observe(agent):
        nonlocal started
        with executing_agent_context(agent):
            started += 1
            if started == 2:
                both_started.set()
            await both_started.wait()
            await asyncio.sleep(0)
            return get_executing_agent()

    observed = await asyncio.gather(observe(first), observe(second))

    assert observed == [first, second]
    assert get_executing_agent() is None
