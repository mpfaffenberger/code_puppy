"""Tests for the context_indicator plugin."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def _plugin_module():
    sys.modules.setdefault("dbos", MagicMock())
    _ensure_agent_manager_stub()
    return importlib.import_module(
        "code_puppy.plugins.context_indicator.register_callbacks"
    )


def _ensure_agent_manager_stub():
    """Stub ``code_puppy.agents.agent_manager`` so ``patch()`` can target it.

    Importing the real module pulls in MCP dependencies that aren't installed
    in the test environment. The plugin only ever calls
    ``get_current_agent`` — a stub with that attribute is plenty.
    """
    if "code_puppy.agents.agent_manager" in sys.modules:
        return
    stub = MagicMock()
    stub.get_current_agent = MagicMock(side_effect=RuntimeError("unstubbed"))
    sys.modules["code_puppy.agents.agent_manager"] = stub
    # Also ensure parent ``code_puppy.agents`` namespace knows about it.
    agents_pkg = sys.modules.get("code_puppy.agents")
    if agents_pkg is not None:
        setattr(agents_pkg, "agent_manager", stub)


def _usage_module():
    _ensure_agent_manager_stub()
    return importlib.import_module("code_puppy.plugins.context_indicator.usage")


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
    usage = _usage_module().ContextUsage(
        used_tokens=10, overhead_tokens=10, capacity=0
    )
    assert usage.proportion == 0.0
    assert usage.indicator == "🟢"


# ---------------------------------------------------------------------------
# get_current_usage — defensive paths
# ---------------------------------------------------------------------------
def test_get_current_usage_returns_none_when_agent_missing():
    mod = _usage_module()
    with patch(
        "code_puppy.agents.agent_manager.get_current_agent",
        side_effect=RuntimeError("nope"),
    ):
        assert mod.get_current_usage() is None


def test_get_current_usage_returns_none_when_capacity_zero():
    mod = _usage_module()
    fake_agent = MagicMock()
    fake_agent.get_message_history.return_value = []
    fake_agent.estimate_tokens_for_message.return_value = 0
    fake_agent._estimate_context_overhead.return_value = 0
    fake_agent._get_model_context_length.return_value = 0
    with patch(
        "code_puppy.agents.agent_manager.get_current_agent",
        return_value=fake_agent,
    ):
        assert mod.get_current_usage() is None


def test_get_current_usage_computes_totals():
    mod = _usage_module()
    fake_agent = MagicMock()
    fake_agent.get_message_history.return_value = ["m1", "m2", "m3"]
    fake_agent.estimate_tokens_for_message.side_effect = lambda m: 1000
    fake_agent._estimate_context_overhead.return_value = 500
    fake_agent._get_model_context_length.return_value = 10000
    with patch(
        "code_puppy.agents.agent_manager.get_current_agent",
        return_value=fake_agent,
    ):
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
