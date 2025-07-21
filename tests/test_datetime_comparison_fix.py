"""
Test file to reproduce and validate the datetime comparison bug fix.

This addresses the error:
"can't compare offset-naive and offset-aware datetimes"

The bug occurs when comparing timezone-aware cutoff times with
potentially timezone-naive parsed timestamps from session history.
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from code_puppy.session_memory import SessionMemory


class TestDatetimeComparisonFix:
    """Test suite for datetime comparison issues in session memory."""

    def test_get_history_with_timezone_aware_timestamps(self):
        """Test that timezone-aware timestamps work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = SessionMemory(storage_path=Path(tmpdir) / "tz_aware.json")

            # Log a task (this should create timezone-aware timestamp)
            mem.log_task("Test task with timezone")

            # Get recent history - this should not throw datetime comparison error
            recent_history = mem.get_history(within_minutes=60)
            assert len(recent_history) == 1
            assert recent_history[0]["description"] == "Test task with timezone"

    def test_get_history_with_mixed_timestamp_formats(self):
        """Test handling of mixed timezone-naive and timezone-aware timestamps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "mixed_tz.json"

            # Create a memory with manually crafted problematic timestamps
            problematic_data = {
                "history": [
                    {
                        "timestamp": "2024-01-01T12:00:00",  # naive timestamp
                        "description": "Naive timestamp task",
                    },
                    {
                        "timestamp": "2024-01-01T12:00:00Z",  # UTC with Z
                        "description": "UTC with Z timestamp task",
                    },
                    {
                        "timestamp": "2024-01-01T12:00:00+00:00",  # explicit UTC
                        "description": "Explicit UTC timestamp task",
                    },
                    {
                        "timestamp": datetime.now(
                            timezone.utc
                        ).isoformat(),  # current format
                        "description": "Current format timestamp task",
                    },
                ],
                "user_preferences": {},
                "watched_files": [],
            }

            # Write the problematic data to file
            storage_path.write_text(json.dumps(problematic_data, indent=2))

            # Now try to load and get history - this should handle all formats gracefully
            mem = SessionMemory(storage_path=storage_path)

            # This call should NOT raise "can't compare offset-naive and offset-aware datetimes"
            try:
                recent_history = mem.get_history(within_minutes=60)
                # If we get here without exception, the fix is working
                assert isinstance(recent_history, list)
            except TypeError as e:
                if "offset-naive and offset-aware" in str(e):
                    pytest.fail(f"Datetime comparison bug still exists: {e}")
                else:
                    raise

    def test_get_history_with_invalid_timestamp_formats(self):
        """Test handling of completely invalid timestamp formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "invalid_tz.json"

            # Create data with invalid timestamps
            invalid_data = {
                "history": [
                    {
                        "timestamp": "not-a-timestamp",
                        "description": "Invalid timestamp task",
                    },
                    {"timestamp": "", "description": "Empty timestamp task"},
                    {
                        "timestamp": "2024-13-45T99:99:99",  # impossible date
                        "description": "Impossible timestamp task",
                    },
                ],
                "user_preferences": {},
                "watched_files": [],
            }

            storage_path.write_text(json.dumps(invalid_data, indent=2))

            # Should handle invalid timestamps gracefully
            mem = SessionMemory(storage_path=storage_path)
            recent_history = mem.get_history(within_minutes=60)

            # Invalid timestamps should be filtered out or handled gracefully
            assert isinstance(recent_history, list)

    def test_reproduce_original_bug_scenario(self):
        """
        Reproduce the exact scenario that caused the original bug.

        This test simulates the conditions where the error occurred:
        - timezone-aware cutoff time
        - timezone-naive stored timestamp
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "bug_repro.json"

            # Create a scenario that would trigger the original bug
            # This simulates old data with naive timestamps
            now_naive = datetime.now()  # This is naive (no timezone)

            bug_data = {
                "history": [
                    {
                        "timestamp": now_naive.isoformat(),  # This creates naive timestamp
                        "description": "Task that causes comparison bug",
                    }
                ],
                "user_preferences": {},
                "watched_files": [],
            }

            storage_path.write_text(json.dumps(bug_data, indent=2))

            # Load the session memory
            mem = SessionMemory(storage_path=storage_path)

            # This specific call should trigger the bug if not fixed
            # The cutoff will be timezone-aware, but stored timestamp is naive
            try:
                recent_history = mem.get_history(within_minutes=1)
                # Success means the bug is fixed
                assert isinstance(recent_history, list)
            except TypeError as e:
                if "offset-naive and offset-aware" in str(e):
                    pytest.fail(
                        "BUG REPRODUCED: The datetime comparison bug still exists. "
                        f"Error: {e}"
                    )
                else:
                    raise

    def test_timezone_consistency_after_save_load_cycle(self):
        """Test that timestamps remain consistent through save/load cycles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = SessionMemory(storage_path=Path(tmpdir) / "consistency.json")

            # Log several tasks
            mem.log_task("Task 1")
            mem.log_task("Task 2")
            mem.log_task("Task 3")

            # Get history immediately
            immediate_history = mem.get_history(within_minutes=5)

            # Create new SessionMemory instance (simulates app restart)
            mem2 = SessionMemory(storage_path=Path(tmpdir) / "consistency.json")

            # Get history after reload
            reloaded_history = mem2.get_history(within_minutes=5)

            # Should be able to get history without datetime comparison errors
            assert len(immediate_history) == len(reloaded_history) == 3

            # Timestamps should be parseable and comparable
            for entry in reloaded_history:
                timestamp_str = entry["timestamp"]
                # This should not raise an exception
                parsed_ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                assert isinstance(parsed_ts, datetime)

    def test_cutoff_time_comparison_edge_cases(self):
        """Test edge cases for cutoff time comparisons."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = SessionMemory(storage_path=Path(tmpdir) / "edge_cases.json")

            # Log tasks at different times (simulate via manual timestamp manipulation)
            base_time = datetime.now(timezone.utc)

            # Create entries with different timestamp formats that might cause issues
            test_entries = [
                {
                    "timestamp": (base_time - timedelta(minutes=5)).isoformat(),
                    "description": "5 minutes ago",
                },
                {
                    "timestamp": (base_time - timedelta(hours=1)).isoformat(),
                    "description": "1 hour ago",
                },
                {
                    "timestamp": (base_time - timedelta(days=1)).isoformat(),
                    "description": "1 day ago",
                },
            ]

            # Manually set up the data
            mem._data["history"] = test_entries
            mem._save()

            # Test various cutoff times
            recent_5min = mem.get_history(within_minutes=10)  # Should get first entry
            recent_30min = mem.get_history(within_minutes=30)  # Should get first entry
            recent_2hours = mem.get_history(within_minutes=120)  # Should get first two

            assert len(recent_5min) >= 1
            assert len(recent_30min) >= 1
            assert len(recent_2hours) >= 2

    def test_datetime_comparison_with_various_formats(self):
        """Test datetime parsing and comparison with various ISO format variations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "formats.json"

            # Various ISO format timestamp variations that could cause issues
            format_variations = [
                datetime.now(timezone.utc).isoformat(),  # Standard format
                datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),  # Z format
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),  # No timezone
                datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%f"
                ),  # Microseconds, no tz
                datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%S.%f+00:00"
                ),  # Full format
            ]

            history_entries = []
            for i, ts_format in enumerate(format_variations):
                history_entries.append(
                    {"timestamp": ts_format, "description": f"Format variation {i + 1}"}
                )

            data = {
                "history": history_entries,
                "user_preferences": {},
                "watched_files": [],
            }

            storage_path.write_text(json.dumps(data, indent=2))

            # Load and test
            mem = SessionMemory(storage_path=storage_path)

            # This should handle all format variations without comparison errors
            try:
                all_history = mem.get_history()
                recent_history = mem.get_history(within_minutes=60)

                assert len(all_history) == len(format_variations)
                assert isinstance(recent_history, list)

            except TypeError as e:
                if "offset-naive and offset-aware" in str(e):
                    pytest.fail(
                        f"Format handling failed with datetime comparison error: {e}"
                    )
                else:
                    raise

    def test_app_history_loading_simulation(self):
        """Simulate the exact scenario from TUI app history loading."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "app_simulation.json"

            # Create session memory and log some TUI interactions
            mem = SessionMemory(storage_path=storage_path)

            # Simulate TUI interactions that would be logged
            mem.log_task(
                "TUI interaction: help command", extras={"output": "Help displayed"}
            )
            mem.log_task(
                "TUI interaction: file listing", extras={"output": "Files listed"}
            )
            mem.log_task(
                "Interactive task: create new file",
                extras={"awaiting_user_input": False},
            )

            # Now simulate what happens in TUI app load_history_list method
            try:
                # This mimics the exact call from tui/app.py line around 463
                recent_history = mem.get_history(
                    within_minutes=24 * 60
                )  # Last 24 hours

                # Filter like the app does
                filtered_history = [
                    entry
                    for entry in recent_history
                    if not entry.get("description", "").startswith("Agent loaded")
                ]

                # The app processes timestamps like this (around line 469 in app.py)
                for entry in filtered_history:
                    timestamp_str = entry.get("timestamp", "")
                    # This exact line from app.py should not fail
                    timestamp_obj = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                    assert isinstance(timestamp_obj, datetime)

                assert len(filtered_history) == 3  # All our test entries

            except TypeError as e:
                if "offset-naive and offset-aware" in str(e):
                    pytest.fail(
                        "TUI app history loading simulation failed with datetime comparison error. "
                        f"This reproduces the original bug: {e}"
                    )
                else:
                    raise


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])
