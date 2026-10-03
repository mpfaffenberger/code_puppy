"""Tests for the core ``code_puppy.token_usage`` module.

Token accounting used to live in the ``context_indicator`` plugin
(``code_puppy_core_plugins.context_indicator.usage``). It moved to this core
module so several consumers (the ``context_indicator`` plugin, the
``statusline`` plugin, and the ``herdr`` integration) can share it without
importing across plugin boundaries.

These are the *implementation-focused* tests — they exercise the estimator,
the ``ContextUsage`` / ``OverheadBreakdown`` dataclasses, the defensive
``get_current_usage`` paths, live MCP lookup, and the kennel carve-out. They
patch private helpers on the **core** module directly.

The plugin-level rendering / slash-command tests stay in
``tests/plugins/test_context_indicator_plugin.py``. A single compatibility
test there asserts the old import path still exposes the same objects.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def _usage_module():
    return importlib.import_module("code_puppy.token_usage")


@pytest.fixture
def stub_agent_manager(monkeypatch):
    """Provide a scoped stub for ``code_puppy.agents.agent_manager``.

    The module only ever calls ``get_current_agent`` from there, so a bare
    ``MagicMock`` with that attribute is enough. ``monkeypatch.setitem``
    guarantees ``sys.modules`` is restored when the test ends — no leakage
    to siblings.
    """
    stub = MagicMock()
    stub.get_current_agent = MagicMock(side_effect=RuntimeError("unstubbed"))
    monkeypatch.setitem(sys.modules, "code_puppy.agents.agent_manager", stub)
    return stub


# ---------------------------------------------------------------------------
# pick_indicator threshold logic
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "proportion,expected_attr",
    [
        (0.0, "GREEN_CIRCLE"),
        (0.05, "GREEN_CIRCLE"),
        (0.299, "GREEN_CIRCLE"),
        (0.30, "YELLOW_CIRCLE"),
        (0.45, "YELLOW_CIRCLE"),
        (0.60, "YELLOW_CIRCLE"),
        (0.649, "YELLOW_CIRCLE"),
        (0.65, "RED_CIRCLE"),
        (0.85, "RED_CIRCLE"),
        (1.50, "RED_CIRCLE"),
    ],
)
def test_pick_indicator_buckets(proportion, expected_attr):
    mod = _usage_module()
    assert mod.pick_indicator(proportion) == getattr(mod, expected_attr)


# ---------------------------------------------------------------------------
# ContextUsage dataclass
# ---------------------------------------------------------------------------
def test_context_usage_proportion_and_percent():
    usage = _usage_module().ContextUsage(
        used_tokens=4000, overhead_tokens=1000, capacity=10000
    )
    assert usage.total_tokens == 5000
    assert usage.proportion == 0.5
    assert usage.percent == 50.0
    assert usage.indicator == _usage_module().YELLOW_CIRCLE


def test_context_usage_zero_capacity_safe():
    usage = _usage_module().ContextUsage(used_tokens=10, overhead_tokens=10, capacity=0)
    assert usage.proportion == 0.0
    assert usage.indicator == _usage_module().GREEN_CIRCLE


# ---------------------------------------------------------------------------
# get_current_usage — defensive paths
# ---------------------------------------------------------------------------
def test_get_current_usage_returns_none_when_agent_missing(stub_agent_manager):
    mod = _usage_module()
    stub_agent_manager.get_current_agent.side_effect = RuntimeError("nope")
    assert mod.get_current_usage() is None


def test_get_current_usage_returns_none_when_history_raises(stub_agent_manager):
    """If reading message history blows up we hide the indicator rather than lying."""
    mod = _usage_module()
    fake_agent = MagicMock()
    fake_agent.get_message_history.side_effect = RuntimeError("boom")
    fake_agent._get_model_context_length.return_value = 10000
    stub_agent_manager.get_current_agent.side_effect = None
    stub_agent_manager.get_current_agent.return_value = fake_agent
    assert mod.get_current_usage() is None


def test_get_current_usage_returns_none_when_overhead_raises(stub_agent_manager):
    """If the breakdown computation explodes, we hide the badge."""
    mod = _usage_module()
    fake_agent = MagicMock()
    fake_agent.get_message_history.return_value = []
    fake_agent._get_model_context_length.return_value = 10000
    stub_agent_manager.get_current_agent.side_effect = None
    stub_agent_manager.get_current_agent.return_value = fake_agent
    with patch.object(
        mod, "compute_overhead_breakdown", side_effect=RuntimeError("boom")
    ):
        assert mod.get_current_usage() is None


def test_get_current_usage_returns_none_when_capacity_zero(stub_agent_manager):
    mod = _usage_module()
    fake_agent = MagicMock()
    fake_agent.get_message_history.return_value = []
    fake_agent._get_model_context_length.return_value = 0
    stub_agent_manager.get_current_agent.side_effect = None
    stub_agent_manager.get_current_agent.return_value = fake_agent
    assert mod.get_current_usage() is None


def test_get_current_usage_computes_totals(stub_agent_manager):
    """Aggregate total shares compaction's API anchor, not a local estimator.

    Message token counts used to go through a *local* raw estimator kept
    deliberately separate from compaction's calibrated one. Both now share
    ``context_accounting.context_tokens`` (see the module docstring), so we
    build a real anchored history -- the same construction the compaction
    and model-switching tests use -- rather than length-counting MagicMocks.
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.usage import RequestUsage

    from code_puppy.context_accounting import record_anchor

    mod = _usage_module()

    prefix = [ModelRequest(parts=[UserPromptPart("hello")])]
    response = ModelResponse(
        parts=[TextPart("reply")],
        model_name="model",
        usage=RequestUsage(input_tokens=3000, output_tokens=5),
    )
    record_anchor(prefix, response, context_overhead=0)
    fake_messages = [*prefix, response]

    fake_agent = MagicMock()
    fake_agent.cur_model = TestModel(model_name="model")
    fake_agent.get_message_history.return_value = fake_messages
    fake_agent._get_model_context_length.return_value = 10000
    fake_agent._estimate_context_overhead.return_value = 0
    stub_agent_manager.get_current_agent.side_effect = None
    stub_agent_manager.get_current_agent.return_value = fake_agent

    fake_breakdown = mod.OverheadBreakdown(
        system_prompt_tokens=300,
        agents_md_tokens=150,
        pydantic_tools_tokens=50,
        mcp_tokens=0,
    )
    with patch.object(mod, "compute_overhead_breakdown", return_value=fake_breakdown):
        usage = mod.get_current_usage()

    assert usage is not None
    # Anchored total: input_tokens (3000) + replayed output usage (5, the
    # response is plain text so output_tokens is used directly) + overhead
    # delta (0 - 0) + nothing after the anchor == 3005.
    assert usage.total_tokens == 3005
    assert usage.used_tokens == 3005 - 500
    assert usage.overhead_tokens == 500
    assert usage.system_prompt_tokens == 300
    assert usage.agents_md_tokens == 150
    assert usage.pydantic_tools_tokens == 50
    assert usage.mcp_tokens == 0
    assert usage.capacity == 10000
    assert usage.indicator == mod.YELLOW_CIRCLE  # (3005 + 500) / 10000 = 35%


# ---------------------------------------------------------------------------
# Live MCP server lookup
# ---------------------------------------------------------------------------
def test_live_mcp_servers_for_uses_fresh_manager_state(monkeypatch):
    """Live MCP lookup bypasses ``agent._mcp_servers`` so bind/unbind take
    effect immediately in ``/context``.

    We stub the manager to return a sentinel list and ensure the helper
    prefers it over the (stale) cached list on the agent.
    """
    mod = _usage_module()
    fresh_servers = [MagicMock(name="fresh-server")]
    fake_manager = MagicMock()
    fake_manager.get_servers_for_agent.return_value = fresh_servers

    fake_mcp_module = MagicMock()
    fake_mcp_module.get_mcp_manager = MagicMock(return_value=fake_manager)
    monkeypatch.setitem(sys.modules, "code_puppy.mcp_", fake_mcp_module)

    fake_config = MagicMock()
    fake_config.get_value = MagicMock(return_value=None)
    monkeypatch.setitem(sys.modules, "code_puppy.config", fake_config)

    fake_agent = MagicMock()
    fake_agent.name = "some-agent"
    # The cached list is intentionally a stale stand-in — we shouldn't pick it.
    fake_agent._mcp_servers = [MagicMock(name="stale-server")]

    result = mod._live_mcp_servers_for(fake_agent)
    assert result is fresh_servers
    fake_manager.get_servers_for_agent.assert_called_once_with(agent_name="some-agent")


def test_live_mcp_servers_for_respects_disable_flag(monkeypatch):
    """When MCP is disabled globally we return ``None`` and don't poke the manager."""
    mod = _usage_module()
    fake_manager = MagicMock()
    fake_mcp_module = MagicMock()
    fake_mcp_module.get_mcp_manager = MagicMock(return_value=fake_manager)
    monkeypatch.setitem(sys.modules, "code_puppy.mcp_", fake_mcp_module)

    fake_config = MagicMock()
    fake_config.get_value = MagicMock(return_value="true")
    monkeypatch.setitem(sys.modules, "code_puppy.config", fake_config)

    fake_agent = MagicMock()
    fake_agent.name = "some-agent"
    fake_agent._mcp_servers = []

    assert mod._live_mcp_servers_for(fake_agent) is None
    fake_manager.get_servers_for_agent.assert_not_called()


def test_live_mcp_servers_for_falls_back_to_cached_on_error(monkeypatch):
    mod = _usage_module()
    fake_mcp_module = MagicMock()
    fake_mcp_module.get_mcp_manager = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "code_puppy.mcp_", fake_mcp_module)
    monkeypatch.setitem(
        sys.modules,
        "code_puppy.config",
        MagicMock(get_value=MagicMock(return_value=None)),
    )

    cached = [MagicMock(name="cached")]
    fake_agent = MagicMock()
    fake_agent.name = "some-agent"
    fake_agent._mcp_servers = cached

    assert mod._live_mcp_servers_for(fake_agent) is cached


# ---------------------------------------------------------------------------
# Kennel memory carve-out
# ---------------------------------------------------------------------------
def test_overhead_breakdown_carves_kennel_memory_out_of_system_prompt():
    """Kennel memory tokens are subtracted from the system prompt bucket.

    The resolved system prompt already contains the kennel recall block
    (because ``load_prompt`` callbacks are folded into it at assembly
    time). To avoid double-counting we report ``system_prompt = resolved
    - kennel`` and surface ``kennel_memory`` as its own additive bucket.
    """
    mod = _usage_module()

    # Pick lengths whose raw-token counts (len // 2.5) are easy to reason
    # about: 1000 chars -> 400 tokens; 250 chars -> 100 tokens.
    resolved_prompt = "S" * 1000
    kennel_block = "P" * 250

    fake_agent = MagicMock()
    with (
        patch.object(mod, "_resolved_system_prompt", return_value=resolved_prompt),
        patch.object(mod, "_kennel_memory_block", return_value=kennel_block),
        patch("code_puppy.agents._builder.load_puppy_rules", return_value=""),
        patch.object(mod, "_agent_tools", return_value=None),
        patch.object(mod, "_live_mcp_servers_for", return_value=None),
    ):
        breakdown = mod.compute_overhead_breakdown(fake_agent)

    assert breakdown.kennel_memory_tokens == 100
    # 400 (raw resolved) - 100 (kennel) == 300 tokens left in system prompt.
    assert breakdown.system_prompt_tokens == 300
    # Carve-out preserves additive total.
    assert breakdown.total == 400


def test_overhead_breakdown_kennel_zero_when_block_empty():
    """No kennel plugin / empty recall block -> bucket is zero, system prompt unchanged."""
    mod = _usage_module()
    resolved_prompt = "S" * 1000  # 400 raw tokens

    fake_agent = MagicMock()
    with (
        patch.object(mod, "_resolved_system_prompt", return_value=resolved_prompt),
        patch.object(mod, "_kennel_memory_block", return_value=""),
        patch("code_puppy.agents._builder.load_puppy_rules", return_value=""),
        patch.object(mod, "_agent_tools", return_value=None),
        patch.object(mod, "_live_mcp_servers_for", return_value=None),
    ):
        breakdown = mod.compute_overhead_breakdown(fake_agent)

    assert breakdown.kennel_memory_tokens == 0
    assert breakdown.system_prompt_tokens == 400
    assert breakdown.total == 400


def test_overhead_breakdown_kennel_clamps_when_block_larger_than_resolved():
    """Defensive: kennel bigger than resolved prompt clamps system_prompt to 0.

    Should never happen in practice (the kennel block is part of the
    resolved prompt), but guard against custom agents that override
    ``get_system_prompt`` and skip ``on_load_prompt``.
    """
    mod = _usage_module()
    resolved_prompt = "S" * 100  # 40 raw tokens
    kennel_block = "P" * 1000  # 400 raw tokens

    fake_agent = MagicMock()
    with (
        patch.object(mod, "_resolved_system_prompt", return_value=resolved_prompt),
        patch.object(mod, "_kennel_memory_block", return_value=kennel_block),
        patch("code_puppy.agents._builder.load_puppy_rules", return_value=""),
        patch.object(mod, "_agent_tools", return_value=None),
        patch.object(mod, "_live_mcp_servers_for", return_value=None),
    ):
        breakdown = mod.compute_overhead_breakdown(fake_agent)

    assert breakdown.system_prompt_tokens == 0
    assert breakdown.kennel_memory_tokens == 400


def test_kennel_memory_block_swallows_provider_exceptions(monkeypatch):
    """Provider blowups must never break /context."""
    mod = _usage_module()

    def _boom():
        raise RuntimeError("db on fire")

    monkeypatch.setattr(
        "code_puppy.kennel_provider.get_kennel_memory_provider",
        lambda: _boom,
    )
    assert mod._kennel_memory_block() == ""


def test_kennel_memory_block_returns_empty_when_no_provider(monkeypatch):
    """Kennel plugin not registered -> empty string, no exception."""
    mod = _usage_module()
    monkeypatch.setattr(
        "code_puppy.kennel_provider.get_kennel_memory_provider",
        lambda: None,
    )
    assert mod._kennel_memory_block() == ""
