"""Tests for subagent_panel model-name shortening + column alignment.

Covers the UX fix where same-version-different-tier models (e.g. gpt-5.4 vs
gpt-5.4-nano) used to collapse to an identical "GPT 5.4" label in the panel.
"""

from __future__ import annotations

import pytest

from code_puppy.plugins.subagent_panel.register_callbacks import (
    _model_short,
    _model_variant,
    _row_lines,
)


@pytest.mark.parametrize(
    "model,expected",
    [
        # The reported bug: nano tier must survive, not collapse to "GPT 5.4".
        ("gpt-5-4-nano", "GPT 5.4-Nano"),
        ("gpt-5.4-nano", "GPT 5.4-Nano"),
        ("chatgpt-gpt-5.4-nano", "GPT 5.4-Nano"),
        ("gpt-5.4-mini", "GPT 5.4-Mini"),
        ("gpt-5.4", "GPT 5.4"),
        ("gpt-4.1-nano", "GPT 4.1-Nano"),
        ("foundry-gpt-5-4", "GPT 5.4"),
        # Gemini variants -- 'mini' inside 'gemini' must NOT false-fire.
        ("gemini-2.5-flash", "Gemini 2.5-Flash"),
        ("gemini-2.0-pro", "Gemini 2.0-Pro"),
        ("gemini-1.5", "Gemini 1.5"),
        # Claude families keep their existing label form, with variants appended.
        ("claude-4-8-opus", "Opus 4.8"),
        ("claude-sonnet-4-6", "Sonnet 4.6"),
        ("claude-3-5-haiku", "Haiku 3.5"),
        # Empty / unknown fall through gracefully.
        ("", ""),
        (None, ""),
        ("some-weird-model", "some-weird-model"),
    ],
)
def test_model_short(model, expected):
    assert _model_short(model) == expected


def test_model_variant_no_false_positive_inside_gemini():
    # 'mini' is a substring of 'gemini' -- the delimiter guard must reject it.
    assert _model_variant("gemini-2.5") == ""
    # But a real delimited token is found.
    assert _model_variant("gpt-5.4-mini") == "Mini"
    assert _model_variant("gpt-5.4-nano") == "Nano"
    assert _model_variant("gemini-2.5-flash") == "Flash"


def test_distinct_tiers_render_distinctly():
    """The whole point: three gpt-5.4 tiers must produce three labels."""
    labels = {_model_short(m) for m in ("gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano")}
    assert labels == {"GPT 5.4", "GPT 5.4-Mini", "GPT 5.4-Nano"}


def _entry(session_id, name, model, **extra):
    base = {
        "session_id": session_id,
        "parent": None,
        "name": name,
        "model": model,
        "status": "starting",
        "start": 0.0,
        "last_seen": 0.0,
    }
    base.update(extra)
    return base


def test_columns_stay_aligned_with_varying_model_lengths():
    """A longer model label must push every row's status column to the same
    tab-stop -- spaces only, no ragged columns."""
    ordered = [
        (_entry("a", "short", "gpt-5.4"), 0),
        (_entry("b", "alpha", "gpt-5.4-nano"), 0),
        (_entry("c", "beta", "claude-4-8-opus"), 0),
    ]
    lines = _row_lines(ordered, frame="*")
    plains = [line.plain for line in lines]

    # No literal tab characters anywhere -- cross-platform safe.
    assert all("\t" not in p for p in plains)

    # The spinner marker '*' must start at the SAME column on every row, which
    # only holds if model+name padding aligned the right block.
    marker_cols = [p.index("*") for p in plains]
    assert len(set(marker_cols)) == 1, (marker_cols, plains)
