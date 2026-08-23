"""Comprehensive test coverage for autosave_menu.py UI components.

Covers menu initialization, user input handling, navigation, rendering,
state management, error scenarios, and console I/O interactions.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from code_puppy.command_line.autosave_menu import (
    _extract_last_user_message,
    _extract_message_content,
    _get_session_entries,
    _get_session_metadata,
    _render_message_browser_panel,
    _render_preview_panel,
    interactive_autosave_picker,
)


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


class TestDisplayResumedHistory:
    """Test the display_resumed_history function."""

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

    def test_empty_history_returns_early(self):
        """Empty history should return without output."""
        from code_puppy.command_line.autosave_menu import display_resumed_history

        # Should not raise
        display_resumed_history([])

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
        # User message shown with > prefix
        assert "Hello from user" in captured.out
        # Assistant message has AGENT RESPONSE banner
        assert "AGENT RESPONSE" in captured.out
        assert "Hello from assistant" in captured.out
        # Tool output shown
        assert "Tool result" in captured.out or "test_tool" in captured.out

    def test_single_system_message_returns_early(self):
        """History with only system message should return without output."""
        from code_puppy.command_line.autosave_menu import display_resumed_history

        mock_msg = MagicMock()
        mock_msg.kind = "request"
        mock_msg.parts = []

        # Should not raise
        display_resumed_history([mock_msg])


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
                assert entries[0][1] == {}


class TestExtractLastUserMessage:
    """Test the _extract_last_user_message function."""

    def test_extracts_last_message_with_content(self):
        """Test extraction of last message with content."""
        mock_message = MagicMock()
        mock_message.parts = [MagicMock(content="Hello world")]

        history = [mock_message]
        result = _extract_last_user_message(history)
        assert result == "Hello world"

    def test_handles_empty_history(self):
        """Test handling of empty message history."""
        result = _extract_last_user_message([])
        assert result == "[No messages found]"


class TestExtractMessageContent:
    """Test the _extract_message_content function."""

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
        assert role == "assistant"

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
        assert "Tool Call: edit_file" in content

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

    def test_user_prompt_returns_user_role(self):
        """Request with user-prompt part returns role='user'."""
        msg = MockModelMessage(
            kind="request",
            parts=[MockMessagePart(part_kind="user-prompt", content="Hello there")],
        )
        role, content = _extract_message_content(msg)
        assert role == "user"
        assert "Hello there" in content


class TestGetSessionEntries:
    """Test the _get_session_entries function."""

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


class TestGetSessionMetadata:
    """Test the _get_session_metadata function."""

    def test_handles_missing_file(self, tmp_path):
        """Test graceful handling of missing metadata file."""
        result = _get_session_metadata(tmp_path, "nonexistent_session")
        assert result == {}

    def test_loads_valid_metadata(self, tmp_path):
        """Test loading valid metadata from JSON file."""
        session_name = "test_session"
        metadata = {"timestamp": "2024-01-01T12:00:00", "message_count": 5}

        meta_file = tmp_path / f"{session_name}_meta.json"
        meta_file.write_text(json.dumps(metadata))

        result = _get_session_metadata(tmp_path, session_name)
        assert result == metadata


class TestInteractiveAutosavePicker:
    """Test the interactive_autosave_picker function."""

    @patch("code_puppy.command_line.autosave_menu._get_session_entries")
    async def test_returns_none_for_no_sessions(self, mock_entries):
        """Test that function returns None when no sessions exist."""
        mock_entries.return_value = []

        result = await interactive_autosave_picker()

        assert result is None


class TestRenderMessageBrowserPanel:
    """Test the _render_message_browser_panel function."""

    def test_assistant_role_shows_assistant_icon(self):
        """Assistant messages show ASSISTANT label."""
        msg = MockModelMessage(
            kind="response",
            parts=[MockMessagePart(part_kind="text", content="Hello!")],
        )
        result = _render_message_browser_panel([msg], 0, "test")
        lines_str = str(result)
        assert "ASSISTANT" in lines_str

    def test_displays_session_name(self):
        """Session name is displayed in output."""
        msg = MockModelMessage(
            kind="request",
            parts=[MockMessagePart(part_kind="user-prompt", content="hello")],
        )
        result = _render_message_browser_panel([msg], 0, "my_cool_session")
        lines_str = str(result)
        assert "my_cool_session" in lines_str

    def test_empty_history_shows_no_messages(self):
        """Empty history list shows 'No messages in this session'."""
        result = _render_message_browser_panel([], 0, "test_session")
        lines_str = str(result)
        assert "No messages in this session" in lines_str

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


class TestRenderPreviewPanel:
    """Test the _render_preview_panel function."""

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

    def test_renders_no_selection_message(self):
        """Test rendering when no session is selected."""
        result = _render_preview_panel(Path("/fake"), None)
        lines_str = str(result)

        assert "No session selected" in lines_str
        assert "PREVIEW" in lines_str


class TestTermflowResumeMenu:
    def drive(self, entries, script, **patches):
        from io import StringIO
        from termflow.ansi.utils import visible
        from code_puppy.command_line.autosave_menu import build_resume_menu

        output = StringIO()
        size = patches.pop("size", lambda: (120, 30))
        menu = build_resume_menu(
            entries=entries,
            base_dir=Path("/fake"),
            key_source=lambda: next(script),
            output=output,
            size=size,
            alt_screen=False,
            **patches,
        )
        return menu, menu.run(), visible(output.getvalue())

    def test_preview_uses_active_theme_accents(self):
        from io import StringIO

        from termflow.ansi.color import fg_color

        from code_puppy.command_line.autosave_menu import build_resume_menu

        ansi = ["#000000"] * 16
        ansi[5] = "#345678"
        ansi[8] = "#456789"
        ansi[9] = "#ff0000"
        ansi[10] = "#234567"
        ansi[12] = "#123456"
        palette = {"ansi": ansi, "bg": "#010101"}
        output = StringIO()
        with patch(
            "code_puppy.command_line.tui_style.get_value",
            return_value=json.dumps(palette),
        ):
            menu = build_resume_menu(
                entries=[("one", {})],
                base_dir=Path("/fake"),
                key_source=lambda: "escape",
                output=output,
                size=lambda: (120, 30),
                alt_screen=False,
            )
            menu.run()

        assert fg_color(ansi[12]) in output.getvalue()

    def test_page_chrome_updates_after_paging(self):
        entries = [(f"session-{index}", {}) for index in range(8)]
        _, result, output = self.drive(
            entries,
            iter(["right", "escape"]),
            size=lambda: (120, 10),
        )
        assert result.cancelled
        assert "Page 1/2 (8 sessions)" in output
        assert "Page 2/2 (8 sessions)" in output

    def test_select_and_cancel(self):
        entries = [("one", {}), ("two", {})]
        _, result, output = self.drive(entries, iter(["down", "enter"]))
        assert result.item.value == "two"
        assert "one" in output and "two" in output
        assert "Page 1/1 (2 sessions)" in output
        _, result, _ = self.drive(entries, iter(["escape"]))
        assert result.cancelled

    @patch("code_puppy.command_line.autosave_menu.load_session")
    def test_browse_navigation_and_escape_priority(self, loader):
        loader.return_value = [
            MockModelMessage("request", [MockMessagePart(content="old")]),
            MockModelMessage("response", [MockMessagePart(content="new")]),
        ]
        menu, result, output = self.drive(
            [("one", {})], iter(["e", "up", "down", "escape", "escape"])
        )
        assert result.cancelled
        assert menu.resume_state["mode"] == "list"
        assert "MESSAGE BROWSER" in output

    def test_search_commit_and_search_escape_priority(self):
        entries = [("alpha", {}), ("beta", {})]
        menu, result, output = self.drive(entries, iter(["/", "b", "enter", "escape"]))
        assert result.cancelled
        assert [item.value for item in menu._items] == ["beta"]
        assert "Search: b\u2588" in output
        assert "Filter: 'b' (1 matches)" in output
        menu, result, _ = self.drive(entries, iter(["/", "a", "escape", "escape"]))
        assert result.cancelled
        assert menu.resume_state["search"] == ""

    def test_scope_toggle_reslices_search_result(self):
        with patch(
            "code_puppy.command_line.autosave_menu.compute_scope_key",
            return_value="here",
        ):
            menu, result, output = self.drive(
                [("local", {"scope_key": "here"}), ("remote", {"scope_key": "there"})],
                iter(["ctrl-t", "escape"]),
            )
        assert result.cancelled
        assert [item.value for item in menu._items] == ["local"]
        assert "[this folder]" in output
