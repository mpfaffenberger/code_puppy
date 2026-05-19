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
        (0.599, "🟡"),
        (0.60, "🔴"),
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


def test_get_current_usage_returns_none_when_estimator_raises(stub_agent_manager):
    """If *any* estimator blows up we hide the indicator rather than lying."""
    mod = _usage_module()
    fake_agent = MagicMock()
    fake_agent.get_message_history.return_value = ["m1"]
    fake_agent.estimate_tokens_for_message.side_effect = RuntimeError("boom")
    fake_agent._estimate_context_overhead.return_value = 0
    fake_agent._get_model_context_length.return_value = 10000
    stub_agent_manager.get_current_agent.side_effect = None
    stub_agent_manager.get_current_agent.return_value = fake_agent
    assert mod.get_current_usage() is None


def test_get_current_usage_returns_none_when_overhead_raises(stub_agent_manager):
    mod = _usage_module()
    fake_agent = MagicMock()
    fake_agent.get_message_history.return_value = []
    fake_agent.estimate_tokens_for_message.return_value = 0
    fake_agent._estimate_context_overhead.side_effect = RuntimeError("boom")
    fake_agent._get_model_context_length.return_value = 10000
    stub_agent_manager.get_current_agent.side_effect = None
    stub_agent_manager.get_current_agent.return_value = fake_agent
    assert mod.get_current_usage() is None


def test_get_current_usage_returns_none_when_capacity_zero(stub_agent_manager):
    mod = _usage_module()
    fake_agent = MagicMock()
    fake_agent.get_message_history.return_value = []
    fake_agent.estimate_tokens_for_message.return_value = 0
    fake_agent._estimate_context_overhead.return_value = 0
    fake_agent._get_model_context_length.return_value = 0
    stub_agent_manager.get_current_agent.side_effect = None
    stub_agent_manager.get_current_agent.return_value = fake_agent
    assert mod.get_current_usage() is None


def test_get_current_usage_computes_totals(stub_agent_manager):
    mod = _usage_module()
    fake_agent = MagicMock()
    fake_agent.get_message_history.return_value = ["m1", "m2", "m3"]
    fake_agent.estimate_tokens_for_message.side_effect = lambda m: 1000
    fake_agent._estimate_context_overhead.return_value = 500
    fake_agent._get_model_context_length.return_value = 10000
    stub_agent_manager.get_current_agent.side_effect = None
    stub_agent_manager.get_current_agent.return_value = fake_agent
    usage = mod.get_current_usage()
    assert usage is not None
    assert usage.used_tokens == 3000
    assert usage.overhead_tokens == 500
    assert usage.capacity == 10000
    assert usage.total_tokens == 3500
    assert usage.indicator == "🟡"  # 35%


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

    original = FormattedText([("bold", "🐶 "), ("class:arrow", ">>> ")])
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
    original = FormattedText([("bold", "🐶 "), ("class:arrow", ">>> ")])
    with patch(
        "code_puppy.plugins.context_indicator.register_callbacks.get_current_usage",
        return_value=fake_usage,
    ):
        result = module._inject_indicator(original)

    parts = list(result)
    assert parts[0] == ("bold", "🐶 ")
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
