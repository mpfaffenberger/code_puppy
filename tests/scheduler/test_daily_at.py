"""Tests for the daily_at schedule type.

Covers parse_daily_at_times() and the daily_at branch of should_run_task().
All wall-clock comparisons use an explicit `now` so tests never depend on
the real system clock.
"""

from datetime import datetime

import pytest

from code_puppy.scheduler.config import ScheduledTask
from code_puppy.scheduler.daemon import parse_daily_at_times, should_run_task

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 2, 27, 10, 0, 0)  # Friday, 10:00:00 am — fixed reference point


def daily_at_task(times: str, last_run: str | None = None) -> ScheduledTask:
    """Build a daily_at ScheduledTask with minimal boilerplate."""
    task = ScheduledTask(
        name="test-task",
        prompt="do the thing",
        schedule_type="daily_at",
        schedule_value=times,
    )
    task.last_run = last_run
    return task


# ---------------------------------------------------------------------------
# parse_daily_at_times
# ---------------------------------------------------------------------------


class TestParseDailyAtTimes:
    """Unit tests for the time-string parser."""

    def test_single_valid_time(self):
        assert parse_daily_at_times("09:00") == [(9, 0)]

    def test_multiple_valid_times(self):
        assert parse_daily_at_times("09:00,13:00,17:30") == [(9, 0), (13, 0), (17, 30)]

    def test_whitespace_around_commas_is_stripped(self):
        assert parse_daily_at_times("09:00 , 17:00") == [(9, 0), (17, 0)]

    def test_midnight(self):
        assert parse_daily_at_times("00:00") == [(0, 0)]

    def test_end_of_day(self):
        assert parse_daily_at_times("23:59") == [(23, 59)]

    def test_invalid_entry_is_skipped(self):
        """A bad entry should not prevent valid ones from being returned."""
        assert parse_daily_at_times("notaime,09:00") == [(9, 0)]

    def test_all_invalid_returns_empty(self):
        assert parse_daily_at_times("abc,xyz,9am") == []

    def test_empty_string_returns_empty(self):
        assert parse_daily_at_times("") == []

    def test_missing_colon_is_invalid(self):
        assert parse_daily_at_times("0900") == []

    def test_out_of_range_hour_is_invalid(self):
        assert parse_daily_at_times("25:00") == []

    def test_out_of_range_minute_is_invalid(self):
        assert parse_daily_at_times("10:60") == []

    def test_invalid_warns_to_stdout(self, capsys):
        parse_daily_at_times("bad")
        out = capsys.readouterr().out
        assert "Warning" in out
        assert "bad" in out

    def test_valid_entry_does_not_warn(self, capsys):
        parse_daily_at_times("09:00")
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# should_run_task — daily_at branch
# ---------------------------------------------------------------------------


class TestShouldRunTaskDailyAt:
    """Behavioural tests for the daily_at scheduling logic."""

    # -- basic fire / no-fire -------------------------------------------------

    def test_never_run_fires_when_past_target(self):
        """A task that has never run should fire once the target time passes."""
        task = daily_at_task("09:00", last_run=None)
        assert should_run_task(task, NOW) is True  # NOW is 10:00, target was 09:00

    def test_never_run_does_not_fire_before_target(self):
        """A task that has never run should NOT fire if the target is still in the future."""
        task = daily_at_task("14:00", last_run=None)
        assert should_run_task(task, NOW) is False  # NOW is 10:00, target is 14:00

    def test_fires_exactly_at_target_time(self):
        """The task should fire right at the target minute (boundary inclusive)."""
        at_target = datetime(2026, 2, 27, 9, 0, 0)
        task = daily_at_task("09:00", last_run=None)
        assert should_run_task(task, at_target) is True

    def test_does_not_fire_one_second_before_target(self):
        """The task must NOT fire before the target minute starts."""
        just_before = datetime(2026, 2, 27, 8, 59, 59)
        task = daily_at_task("09:00", last_run=None)
        assert should_run_task(task, just_before) is False

    # -- last_run logic -------------------------------------------------------

    def test_does_not_refire_after_running_today(self):
        """Once a task has run today after the target, it must not fire again."""
        ran_at_nine_oh_five = "2026-02-27T09:05:00"
        task = daily_at_task("09:00", last_run=ran_at_nine_oh_five)
        assert should_run_task(task, NOW) is False

    def test_fires_when_last_run_was_yesterday(self):
        """If last_run was yesterday the task is due again today."""
        yesterday = "2026-02-26T09:05:00"
        task = daily_at_task("09:00", last_run=yesterday)
        assert should_run_task(task, NOW) is True

    def test_restart_safe_fires_after_missed_window(self):
        """If the daemon was down at fire-time it must catch up on next wakeup.

        Scenario: target=09:00, daemon restarted at 09:47, last_run=yesterday.
        """
        restarted_late = datetime(2026, 2, 27, 9, 47, 0)
        yesterday = "2026-02-26T22:00:00"
        task = daily_at_task("09:00", last_run=yesterday)
        assert should_run_task(task, restarted_late) is True

    def test_last_run_before_target_but_same_day_fires(self):
        """last_run earlier today but before the target should still trigger."""
        ran_early_morning = "2026-02-27T07:00:00"  # before 09:00 target
        task = daily_at_task("09:00", last_run=ran_early_morning)
        assert should_run_task(task, NOW) is True

    # -- multiple times -------------------------------------------------------

    def test_multiple_times_first_due_second_future(self):
        """With two targets, only fire if at least one is due and not yet run."""
        # 09:00 passed, 17:00 is future — last_run is yesterday so 09:00 is due
        yesterday = "2026-02-26T09:05:00"
        task = daily_at_task("09:00,17:00", last_run=yesterday)
        assert should_run_task(task, NOW) is True

    def test_multiple_times_first_already_ran_second_future(self):
        """If the only due target has already been serviced, do not fire."""
        ran_after_nine = "2026-02-27T09:05:00"  # ran after 09:00 target
        task = daily_at_task("09:00,17:00", last_run=ran_after_nine)
        # 09:00 already serviced, 17:00 not yet reached
        assert should_run_task(task, NOW) is False

    def test_multiple_times_second_now_due(self):
        """When a later target becomes due the task should fire."""
        ran_after_nine = "2026-02-27T09:05:00"
        at_five_pm = datetime(2026, 2, 27, 17, 1, 0)
        task = daily_at_task("09:00,17:00", last_run=ran_after_nine)
        assert should_run_task(task, at_five_pm) is True

    def test_multiple_times_all_future(self):
        """When all targets are still in the future nothing should fire."""
        task = daily_at_task("13:00,17:00", last_run=None)
        assert should_run_task(task, NOW) is False  # NOW is 10:00

    def test_multiple_times_both_past_runs_on_first_match(self):
        """If both targets have passed and last_run is yesterday, task fires."""
        yesterday = "2026-02-26T22:00:00"
        task = daily_at_task("08:00,09:00", last_run=yesterday)
        assert should_run_task(task, NOW) is True

    # -- edge cases & error handling ------------------------------------------

    def test_disabled_task_never_fires(self):
        task = daily_at_task("09:00", last_run=None)
        task.enabled = False
        assert should_run_task(task, NOW) is False

    def test_all_invalid_times_returns_false_and_warns(self, capsys):
        task = daily_at_task("bad,worse", last_run=None)
        result = should_run_task(task, NOW)
        assert result is False
        out = capsys.readouterr().out
        assert "Warning" in out

    def test_mix_valid_and_invalid_times_uses_valid_ones(self):
        """Invalid entries in schedule_value are skipped; valid ones still work."""
        yesterday = "2026-02-26T09:05:00"
        task = daily_at_task("bogus,09:00", last_run=yesterday)
        assert should_run_task(task, NOW) is True

    def test_midnight_target_fires_after_midnight(self):
        just_after_midnight = datetime(2026, 2, 27, 0, 1, 0)
        task = daily_at_task("00:00", last_run="2026-02-26T00:05:00")
        assert should_run_task(task, just_after_midnight) is True

    def test_midnight_target_does_not_fire_previous_night(self):
        """Ran at 00:05 today — must not fire again until tomorrow's midnight."""
        ran_this_morning = "2026-02-27T00:05:00"
        task = daily_at_task("00:00", last_run=ran_this_morning)
        assert should_run_task(task, NOW) is False
