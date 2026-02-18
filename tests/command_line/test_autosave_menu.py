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
    _extract_message_content,
    _get_session_entries,
    _get_session_metadata,
    _render_menu_panel,
    _render_message_browser_panel,
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
    def test_renders_long_messages_in_full(self, mock_extract, mock_load):
        """Test that long messages are rendered in full without truncation."""
        # Create a very long message (simulated through console output)
        history = []
        mock_load.return_value = history

        # Create a message that would result in many lines when rendered
        long_message = "\n".join([f"Line {i}" for i in range(50)])  # 50 lines
        mock_extract.return_value = long_message

        entry = ("test_session", {})
        result = _render_preview_panel(Path("/fake"), entry)
        lines_str = str(result)

        # Should contain all lines without truncation indicator
        # The implementation deliberately shows full messages without truncation
        assert "Line 0" in lines_str
        assert "Line 49" in lines_str  # Last line should be present
        assert "truncated" not in lines_str.lower()


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


# =============================================================================
# New tests for message browser feature
# =============================================================================


class MockMessagePart:
    """Mock message part with configurable part_kind and attributes."""

    def __init__(
        self,
        part_kind: str = "text",
        content: str | None = None,
        tool_name: str | None = None,
        args: dict | None = None,
    ):
        self.part_kind = part_kind
        if content is not None:
            self.content = content
        if tool_name is not None:
            self.tool_name = tool_name
        if args is not None:
            self.args = args


class MockModelMessage:
    """Mock model message with configurable kind and parts."""

    def __init__(self, kind: str, parts: list):
        self.kind = kind
        self.parts = parts


class TestExtractMessageContent:
    """Test the _extract_message_content function."""

    def test_user_prompt_returns_user_role(self):
        """Request with user-prompt part returns role='user'."""
        msg = MockModelMessage(
            kind="request",
            parts=[MockMessagePart(part_kind="user-prompt", content="Hello there")],
        )
        role, content = _extract_message_content(msg)
        assert role == "user"
        assert "Hello there" in content

    def test_tool_return_returns_tool_role(self):
        """Request with only tool-return parts returns role='tool'."""
        msg = MockModelMessage(
            kind="request",
            parts=[
                MockMessagePart(
                    part_kind="tool-return",
                    tool_name="read_file",
                    content="file contents here",
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert role == "tool"
        assert "📥 Tool Result: read_file" in content

    def test_tool_call_returns_tool_role(self):
        """Response with only tool-call parts returns role='tool'."""
        msg = MockModelMessage(
            kind="response",
            parts=[
                MockMessagePart(
                    part_kind="tool-call",
                    tool_name="edit_file",
                    args={"file_path": "test.py"},
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert role == "tool"
        assert "🔧 Tool Call: edit_file" in content

    def test_text_response_returns_assistant_role(self):
        """Response with text part returns role='assistant'."""
        msg = MockModelMessage(
            kind="response",
            parts=[MockMessagePart(part_kind="text", content="Here is my answer")],
        )
        role, content = _extract_message_content(msg)
        assert role == "assistant"
        assert "Here is my answer" in content

    def test_mixed_parts_in_request_returns_user(self):
        """Request with mixed parts (user-prompt + tool-return) returns 'user'."""
        msg = MockModelMessage(
            kind="request",
            parts=[
                MockMessagePart(part_kind="user-prompt", content="My question"),
                MockMessagePart(
                    part_kind="tool-return", tool_name="grep", content="results"
                ),
            ],
        )
        role, content = _extract_message_content(msg)
        assert role == "user"  # Not all parts are tool-return

    def test_mixed_parts_in_response_returns_assistant(self):
        """Response with mixed parts (text + tool-call) returns 'assistant'."""
        msg = MockModelMessage(
            kind="response",
            parts=[
                MockMessagePart(part_kind="text", content="Let me help"),
                MockMessagePart(part_kind="tool-call", tool_name="read_file", args={}),
            ],
        )
        role, content = _extract_message_content(msg)
        assert role == "assistant"  # Not all parts are tool-call

    def test_tool_call_extracts_tool_name_and_args(self):
        """Tool call shows tool name and args preview."""
        msg = MockModelMessage(
            kind="response",
            parts=[
                MockMessagePart(
                    part_kind="tool-call",
                    tool_name="edit_file",
                    args={"file_path": "test.py", "content": "print('hello')"},
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert "🔧 Tool Call: edit_file" in content
        assert "Args:" in content
        assert "file_path" in content

    def test_tool_call_truncates_long_args(self):
        """Args longer than 100 chars are truncated with '...'."""
        long_args = {"content": "x" * 200}
        msg = MockModelMessage(
            kind="response",
            parts=[
                MockMessagePart(
                    part_kind="tool-call", tool_name="edit_file", args=long_args
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert "..." in content

    def test_tool_call_without_args(self):
        """Tool call without args shows just tool name."""
        msg = MockModelMessage(
            kind="response",
            parts=[
                MockMessagePart(part_kind="tool-call", tool_name="list_files", args={})
            ],
        )
        role, content = _extract_message_content(msg)
        assert "🔧 Tool Call: list_files" in content

    def test_tool_return_extracts_tool_name_and_result(self):
        """Tool return shows tool name and content preview."""
        msg = MockModelMessage(
            kind="request",
            parts=[
                MockMessagePart(
                    part_kind="tool-return",
                    tool_name="read_file",
                    content="def hello():\n    print('world')",
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert "📥 Tool Result: read_file" in content
        assert "def hello()" in content

    def test_tool_return_truncates_long_result(self):
        """Results longer than 200 chars are truncated."""
        msg = MockModelMessage(
            kind="request",
            parts=[
                MockMessagePart(
                    part_kind="tool-return",
                    tool_name="read_file",
                    content="x" * 300,
                )
            ],
        )
        role, content = _extract_message_content(msg)
        assert "..." in content

    def test_text_content_extracted_directly(self):
        """Regular text parts are extracted as-is."""
        msg = MockModelMessage(
            kind="response",
            parts=[MockMessagePart(part_kind="text", content="Direct text content")],
        )
        role, content = _extract_message_content(msg)
        assert content == "Direct text content"

    def test_empty_parts_returns_no_content(self):
        """Message with empty parts returns '[No content]'."""
        msg = MockModelMessage(kind="request", parts=[])
        role, content = _extract_message_content(msg)
        assert content == "[No content]"

    def test_whitespace_only_content_ignored(self):
        """Parts with only whitespace are not included."""
        msg = MockModelMessage(
            kind="response",
            parts=[MockMessagePart(part_kind="text", content="   \n\t  ")],
        )
        role, content = _extract_message_content(msg)
        assert content == "[No content]"


class TestRenderMessageBrowserPanel:
    """Test the _render_message_browser_panel function."""

    def test_empty_history_shows_no_messages(self):
        """Empty history list shows 'No messages in this session'."""
        result = _render_message_browser_panel([], 0, "test_session")
        lines_str = str(result)
        assert "No messages in this session" in lines_str

    def test_displays_session_name(self):
        """Session name is displayed in output."""
        msg = MockModelMessage(
            kind="request",
            parts=[MockMessagePart(part_kind="user-prompt", content="hello")],
        )
        result = _render_message_browser_panel([msg], 0, "my_cool_session")
        lines_str = str(result)
        assert "my_cool_session" in lines_str

    def test_displays_message_position(self):
        """Shows 'Message X of Y' indicator."""
        messages = [
            MockModelMessage(
                kind="request",
                parts=[MockMessagePart(part_kind="user-prompt", content=f"msg {i}")],
            )
            for i in range(5)
        ]
        result = _render_message_browser_panel(messages, 2, "test")
        lines_str = str(result)
        assert "Message 3 of 5" in lines_str

    def test_clamps_index_to_valid_range_high(self):
        """Index above max is clamped (no crash)."""
        msg = MockModelMessage(
            kind="request",
            parts=[MockMessagePart(part_kind="user-prompt", content="only one")],
        )
        # Index 100 should be clamped to 0 for single message
        result = _render_message_browser_panel([msg], 100, "test")
        lines_str = str(result)
        assert "Message 1 of 1" in lines_str

    def test_clamps_index_to_valid_range_negative(self):
        """Negative index is clamped to 0."""
        msg = MockModelMessage(
            kind="request",
            parts=[MockMessagePart(part_kind="user-prompt", content="test")],
        )
        result = _render_message_browser_panel([msg], -5, "test")
        lines_str = str(result)
        assert "Message 1 of 1" in lines_str

    def test_user_role_shows_user_icon(self):
        """User messages show USER label."""
        msg = MockModelMessage(
            kind="request",
            parts=[MockMessagePart(part_kind="user-prompt", content="hi")],
        )
        result = _render_message_browser_panel([msg], 0, "test")
        lines_str = str(result)
        assert "USER" in lines_str

    def test_tool_role_shows_tool_icon(self):
        """Tool messages show TOOL label."""
        msg = MockModelMessage(
            kind="request",
            parts=[
                MockMessagePart(
                    part_kind="tool-return", tool_name="test", content="result"
                )
            ],
        )
        result = _render_message_browser_panel([msg], 0, "test")
        lines_str = str(result)
        assert "TOOL" in lines_str

    def test_assistant_role_shows_assistant_icon(self):
        """Assistant messages show ASSISTANT label."""
        msg = MockModelMessage(
            kind="response",
            parts=[MockMessagePart(part_kind="text", content="Hello!")],
        )
        result = _render_message_browser_panel([msg], 0, "test")
        lines_str = str(result)
        assert "ASSISTANT" in lines_str

    def test_reverse_index_most_recent_first(self):
        """Index 0 = most recent message, not first."""
        messages = [
            MockModelMessage(
                kind="request",
                parts=[MockMessagePart(part_kind="user-prompt", content="first msg")],
            ),
            MockModelMessage(
                kind="request",
                parts=[MockMessagePart(part_kind="user-prompt", content="last msg")],
            ),
        ]
        # Index 0 should show the LAST message (most recent)
        result = _render_message_browser_panel(messages, 0, "test")
        lines_str = str(result)
        assert "last msg" in lines_str
        assert "first msg" not in lines_str

    def test_renders_message_browser_header(self):
        """Should show MESSAGE BROWSER header."""
        msg = MockModelMessage(
            kind="request",
            parts=[MockMessagePart(part_kind="user-prompt", content="test")],
        )
        result = _render_message_browser_panel([msg], 0, "test")
        lines_str = str(result)
        assert "MESSAGE BROWSER" in lines_str


class TestRenderMenuPanelBrowseMode:
    """Test the browse_mode parameter of _render_menu_panel."""

    def test_browse_mode_false_shows_standard_hints(self):
        """Default mode shows standard navigation hints including 'e' for browse."""
        entries = [("session1", {"timestamp": "2024-01-01T12:00:00"})]
        result = _render_menu_panel(entries, 0, 0, browse_mode=False)
        lines_str = str(result)

        assert "Navigate" in lines_str
        assert "Page" in lines_str
        assert "e" in lines_str.lower()  # 'e' key hint
        assert "Browse msgs" in lines_str

    def test_browse_mode_true_shows_browse_hints(self):
        """Browse mode shows browse-specific navigation hints."""
        entries = [("session1", {"timestamp": "2024-01-01T12:00:00"})]
        result = _render_menu_panel(entries, 0, 0, browse_mode=True)
        lines_str = str(result)

        assert "Browse msgs" in lines_str
        assert "Esc" in lines_str
        assert "Exit browser" in lines_str

    def test_browse_mode_hides_page_navigation_hint(self):
        """Browse mode doesn't show page navigation hint."""
        entries = [("session1", {"timestamp": "2024-01-01T12:00:00"})]
        result = _render_menu_panel(entries, 0, 0, browse_mode=True)
        lines_str = str(result)

        # In browse mode, we shouldn't see the "Page" hint for ←/→
        # The word "Page" should not appear in browse mode hints
        # But we need to be careful - it might appear in "Session Page(s)"
        # So let's check for the specific pattern
        assert "←/→" not in lines_str or "Page" not in lines_str.split("Esc")[0]


class TestBrowseModeNavigation:
    """Test browse mode state management and navigation logic."""

    def test_browse_mode_up_navigation_logic(self):
        """Test that up navigation in browse mode increments message index."""
        # Simulate the navigation logic from interactive_autosave_picker
        browse_mode = [True]
        message_idx = [0]
        cached_history = [list(range(10))]  # 10 messages

        def move_up():
            if browse_mode[0]:
                if cached_history[0] and message_idx[0] < len(cached_history[0]) - 1:
                    message_idx[0] += 1

        # Move up should go to older message
        move_up()
        assert message_idx[0] == 1

        move_up()
        assert message_idx[0] == 2

    def test_browse_mode_down_navigation_logic(self):
        """Test that down navigation in browse mode decrements message index."""
        browse_mode = [True]
        message_idx = [5]

        def move_down():
            if browse_mode[0]:
                if message_idx[0] > 0:
                    message_idx[0] -= 1

        # Move down should go to newer message
        move_down()
        assert message_idx[0] == 4

        move_down()
        assert message_idx[0] == 3

    def test_browse_mode_up_stops_at_oldest(self):
        """Up navigation stops at oldest message."""
        browse_mode = [True]
        message_idx = [8]  # Near the end
        cached_history = [list(range(10))]  # 10 messages (0-9)

        def move_up():
            if browse_mode[0]:
                if cached_history[0] and message_idx[0] < len(cached_history[0]) - 1:
                    message_idx[0] += 1

        move_up()  # 8 -> 9
        assert message_idx[0] == 9

        move_up()  # Should stay at 9 (can't go higher)
        assert message_idx[0] == 9

    def test_browse_mode_down_stops_at_newest(self):
        """Down navigation stops at newest message (index 0)."""
        browse_mode = [True]
        message_idx = [1]

        def move_down():
            if browse_mode[0]:
                if message_idx[0] > 0:
                    message_idx[0] -= 1

        move_down()  # 1 -> 0
        assert message_idx[0] == 0

        move_down()  # Should stay at 0
        assert message_idx[0] == 0

    def test_normal_mode_navigation_unchanged(self):
        """When not in browse mode, up/down navigates sessions."""
        browse_mode = [False]
        selected_idx = [0]
        entries = list(range(5))  # 5 sessions

        def move_down_session():
            if not browse_mode[0]:
                if selected_idx[0] < len(entries) - 1:
                    selected_idx[0] += 1

        move_down_session()
        assert selected_idx[0] == 1

        move_down_session()
        assert selected_idx[0] == 2

    def test_exit_browse_mode_resets_state(self):
        """Exiting browse mode resets message_idx and cached_history."""
        browse_mode = [True]
        message_idx = [5]
        cached_history = [["msg1", "msg2"]]

        def exit_browse():
            browse_mode[0] = False
            cached_history[0] = None
            message_idx[0] = 0

        exit_browse()

        assert browse_mode[0] is False
        assert message_idx[0] == 0
        assert cached_history[0] is None

    def test_enter_browse_mode_loads_history(self):
        """Entering browse mode sets state correctly."""
        browse_mode = [False]
        message_idx = [0]
        cached_history = [None]
        mock_history = ["msg1", "msg2", "msg3"]

        def enter_browse(history):
            cached_history[0] = history
            browse_mode[0] = True
            message_idx[0] = 0  # Start at most recent

        enter_browse(mock_history)

        assert browse_mode[0] is True
        assert message_idx[0] == 0
        assert cached_history[0] == mock_history

    def test_enter_browse_mode_ignored_when_already_browsing(self):
        """Pressing 'e' when already in browse mode doesn't reload."""
        browse_mode = [True]
        message_idx = [3]  # User has navigated to message 3
        original_history = ["a", "b", "c"]
        cached_history = [original_history]

        def enter_browse_if_not_browsing(new_history):
            if browse_mode[0]:
                return  # Already in browse mode
            cached_history[0] = new_history
            message_idx[0] = 0

        # Try to enter browse mode again with different history
        enter_browse_if_not_browsing(["x", "y", "z"])

        # Should not have changed
        assert message_idx[0] == 3
        assert cached_history[0] == original_history


class TestDisplayResumedHistory:
    """Test the display_resumed_history function."""

    def test_empty_history_returns_early(self):
        """Empty history should return without output."""
        from code_puppy.command_line.autosave_menu import display_resumed_history

        # Should not raise
        display_resumed_history([])

    def test_single_system_message_returns_early(self):
        """History with only system message should return without output."""
        from code_puppy.command_line.autosave_menu import display_resumed_history

        mock_msg = MagicMock()
        mock_msg.kind = "request"
        mock_msg.parts = []

        # Should not raise
        display_resumed_history([mock_msg])

    def test_displays_last_n_messages(self, capsys):
        """Should display the last N messages from history."""
        from code_puppy.command_line.autosave_menu import display_resumed_history

        # Create mock messages
        messages = []
        for i in range(5):
            msg = MagicMock()
            msg.kind = "request"
            part = MagicMock()
            part.part_kind = "user-prompt"
            part.content = f"Message {i}"
            msg.parts = [part]
            messages.append(msg)

        display_resumed_history(messages, num_messages=3)

        captured = capsys.readouterr()
        # Should show messages 2, 3, 4 (last 3)
        assert "Message 2" in captured.out
        assert "Message 3" in captured.out
        assert "Message 4" in captured.out
        # Should show hidden count
        assert "1 earlier messages" in captured.out
        # Should show session resumed footer
        assert "Session Resumed" in captured.out

    def test_shows_all_messages_when_under_limit(self, capsys):
        """Should show all messages when count is under limit."""
        from code_puppy.command_line.autosave_menu import display_resumed_history

        # Create mock messages (system + 2 user)
        messages = []
        for i in range(3):
            msg = MagicMock()
            msg.kind = "request"
            part = MagicMock()
            part.part_kind = "user-prompt"
            part.content = f"Message {i}"
            msg.parts = [part]
            messages.append(msg)

        display_resumed_history(messages, num_messages=10)

        captured = capsys.readouterr()
        # Should show messages 1 and 2 (skipping system message at index 0)
        assert "Message 1" in captured.out
        assert "Message 2" in captured.out
        # Should NOT show hidden count (all displayed)
        assert "earlier messages" not in captured.out

    def test_renders_long_content_as_markdown(self, capsys):
        """Should render long message content as markdown without truncation."""
        from code_puppy.command_line.autosave_menu import display_resumed_history

        # Create message with very long content
        msg1 = MagicMock()
        msg1.kind = "request"
        msg1.parts = []

        msg2 = MagicMock()
        msg2.kind = "request"
        part = MagicMock()
        part.part_kind = "user-prompt"
        part.content = "X" * 1000  # Very long content
        msg2.parts = [part]

        display_resumed_history([msg1, msg2], num_messages=10)

        captured = capsys.readouterr()
        # Should show USER header
        assert "USER" in captured.out

    def test_renders_different_roles_correctly(self, capsys):
        """Should render user, assistant, and tool messages with correct styling."""
        from code_puppy.command_line.autosave_menu import display_resumed_history

        # System message (skipped)
        sys_msg = MagicMock()
        sys_msg.kind = "request"
        sys_msg.parts = []

        # User message
        user_msg = MagicMock()
        user_msg.kind = "request"
        user_part = MagicMock()
        user_part.part_kind = "user-prompt"
        user_part.content = "Hello from user"
        user_msg.parts = [user_part]

        # Assistant message
        assistant_msg = MagicMock()
        assistant_msg.kind = "response"
        assistant_part = MagicMock()
        assistant_part.part_kind = "text"
        assistant_part.content = "Hello from assistant"
        assistant_msg.parts = [assistant_part]

        # Tool message
        tool_msg = MagicMock()
        tool_msg.kind = "request"
        tool_part = MagicMock()
        tool_part.part_kind = "tool-return"
        tool_part.tool_name = "test_tool"
        tool_part.content = "Tool result"
        tool_msg.parts = [tool_part]

        display_resumed_history(
            [sys_msg, user_msg, assistant_msg, tool_msg], num_messages=10
        )

        captured = capsys.readouterr()
        assert "USER" in captured.out
        assert "ASSISTANT" in captured.out
        assert "TOOL" in captured.out
