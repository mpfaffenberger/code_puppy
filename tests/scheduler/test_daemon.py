"""Tests for scheduler daemon functionality."""

from datetime import datetime, timedelta

from code_puppy.scheduler.daemon import (
    parse_interval,
    should_run_task,
)
from code_puppy.scheduler.config import ScheduledTask


class TestParseInterval:
    """Tests for interval parsing."""

    def test_parse_seconds(self):
        """Test parsing seconds interval."""
        result = parse_interval("30s")
        assert result == timedelta(seconds=30)

    def test_parse_minutes(self):
        """Test parsing minutes interval."""
        result = parse_interval("15m")
        assert result == timedelta(minutes=15)

    def test_parse_hours(self):
        """Test parsing hours interval."""
        result = parse_interval("2h")
        assert result == timedelta(hours=2)

    def test_parse_days(self):
        """Test parsing days interval."""
        result = parse_interval("7d")
        assert result == timedelta(days=7)

    def test_parse_invalid(self):
        """Test parsing invalid interval."""
        assert parse_interval("invalid") is None
        assert parse_interval("") is None
        assert parse_interval("10x") is None

    def test_parse_case_insensitive(self):
        """Test case insensitivity."""
        assert parse_interval("1H") == timedelta(hours=1)
        assert parse_interval("30M") == timedelta(minutes=30)


class TestShouldRunTask:
    """Tests for task scheduling logic."""

    def test_disabled_task_should_not_run(self):
        """Test that disabled tasks don't run."""
        task = ScheduledTask(
            name="Disabled",
            prompt="Test",
            enabled=False,
            schedule_type="interval",
            schedule_value="1h",
        )
        assert should_run_task(task, datetime.now()) is False

    def test_never_run_task_should_run(self):
        """Test that tasks that never ran should run."""
        task = ScheduledTask(
            name="Never Run",
            prompt="Test",
            enabled=True,
            schedule_type="interval",
            schedule_value="1h",
            last_run=None,
        )
        assert should_run_task(task, datetime.now()) is True

    def test_interval_not_elapsed(self):
        """Test task where interval hasn't elapsed."""
        task = ScheduledTask(
            name="Recent",
            prompt="Test",
            enabled=True,
            schedule_type="interval",
            schedule_value="1h",
            last_run=datetime.now().isoformat(),
        )
        assert should_run_task(task, datetime.now()) is False

    def test_interval_elapsed(self):
        """Test task where interval has elapsed."""
        task = ScheduledTask(
            name="Old",
            prompt="Test",
            enabled=True,
            schedule_type="interval",
            schedule_value="1h",
            last_run=(datetime.now() - timedelta(hours=2)).isoformat(),
        )
        assert should_run_task(task, datetime.now()) is True

    def test_hourly_schedule(self):
        """Test hourly schedule type."""
        task = ScheduledTask(
            name="Hourly",
            prompt="Test",
            enabled=True,
            schedule_type="hourly",
            schedule_value="1h",
            last_run=(datetime.now() - timedelta(hours=2)).isoformat(),
        )
        assert should_run_task(task, datetime.now()) is True

    def test_daily_schedule(self):
        """Test daily schedule type."""
        task = ScheduledTask(
            name="Daily",
            prompt="Test",
            enabled=True,
            schedule_type="daily",
            schedule_value="24h",
            last_run=(datetime.now() - timedelta(days=2)).isoformat(),
        )
        assert should_run_task(task, datetime.now()) is True

    def test_cron_schedule_skipped(self):
        """Test that cron schedules are currently skipped."""
        task = ScheduledTask(
            name="Cron",
            prompt="Test",
            enabled=True,
            schedule_type="cron",
            schedule_value="0 * * * *",
        )
        # Cron is not implemented, should return False
        assert should_run_task(task, datetime.now()) is False
