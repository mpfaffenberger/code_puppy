"""Unit tests for the in-place StepLedger."""

import pytest

from code_puppy.messaging.step_ledger import (
    StepLedger,
    StepRow,
    configure_ledger,
    get_ledger,
)


@pytest.fixture
def fresh_ledger():
    """A clean ledger per test — never touch the module singleton."""
    return StepLedger(max_visible=3)


def test_starts_empty(fresh_ledger):
    assert fresh_ledger.active is None
    assert fresh_ledger.recent == []
    assert fresh_ledger.history == []
    assert fresh_ledger.completed_count() == 0
    assert not fresh_ledger.has_active()


def test_begin_active_marks_one_running(fresh_ledger):
    fresh_ledger.begin_active("Running: npm test")
    assert fresh_ledger.has_active()
    assert fresh_ledger.active is not None
    assert fresh_ledger.active.label == "Running: npm test"
    assert fresh_ledger.active.kind == "tool"
    assert not fresh_ledger.active.completed


def test_complete_active_collapses_to_recent(fresh_ledger):
    fresh_ledger.begin_active("Running: npm test")
    fresh_ledger.complete_active("npm test (passed)")
    assert not fresh_ledger.has_active()
    assert len(fresh_ledger.recent) == 1
    row = fresh_ledger.recent[0]
    assert row.label == "npm test (passed)"
    assert row.kind == "tool"
    assert row.completed
    assert fresh_ledger.completed_count() == 1


def test_complete_active_without_label_keeps_original(fresh_ledger):
    fresh_ledger.begin_active("Running: tests")
    fresh_ledger.complete_active()  # no override
    assert fresh_ledger.recent[0].label == "Running: tests"


def test_cancel_active_drops_without_recording(fresh_ledger):
    fresh_ledger.begin_active("ephemeral")
    fresh_ledger.cancel_active()
    assert fresh_ledger.recent == []
    assert fresh_ledger.history == []
    assert fresh_ledger.completed_count() == 0


def test_recent_is_bounded(fresh_ledger):
    # max_visible=3 in fixture
    for i in range(10):
        fresh_ledger.push_completed(f"step {i}")
    assert len(fresh_ledger.recent) == 3
    # History is unbounded — full record kept for /steps replay.
    assert len(fresh_ledger.history) == 10
    # Most recent wins at the tail.
    assert [r.label for r in fresh_ledger.recent] == ["step 7", "step 8", "step 9"]


def test_push_narration_uses_narration_glyph(fresh_ledger):
    fresh_ledger.push_narration("Let me read the file first")
    row = fresh_ledger.recent[0]
    assert row.kind == "narration"
    text = fresh_ledger.render()
    assert "•" in text.plain
    assert "Let me read the file first" in text.plain


def test_render_includes_active_row_when_running(fresh_ledger):
    fresh_ledger.begin_active("Running: pytest")
    text = fresh_ledger.render(frame="⠹")
    assert "Running: pytest" in text.plain
    assert "⠹" in text.plain


def test_render_skips_active_when_disabled(fresh_ledger):
    fresh_ledger.begin_active("Running: pytest")
    text = fresh_ledger.render(frame="⠹", include_active=False)
    assert "Running: pytest" not in text.plain
    assert "⠹" not in text.plain


def test_render_shows_completed_tail_dim(fresh_ledger):
    fresh_ledger.push_completed("✓ npm test")
    text = fresh_ledger.render()
    # The dim style is applied — Text.plain keeps the chars regardless.
    assert "npm test" in text.plain
    assert "✓" in text.plain


def test_reset_clears_state_and_returns_history(fresh_ledger):
    fresh_ledger.begin_active("active")
    fresh_ledger.push_completed("a")
    fresh_ledger.push_completed("b")
    snapshot = fresh_ledger.reset()
    assert len(snapshot) == 2
    assert fresh_ledger.active is None
    assert fresh_ledger.recent == []
    assert fresh_ledger.history == []


def test_set_max_visible_rebounds_recent(fresh_ledger):
    # Fill past the original bound.
    for i in range(8):
        fresh_ledger.push_completed(f"step {i}")
    # Rebound to 2 — only the last 2 should remain visible.
    fresh_ledger.set_max_visible(2)
    assert fresh_ledger.max_visible == 2
    assert len(fresh_ledger.recent) == 2
    assert [r.label for r in fresh_ledger.recent] == ["step 6", "step 7"]


def test_render_truncates_long_labels():
    ledger = StepLedger(max_visible=1)
    ledger.push_completed("x" * 500)
    text = ledger.render()
    plain = text.plain
    # Truncation adds an ellipsis at the end.
    assert plain.endswith("…")
    # And the truncated body stays under the configured width.
    assert len(plain) <= 200


def test_render_strips_trailing_newline(fresh_ledger):
    fresh_ledger.push_completed("a step")
    text = fresh_ledger.render()
    # A trailing newline would push a phantom blank row in the Live region.
    assert not text.plain.endswith("\n")


def test_step_row_is_immutable():
    row = StepRow(kind="tool", label="x")
    with pytest.raises(Exception):
        row.label = "y"  # frozen dataclass — assignment should fail


def test_get_ledger_returns_singleton():
    a = get_ledger()
    b = get_ledger()
    assert a is b


def test_configure_ledger_replaces_singleton():
    original = get_ledger()
    new = configure_ledger(max_visible=2)
    assert new is not original
    assert get_ledger() is new
    # Restore so other tests see a clean slate.
    configure_ledger(max_visible=5)
