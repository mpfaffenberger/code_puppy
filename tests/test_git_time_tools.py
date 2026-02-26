"""Tests for git_time_tools module."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from code_puppy.plugins.walmart_specific.git_time_tools import (
    GitTimeEstimateOutput,
    WorkSession,
    _format_duration,
    _group_into_sessions,
    git_estimated_time,
    SESSION_GAP_THRESHOLD,
    MIN_COMMIT_TIME,
)


# =============================================================================
# WorkSession
# =============================================================================


class TestWorkSession:
    def test_single_commit_gets_minimum_time(self):
        now = datetime.now(timezone.utc)
        session = WorkSession(
            start_time=now,
            end_time=now,
            commit_count=1,
        )
        # Single commit should get at least MIN_COMMIT_TIME
        assert session.duration_seconds >= MIN_COMMIT_TIME

    def test_multi_commit_session_duration(self):
        start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)  # 2 hours later
        session = WorkSession(
            start_time=start,
            end_time=end,
            commit_count=5,
        )
        # Should be 2 hours + MIN_COMMIT_TIME for first commit
        expected = 2 * 3600 + MIN_COMMIT_TIME
        assert session.duration_seconds == expected


# =============================================================================
# Session Grouping
# =============================================================================


class TestGroupIntoSessions:
    def test_empty_list(self):
        assert _group_into_sessions([]) == []

    def test_single_commit(self):
        now = datetime.now(timezone.utc)
        sessions = _group_into_sessions([now])
        assert len(sessions) == 1
        assert sessions[0].commit_count == 1

    def test_close_commits_same_session(self):
        base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        timestamps = [
            base,
            base + timedelta(minutes=30),
            base + timedelta(minutes=60),
        ]
        sessions = _group_into_sessions(timestamps)
        assert len(sessions) == 1
        assert sessions[0].commit_count == 3

    def test_gap_creates_new_session(self):
        base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        timestamps = [
            base,
            base + timedelta(minutes=30),
            # Big gap - more than SESSION_GAP_THRESHOLD
            base + timedelta(hours=5),
            base + timedelta(hours=5, minutes=15),
        ]
        sessions = _group_into_sessions(timestamps)
        assert len(sessions) == 2
        assert sessions[0].commit_count == 2
        assert sessions[1].commit_count == 2

    def test_unordered_timestamps_sorted(self):
        base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        # Out of order
        timestamps = [
            base + timedelta(hours=1),
            base,
            base + timedelta(minutes=30),
        ]
        sessions = _group_into_sessions(timestamps)
        assert len(sessions) == 1
        assert sessions[0].commit_count == 3


# =============================================================================
# Format Duration
# =============================================================================


class TestFormatDuration:
    def test_minutes(self):
        assert "30 minutes" in _format_duration(0.5)

    def test_hours(self):
        assert "5.0 hours" in _format_duration(5)

    def test_workdays(self):
        result = _format_duration(40)
        assert "workday" in result.lower()


# =============================================================================
# Git Estimated Time (Integration)
# =============================================================================


class TestGitEstimatedTime:
    def test_not_git_repo(self, tmp_path):
        result = git_estimated_time(cwd=str(tmp_path))
        assert result.success is False
        assert "not a git repository" in result.error.lower()

    def test_git_repo_with_commits(self, tmp_path):
        """Test with a real temporary git repo."""
        import subprocess

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create some commits
        for i in range(3):
            (tmp_path / f"file{i}.txt").write_text(f"content {i}")
            subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}"],
                cwd=tmp_path,
                capture_output=True,
            )

        result = git_estimated_time(cwd=str(tmp_path))

        assert result.success is True
        assert result.total_commits == 3
        assert result.work_sessions >= 1
        assert result.estimated_hours is not None
        assert result.estimated_hours > 0
        assert result.message is not None

    def test_empty_git_repo(self, tmp_path):
        """Test git repo with no commits."""
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        result = git_estimated_time(cwd=str(tmp_path))

        assert result.success is False
        assert "no commits" in result.error.lower()
