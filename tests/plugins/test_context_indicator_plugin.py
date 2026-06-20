"""Tests for the context_indicator plugin.

Important: we do **not** permanently inject a stub for
``code_puppy.agents.agent_manager`` into ``sys.modules``. Doing so at import
time would leak the MagicMock to every other test that imports the real
``agent_manager`` afterwards, causing order-dependent failures.

Instead, the ``stub_agent_manager`` fixture below uses ``monkeypatch`` so the
stub is automatically torn down after the test. Tests that don't actually
exercise ``get_current_agent`` don't take the fixture at all.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def _plugin_module():
    return importlib.import_module(
        "code_puppy.plugins.context_indicator.register_callbacks"
    )


def _usage_module():
    return importlib.import_module("code_puppy.plugins.context_indicator.usage")


@pytest.fixture
def stub_agent_manager(monkeypatch):
    """Provide a scoped stub for ``code_puppy.agents.agent_manager``.

    The plugin only ever calls ``get_current_agent`` from that module, so a
    bare ``MagicMock`` with that attribute is enough. ``monkeypatch.setitem``
    guarantees ``sys.modules`` is restored to its previous state when the
    test ends — no leakage to siblings.
    """
    stub = MagicMock()
    stub.get_current_agent = MagicMock(side_effect=RuntimeError("unstubbed"))
    monkeypatch.setitem(sys.modules, "code_puppy.agents.agent_manager", stub)
    return stub


# ---------------------------------------------------------------------------
# pick_indicator threshold logic
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "proportion,expected",
    [
        (0.0, "🟢"),
        (0.05, "🟢"),
        (0.299, "🟢"),
        (0.30, "🟡"),
        (0.45, "🟡"),
        (0.60, "🟡"),
        (0.649, "🟡"),
        (0.65, "🔴"),
        (0.85, "🔴"),
        (1.50, "🔴"),
    ],
)
def test_pick_indicator_buckets(proportion, expected):
    assert _usage_module().pick_indicator(proportion) == expected


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
    assert usage.indicator == "🟡"


def test_context_usage_zero_capacity_safe():
    usage = _usage_module().ContextUsage(used_tokens=10, overhead_tokens=10, capacity=0)
    assert usage.proportion == 0.0
    assert usage.indicator == "🟢"


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
    """Aggregate overhead is sourced from the per-bucket breakdown.

    Message token counts now go through the *local* raw estimator instead
    of ``agent.estimate_tokens_for_message`` (which is patched by the
    token_ratio_learner plugin and would bias the badge). We construct
    fake messages with a single text part of known length so the raw
    char/2.5 heuristic produces predictable counts.
    """
    mod = _usage_module()

    # 2500 chars / 2.5 chars-per-token == 1000 raw tokens per message.
    fake_messages = [MagicMock(parts=[MagicMock()]) for _ in range(3)]
    with patch(
        "code_puppy.agents._history.stringify_part",
        return_value="x" * 2500,
    ):
        fake_agent = MagicMock()
        fake_agent.get_message_history.return_value = fake_messages
        fake_agent._get_model_context_length.return_value = 10000
        stub_agent_manager.get_current_agent.side_effect = None
        stub_agent_manager.get_current_agent.return_value = fake_agent

        fake_breakdown = mod.OverheadBreakdown(
            system_prompt_tokens=300,
            agents_md_tokens=150,
            pydantic_tools_tokens=50,
            mcp_tokens=0,
        )
        with patch.object(
            mod, "compute_overhead_breakdown", return_value=fake_breakdown
        ):
            usage = mod.get_current_usage()

    assert usage is not None
    assert usage.used_tokens == 3000
    assert usage.overhead_tokens == 500
    assert usage.system_prompt_tokens == 300
    assert usage.agents_md_tokens == 150
    assert usage.pydantic_tools_tokens == 50
    assert usage.mcp_tokens == 0
    assert usage.capacity == 10000
    assert usage.total_tokens == 3500
    assert usage.indicator == "🟡"  # 35%


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
# Prompt patch
# ---------------------------------------------------------------------------
def test_install_prompt_patch_is_idempotent():
    module = _plugin_module()
    from code_puppy.command_line import prompt_toolkit_completion as ptc

    original = ptc.get_prompt_with_active_model
    try:
        module._install_prompt_patch()
        first = ptc.get_prompt_with_active_model
        module._install_prompt_patch()
        second = ptc.get_prompt_with_active_model
        assert first is second
        assert getattr(ptc, "_context_indicator_original") is original
    finally:
        ptc.get_prompt_with_active_model = original
        if hasattr(ptc, "_context_indicator_original"):
            delattr(ptc, "_context_indicator_original")


def test_inject_indicator_returns_unchanged_when_usage_none():
    module = _plugin_module()
    from prompt_toolkit.formatted_text import FormattedText

    original = FormattedText([("bold", "🌫️ "), ("class:arrow", ">>> ")])
    with patch(
        "code_puppy.plugins.context_indicator.register_callbacks.get_current_usage",
        return_value=None,
    ):
        result = module._inject_indicator(original)
    assert result is original


def test_inject_indicator_inserts_circle_after_dog():
    module = _plugin_module()
    from prompt_toolkit.formatted_text import FormattedText

    fake_usage = _usage_module().ContextUsage(
        used_tokens=100, overhead_tokens=0, capacity=10000
    )
    original = FormattedText([("bold", "🌫️ "), ("class:arrow", ">>> ")])
    with patch(
        "code_puppy.plugins.context_indicator.register_callbacks.get_current_usage",
        return_value=fake_usage,
    ):
        result = module._inject_indicator(original)

    parts = list(result)
    assert parts[0] == ("bold", "🌫️ ")
    assert parts[1][0] == "class:context-indicator"
    assert "🟢" in parts[1][1]


# ---------------------------------------------------------------------------
# /context slash command
# ---------------------------------------------------------------------------
def test_custom_help_lists_command():
    entries = dict(_plugin_module()._custom_help())
    assert "context" in entries


def test_handle_custom_command_ignores_unrelated_names():
    assert _plugin_module()._handle_custom_command("/nope", "nope") is None


def test_handle_context_command_emits_info_when_usage_present():
    module = _plugin_module()
    fake_usage = _usage_module().ContextUsage(
        used_tokens=2000, overhead_tokens=500, capacity=10000
    )
    with (
        patch(
            "code_puppy.plugins.context_indicator.register_callbacks.get_current_usage",
            return_value=fake_usage,
        ),
        patch(
            "code_puppy.plugins.context_indicator.register_callbacks._emit_info"
        ) as mock_info,
    ):
        result = module._handle_custom_command("/context", "context")
    assert result is True
    mock_info.assert_called_once()
    msg = mock_info.call_args[0][0]
    assert "25.0%" in msg
    assert "🟢" in msg


def test_handle_context_command_emits_friendly_message_when_no_usage():
    module = _plugin_module()
    with (
        patch(
            "code_puppy.plugins.context_indicator.register_callbacks.get_current_usage",
            return_value=None,
        ),
        patch(
            "code_puppy.plugins.context_indicator.register_callbacks._emit_info"
        ) as mock_info,
    ):
        result = module._handle_custom_command("/context", "context")
    assert result is True
    mock_info.assert_called_once()
    assert "No context info" in mock_info.call_args[0][0]


def test_format_usage_report_includes_progress_bar():
    module = _plugin_module()
    usage = _usage_module().ContextUsage(
        used_tokens=6000, overhead_tokens=1000, capacity=10000
    )
    report = module._format_usage_report(usage)
    assert "🔴" in report
    assert "70.0%" in report
    assert "█" in report
    assert "░" in report


def test_format_usage_report_breaks_out_mcp_and_agents_md():
    """When breakdown buckets are populated they each get their own line."""
    module = _plugin_module()
    usage = _usage_module().ContextUsage(
        used_tokens=1000,
        overhead_tokens=1300,
        capacity=10000,
        system_prompt_tokens=300,
        agents_md_tokens=200,
        pydantic_tools_tokens=150,
        mcp_tokens=250,
        kennel_memory_tokens=400,
    )
    report = module._format_usage_report(usage)
    assert "System prompt" in report
    assert "AGENTS.md" in report
    assert "Kennel memory" in report
    assert "Pydantic tools" in report
    assert "MCP toolsets" in report
    # Numbers show up with thousands separators.
    assert "300" in report
    assert "250" in report
    assert "400" in report


def test_format_usage_report_hides_empty_breakdown_buckets():
    """Zero-valued buckets are hidden so the report stays clean."""
    module = _plugin_module()
    usage = _usage_module().ContextUsage(
        used_tokens=1000,
        overhead_tokens=300,
        capacity=10000,
        system_prompt_tokens=300,
        agents_md_tokens=0,
        pydantic_tools_tokens=0,
        mcp_tokens=0,
        kennel_memory_tokens=0,
    )
    report = module._format_usage_report(usage)
    # Use the breakdown row prefix "└─" so we don't false-positive on the
    # "AGENTS.md" / "MCP" mentions in the Overhead description line above.
    assert "└─ System prompt" in report
    assert "└─ AGENTS.md" not in report
    assert "└─ MCP toolsets" not in report
    assert "└─ Kennel memory" not in report


def test_format_usage_report_omits_breakdown_block_when_all_zero():
    """Legacy ContextUsage with no breakdown fields renders cleanly."""
    module = _plugin_module()
    usage = _usage_module().ContextUsage(
        used_tokens=1000, overhead_tokens=500, capacity=10000
    )
    report = module._format_usage_report(usage)
    assert "└─" not in report
    assert "Overhead" in report


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


def test_kennel_memory_block_swallows_retriever_exceptions(monkeypatch):
    """Retriever blowups must never break /context."""
    mod = _usage_module()
    fake_retriever = MagicMock()
    fake_retriever.build_recall_block.side_effect = RuntimeError("db on fire")
    monkeypatch.setitem(
        sys.modules,
        "code_puppy.plugins.puppy_kennel.retriever",
        fake_retriever,
    )
    assert mod._kennel_memory_block() == ""


def test_kennel_memory_block_returns_empty_when_retriever_missing(monkeypatch):
    """Kennel plugin uninstalled -> empty string, no exception."""
    mod = _usage_module()
    # Force the import inside ``_kennel_memory_block`` to fail.
    monkeypatch.setitem(
        sys.modules,
        "code_puppy.plugins.puppy_kennel.retriever",
        None,
    )
    assert mod._kennel_memory_block() == ""
