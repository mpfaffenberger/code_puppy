"""Coverage tests for session_storage.py - focusing on restore_autosave_interactively.

This module targets the uncovered code paths in session_storage.py, especially:
- The restore_autosave_interactively async function
- Metadata reading error handling
- Pagination logic
- User selection flows
- Error handling for session loading
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy import session_storage
from code_puppy.session_storage import (
    _LEGACY_SIGNATURE_SIZE,
    _LEGACY_SIGNED_HEADER,
    restore_autosave_interactively,
)


# Helper context manager to mock all the imports used by restore_autosave_interactively
def mock_interactive_imports(
    mock_input_return=None,
    mock_input_side_effect=None,
    mock_agent=None,
    capture_system=None,
    capture_warning=None,
    capture_success=None,
    mock_load_session=None,
):
    """Context manager that mocks all the required imports for the interactive function."""
    import contextlib

    @contextlib.asynccontextmanager
    async def _manager():
        mock_input = AsyncMock()
        if mock_input_side_effect:
            mock_input.side_effect = mock_input_side_effect
        elif mock_input_return is not None:
            mock_input.return_value = mock_input_return
        else:
            mock_input.return_value = ""

        agent = mock_agent or MagicMock()
        if mock_agent is None:
            agent.estimate_tokens_for_message.return_value = 10

        system_msgs = [] if capture_system is None else capture_system
        warning_msgs = [] if capture_warning is None else capture_warning
        success_msgs = [] if capture_success is None else capture_success

        patches = [
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_input_with_combined_completion",
                mock_input,
            ),
            patch(
                "code_puppy.messaging.emit_system_message",
                side_effect=lambda msg: system_msgs.append(msg),
            ),
            patch(
                "code_puppy.messaging.emit_warning",
                side_effect=lambda msg: warning_msgs.append(msg),
            ),
            patch(
                "code_puppy.messaging.emit_success",
                side_effect=lambda msg: success_msgs.append(msg),
            ),
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.config.set_current_autosave_from_session_name",
                MagicMock(),
            ),
        ]

        if mock_load_session is not None:
            patches.append(
                patch(
                    "code_puppy.session_storage.load_session",
                    mock_load_session,
                )
            )

        for p in patches:
            p.start()
        try:
            yield {
                "mock_input": mock_input,
                "agent": agent,
                "system_msgs": system_msgs,
                "warning_msgs": warning_msgs,
                "success_msgs": success_msgs,
            }
        finally:
            for p in patches:
                p.stop()

    return _manager()


class TestRestoreAutosaveInteractivelyNoSessions:
    """Test early return when no sessions exist."""

    @pytest.mark.asyncio
    async def test_returns_early_when_no_sessions(self, tmp_path):
        """Should return immediately if no sessions exist in base_dir."""
        # Empty directory - no sessions
        result = await restore_autosave_interactively(tmp_path)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_early_when_directory_does_not_exist(self, tmp_path):
        """Should return immediately if base_dir doesn't exist."""
        nonexistent = tmp_path / "nonexistent" / "path"
        result = await restore_autosave_interactively(nonexistent)
        assert result is None


class TestRestoreAutosaveMetadataReading:
    """Test metadata file reading and error handling."""

    @pytest.mark.asyncio
    async def test_handles_missing_metadata_file(self, tmp_path):
        """Should handle gracefully when metadata JSON doesn't exist."""
        # Create session pickle without metadata
        (tmp_path / "orphan_session.pkl").write_bytes(b"dummy")

        async with mock_interactive_imports(mock_input_return=""):
            result = await restore_autosave_interactively(tmp_path)

        # Should return None (user skipped)
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_corrupted_metadata_json(self, tmp_path):
        """Should handle gracefully when metadata JSON is corrupted."""
        # Create session with corrupted metadata
        (tmp_path / "corrupted.pkl").write_bytes(b"dummy")
        (tmp_path / "corrupted_meta.json").write_text(
            "not valid json{{{", encoding="utf-8"
        )

        async with mock_interactive_imports(mock_input_return=""):
            result = await restore_autosave_interactively(tmp_path)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_metadata_missing_fields(self, tmp_path):
        """Should handle metadata JSON with missing timestamp/message_count."""
        (tmp_path / "partial.pkl").write_bytes(b"dummy")
        # Metadata with missing fields
        (tmp_path / "partial_meta.json").write_text(
            json.dumps({"session_name": "partial"}), encoding="utf-8"
        )

        async with mock_interactive_imports(mock_input_return=""):
            result = await restore_autosave_interactively(tmp_path)

        assert result is None


class TestRestoreAutosaveTimestampSorting:
    """Test timestamp sorting logic with edge cases."""

    @pytest.mark.asyncio
    async def test_sorts_sessions_by_timestamp_descending(self, tmp_path):
        """Should sort sessions with newest first."""
        # Create sessions with different timestamps
        sessions = [
            ("old_session", "2024-01-01T00:00:00"),
            ("middle_session", "2024-06-15T12:00:00"),
            ("new_session", "2024-12-31T23:59:59"),
        ]

        for name, timestamp in sessions:
            (tmp_path / f"{name}.pkl").write_bytes(b"dummy")
            (tmp_path / f"{name}_meta.json").write_text(
                json.dumps({"timestamp": timestamp, "message_count": 5}),
                encoding="utf-8",
            )

        displayed_sessions = []

        async with mock_interactive_imports(
            mock_input_return="", capture_system=displayed_sessions
        ):
            await restore_autosave_interactively(tmp_path)

        # Find the session listing lines - newest should appear first
        session_lines = [s for s in displayed_sessions if "[" in s and "]" in s]
        # Verify new_session appears before old_session in ordering
        assert any("new_session" in line for line in session_lines[:3])

    @pytest.mark.asyncio
    async def test_handles_invalid_timestamp_format(self, tmp_path):
        """Should handle sessions with invalid timestamp format."""
        (tmp_path / "bad_time.pkl").write_bytes(b"dummy")
        (tmp_path / "bad_time_meta.json").write_text(
            json.dumps({"timestamp": "not-a-valid-timestamp", "message_count": 1}),
            encoding="utf-8",
        )

        async with mock_interactive_imports(mock_input_return=""):
            # Should not crash even with invalid timestamp
            result = await restore_autosave_interactively(tmp_path)

        assert result is None

    @pytest.mark.asyncio
    async def test_handles_none_timestamp(self, tmp_path):
        """Should handle sessions with null timestamp."""
        (tmp_path / "null_time.pkl").write_bytes(b"dummy")
        (tmp_path / "null_time_meta.json").write_text(
            json.dumps({"timestamp": None, "message_count": 1}),
            encoding="utf-8",
        )

        async with mock_interactive_imports(mock_input_return=""):
            result = await restore_autosave_interactively(tmp_path)

        assert result is None


class TestRestoreAutosavePagination:
    """Test pagination logic for multiple sessions."""

    @pytest.mark.asyncio
    async def test_pagination_with_more_than_five_sessions(self, tmp_path):
        """Should show pagination controls when more than 5 sessions exist."""
        # Create 8 sessions
        for i in range(8):
            (tmp_path / f"session_{i}.pkl").write_bytes(b"dummy")
            (tmp_path / f"session_{i}_meta.json").write_text(
                json.dumps(
                    {"timestamp": f"2024-01-0{i + 1}T00:00:00", "message_count": i}
                ),
                encoding="utf-8",
            )

        displayed_messages = []

        async with mock_interactive_imports(
            mock_input_return="", capture_system=displayed_messages
        ):
            await restore_autosave_interactively(tmp_path)

        # Should show "Next page" or page navigation option
        all_output = " ".join(displayed_messages)
        assert "[6]" in all_output  # Page navigation should be shown

    @pytest.mark.asyncio
    async def test_page_navigation_cycles_through_pages(self, tmp_path):
        """Should cycle through pages when user selects option 6."""
        # Create 8 sessions for 2 pages
        for i in range(8):
            (tmp_path / f"session_{i}.pkl").write_bytes(b"dummy")
            (tmp_path / f"session_{i}_meta.json").write_text(
                json.dumps(
                    {"timestamp": f"2024-01-{i + 1:02d}T00:00:00", "message_count": i}
                ),
                encoding="utf-8",
            )

        call_count = 0

        def input_sequence(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "6"  # Navigate to next page
            elif call_count == 2:
                return "6"  # Navigate again (should wrap to first page)
            else:
                return ""  # Skip on third iteration

        async with mock_interactive_imports(mock_input_side_effect=input_sequence):
            result = await restore_autosave_interactively(tmp_path)

        assert call_count >= 2  # Should have navigated at least twice
        assert result is None

    @pytest.mark.asyncio
    async def test_five_or_fewer_sessions_no_pagination(self, tmp_path):
        """Should not show pagination when 5 or fewer sessions."""
        # Create exactly 5 sessions
        for i in range(5):
            (tmp_path / f"session_{i}.pkl").write_bytes(b"dummy")
            (tmp_path / f"session_{i}_meta.json").write_text(
                json.dumps(
                    {"timestamp": f"2024-01-0{i + 1}T00:00:00", "message_count": i}
                ),
                encoding="utf-8",
            )

        displayed_messages = []

        async with mock_interactive_imports(
            mock_input_return="", capture_system=displayed_messages
        ):
            await restore_autosave_interactively(tmp_path)

        # Should NOT show [6] for pagination when 5 or fewer
        pagination_lines = [m for m in displayed_messages if "[6]" in m]
        assert len(pagination_lines) == 0


class TestRestoreAutosaveUserSelection:
    """Test user input selection flows."""

    @pytest.mark.asyncio
    async def test_numeric_selection_loads_session(self, tmp_path):
        """User selecting 1-5 should load the corresponding session."""
        import pickle

        # Create a valid session with proper pickle content
        history = [{"role": "user", "content": "test message"}]
        _pkl = pickle.dumps(history)
        (tmp_path / "test_session.pkl").write_bytes(
            _LEGACY_SIGNED_HEADER + (b"x" * _LEGACY_SIGNATURE_SIZE) + _pkl
        )
        (tmp_path / "test_session_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        mock_agent = MagicMock()
        mock_agent.estimate_tokens_for_message.return_value = 10

        async with mock_interactive_imports(
            mock_input_return="1", mock_agent=mock_agent
        ):
            await restore_autosave_interactively(tmp_path)

        # Agent should have received the history
        mock_agent.set_message_history.assert_called_once_with(history)

    @pytest.mark.asyncio
    async def test_direct_name_selection(self, tmp_path):
        """User typing exact session name should load that session."""
        import pickle

        history = [{"role": "user", "content": "named session"}]
        _pkl = pickle.dumps(history)
        (tmp_path / "my_specific_session.pkl").write_bytes(
            _LEGACY_SIGNED_HEADER + (b"x" * _LEGACY_SIGNATURE_SIZE) + _pkl
        )
        (tmp_path / "my_specific_session_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        mock_agent = MagicMock()
        mock_agent.estimate_tokens_for_message.return_value = 5

        async with mock_interactive_imports(
            mock_input_return="my_specific_session", mock_agent=mock_agent
        ):
            await restore_autosave_interactively(tmp_path)

        mock_agent.set_message_history.assert_called_once_with(history)

    @pytest.mark.asyncio
    async def test_empty_selection_skips_loading(self, tmp_path):
        """User pressing Enter without input should skip loading."""
        (tmp_path / "session.pkl").write_bytes(b"dummy")
        (tmp_path / "session_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        async with mock_interactive_imports(mock_input_return=""):
            result = await restore_autosave_interactively(tmp_path)

        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_numeric_selection_warns_user(self, tmp_path):
        """Invalid numeric selection should warn and allow retry."""
        (tmp_path / "session.pkl").write_bytes(b"dummy")
        (tmp_path / "session_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        call_count = 0

        def input_sequence(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "9"  # Invalid selection
            else:
                return ""  # Skip

        warnings = []

        async with mock_interactive_imports(
            mock_input_side_effect=input_sequence, capture_warning=warnings
        ):
            await restore_autosave_interactively(tmp_path)

        # Should have warned about invalid selection
        assert any("Invalid" in w or "invalid" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_invalid_name_selection_warns_user(self, tmp_path):
        """Typing non-existent session name should warn and allow retry."""
        (tmp_path / "real_session.pkl").write_bytes(b"dummy")
        (tmp_path / "real_session_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        call_count = 0

        def input_sequence(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "nonexistent_session"  # Invalid name
            else:
                return ""  # Skip

        warnings = []

        async with mock_interactive_imports(
            mock_input_side_effect=input_sequence, capture_warning=warnings
        ):
            await restore_autosave_interactively(tmp_path)

        # Should have warned about invalid selection
        assert any("invalid" in w.lower() for w in warnings)


class TestRestoreAutosaveErrorHandling:
    """Test error handling during session loading."""

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_cancels(self, tmp_path):
        """KeyboardInterrupt should cancel selection."""
        (tmp_path / "session.pkl").write_bytes(b"dummy")
        (tmp_path / "session_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        warnings = []

        async with mock_interactive_imports(
            mock_input_side_effect=KeyboardInterrupt(), capture_warning=warnings
        ):
            result = await restore_autosave_interactively(tmp_path)

        assert result is None
        assert any("cancelled" in w.lower() for w in warnings)

    @pytest.mark.asyncio
    async def test_eof_error_cancels(self, tmp_path):
        """EOFError should cancel selection."""
        (tmp_path / "session.pkl").write_bytes(b"dummy")
        (tmp_path / "session_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        warnings = []

        async with mock_interactive_imports(
            mock_input_side_effect=EOFError(), capture_warning=warnings
        ):
            result = await restore_autosave_interactively(tmp_path)

        assert result is None
        assert any("cancelled" in w.lower() for w in warnings)

    @pytest.mark.asyncio
    async def test_file_not_found_on_load(self, tmp_path):
        """Should handle FileNotFoundError during session load."""
        # Create session file that will be "deleted" between listing and loading
        (tmp_path / "disappearing.pkl").write_bytes(b"dummy")
        (tmp_path / "disappearing_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        warnings = []

        async with mock_interactive_imports(
            mock_input_return="1",
            capture_warning=warnings,
            mock_load_session=MagicMock(
                side_effect=FileNotFoundError("Session file deleted")
            ),
        ):
            result = await restore_autosave_interactively(tmp_path)

        assert result is None
        assert any("could not be found" in w.lower() for w in warnings)

    @pytest.mark.asyncio
    async def test_generic_exception_on_load(self, tmp_path):
        """Should handle generic Exception during session load."""
        (tmp_path / "broken.pkl").write_bytes(b"dummy")
        (tmp_path / "broken_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        warnings = []

        async with mock_interactive_imports(
            mock_input_return="1",
            capture_warning=warnings,
            mock_load_session=MagicMock(side_effect=Exception("Corrupted pickle")),
        ):
            result = await restore_autosave_interactively(tmp_path)

        assert result is None
        assert any("Failed to load" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_set_autosave_id_failure_ignored(self, tmp_path):
        """Failure to set autosave ID should be silently ignored."""
        import pickle

        history = [{"role": "user", "content": "test"}]
        _pkl = pickle.dumps(history)
        (tmp_path / "session.pkl").write_bytes(
            _LEGACY_SIGNED_HEADER + (b"x" * _LEGACY_SIGNATURE_SIZE) + _pkl
        )
        (tmp_path / "session_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 1}),
            encoding="utf-8",
        )

        mock_agent = MagicMock()
        mock_agent.estimate_tokens_for_message.return_value = 5

        # Patch set_current_autosave_from_session_name to raise an exception
        with patch(
            "code_puppy.config.set_current_autosave_from_session_name",
            side_effect=Exception("Config error"),
        ):
            async with mock_interactive_imports(
                mock_input_return="1", mock_agent=mock_agent
            ):
                # Should not raise, exception should be caught
                await restore_autosave_interactively(tmp_path)

        # Session should still be loaded despite config error
        mock_agent.set_message_history.assert_called_once()


class TestRestoreAutosaveDisplayFormatting:
    """Test display formatting for sessions."""

    @pytest.mark.asyncio
    async def test_displays_message_count_and_timestamp(self, tmp_path):
        """Should display message count and timestamp for each session."""
        (tmp_path / "formatted.pkl").write_bytes(b"dummy")
        (tmp_path / "formatted_meta.json").write_text(
            json.dumps({"timestamp": "2024-06-15T14:30:00", "message_count": 42}),
            encoding="utf-8",
        )

        displayed = []

        async with mock_interactive_imports(
            mock_input_return="", capture_system=displayed
        ):
            await restore_autosave_interactively(tmp_path)

        combined = " ".join(displayed)
        assert "42 messages" in combined
        assert "2024-06-15T14:30:00" in combined

    @pytest.mark.asyncio
    async def test_displays_unknown_for_missing_metadata(self, tmp_path):
        """Should display 'unknown' for missing timestamp/message_count."""
        (tmp_path / "missing_info.pkl").write_bytes(b"dummy")
        # No metadata file

        displayed = []

        async with mock_interactive_imports(
            mock_input_return="", capture_system=displayed
        ):
            await restore_autosave_interactively(tmp_path)

        combined = " ".join(displayed)
        assert "unknown" in combined.lower()


class TestRestoreAutosaveSuccessPath:
    """Test the complete success path."""

    @pytest.mark.asyncio
    async def test_successful_restore_emits_success_message(self, tmp_path):
        """Should emit success message with token count after restore."""
        import pickle

        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        _pkl = pickle.dumps(history)
        (tmp_path / "success.pkl").write_bytes(
            _LEGACY_SIGNED_HEADER + (b"x" * _LEGACY_SIGNATURE_SIZE) + _pkl
        )
        (tmp_path / "success_meta.json").write_text(
            json.dumps({"timestamp": "2024-01-01T00:00:00", "message_count": 2}),
            encoding="utf-8",
        )

        mock_agent = MagicMock()
        mock_agent.estimate_tokens_for_message.return_value = 10

        success_messages = []

        async with mock_interactive_imports(
            mock_input_return="1",
            mock_agent=mock_agent,
            capture_success=success_messages,
        ):
            await restore_autosave_interactively(tmp_path)

        # Should have emitted success with token count
        assert len(success_messages) == 1
        msg = success_messages[0]
        assert "2 messages" in msg
        assert "20 tokens" in msg  # 2 messages * 10 tokens each
        assert "✅" in msg


class TestRestoreAutosaveLastPageBehavior:
    """Test behavior when on the last page of pagination."""

    @pytest.mark.asyncio
    async def test_last_page_shows_return_to_first(self, tmp_path):
        """On last page, option 6 should show 'Return to first page'."""
        # Create 7 sessions (will need 2 pages)
        for i in range(7):
            (tmp_path / f"session_{i}.pkl").write_bytes(b"dummy")
            (tmp_path / f"session_{i}_meta.json").write_text(
                json.dumps(
                    {"timestamp": f"2024-01-{i + 1:02d}T00:00:00", "message_count": i}
                ),
                encoding="utf-8",
            )

        displayed = []
        call_count = 0

        def input_sequence(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "6"  # Go to second (last) page
            else:
                return ""  # Skip

        async with mock_interactive_imports(
            mock_input_side_effect=input_sequence, capture_system=displayed
        ):
            await restore_autosave_interactively(tmp_path)

        # After going to page 2, should see "Return to first page"
        combined = " ".join(displayed)
        assert "Return to first page" in combined


class TestSessionPathsDataclass:
    """Tests for SessionPaths dataclass."""

    def test_session_paths_creation(self, tmp_path):
        """Test SessionPaths can be created with paths."""
        paths = session_storage.SessionPaths(
            pickle_path=tmp_path / "test.pkl",
            metadata_path=tmp_path / "test_meta.json",
        )
        assert paths.pickle_path == tmp_path / "test.pkl"
        assert paths.metadata_path == tmp_path / "test_meta.json"


class TestCleanupSessionsEdgeCases:
    """Additional edge cases for cleanup_sessions."""

    def test_cleanup_with_negative_max_sessions(self, tmp_path):
        """Negative max_sessions should return empty list."""
        (tmp_path / "session.pkl").write_bytes(b"dummy")

        removed = session_storage.cleanup_sessions(tmp_path, max_sessions=-5)
        assert removed == []

    def test_cleanup_nonexistent_directory(self, tmp_path):
        """Cleanup on nonexistent directory should return empty list."""
        nonexistent = tmp_path / "does_not_exist"
        removed = session_storage.cleanup_sessions(nonexistent, max_sessions=5)
        assert removed == []

    def test_cleanup_fewer_than_max(self, tmp_path):
        """Should not remove anything if fewer sessions than max."""
        (tmp_path / "session1.pkl").write_bytes(b"dummy")
        (tmp_path / "session2.pkl").write_bytes(b"dummy")

        removed = session_storage.cleanup_sessions(tmp_path, max_sessions=10)
        assert removed == []
        assert len(session_storage.list_sessions(tmp_path)) == 2


class TestRestoreAutosaveInvalidPageSelection:
    """Test invalid page selection edge cases."""

    @pytest.mark.asyncio
    async def test_selection_out_of_range_on_partial_page(self, tmp_path):
        """Selecting 5 when only 2 items exist on page should warn."""
        # Create 7 sessions (5 on page 1, 2 on page 2)
        for i in range(7):
            (tmp_path / f"session_{i}.pkl").write_bytes(b"dummy")
            (tmp_path / f"session_{i}_meta.json").write_text(
                json.dumps(
                    {"timestamp": f"2024-01-{i + 1:02d}T00:00:00", "message_count": i}
                ),
                encoding="utf-8",
            )

        call_count = 0
        warnings = []

        def input_sequence(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "6"  # Go to second page (only has 2 items)
            elif call_count == 2:
                return "5"  # Invalid - only 2 items on this page
            else:
                return ""  # Skip

        async with mock_interactive_imports(
            mock_input_side_effect=input_sequence, capture_warning=warnings
        ):
            await restore_autosave_interactively(tmp_path)

        # Should have warned about invalid selection for this page
        assert any("Invalid" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_selection_6_not_valid_when_no_more_pages(self, tmp_path):
        """Selecting 6 when only 3 sessions exist should warn."""
        # Create only 3 sessions (no pagination)
        for i in range(3):
            (tmp_path / f"session_{i}.pkl").write_bytes(b"dummy")
            (tmp_path / f"session_{i}_meta.json").write_text(
                json.dumps(
                    {"timestamp": f"2024-01-{i + 1:02d}T00:00:00", "message_count": i}
                ),
                encoding="utf-8",
            )

        call_count = 0
        warnings = []

        def input_sequence(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "6"  # Invalid - no more pages
            else:
                return ""  # Skip

        async with mock_interactive_imports(
            mock_input_side_effect=input_sequence, capture_warning=warnings
        ):
            await restore_autosave_interactively(tmp_path)

        # Should have warned about invalid selection
        assert any("Invalid" in w or "invalid" in w.lower() for w in warnings)
