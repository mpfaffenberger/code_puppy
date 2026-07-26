"""Tests for the timestamp_heartbeat plugin."""

from __future__ import annotations

import asyncio
import re

import pytest

from code_puppy.plugins.timestamp_heartbeat import register_callbacks as hb


@pytest.fixture(autouse=True)
def _reset_state():
    hb._reset_state()
    yield
    hb._reset_state()


@pytest.fixture
def interval_3(monkeypatch):
    monkeypatch.setattr(hb, "_get_interval", lambda: 3)


def _call(result):
    hb._on_post_tool_call("some_tool", {}, result, 1.0)
    return result


# ---------------------------------------------------------------------------
# Core counting behaviour
# ---------------------------------------------------------------------------
def test_stamps_every_kth_call(interval_3):
    results = [_call({}) for _ in range(6)]
    stamped = [i for i, r in enumerate(results) if hb.TIMESTAMP_KEY in r]
    assert stamped == [2, 5]  # calls 3 and 6 (0-indexed)


def test_stamp_value_is_isoformat_with_offset(interval_3):
    for _ in range(2):
        _call({})
    result = _call({})
    stamp = result[hb.TIMESTAMP_KEY]
    # e.g. 2025-05-17T14:03:22-07:00 or ...+00:00
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$", stamp)


def test_non_dict_result_defers_stamp_to_next_dict(interval_3):
    _call({})
    _call({})
    _call("plain string result")  # k-th call, unstampable — stamp goes due
    result = _call({})  # next dict gets the deferred stamp
    assert hb.TIMESTAMP_KEY in result


def test_deferred_stamp_only_lands_once(interval_3):
    for _ in range(3):
        _call("nope")
    first = _call({})
    second = _call({})
    assert hb.TIMESTAMP_KEY in first
    assert hb.TIMESTAMP_KEY not in second


def test_never_raises_on_weird_results(interval_3):
    for weird in (None, 42, object(), ["list"], "str"):
        hb._on_post_tool_call("t", {}, weird, 0.0)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def test_interval_zero_disables(monkeypatch):
    monkeypatch.setattr(hb, "_get_interval", lambda: 0)
    for _ in range(50):
        result = _call({})
        assert hb.TIMESTAMP_KEY not in result


def test_get_interval_default_when_unset(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: None)
    assert hb._get_interval() == hb.DEFAULT_INTERVAL


def test_get_interval_parses_config(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: " 7 ")
    assert hb._get_interval() == 7


def test_get_interval_garbage_falls_back(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: "banana")
    assert hb._get_interval() == hb.DEFAULT_INTERVAL


# ---------------------------------------------------------------------------
# The load-bearing CPython semantics: `return result` inside `try` snapshots a
# REFERENCE, so an in-place mutation from the `finally`-awaited post_tool_call
# hook is visible to the caller. This mirrors pydantic_patches._patched_call_tool.
# ---------------------------------------------------------------------------
def test_finally_mutation_reaches_caller(interval_3):
    async def fake_call_tool():
        result = {"content": "tool output"}
        try:
            return result
        finally:
            hb._on_post_tool_call("t", {}, result, 1.0)

    async def scenario():
        outputs = [await fake_call_tool() for _ in range(3)]
        return outputs

    outputs = asyncio.run(scenario())
    assert hb.TIMESTAMP_KEY not in outputs[0]
    assert hb.TIMESTAMP_KEY not in outputs[1]
    assert hb.TIMESTAMP_KEY in outputs[2]


def test_callback_is_registered():
    from code_puppy.callbacks import get_callbacks

    assert hb._on_post_tool_call in get_callbacks("post_tool_call")
