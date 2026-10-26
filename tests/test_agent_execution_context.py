"""Tests for async-safe executing-agent attribution."""

from __future__ import annotations

import asyncio

import pytest

from code_puppy.agent_execution_context import (
    executing_agent_context,
    get_executing_agent,
    get_execution_output_type,
)


def test_context_defaults_to_none_and_restores_nested_values():
    outer = object()
    inner = object()

    assert get_executing_agent() is None
    assert get_execution_output_type() is str
    with executing_agent_context(outer, output_type=dict):
        assert get_executing_agent() is outer
        assert get_execution_output_type() is dict
        with executing_agent_context(inner):
            assert get_executing_agent() is inner
            assert get_execution_output_type() is str
        assert get_executing_agent() is outer
        assert get_execution_output_type() is dict
    assert get_executing_agent() is None
    assert get_execution_output_type() is str


@pytest.mark.asyncio
async def test_context_is_isolated_between_concurrent_tasks():
    first = object()
    second = object()
    both_started = asyncio.Event()
    started = 0

    async def observe(agent, output_type):
        nonlocal started
        with executing_agent_context(agent, output_type=output_type):
            started += 1
            if started == 2:
                both_started.set()
            await both_started.wait()
            await asyncio.sleep(0)
            return get_executing_agent(), get_execution_output_type()

    observed = await asyncio.gather(observe(first, dict), observe(second, list))

    assert observed == [(first, dict), (second, list)]
    assert get_executing_agent() is None
    assert get_execution_output_type() is str


def test_output_contract_restored_after_exception():
    with pytest.raises(RuntimeError, match="offline failure"):
        with executing_agent_context(object(), output_type=dict):
            raise RuntimeError("offline failure")
    assert get_executing_agent() is None
    assert get_execution_output_type() is str
