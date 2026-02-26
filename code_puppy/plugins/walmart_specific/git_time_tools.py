"""Git time estimation tool for PuppyTales.

Estimates total development time by analyzing git commit patterns.
Groups commits into "work sessions" based on time proximity.
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Configuration
# =============================================================================

# Max gap between commits to be considered same session (in seconds)
SESSION_GAP_THRESHOLD = 2 * 60 * 60  # 2 hours

# Minimum time to attribute to a single commit (assumed work before commit)
MIN_COMMIT_TIME = 15 * 60  # 15 minutes

# Max commits to analyze (no limit effectively)
MAX_COMMITS = 100000


# =============================================================================
# Output Models
# =============================================================================


class GitTimeEstimateOutput(BaseModel):
    """Result of git time estimation."""

    success: bool = Field(description="Whether estimation succeeded")
    estimated_hours: Optional[float] = Field(
        default=None, description="Estimated total development hours"
    )
    estimated_days: Optional[float] = Field(
        default=None, description="Estimated development days (8hr workdays)"
    )
    total_commits: Optional[int] = Field(
        default=None, description="Total commits analyzed"
    )
    work_sessions: Optional[int] = Field(
        default=None, description="Number of distinct work sessions detected"
    )
    first_commit_date: Optional[str] = Field(
        default=None, description="Date of first commit"
    )
    last_commit_date: Optional[str] = Field(
        default=None, description="Date of most recent commit"
    )
    calendar_days: Optional[int] = Field(
        default=None, description="Calendar days from first to last commit"
    )
    avg_session_hours: Optional[float] = Field(
        default=None, description="Average hours per work session"
    )
    main_branch_only: bool = Field(
        default=False, description="Deprecated - always analyzes full tree now"
    )
    message: Optional[str] = Field(
        default=None, description="Human-readable summary"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if estimation failed"
    )


@dataclass
class WorkSession:
    """A group of commits representing a work session."""

    start_time: datetime
    end_time: datetime
    commit_count: int

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds, with minimum time for single commits."""
        actual_duration = (self.end_time - self.start_time).total_seconds()
        # Add minimum time for the first commit (work before committing)
        return max(actual_duration + MIN_COMMIT_TIME, MIN_COMMIT_TIME)


# =============================================================================
# Core Functions
# =============================================================================


def _is_git_repo(cwd: Optional[str] = None) -> bool:
    """Check if current directory is a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=cwd,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_commit_count(cwd: Optional[str] = None, branch: Optional[str] = None) -> int:
    """Get total commit count quickly."""
    try:
        cmd = ["git", "rev-list", "--count"]
        if branch:
            cmd.append(branch)
        else:
            cmd.append("--all")

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 0


def _get_main_branch(cwd: Optional[str] = None) -> str:
    """Detect the main branch name (main, master, etc)."""
    for branch in ["main", "master", "trunk", "develop"]:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=cwd,
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return branch
    return "HEAD"  # Fallback to current HEAD


def _get_commit_timestamps(
    cwd: Optional[str] = None,
    branch: Optional[str] = None,
    max_commits: int = MAX_COMMITS,
) -> list[datetime]:
    """Get commit timestamps, newest first."""
    try:
        cmd = ["git", "log", "--format=%at", f"-n{max_commits}"]
        if branch:
            cmd.append(branch)
        else:
            cmd.append("--all")

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        timestamps = []
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    ts = int(line)
                    timestamps.append(datetime.fromtimestamp(ts, tz=timezone.utc))
                except ValueError:
                    continue

        return timestamps

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _group_into_sessions(timestamps: list[datetime]) -> list[WorkSession]:
    """Group timestamps into work sessions based on time gaps."""
    if not timestamps:
        return []

    # Sort oldest first for session building
    sorted_times = sorted(timestamps)

    sessions: list[WorkSession] = []
    session_start = sorted_times[0]
    session_end = sorted_times[0]
    session_commits = 1

    for i in range(1, len(sorted_times)):
        current = sorted_times[i]
        gap = (current - session_end).total_seconds()

        if gap <= SESSION_GAP_THRESHOLD:
            # Same session - extend it
            session_end = current
            session_commits += 1
        else:
            # New session - save the old one and start fresh
            sessions.append(
                WorkSession(
                    start_time=session_start,
                    end_time=session_end,
                    commit_count=session_commits,
                )
            )
            session_start = current
            session_end = current
            session_commits = 1

    # Don't forget the last session
    sessions.append(
        WorkSession(
            start_time=session_start,
            end_time=session_end,
            commit_count=session_commits,
        )
    )

    return sessions


def _format_duration(hours: float) -> str:
    """Format hours into a human-readable string."""
    if hours < 1:
        return f"{int(hours * 60)} minutes"
    elif hours < 24:
        return f"{hours:.1f} hours"
    else:
        days = hours / 8  # 8-hour workdays
        if days < 5:
            return f"{hours:.1f} hours (~{days:.1f} workdays)"
        else:
            return f"{days:.1f} workdays ({hours:.0f} hours)"


def git_estimated_time(cwd: Optional[str] = None) -> GitTimeEstimateOutput:
    """Estimate total development time from git commit history.

    Analyzes commit timestamps to detect work sessions and estimate
    total development effort.

    Args:
        cwd: Working directory (defaults to current directory).

    Returns:
        GitTimeEstimateOutput with estimated hours, sessions, etc.
    """
    # Resolve working directory
    if cwd:
        work_dir = str(Path(cwd).expanduser().resolve())
    else:
        work_dir = None

    # Check if this is a git repo
    if not _is_git_repo(work_dir):
        return GitTimeEstimateOutput(
            success=False,
            error="Not a git repository",
        )

    # Get commit timestamps from entire tree
    timestamps = _get_commit_timestamps(work_dir, branch=None, max_commits=MAX_COMMITS)

    if not timestamps:
        return GitTimeEstimateOutput(
            success=False,
            error="No commits found or git command failed",
        )

    # Group into sessions
    sessions = _group_into_sessions(timestamps)

    # Calculate totals
    total_seconds = sum(s.duration_seconds for s in sessions)
    total_hours = total_seconds / 3600
    total_days = total_hours / 8  # 8-hour workdays

    # Get date range
    sorted_times = sorted(timestamps)
    first_commit = sorted_times[0]
    last_commit = sorted_times[-1]
    calendar_days = (last_commit - first_commit).days + 1

    # Average session duration
    avg_session_hours = total_hours / len(sessions) if sessions else 0

    # Build human-readable message
    duration_str = _format_duration(total_hours)
    message = (
        f"Estimated {duration_str} of development time across "
        f"{len(sessions)} work sessions and {len(timestamps)} commits."
    )

    return GitTimeEstimateOutput(
        success=True,
        estimated_hours=round(total_hours, 1),
        estimated_days=round(total_days, 1),
        total_commits=len(timestamps),
        work_sessions=len(sessions),
        first_commit_date=first_commit.strftime("%Y-%m-%d"),
        last_commit_date=last_commit.strftime("%Y-%m-%d"),
        calendar_days=calendar_days,
        avg_session_hours=round(avg_session_hours, 2),
        main_branch_only=False,
        message=message,
    )


# =============================================================================
# Tool Registration
# =============================================================================


def register_git_estimated_time(agent):
    """Register the git_estimated_time tool with an agent."""
    from pydantic_ai import RunContext

    @agent.tool
    def git_estimated_time_tool(
        context: RunContext,
        cwd: str = "",
    ) -> GitTimeEstimateOutput:
        """Estimate total development time from git commit history.

        Analyzes commit timestamps to detect work sessions and estimate
        how much time was spent developing the project. Groups commits
        that are close together (within 2 hours) into "work sessions".

        Args:
            context: Run context (injected automatically).
            cwd: Working directory (defaults to current directory).

        Returns:
            GitTimeEstimateOutput with:
            - estimated_hours: Total estimated development hours
            - estimated_days: Workdays (8-hour days)
            - work_sessions: Number of distinct coding sessions
            - total_commits: Commits analyzed
            - avg_session_hours: Average session length
            - calendar_days: Wall-clock days from first to last commit
        """
        return git_estimated_time(cwd=cwd if cwd else None)
