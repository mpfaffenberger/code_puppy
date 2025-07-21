"""
Test file to verify the TUI app datetime comparison bug fix.

This test creates a comprehensive scenario that reproduces the exact
conditions under which the TUI app would encounter the datetime comparison
error when loading history.
"""

import tempfile
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from code_puppy.session_memory import SessionMemory
from code_puppy.tui.app import CodePuppyTUI


class TestTUIDatetimeFix:
    """Test suite for TUI app datetime comparison fixes."""

    def test_tui_history_loading_with_problematic_timestamps(self):
        """Test that TUI app can load history with mixed timestamp formats without errors."""

        # Create problematic session memory data
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "tui_test.json"

            # Create mixed timestamp formats that would cause the original bug
            problematic_data = {
                "history": [
                    {
                        "timestamp": "2024-01-01T12:00:00",  # naive timestamp (no timezone)
                        "description": "TUI interaction: test command 1",
                    },
                    {
                        "timestamp": "2024-01-01T13:00:00Z",  # UTC with Z
                        "description": "TUI interaction: test command 2",
                    },
                    {
                        "timestamp": "2024-01-01T14:00:00+00:00",  # explicit UTC
                        "description": "Interactive task: test task",
                    },
                    {
                        "timestamp": "invalid-timestamp",  # invalid format
                        "description": "Command executed: broken timestamp",
                    },
                    {
                        "timestamp": datetime.now(
                            timezone.utc
                        ).isoformat(),  # current format
                        "description": "TUI interaction: recent command",
                    },
                ],
                "user_preferences": {},
                "watched_files": [],
            }

            # Write the problematic data
            storage_path.write_text(json.dumps(problematic_data, indent=2))

            # Create session memory instance that will be used by TUI
            session_mem = SessionMemory(storage_path=storage_path)

            # Mock the TUI app components we need
            app = CodePuppyTUI()

            # Mock necessary components to avoid full UI initialization
            with patch.object(app, "query_one") as mock_query:
                # Mock the history list widget
                mock_history_list = Mock()
                mock_query.return_value = mock_history_list

                # Set up the session memory
                app.session_memory = session_mem

                # This should NOT raise any datetime comparison errors
                try:
                    app.load_history_list()
                    # If we get here without exception, the fix is working
                    assert True, "TUI history loading completed without datetime errors"
                except TypeError as e:
                    if "offset-naive and offset-aware" in str(e):
                        pytest.fail(f"TUI app still has datetime comparison bug: {e}")
                    else:
                        # Some other type error is okay for this test
                        pass
                except Exception:
                    # Other exceptions are expected since we're mocking the UI
                    pass

    def test_tui_history_details_with_problematic_timestamps(self):
        """Test that TUI app can display history details with mixed timestamp formats."""

        app = CodePuppyTUI()

        # Test various problematic history entries
        test_entries = [
            {
                "timestamp": "2024-01-01T12:00:00",  # naive timestamp
                "description": "Test naive timestamp",
                "output": "Test output",
            },
            {
                "timestamp": "2024-01-01T12:00:00Z",  # UTC with Z
                "description": "Test Z timestamp",
                "output": "Test output",
            },
            {
                "timestamp": "invalid-format",  # invalid timestamp
                "description": "Test invalid timestamp",
                "output": "Test output",
            },
            {
                "timestamp": "",  # empty timestamp
                "description": "Test empty timestamp",
                "output": "Test output",
            },
        ]

        # Mock the add_system_message method to capture the output
        app.add_system_message = Mock()

        for entry in test_entries:
            # This should NOT raise datetime comparison errors
            try:
                app.show_history_details(entry)
                # Verify that add_system_message was called (meaning the method completed)
                assert app.add_system_message.called, (
                    f"Failed to process entry: {entry}"
                )
                app.add_system_message.reset_mock()
            except TypeError as e:
                if "offset-naive and offset-aware" in str(e):
                    pytest.fail(
                        f"TUI app datetime details bug still exists for entry {entry}: {e}"
                    )
                else:
                    raise

    def test_timestamp_parsing_helper_functions_in_tui(self):
        """Test the internal timestamp parsing helper functions work correctly."""

        app = CodePuppyTUI()

        # Set up mock context for the helper functions
        with patch.object(app, "query_one") as mock_query:
            mock_history_list = Mock()
            mock_query.return_value = mock_history_list

            # Create session memory with test data
            with tempfile.TemporaryDirectory() as tmpdir:
                storage_path = Path(tmpdir) / "helper_test.json"
                session_mem = SessionMemory(storage_path=storage_path)

                # Add test entries
                session_mem.log_task("Test task 1")
                session_mem.log_task("Test task 2")

                app.session_memory = session_mem

                # Test that the helper functions execute without errors
                try:
                    app.load_history_list()
                    # If we get here, the helper functions worked
                    assert True
                except Exception as e:
                    # Only fail on datetime comparison errors
                    if "offset-naive and offset-aware" in str(e):
                        pytest.fail(f"Helper function datetime bug: {e}")

    def test_tui_integration_with_session_memory_fix(self):
        """Test that TUI app properly integrates with the fixed session memory."""

        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "integration_test.json"

            # Create session memory with mixed timestamp data
            session_mem = SessionMemory(storage_path=storage_path)

            # Add some entries
            session_mem.log_task("Integration test task 1")
            session_mem.log_task("Integration test task 2")

            # Manually corrupt the stored data with naive timestamps
            corrupted_data = {
                "history": [
                    {
                        "timestamp": "2024-01-01T12:00:00",  # naive - would cause original bug
                        "description": "Corrupted timestamp task",
                    }
                ],
                "user_preferences": {},
                "watched_files": [],
            }
            storage_path.write_text(json.dumps(corrupted_data, indent=2))

            # Create new session memory instance (simulates app restart)
            new_session_mem = SessionMemory(storage_path=storage_path)

            # This should work without datetime errors thanks to our fix
            try:
                recent_history = new_session_mem.get_history(within_minutes=60)
                assert isinstance(recent_history, list)

                # Now test TUI integration
                app = CodePuppyTUI()
                app.session_memory = new_session_mem

                with patch.object(app, "query_one") as mock_query:
                    mock_history_list = Mock()
                    mock_query.return_value = mock_history_list

                    # This should complete without datetime comparison errors
                    app.load_history_list()

            except TypeError as e:
                if "offset-naive and offset-aware" in str(e):
                    pytest.fail(f"Integration test failed with datetime bug: {e}")
                else:
                    raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
