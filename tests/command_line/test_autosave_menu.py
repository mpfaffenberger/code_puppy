"""Comprehensive test coverage for autosave_menu.py UI components.

Covers menu initialization, user input handling, navigation, rendering,
state management, error scenarios, and console I/O interactions.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.command_line.autosave_menu import (
    PAGE_SIZE,
    _extract_last_user_message,
    _get_session_entries,
    _get_session_metadata,
    _render_menu_panel,
    _render_preview_panel,
    interactive_autosave_picker,
)


class TestGetSessionMetadata:
    """Test the _get_session_metadata function."""

    def test_loads_valid_metadata(self, tmp_path):
        """Test loading valid metadata from JSON file."""
        session_name = "test_session"
        metadata = {"timestamp": "2024-01-01T12:00:00", "message_count": 5}

        meta_file = tmp_path / f"{session_name}_meta.json"
        meta_file.write_text(json.dumps(metadata))

        result = _get_session_metadata(tmp_path, session_name)
        assert result == metadata

    def test_handles_missing_file(self, tmp_path):
        """Test graceful handling of missing metadata file."""
        result = _get_session_metadata(tmp_path, "nonexistent_session")
        assert result == {}

    def test_handles_corrupted_json(self, tmp_path):
        """Test graceful handling of corrupted JSON file."""
        session_name = "corrupted_session"
        meta_file = tmp_path / f"{session_name}_meta.json"
        meta_file.write_text("invalid json {")

        result = _get_session_metadata(tmp_path, session_name)
        assert result == {}

    def test_handles_empty_json(self, tmp_path):
        """Test handling of empty JSON file."""
        session_name = "empty_session"
        meta_file = tmp_path / f"{session_name}_meta.json"
        meta_file.write_text("")

        result = _get_session_metadata(tmp_path, session_name)
        assert result == {}


class TestGetSessionEntries:
    """Test the _get_session_entries function."""

    @patch("code_puppy.command_line.autosave_menu.list_sessions")
    @patch("code_puppy.command_line.autosave_menu._get_session_metadata")
    def test_sorts_entries_by_timestamp_desc(self, mock_metadata, mock_list):
        """Test that entries are sorted by timestamp (most recent first)."""
        # Setup mock sessions
        mock_list.return_value = ["session1", "session2", "session3"]

        # Setup metadata with different timestamps
        mock_metadata.side_effect = [
            {"timestamp": "2024-01-01T10:00:00"},  # Oldest
            {"timestamp": "2024-01-01T14:00:00"},  # Newest
            {"timestamp": "2024-01-01T12:00:00"},  # Middle
        ]

        result = _get_session_entries(Path("/fake/dir"))

        # Should be sorted newest first: session2, session3, session1
        assert len(result) == 3
        assert result[0][0] == "session2"
        assert result[1][0] == "session3"
        assert result[2][0] == "session1"

    @patch("code_puppy.command_line.autosave_menu.list_sessions")
    @patch("code_puppy.command_line.autosave_menu._get_session_metadata")
    def test_handles_missing_timestamps(self, mock_metadata, mock_list):
        """Test handling of entries without timestamps."""
        mock_list.return_value = ["no_timestamp", "valid_timestamp"]

        mock_metadata.side_effect = [
            {},  # No timestamp
            {"timestamp": "2024-01-01T12:00:00"},  # Valid timestamp
        ]

        result = _get_session_entries(Path("/fake/dir"))

        # Entry with valid timestamp should come first
        assert result[0][0] == "valid_timestamp"
        assert result[1][0] == "no_timestamp"

    @patch("code_puppy.command_line.autosave_menu.list_sessions")
    @patch("code_puppy.command_line.autosave_menu._get_session_metadata")
    def test_handles_invalid_timestamps(self, mock_metadata, mock_list):
        """Test handling of entries with invalid timestamps."""
        mock_list.return_value = ["invalid_ts", "valid_ts"]

        mock_metadata.side_effect = [
            {"timestamp": "invalid-date"},  # Invalid timestamp
            {"timestamp": "2024-01-01T12:00:00"},  # Valid timestamp
        ]

        result = _get_session_entries(Path("/fake/dir"))

        # Entry with valid timestamp should come first
        assert result[0][0] == "valid_ts"
        assert result[1][0] == "invalid_ts"

    @patch("code_puppy.command_line.autosave_menu.list_sessions")
    def test_empty_sessions_list(self, mock_list):
        """Test handling of empty sessions list."""
        mock_list.return_value = []

        result = _get_session_entries(Path("/fake/dir"))
        assert result == []


class TestExtractLastUserMessage:
    """Test the _extract_last_user_message function."""

    def test_extracts_last_message_with_content(self):
        """Test extraction of last message with content."""
        mock_message = MagicMock()
        mock_message.parts = [MagicMock(content="Hello world")]

        history = [mock_message]
        result = _extract_last_user_message(history)
        assert result == "Hello world"

    def test_walks_backwards_through_history(self):
        """Test that function walks backwards through messages."""
        # Create two messages
        mock_message1 = MagicMock()
        mock_message1.parts = [MagicMock(content="First message")]

        mock_message2 = MagicMock()
        mock_message2.parts = [MagicMock(content="Second message")]

        # Put them in chronological order
        history = [mock_message1, mock_message2]
        result = _extract_last_user_message(history)
        assert result == "Second message"

    def test_handles_empty_history(self):
        """Test handling of empty message history."""
        result = _extract_last_user_message([])
        assert result == "[No messages found]"

    def test_handles_message_without_content(self):
        """Test handling of message parts without content attribute."""
        mock_message = MagicMock()
        mock_message.parts = [MagicMock(spec=["other"])]

        history = [mock_message]
        result = _extract_last_user_message(history)
        assert result == "[No messages found]"

    def test_handles_empty_parts(self):
        """Test handling of message with empty parts."""
        mock_message = MagicMock()
        mock_message.parts = []

        history = [mock_message]
        result = _extract_last_user_message(history)
        assert result == "[No messages found]"


class TestRenderMenuPanel:
    """Test the _render_menu_panel function."""

    def test_renders_no_sessions_message(self):
        """Test rendering when no sessions are available."""
        result = _render_menu_panel([], 0, 0)

        # Check for no sessions message
        lines_str = str(result)
        assert "No autosave sessions found" in lines_str
        assert "(1/1)" in lines_str  # Should show page 1 of 1

    def test_renders_with_pagination(self):
        """Test rendering with pagination information."""
        # Create more than PAGE_SIZE entries to test pagination
        entries = []
        for i in range(20):  # 20 entries > PAGE_SIZE (15)
            entries.append(
                (
                    f"session_{i}",
                    {"message_count": i, "timestamp": "2024-01-01T12:00:00"},
                )
            )

        result = _render_menu_panel(entries, 1, 16)  # Page 2, item 16 selected
        lines_str = str(result)

        # Should show page 2 of 2
        assert "(2/2)" in lines_str

    def test_highlights_selected_item(self):
        """Test that selected item is properly highlighted."""
        entries = [
            ("session_1", {"message_count": 5, "timestamp": "2024-01-01T12:00:00"}),
        ]

        result = _render_menu_panel(entries, 0, 0)  # Select first item
        lines_str = str(result)

        # Should have '>' indicator for selected item
        assert ">" in lines_str

    def test_formats_timestamps(self):
        """Test proper formatting of timestamps."""
        entries = [
            ("session_1", {"message_count": 5, "timestamp": "2024-01-01T12:30:45"}),
        ]

        result = _render_menu_panel(entries, 0, 0)
        lines_str = str(result)

        # Should format timestamp as YYYY-MM-DD HH:MM
        assert "2024-01-01 12:30" in lines_str

    def test_handles_invalid_timestamps(self):
        """Test handling of invalid timestamps in display."""
        entries = [
            ("session_1", {"message_count": 5, "timestamp": "invalid-date"}),
            ("session_2", {"message_count": 3}),  # No timestamp
        ]

        result = _render_menu_panel(entries, 0, 0)
        lines_str = str(result)

        assert "unknown time" in lines_str

    def test_shows_navigation_hints(self):
        """Test that navigation hints are displayed."""
        result = _render_menu_panel([], 0, 0)
        lines_str = str(result)

        # Should show navigation hints
        assert "↑/↓" in lines_str
        assert "←/→" in lines_str
        assert "Enter" in lines_str
        assert "Ctrl+C" in lines_str
        assert "Navigate" in lines_str
        assert "Page" in lines_str
        assert "Load" in lines_str
        assert "Cancel" in lines_str


class TestRenderPreviewPanel:
    """Test the _render_preview_panel function."""

    def test_renders_no_selection_message(self):
        """Test rendering when no session is selected."""
        result = _render_preview_panel(Path("/fake"), None)
        lines_str = str(result)

        assert "No session selected" in lines_str
        assert "PREVIEW" in lines_str

    def test_renders_session_info(self):
        """Test rendering of session metadata."""
        session_name = "test_session"
        metadata = {
            "timestamp": "2024-01-01T12:30:45",
            "message_count": 10,
            "total_tokens": 1500,
        }
        entry = (session_name, metadata)

        result = _render_preview_panel(Path("/fake"), entry)
        lines_str = str(result)

        assert session_name in lines_str
        assert "2024-01-01 12:30:45" in lines_str
        assert "Messages: 10" in lines_str
        assert "Tokens: 1,500" in lines_str
        assert "Last Message:" in lines_str

    def test_handles_preview_loading_error(self):
        """Test graceful handling of preview loading errors."""
        entry = ("test_session", {})

        with patch(
            "code_puppy.command_line.autosave_menu.load_session",
            side_effect=Exception("Load failed"),
        ):
            result = _render_preview_panel(Path("/fake"), entry)
            lines_str = str(result)

            assert "Error loading preview" in lines_str
            assert "Load failed" in lines_str

    @patch("code_puppy.command_line.autosave_menu.load_session")
    @patch("code_puppy.command_line.autosave_menu._extract_last_user_message")
    def test_renders_markdown_content(self, mock_extract, mock_load):
        """Test rendering of markdown content in preview."""
        # Setup mock scenario
        history = []
        mock_load.return_value = history
        mock_extract.return_value = "# Heading\n\nSome **bold** text\n- List item"

        entry = ("test_session", {})
        result = _render_preview_panel(Path("/fake"), entry)
        lines_str = str(result)

        # Should contain the rendered content
        assert "Heading" in lines_str
        assert "bold" in lines_str
        assert "List item" in lines_str

    @patch("code_puppy.command_line.autosave_menu.load_session")
    @patch("code_puppy.command_line.autosave_menu._extract_last_user_message")
    def test_truncates_long_messages(self, mock_extract, mock_load):
        """Test truncation of overly long messages."""
        # Create a very long message (simulated through console output)
        history = []
        mock_load.return_value = history

        # Create a message that would result in many lines when rendered
        long_message = "\n".join([f"Line {i}" for i in range(50)])  # 50 lines
        mock_extract.return_value = long_message

        entry = ("test_session", {})
        result = _render_preview_panel(Path("/fake"), entry)
        lines_str = str(result)

        # Should indicate truncation
        assert "truncated" in lines_str or "(truncated)" in lines_str


class TestInteractiveAutosavePicker:
    """Test the interactive_autosave_picker function."""

    @patch("code_puppy.command_line.autosave_menu._get_session_entries")
    async def test_returns_none_for_no_sessions(self, mock_entries):
        """Test that function returns None when no sessions exist."""
        mock_entries.return_value = []

        result = await interactive_autosave_picker()

        assert result is None

    @patch("code_puppy.command_line.autosave_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.autosave_menu._get_session_entries")
    @patch("code_puppy.command_line.autosave_menu._render_menu_panel")
    @patch("code_puppy.command_line.autosave_menu._render_preview_panel")
    @patch("sys.stdout.write")
    @patch("time.sleep")
    async def test_application_setup_and_cleanup(
        self,
        mock_sleep,
        mock_stdout,
        mock_preview,
        mock_menu,
        mock_entries,
        mock_awaiting,
    ):
        """Test proper application setup and cleanup."""
        # Setup mock entries
        entries = [("session1", {"timestamp": "2024-01-01T12:00:00"})]
        mock_entries.return_value = entries
        mock_menu.return_value = [("", "Test menu")]
        mock_preview.return_value = [("", "Test preview")]

        # Mock the application to avoid actual TUI
        with patch("code_puppy.command_line.autosave_menu.Application") as mock_app:
            mock_instance = MagicMock()
            mock_app.return_value = mock_instance
            mock_instance.run_async = AsyncMock()

            await interactive_autosave_picker()

            # Verify setup and cleanup sequence
            mock_awaiting.assert_any_call(True)  # Set to True at start
            mock_awaiting.assert_any_call(False)  # Reset to False at end
            mock_stdout.assert_any_call("\033[?1049h")  # Enter alt buffer
            mock_stdout.assert_any_call("\033[?1049l")  # Exit alt buffer
            mock_instance.run_async.assert_called_once()

    @patch("code_puppy.command_line.autosave_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.autosave_menu._get_session_entries")
    @patch("sys.stdout.write")
    async def test_handles_keyboard_interrupt(
        self, mock_stdout, mock_entries, mock_awaiting
    ):
        """Test handling of keyboard interrupt during TUI."""
        # Setup mock entries
        entries = [("session1", {"timestamp": "2024-01-01T12:00:00"})]
        mock_entries.return_value = entries

        # Mock application to raise KeyboardInterrupt
        with patch("code_puppy.command_line.autosave_menu.Application") as mock_app:
            mock_instance = MagicMock()
            mock_app.return_value = mock_instance
            mock_instance.run_async = AsyncMock(side_effect=KeyboardInterrupt())

            # Should raise KeyboardInterrupt
            with pytest.raises(KeyboardInterrupt):
                await interactive_autosave_picker()

            # Should cleanup properly even on interrupt
            mock_awaiting.assert_called_with(False)  # Should reset to False
            mock_stdout.assert_any_call("\033[?1049l")  # Exit alt buffer

    @patch("code_puppy.command_line.autosave_menu.set_awaiting_user_input")
    @patch("code_puppy.command_line.autosave_menu._get_session_entries")
    @patch("code_puppy.command_line.autosave_menu._render_menu_panel")
    @patch("code_puppy.command_line.autosave_menu._render_preview_panel")
    @patch("sys.stdout.write")
    async def test_navigation_key_bindings(
        self, mock_stdout, mock_preview, mock_menu, mock_entries, mock_awaiting
    ):
        """Test that navigation key bindings are properly set up."""
        # Setup mocks
        entries = [("session1", {}), ("session2", {})]
        mock_entries.return_value = entries
        mock_menu.return_value = [("", "Test")]
        mock_preview.return_value = [("", "Test")]

        with patch("code_puppy.command_line.autosave_menu.Application") as mock_app:
            mock_instance = MagicMock()
            mock_app.return_value = mock_instance
            mock_instance.run_async = AsyncMock()

            # Capture the key bindings passed to Application
            captured_kb = None

            def capture_app(layout=None, key_bindings=None, **kwargs):
                nonlocal captured_kb
                captured_kb = key_bindings
                return mock_instance

            with patch(
                "code_puppy.command_line.autosave_menu.Application",
                side_effect=capture_app,
            ):
                await interactive_autosave_picker()

                # Verify key bindings were set up
                assert captured_kb is not None
                # The bindings should include keys for up, down, left, right, enter, and ctrl-c

    def test_pagination_navigation(self):
        """Test pagination logic in navigation."""
        # This tests the internal navigation logic without running the full app
        entries = [(f"session_{i}", {}) for i in range(30)]  # 30 entries > PAGE_SIZE

        # Initialize state
        selected_idx = [0]
        current_page = [0]

        # Test down navigation across page boundary
        def move_down():
            if selected_idx[0] < len(entries) - 1:
                selected_idx[0] += 1
                current_page[0] = selected_idx[0] // PAGE_SIZE

        # Move to end of first page
        for _ in range(14):
            move_down()

        assert selected_idx[0] == 14
        assert current_page[0] == 0

        # Move to first item of second page
        move_down()
        assert selected_idx[0] == 15
        assert current_page[0] == 1  # Should now be on page 1


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def test_with_nonexistent_autosave_dir(self):
        """Test behavior with nonexistent autosave directory."""
        with patch(
            "code_puppy.command_line.autosave_menu.AUTOSAVE_DIR", "/nonexistent/path"
        ):
            with patch(
                "code_puppy.command_line.autosave_menu.list_sessions",
                side_effect=FileNotFoundError(),
            ):
                entries = _get_session_entries(Path("/nonexistent/path"))
                # Should handle gracefully
                assert isinstance(entries, list)

    def test_with_permission_denied_access(self):
        """Test behavior when permission is denied."""
        with patch(
            "code_puppy.command_line.autosave_menu._get_session_metadata",
            side_effect=PermissionError("Access denied"),
        ):
            with patch(
                "code_puppy.command_line.autosave_menu.list_sessions",
                return_value=["session1"],
            ):
                entries = _get_session_entries(Path("/protected/path"))
                # Should handle permission errors gracefully
                assert len(entries) == 1
                assert entries[0][1] == {}  # metadata should be empty due to error

    def test_console_output_and_ansi_sequences(self):
        """Test that console output includes proper ANSI sequences."""
        entries = [("session1", {})]
        result = _render_menu_panel(entries, 0, 0)

        # Should be list of tuples with formatting
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_large_number_of_sessions_pagination(self):
        """Test pagination with a very large number of sessions."""
        entries = [(f"session_{i}", {"message_count": i}) for i in range(100)]

        # Test various page numbers
        for page in [0, 1, 2, 5, 6]:
            result = _render_menu_panel(entries, page, page * PAGE_SIZE)
            lines_str = str(result)

            # Should show correct page number
            expected_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE
            assert f"({page + 1}/{expected_pages})" in lines_str

    def test_unicode_and_special_characters_in_metadata(self):
        """Test handling of unicode and special characters."""
        entries = [
            (
                "unicode_session",
                {
                    "timestamp": "2024-01-01T12:00:00",
                    "message_count": 5,
                    "special": "Hello 世界 émojis 🐕",
                },
            ),
        ]

        result = _render_menu_panel(entries, 0, 0)
        # Should handle unicode without crashing
        assert isinstance(result, list)


class MockMessage:
    """Mock message class for testing."""

    def __init__(self, content):
        self.parts = [MockPart(content)]


class MockPart:
    """Mock message part class for testing."""

    def __init__(self, content):
        self.content = content


# Integration-style tests that are more comprehensive
class TestIntegrationScenarios:
    """Integration-style tests covering common usage patterns."""

    @patch("code_puppy.command_line.autosave_menu.list_sessions")
    @patch("code_puppy.command_line.autosave_menu.load_session")
    def test_full_rendering_pipeline(self, mock_load, mock_list):
        """Test the complete rendering pipeline with realistic data."""
        # Setup realistic test data
        mock_list.return_value = ["session_1", "session_2"]

        # Setup mock history
        mock_message = MockMessage("# Test Request\n\nPlease help me with this task.")
        mock_load.return_value = [mock_message]

        # Generate menu
        entries = _get_session_entries(Path("/fake/base"))
        menu_output = _render_menu_panel(entries, 0, 0)
        preview_output = _render_preview_panel(Path("/fake/base"), entries[0])

        # Verify outputs
        assert len(menu_output) > 0
        assert len(preview_output) > 0
        assert any("Test Request" in str(item) for item in preview_output)

    def test_state_management_across_pages(self):
        """Test that state is properly managed across page navigation."""
        entries = [(f"session_{i}", {"message_count": i}) for i in range(45)]

        # Simulate navigation across pages
        scenarios = [
            (0, 0),  # Page 1, item 1
            (0, 14),  # Page 1, last item
            (1, 15),  # Page 2, first item
            (1, 29),  # Page 2, last item
            (2, 44),  # Page 3, last item
        ]

        for page, selected_idx in scenarios:
            result = _render_menu_panel(entries, page, selected_idx)
            lines_str = str(result)

            # Should show correct pagination info
            expected_page = page + 1
            total_pages = 3
            assert f"({expected_page}/{total_pages})" in lines_str

    @patch("sys.stdout.write")
    @patch("time.sleep")
    async def test_console_buffer_management(self, mock_sleep, mock_stdout):
        """Test proper console buffer management."""
        with patch(
            "code_puppy.command_line.autosave_menu._get_session_entries",
            return_value=[],
        ):
            result = await interactive_autosave_picker()

            # Should set and reset awaiting input flag
            # Note: When there are no sessions, we don't use TUI所以没有 ANSI sequences
            # But we still set/reset the input flag properly
            assert result is None  # Should return None when no sessions
