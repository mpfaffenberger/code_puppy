"""Tests for durable UUID-based goal resumption."""

from __future__ import annotations

from unittest.mock import patch

from code_puppy.plugins.wiggum import goal_runs, state
from code_puppy.plugins.wiggum.register_callbacks import (
    _on_interactive_turn_cancel,
    handle_goal_command,
)


def test_goal_run_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(goal_runs, "_RUNS_DIR", tmp_path)

    created = goal_runs.create("ship the feature")
    goal_runs.update(
        created.run_id,
        loop_count=3,
        remediation_notes="add a regression test",
        status="interrupted",
    )

    loaded = goal_runs.load(created.run_id)
    assert loaded is not None
    assert loaded.prompt == "ship the feature"
    assert loaded.loop_count == 3
    assert loaded.remediation_notes == "add a regression test"
    assert loaded.status == "interrupted"
    assert goal_runs.load("definitely-not-a-uuid") is None


def test_goal_resume_restores_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(goal_runs, "_RUNS_DIR", tmp_path)
    run = goal_runs.create("ship the feature")
    goal_runs.update(
        run.run_id,
        loop_count=2,
        remediation_notes="fix the flaky test",
        status="interrupted",
    )

    with (
        patch("code_puppy.plugins.wiggum.register_callbacks._display_banner_message"),
        patch("code_puppy.plugins.wiggum.register_callbacks.emit_info"),
    ):
        prompt = handle_goal_command(f"/goal resume {run.run_id}")

    current = state.get_state()
    assert current.active is True
    assert current.run_id == run.run_id
    assert current.loop_count == 2
    assert prompt == "ship the feature\n\nJudge remediation notes:\nfix the flaky test"
    state.stop()


def test_cancel_marks_goal_interrupted_and_prints_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(goal_runs, "_RUNS_DIR", tmp_path)
    run = goal_runs.create("ship the feature")
    state.start(run.prompt, mode="goal", run_id=run.run_id, loop_count=4)

    with (
        patch("code_puppy.plugins.wiggum.register_callbacks.emit_warning"),
        patch("code_puppy.plugins.wiggum.register_callbacks.emit_info") as emit_info,
    ):
        _on_interactive_turn_cancel(run.prompt, reason="cancelled")

    saved = goal_runs.load(run.run_id)
    assert saved is not None
    assert saved.status == "interrupted"
    assert saved.loop_count == 4
    emit_info.assert_called_once_with(f"Resume it with: /goal resume {run.run_id}")
    assert state.is_active() is False
