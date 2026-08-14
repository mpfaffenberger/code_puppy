"""Tests for the context_indicator plugin (rendering + slash command).

The token-accounting *implementation* tests moved to
``tests/test_token_usage.py`` when the estimator relocated to the core
module ``code_puppy.token_usage``. This file keeps the plugin-level tests:
the bottom-bar status patch, the ``/context`` slash command, and the
``_format_usage_report`` rendering. It also keeps a single compatibility
test proving the old import path still re-exports the same core objects.

Glyphs are written as unicode escapes on purpose (the repo's emoji filter
strips raw emoji from file writes).
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

# Colored-circle + progress-bar glyphs, as escapes to survive the emoji filter.
GREEN_CIRCLE = "\U0001f7e2"
YELLOW_CIRCLE = "\U0001f7e1"
RED_CIRCLE = "\U0001f534"
BAR_FULL = "\u2588"  # full block
BAR_EMPTY = "\u2591"  # light shade
TREE_ROW = "\u2514\u2500"  # "corner + horizontal" breakdown-row prefix


def _plugin_module():
    return importlib.import_module(
        "code_puppy_core_plugins.context_indicator.register_callbacks"
    )


def _usage_module():
    """The core token-usage module (post-relocation home of the estimator)."""
    return importlib.import_module("code_puppy.token_usage")


# ---------------------------------------------------------------------------
# Compatibility: the old plugin path re-exports the same core objects
# ---------------------------------------------------------------------------
def test_usage_shim_reexports_core_objects():
    """``context_indicator.usage`` must expose the *same* objects as core.

    Downstream code and tests still import the old path; identity (not just
    equality) guarantees patching either module observes one implementation.
    """
    core = importlib.import_module("code_puppy.token_usage")
    shim = importlib.import_module("code_puppy_core_plugins.context_indicator.usage")
    for name in (
        "ContextUsage",
        "OverheadBreakdown",
        "get_current_usage",
        "compute_overhead_breakdown",
        "pick_indicator",
        "GREEN_THRESHOLD",
        "YELLOW_THRESHOLD",
        "GREEN_CIRCLE",
        "YELLOW_CIRCLE",
        "RED_CIRCLE",
    ):
        assert getattr(shim, name) is getattr(core, name), name


# ---------------------------------------------------------------------------
# Status-line patch
# ---------------------------------------------------------------------------
def test_install_status_patch_is_idempotent():
    module = _plugin_module()
    from code_puppy.agents import _compaction

    original = _compaction.update_spinner_context
    try:
        module._install_status_patch()
        first = _compaction.update_spinner_context
        module._install_status_patch()
        second = _compaction.update_spinner_context
        assert first is second
        assert getattr(_compaction, "_context_indicator_original") is original
    finally:
        _compaction.update_spinner_context = original
        if hasattr(_compaction, "_context_indicator_original"):
            delattr(_compaction, "_context_indicator_original")


def test_patched_status_writer_forwards_decorated_info():
    """The installed patch forwards ``_decorate_status(info)`` to the original."""
    module = _plugin_module()
    from code_puppy.agents import _compaction

    original = _compaction.update_spinner_context
    captured = []
    fake_usage = _usage_module().ContextUsage(
        used_tokens=100, overhead_tokens=0, capacity=10000
    )
    try:
        _compaction.update_spinner_context = captured.append
        module._install_status_patch()
        with patch(
            "code_puppy_core_plugins.context_indicator.register_callbacks.get_current_usage",
            return_value=fake_usage,
        ):
            _compaction.update_spinner_context("5k/10k tokens (50%)")
    finally:
        _compaction.update_spinner_context = original
        if hasattr(_compaction, "_context_indicator_original"):
            delattr(_compaction, "_context_indicator_original")

    assert captured == [f"{GREEN_CIRCLE} 5k/10k tokens (50%)"]


def test_decorate_status_returns_unchanged_when_usage_none():
    module = _plugin_module()
    with patch(
        "code_puppy_core_plugins.context_indicator.register_callbacks.get_current_usage",
        return_value=None,
    ):
        assert module._decorate_status("5k/10k tokens (50%)") == "5k/10k tokens (50%)"


def test_decorate_status_prepends_circle():
    module = _plugin_module()
    fake_usage = _usage_module().ContextUsage(
        used_tokens=100, overhead_tokens=0, capacity=10000
    )
    with patch(
        "code_puppy_core_plugins.context_indicator.register_callbacks.get_current_usage",
        return_value=fake_usage,
    ):
        result = module._decorate_status("5k/10k tokens (50%)")
    assert result == f"{GREEN_CIRCLE} 5k/10k tokens (50%)"


def test_decorate_status_leaves_clear_calls_empty():
    """Empty info means 'clear the row' -- no lone circle haunting idle prompts."""
    module = _plugin_module()
    fake_usage = _usage_module().ContextUsage(
        used_tokens=100, overhead_tokens=0, capacity=10000
    )
    with patch(
        "code_puppy_core_plugins.context_indicator.register_callbacks.get_current_usage",
        return_value=fake_usage,
    ):
        assert module._decorate_status("") == ""


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
            "code_puppy_core_plugins.context_indicator.register_callbacks.get_current_usage",
            return_value=fake_usage,
        ),
        patch(
            "code_puppy_core_plugins.context_indicator.register_callbacks._emit_info"
        ) as mock_info,
    ):
        result = module._handle_custom_command("/context", "context")
    assert result is True
    mock_info.assert_called_once()
    msg = mock_info.call_args[0][0]
    assert "25.0%" in msg
    assert GREEN_CIRCLE in msg


def test_handle_context_command_emits_friendly_message_when_no_usage():
    module = _plugin_module()
    with (
        patch(
            "code_puppy_core_plugins.context_indicator.register_callbacks.get_current_usage",
            return_value=None,
        ),
        patch(
            "code_puppy_core_plugins.context_indicator.register_callbacks._emit_info"
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
    assert RED_CIRCLE in report
    assert "70.0%" in report
    assert BAR_FULL in report
    assert BAR_EMPTY in report


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
    # Use the breakdown row prefix so we don't false-positive on the
    # "AGENTS.md" / "MCP" mentions in the Overhead description line above.
    assert f"{TREE_ROW} System prompt" in report
    assert f"{TREE_ROW} AGENTS.md" not in report
    assert f"{TREE_ROW} MCP toolsets" not in report
    assert f"{TREE_ROW} Kennel memory" not in report


def test_format_usage_report_omits_breakdown_block_when_all_zero():
    """Legacy ContextUsage with no breakdown fields renders cleanly."""
    module = _plugin_module()
    usage = _usage_module().ContextUsage(
        used_tokens=1000, overhead_tokens=500, capacity=10000
    )
    report = module._format_usage_report(usage)
    assert TREE_ROW not in report
    assert "Overhead" in report
