"""Tests for the bottom-bar panel rendering path (Phase 4).

Covers: styled Text row rendering, every tracked agent being visible,
throttled pushes, collapse on completion, and the swarm-cancel wipe via
command_runner._tear_down_live_panels.
"""

from __future__ import annotations

import pytest
from rich.text import Text

from code_puppy.plugins.subagent_panel import register_callbacks as rc
from code_puppy.plugins.subagent_panel import state


def _plain(line):
    """Plain text of a panel row (Text rows carry styles out-of-band)."""
    return line.plain if isinstance(line, Text) else line


class FakeBar:
    def __init__(self):
        self.calls: list[list[str]] = []

    def set_panel_lines(self, lines):
        self.calls.append(list(lines))


@pytest.fixture(autouse=True)
def clean_state():
    state.clear()
    rc._push_state["t"] = 0.0
    rc._push_state["count"] = -1
    yield
    state.clear()


@pytest.fixture
def bar(monkeypatch):
    fake = FakeBar()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: fake)
    return fake


# =========================================================================
# _panel_lines rendering
# =========================================================================


def test_empty_state_renders_no_lines():
    assert rc._panel_lines() == []


def test_single_agent_renders_one_styled_line():
    state.register("sid-1", "qa-kitten", "claude-4-8-opus")
    lines = rc._panel_lines()
    assert len(lines) == 1
    line = lines[0]
    # Styled Text row: color lives in out-of-band Style spans (regenerated
    # by the bar at paint time), NEVER as in-band escapes in the content.
    assert isinstance(line, Text)
    plain = line.plain
    assert "INVOKE AGENT" in plain
    assert "qa-kitten" in plain
    assert "Opus 4.8" in plain
    assert "starting" in plain
    assert "\x1b" not in plain  # no in-band ANSI in the content
    assert any(span.style for span in line.spans)  # styling present


def test_nested_child_renders_tree_elbow():
    state.register("root", "parent-agent", "gpt-5.4")
    state.register("kid", "child-agent", "gpt-5.4-mini", parent="root")
    lines = rc._panel_lines()
    assert len(lines) == 2
    assert "\u2514\u2500" in _plain(lines[1])  # tree elbow on the nested row
    assert "child-agent" in _plain(lines[1])


def test_all_agents_render_without_an_overflow_summary():
    for i in range(6):
        state.register(f"sid-{i}", f"agent-{i}", "gpt-5.4")

    lines = rc._panel_lines()

    assert len(lines) == 6
    assert [f"agent-{i}" in _plain(line) for i, line in enumerate(lines)] == [True] * 6
    assert all("more)" not in _plain(line) for line in lines)


def test_done_agent_shows_completed():
    state.register("sid-1", "worker", "gpt-5.4")
    state.mark_done("sid-1")
    lines = rc._panel_lines()
    assert "completed" in _plain(lines[0])
    assert "\u2713" in _plain(lines[0])


def test_failed_agent_shows_failed():
    state.register("sid-1", "worker", "gpt-5.4")
    state.mark_failed("sid-1")
    assert "failed" in _plain(rc._panel_lines()[0])


def test_disabled_runtime_renders_nothing(monkeypatch):
    state.register("sid-1", "worker", "gpt-5.4")
    monkeypatch.setattr(rc, "_runtime_enabled", lambda: False)
    assert rc._panel_lines() == []


# =========================================================================
# _push_panel
# =========================================================================


def test_push_panel_sends_lines_to_bar(bar):
    state.register("sid-1", "worker", "gpt-5.4")
    rc._push_panel(force=True)
    assert len(bar.calls) == 1
    assert "worker" in _plain(bar.calls[0][0])


def test_push_panel_collapse_after_clear(bar):
    state.register("sid-1", "worker", "gpt-5.4")
    rc._push_panel(force=True)
    state.clear()
    rc._push_panel(force=True)
    assert bar.calls[-1] == []


def test_push_panel_throttles_same_shape_repaints(bar):
    state.register("sid-1", "worker", "gpt-5.4")
    rc._push_panel(force=True)
    rc._push_panel()  # same shape, immediately after -> throttled
    assert len(bar.calls) == 1


def test_push_panel_shape_change_bypasses_throttle(bar):
    state.register("sid-1", "worker", "gpt-5.4")
    rc._push_panel(force=True)
    state.register("sid-2", "helper", "gpt-5.4")
    rc._push_panel()  # row count changed -> pushes despite throttle
    assert len(bar.calls) == 2
    assert len(bar.calls[1]) == 2


def test_push_panel_force_bypasses_throttle(bar):
    state.register("sid-1", "worker", "gpt-5.4")
    rc._push_panel(force=True)
    rc._push_panel(force=True)
    assert len(bar.calls) == 2


def test_push_panel_never_raises_without_bar(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.messaging.bottom_bar.get_bottom_bar",
        lambda: (_ for _ in ()).throw(RuntimeError("no bar")),
    )
    state.register("sid-1", "worker", "gpt-5.4")
    rc._push_panel(force=True)  # must not raise


# =========================================================================
# Swarm-cancel wipe (command_runner._tear_down_live_panels)
# =========================================================================


def test_tear_down_live_panels_clears_panel(bar):
    from code_puppy.tools.command_runner import _tear_down_live_panels

    state.register("sid-1", "worker", "gpt-5.4")
    rc._push_panel(force=True)
    _tear_down_live_panels()
    assert bar.calls[-1] == []


def test_tear_down_live_panels_never_raises(monkeypatch):
    from code_puppy.tools.command_runner import _tear_down_live_panels

    monkeypatch.setattr(
        "code_puppy.messaging.bottom_bar.get_bottom_bar",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    _tear_down_live_panels()  # must not raise
