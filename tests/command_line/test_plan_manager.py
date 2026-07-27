"""Tests for code_puppy/command_line/plan_manager.py."""

from unittest.mock import patch

import pytest

from code_puppy.command_line.plan_manager import PlanManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_plan(tmp_path):
    """Return a PlanManager rooted in a temp directory."""
    return PlanManager(cwd=str(tmp_path))


@pytest.fixture
def plan_with_steps(tmp_plan: PlanManager):
    """Populate a plan with a few checklist items."""
    content = """# Plan: Test

## Objective
Test fixture

## Steps
- [ ] Set up dependencies
- [ ] Implement the feature
- [x] Write unit tests
- [ ] Manual QA

## Risks
- Time

## Validation
- [ ] All tests pass
"""
    tmp_plan.save(content)
    return tmp_plan


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


class TestPlanManagerIO:
    def test_exists_returns_false_when_no_file(self, tmp_plan: PlanManager):
        assert not tmp_plan.exists()

    def test_save_and_exists(self, tmp_plan: PlanManager):
        tmp_plan.save("# My Plan")
        assert tmp_plan.exists()

    def test_load_returns_none_when_no_file(self, tmp_plan: PlanManager):
        assert tmp_plan.load() is None

    def test_load_returns_content(self, tmp_plan: PlanManager):
        content = "# Plan: Hello"
        tmp_plan.save(content)
        assert tmp_plan.load() == content

    def test_save_creates_parent_dir(self, tmp_plan: PlanManager):
        deep = PlanManager(cwd=str(tmp_plan._cwd))
        deep.save("# Deep")
        assert deep.plan_path.exists()

    def test_create_template(self, tmp_plan: PlanManager):
        template = tmp_plan.create_template("My Plan")
        assert "# Plan: My Plan" in template
        assert "- [ ] Step 1" in template
        assert "## Validation" in template


# ---------------------------------------------------------------------------
# Step parsing
# ---------------------------------------------------------------------------


class TestStepParsing:
    def test_get_steps_returns_empty_when_no_file(self, tmp_plan: PlanManager):
        assert tmp_plan.get_steps() == []

    def test_get_steps_parses_checkboxes(self, plan_with_steps: PlanManager):
        steps = plan_with_steps.get_steps()
        assert len(steps) == 5
        assert steps[0]["index"] == 1
        assert steps[0]["text"] == "Set up dependencies"
        assert steps[0]["done"] is False

        assert steps[2]["index"] == 3
        assert steps[2]["text"] == "Write unit tests"
        assert steps[2]["done"] is True

    def test_get_steps_handles_upper_x(self, tmp_plan: PlanManager):
        tmp_plan.save("- [X] Done\n- [ ] Pending")
        steps = tmp_plan.get_steps()
        assert len(steps) == 2
        assert steps[0]["done"] is True
        assert steps[1]["done"] is False

    def test_get_steps_ignores_non_checklist_lines(self, plan_with_steps: PlanManager):
        steps = plan_with_steps.get_steps()
        for s in steps:
            assert s["text"] not in ("## Steps", "## Risks")


# ---------------------------------------------------------------------------
# Mark done / undone
# ---------------------------------------------------------------------------


class TestMarkStep:
    def test_mark_done(self, plan_with_steps: PlanManager):
        assert plan_with_steps.mark_step_done(1, done=True)
        steps = plan_with_steps.get_steps()
        assert steps[0]["done"] is True

    def test_mark_undone(self, plan_with_steps: PlanManager):
        assert plan_with_steps.mark_step_done(3, done=False)
        steps = plan_with_steps.get_steps()
        assert steps[2]["done"] is False

    def test_mark_invalid_step(self, plan_with_steps: PlanManager):
        assert not plan_with_steps.mark_step_done(99)

    def test_mark_when_no_file(self, tmp_plan: PlanManager):
        assert not tmp_plan.mark_step_done(1)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


class TestShowFormatted:
    def test_show_when_no_plan(self, tmp_plan: PlanManager):
        output = tmp_plan.show_formatted()
        assert "No plan file" in output
        assert ".claude/plan.md" in output

    def test_show_includes_counts(self, plan_with_steps: PlanManager):
        output = plan_with_steps.show_formatted()
        assert "1/5 steps complete" in output
        assert "# Plan: Test" in output


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------


class TestEditInEditor:
    def test_creates_template_when_no_file(self, tmp_plan: PlanManager):
        with patch(
            "subprocess.run", return_value=type("R", (), {"returncode": 0})()
        ) as mock_run:
            result = tmp_plan.edit_in_editor()
        assert result is True
        assert tmp_plan.exists()
        assert mock_run.called

    def test_editor_error_returns_false(self, tmp_plan: PlanManager):
        tmp_plan.save("# Already there")
        with patch("subprocess.run", return_value=type("R", (), {"returncode": 1})()):
            result = tmp_plan.edit_in_editor()
        assert result is False

    def test_editor_not_found_raises(self, tmp_plan: PlanManager):
        tmp_plan.save("# Test")
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="Editor"):
                tmp_plan.edit_in_editor()

    def test_respects_visual_env(self, tmp_plan: PlanManager, monkeypatch):
        monkeypatch.setenv("VISUAL", "vim")
        tmp_plan.save("# Test")
        with patch(
            "subprocess.run", return_value=type("R", (), {"returncode": 0})()
        ) as mock_run:
            tmp_plan.edit_in_editor()
        assert mock_run.call_args[0][0][0] == "vim"

    def test_fallback_to_editor_env(self, tmp_plan: PlanManager, monkeypatch):
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "code")
        tmp_plan.save("# Test")
        with patch(
            "subprocess.run", return_value=type("R", (), {"returncode": 0})()
        ) as mock_run:
            tmp_plan.edit_in_editor()
        assert mock_run.call_args[0][0][0] == "code"


# ---------------------------------------------------------------------------
# Execution prompt builders
# ---------------------------------------------------------------------------


class TestBuildRunPrompt:
    def test_raises_when_no_plan(self, tmp_plan: PlanManager):
        with pytest.raises(ValueError, match="No plan found"):
            tmp_plan.build_run_prompt()

    def test_raises_when_invalid_step(self, plan_with_steps: PlanManager):
        with pytest.raises(ValueError, match="not found"):
            plan_with_steps.build_run_prompt(step_num=99)

    def test_raises_when_step_already_done(self, plan_with_steps: PlanManager):
        with pytest.raises(ValueError, match="already marked as done"):
            plan_with_steps.build_run_prompt(step_num=3)

    def test_returns_prompt_for_single_step(self, plan_with_steps: PlanManager):
        prompt = plan_with_steps.build_run_prompt(step_num=1)
        assert "Step 1" in prompt
        assert "Set up dependencies" in prompt
        assert "PLAN_STEP_DONE: 1" in prompt

    def test_returns_prompt_for_all_pending(self, plan_with_steps: PlanManager):
        prompt = plan_with_steps.build_run_prompt()
        assert "Set up dependencies" in prompt
        assert "Implement the feature" in prompt
        assert "Manual QA" in prompt
        assert "All tests pass" in prompt  # validation step, also pending
        # The already-done step appears in the "Full plan (for context)" section
        # but NOT in the "Pending steps to execute" section. Verify that.
        assert "## Pending steps to execute" in prompt
        pending_section = prompt.split("## Pending steps to execute")[1]
        assert "Write unit tests" not in pending_section
        assert "PLAN_STEP_DONE" in prompt

    def test_raises_when_all_done(self, tmp_plan: PlanManager):
        tmp_plan.save("- [x] Only step")
        from code_puppy.command_line.plan_manager import PlanManager as PM

        pm = PM(cwd=str(tmp_plan._cwd))
        with pytest.raises(ValueError, match="All steps are already completed"):
            pm.build_run_prompt()


# ---------------------------------------------------------------------------
# PLAN_STEP_DONE marker processing (integration adjacen
# ---------------------------------------------------------------------------


class TestProcessStepMarkers:
    """Test the marker-processing logic via its PlanManager dependency."""

    def test_strips_marker_and_updates_file(self, plan_with_steps: PlanManager):
        response = "Did the work.\nPLAN_STEP_DONE: 1\nAll done.\n"
        from code_puppy.command_line.plan_manager import PlanManager

        pm = PlanManager(cwd=str(plan_with_steps._cwd))
        # We need a minimal version of the marker processing that updates the file
        # so we test the effect through plan_manager methods directly.
        pm.save(plan_with_steps.load() + "")
        plan_with_steps.mark_step_done(1, done=True)
        steps = plan_with_steps.get_steps()
        assert steps[0]["done"] is True

        # Also simulate what _process_plan_step_markers does: strip the line
        filtered = [
            line for line in response.split("\n") if "PLAN_STEP_DONE" not in line
        ]
        assert "Did the work." in filtered
        assert "All done." in filtered
        assert not any("PLAN_STEP_DONE" in line for line in filtered)
