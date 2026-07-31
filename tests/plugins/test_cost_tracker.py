"""Tests for the cost_tracker plugin (pricing math, accumulation, /cost)."""

import asyncio
from unittest.mock import patch

import pytest

from code_puppy.plugins.cost_tracker import pricing as pricing_module
from code_puppy.plugins.cost_tracker.pricing import (
    ModelPricing,
    estimate_cost_usd,
    resolve_pricing,
)
from code_puppy.plugins.cost_tracker.register_callbacks import (
    COMMAND_NAME,
    _custom_help,
    _handle_custom_command,
    _on_agent_run_end,
    _render_report,
)
from code_puppy.plugins.cost_tracker.tracker import (
    SessionCostTracker,
    format_tokens,
    format_usd,
    get_tracker,
)


@pytest.fixture(autouse=True)
def _fresh_global_tracker():
    """Zero the module-level tracker around every test."""
    get_tracker().reset()
    yield
    get_tracker().reset()


# ---------------------------------------------------------------------------
# Cost math
# ---------------------------------------------------------------------------
def test_estimate_cost_openai_style_discounts_cached_input():
    # $2/M in, $8/M out, $0.50/M cache-read (gpt-ish numbers).
    p = ModelPricing("openai", "gpt-x", input=2.0, output=8.0, cache_read=0.5)
    # 1M input INCLUDING 400k cached; 100k output.
    cost = estimate_cost_usd(
        p, 1_000_000, 100_000, cache_read_tokens=400_000, anthropic_style=False
    )
    # 600k @ $2/M + 400k @ $0.5/M + 100k @ $8/M = 1.2 + 0.2 + 0.8
    assert cost == pytest.approx(2.2)


def test_estimate_cost_anthropic_style_bills_buckets_separately():
    # $3/M in, $15/M out, $0.30/M cache-read, $3.75/M cache-write.
    p = ModelPricing(
        "anthropic",
        "claude-x",
        input=3.0,
        output=15.0,
        cache_read=0.3,
        cache_write=3.75,
    )
    # Anthropic-style: input EXCLUDES cache traffic - nothing subtracted.
    cost = estimate_cost_usd(
        p,
        200_000,
        50_000,
        cache_read_tokens=1_000_000,
        cache_write_tokens=100_000,
        anthropic_style=True,
    )
    # 0.2M*3 + 0.05M*15 + 1M*0.3 + 0.1M*3.75 = 0.6 + 0.75 + 0.3 + 0.375
    assert cost == pytest.approx(2.025)


def test_estimate_cost_without_cache_rate_bills_full_input():
    p = ModelPricing("x", "m", input=1.0, output=2.0, cache_read=None)
    cost = estimate_cost_usd(
        p, 1_000_000, 0, cache_read_tokens=999_999, anthropic_style=False
    )
    assert cost == pytest.approx(1.0)  # no subtraction without a cache rate


def test_estimate_cost_clamps_negative_and_none_tokens():
    p = ModelPricing("x", "m", input=1.0, output=1.0)
    assert estimate_cost_usd(p, -5, None) == 0.0  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Pricing resolution against the bundled DB
# ---------------------------------------------------------------------------
def test_resolve_pricing_prefers_provider_from_type():
    config = {"my-claude": {"type": "anthropic", "name": "claude-opus-4-0"}}
    pricing, anthropic_style = resolve_pricing("my-claude", config)
    assert pricing is not None
    assert pricing.provider_id == "anthropic"
    assert anthropic_style is True
    assert pricing.input and pricing.output  # bundled DB has real prices


def test_resolve_pricing_round_robin_uses_first_member():
    config = {
        "qwen1": {"type": "anthropic", "name": "claude-opus-4-0"},
        "rr": {"type": "round_robin", "models": ["qwen1", "qwen2"]},
    }
    pricing, anthropic_style = resolve_pricing("rr", config)
    assert pricing is not None
    assert pricing.model_id == "claude-opus-4-0"
    assert anthropic_style is True  # inherited from the member's type


def test_resolve_pricing_unknown_model_returns_none():
    config = {"mystery": {"type": "custom_openai", "name": "totally-not-real-9000"}}
    pricing, _ = resolve_pricing("mystery", config)
    assert pricing is None


def test_resolve_pricing_strips_date_suffix():
    # Only meaningful if the dateless id exists in the bundle; the exact-id
    # miss must at minimum not crash and fall through deterministically.
    config = {"m": {"type": "anthropic", "name": "claude-opus-4-0-20250522"}}
    pricing, _ = resolve_pricing("m", config)
    assert pricing is None or pricing.model_id == "claude-opus-4-0"


def test_resolve_pricing_handles_empty_config_and_missing_entry():
    pricing, anthropic_style = resolve_pricing("nonexistent-model", {})
    # Must not raise; unpriced unless the raw name happens to exist upstream.
    assert anthropic_style is False
    assert pricing is None or pricing.model_id


# ---------------------------------------------------------------------------
# Tracker accumulation
# ---------------------------------------------------------------------------
def _meta(inp=0, out=0, cr=0, cw=0):
    return {
        "usage_input_tokens": inp,
        "usage_output_tokens": out,
        "usage_cached_read_tokens": cr,
        "usage_cached_write_tokens": cw,
    }


def test_tracker_accumulates_runs_and_costs():
    tracker = SessionCostTracker()
    fixed = (ModelPricing("openai", "gpt-x", input=1.0, output=1.0), False)
    with patch.object(SessionCostTracker, "_get_pricing", return_value=fixed):
        tracker.record_run("gpt-x", _meta(inp=1_000_000, out=1_000_000))
        tracker.record_run("gpt-x", _meta(inp=500_000))
    snap = tracker.snapshot()
    assert snap.total_cost_usd == pytest.approx(2.5)
    assert snap.known_cost is True
    assert snap.last_run_cost_usd == pytest.approx(0.5)
    assert snap.last_run_model == "gpt-x"
    (spend,) = snap.per_model
    assert spend.runs == 2
    assert spend.input_tokens == 1_500_000
    assert spend.output_tokens == 1_000_000


def test_tracker_tracks_tokens_for_unpriced_models():
    tracker = SessionCostTracker()
    with patch.object(SessionCostTracker, "_get_pricing", return_value=(None, False)):
        tracker.record_run("mystery", _meta(inp=1000, out=2000))
    snap = tracker.snapshot()
    assert snap.total_cost_usd == 0.0
    assert snap.known_cost is False
    assert snap.last_run_cost_usd is None
    (spend,) = snap.per_model
    assert spend.cost_usd is None
    assert spend.input_tokens == 1000
    assert snap.unknown_models == [spend]


def test_tracker_ignores_zero_usage_and_bad_metadata():
    tracker = SessionCostTracker()
    tracker.record_run("gpt-x", _meta())  # all zeros: cancelled pre-billing
    tracker.record_run("gpt-x", None)
    tracker.record_run("gpt-x", {"usage_input_tokens": "garbage"})
    tracker.record_run("", _meta(inp=100))
    assert tracker.snapshot().per_model == ()


def test_tracker_reset_zeroes_meter():
    tracker = SessionCostTracker()
    fixed = (ModelPricing("openai", "gpt-x", input=1.0, output=1.0), False)
    with patch.object(SessionCostTracker, "_get_pricing", return_value=fixed):
        tracker.record_run("gpt-x", _meta(inp=1_000_000))
    tracker.reset()
    snap = tracker.snapshot()
    assert snap.per_model == ()
    assert snap.total_cost_usd == 0.0
    assert snap.last_run_cost_usd is None


def test_tracker_record_run_never_raises():
    tracker = SessionCostTracker()
    with patch.object(
        SessionCostTracker, "_get_pricing", side_effect=RuntimeError("boom")
    ):
        tracker.record_run("gpt-x", _meta(inp=100))  # must swallow
    assert tracker.snapshot().per_model == ()


# ---------------------------------------------------------------------------
# agent_run_end callback
# ---------------------------------------------------------------------------
def test_run_end_callback_records_usage():
    fixed = (ModelPricing("openai", "gpt-x", input=1.0, output=1.0), False)
    with patch.object(SessionCostTracker, "_get_pricing", return_value=fixed):
        asyncio.run(
            _on_agent_run_end(
                agent_name="code-puppy",
                model_name="gpt-x",
                metadata={"model": "gpt-x", **_meta(inp=2_000_000)},
            )
        )
    snap = get_tracker().snapshot()
    assert snap.total_cost_usd == pytest.approx(2.0)


def test_run_end_callback_counts_failed_runs_with_billing():
    fixed = (ModelPricing("openai", "gpt-x", input=1.0, output=1.0), False)
    with patch.object(SessionCostTracker, "_get_pricing", return_value=fixed):
        asyncio.run(
            _on_agent_run_end(
                agent_name="code-puppy",
                model_name="gpt-x",
                success=False,
                error=RuntimeError("mid-run explosion"),
                metadata=_meta(inp=1_000_000),
            )
        )
    assert get_tracker().snapshot().total_cost_usd == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# /cost command
# ---------------------------------------------------------------------------
def test_help_lists_cost():
    entries = _custom_help()
    assert any(name == COMMAND_NAME for name, _ in entries)


def test_other_commands_are_not_ours():
    assert _handle_custom_command("/woof hi", "woof") is None


def test_cost_empty_session_report():
    with patch("code_puppy.messaging.emit_info") as emit:
        assert _handle_custom_command("/cost", "cost") is True
    assert emit.called
    assert "nothing spent" in str(emit.call_args).lower()


def test_cost_report_shows_totals_and_unknowns():
    tracker = get_tracker()
    fixed = (ModelPricing("openai", "gpt-x", input=1.0, output=1.0), False)
    with patch.object(SessionCostTracker, "_get_pricing", return_value=fixed):
        tracker.record_run("gpt-x", _meta(inp=1_000_000))
    with patch.object(SessionCostTracker, "_get_pricing", return_value=(None, False)):
        tracker.record_run("mystery", _meta(inp=500))
    report = _render_report()
    assert "$1.00" in report
    assert "gpt-x" in report
    assert "mystery" in report
    assert "No pricing data" in report
    assert "models.dev" in report


def test_cost_reset_subcommand():
    fixed = (ModelPricing("openai", "gpt-x", input=1.0, output=1.0), False)
    with patch.object(SessionCostTracker, "_get_pricing", return_value=fixed):
        get_tracker().record_run("gpt-x", _meta(inp=1_000_000))
    with patch("code_puppy.messaging.emit_success") as emit:
        assert _handle_custom_command("/cost reset", "cost") is True
    assert emit.called
    assert get_tracker().snapshot().total_cost_usd == 0.0


def test_cost_help_subcommand():
    with patch("code_puppy.messaging.emit_info") as emit:
        assert _handle_custom_command("/cost --help", "cost") is True
    assert "Usage" in str(emit.call_args)


def test_cost_unknown_subcommand_warns():
    with patch("code_puppy.messaging.emit_warning") as emit:
        assert _handle_custom_command("/cost frobnicate", "cost") is True
    assert "frobnicate" in str(emit.call_args)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def test_format_usd_precision_bands():
    assert format_usd(None) == "unknown"
    assert format_usd(0) == "$0.00"
    assert format_usd(0.0042) == "$0.0042"
    assert format_usd(0.042) == "$0.042"
    assert format_usd(1234.5) == "$1,234.50"


def test_format_tokens_bands():
    assert format_tokens(999) == "999"
    assert format_tokens(1_500) == "1.5k"
    assert format_tokens(25_000) == "25k"
    assert format_tokens(3_400_000) == "3.4M"


# ---------------------------------------------------------------------------
# Bundled DB index sanity
# ---------------------------------------------------------------------------
def test_bundled_index_builds_and_is_sorted():
    pricing_module.clear_pricing_cache()
    index = pricing_module._get_index()
    assert index, "bundled models_dev_api.json should produce a non-empty index"
    some_candidates = next(iter(index.values()))
    providers = [provider for provider, _ in some_candidates]
    assert providers == sorted(providers)
