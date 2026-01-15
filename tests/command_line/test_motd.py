"""Comprehensive tests for MOTD (Message of the Day) functionality.

Covers has_seen_motd, mark_motd_seen, and print_motd functions
with proper mocking of file system operations.
"""

from unittest.mock import MagicMock, mock_open, patch


class TestHasSeenMotd:
    """Tests for has_seen_motd function."""

    def test_returns_false_when_file_does_not_exist(self):
        """When track file doesn't exist, version hasn't been seen."""
        from code_puppy.command_line.motd import has_seen_motd

        with patch("code_puppy.command_line.motd.os.path.exists", return_value=False):
            result = has_seen_motd("2026-01-01")

        assert result is False

    def test_returns_true_when_version_in_file(self):
        """When version is in the track file, return True."""
        from code_puppy.command_line.motd import has_seen_motd

        mock_file_content = "2025-12-01\n2026-01-01\n2026-02-01\n"
        with patch("code_puppy.command_line.motd.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_file_content)):
                result = has_seen_motd("2026-01-01")

        assert result is True

    def test_returns_false_when_version_not_in_file(self):
        """When version is NOT in the track file, return False."""
        from code_puppy.command_line.motd import has_seen_motd

        mock_file_content = "2025-12-01\n2025-11-01\n"
        with patch("code_puppy.command_line.motd.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_file_content)):
                result = has_seen_motd("2026-01-01")

        assert result is False

    def test_handles_empty_lines_in_file(self):
        """Empty lines in file should be ignored."""
        from code_puppy.command_line.motd import has_seen_motd

        mock_file_content = "\n\n2026-01-01\n\n\n"
        with patch("code_puppy.command_line.motd.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_file_content)):
                result = has_seen_motd("2026-01-01")

        assert result is True

    def test_handles_whitespace_in_versions(self):
        """Whitespace around versions should be stripped."""
        from code_puppy.command_line.motd import has_seen_motd

        mock_file_content = "  2026-01-01  \n"
        with patch("code_puppy.command_line.motd.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=mock_file_content)):
                result = has_seen_motd("2026-01-01")

        assert result is True


class TestMarkMotdSeen:
    """Tests for mark_motd_seen function."""

    def test_creates_directory_if_not_exists(self):
        """Should create config directory if it doesn't exist."""
        from code_puppy.command_line.motd import mark_motd_seen

        with patch("code_puppy.command_line.motd.os.makedirs") as mock_makedirs:
            with patch(
                "code_puppy.command_line.motd.os.path.exists", return_value=False
            ):
                with patch("builtins.open", mock_open()):
                    mark_motd_seen("2026-01-01")

        mock_makedirs.assert_called_once()
        # Check exist_ok=True was passed
        assert mock_makedirs.call_args[1]["exist_ok"] is True

    def test_appends_version_when_file_empty(self):
        """Should append version to file when file is new/empty."""
        from code_puppy.command_line.motd import mark_motd_seen

        mock_file = mock_open(read_data="")
        with patch("code_puppy.command_line.motd.os.makedirs"):
            with patch(
                "code_puppy.command_line.motd.os.path.exists", return_value=False
            ):
                with patch("builtins.open", mock_file):
                    mark_motd_seen("2026-01-01")

        # Should have opened file for appending and written version
        mock_file().write.assert_called_with("2026-01-01\n")

    def test_appends_version_when_not_already_present(self):
        """Should append version when it's not already in the file."""
        from code_puppy.command_line.motd import mark_motd_seen

        existing_content = "2025-12-01\n2025-11-01\n"

        # Create a mock that returns different handles for 'r' and 'a' modes
        mock_read = mock_open(read_data=existing_content)
        mock_append = mock_open()

        def open_side_effect(path, mode="r"):
            if mode == "r":
                return mock_read()
            elif mode == "a":
                return mock_append()
            return mock_open()()

        with patch("code_puppy.command_line.motd.os.makedirs"):
            with patch(
                "code_puppy.command_line.motd.os.path.exists", return_value=True
            ):
                with patch("builtins.open", side_effect=open_side_effect):
                    mark_motd_seen("2026-01-01")

        # Should write the new version
        mock_append().write.assert_called_with("2026-01-01\n")

    def test_does_not_duplicate_version(self):
        """Should NOT write version if it's already in the file."""
        from code_puppy.command_line.motd import mark_motd_seen

        existing_content = "2025-12-01\n2026-01-01\n"  # Version already exists

        mock_read = mock_open(read_data=existing_content)
        mock_append = mock_open()

        def open_side_effect(path, mode="r"):
            if mode == "r":
                return mock_read()
            elif mode == "a":
                return mock_append()
            return mock_open()()

        with patch("code_puppy.command_line.motd.os.makedirs"):
            with patch(
                "code_puppy.command_line.motd.os.path.exists", return_value=True
            ):
                with patch("builtins.open", side_effect=open_side_effect):
                    mark_motd_seen("2026-01-01")

        # Should NOT have opened file for appending (version already there)
        mock_append().write.assert_not_called()


class TestPrintMotd:
    """Tests for print_motd function."""

    def test_prints_motd_when_not_seen(self):
        """Should print MOTD and return True when version hasn't been seen."""
        from code_puppy.command_line.motd import print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=False):
            with patch("code_puppy.command_line.motd.emit_info") as mock_emit:
                with patch("code_puppy.command_line.motd.mark_motd_seen") as mock_mark:
                    result = print_motd()

        assert result is True
        mock_emit.assert_called_once()
        mock_mark.assert_called_once()

    def test_does_not_print_when_already_seen(self):
        """Should NOT print MOTD and return False when already seen."""
        from code_puppy.command_line.motd import print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=True):
            with patch("code_puppy.command_line.motd.emit_info") as mock_emit:
                with patch("code_puppy.command_line.motd.mark_motd_seen") as mock_mark:
                    result = print_motd()

        assert result is False
        mock_emit.assert_not_called()
        mock_mark.assert_not_called()

    def test_prints_when_force_is_true(self):
        """Should print MOTD when force=True even if already seen."""
        from code_puppy.command_line.motd import print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=True):
            with patch("code_puppy.command_line.motd.emit_info") as mock_emit:
                with patch("code_puppy.command_line.motd.mark_motd_seen") as mock_mark:
                    result = print_motd(force=True)

        assert result is True
        mock_emit.assert_called_once()
        mock_mark.assert_called_once()

    def test_emits_markdown_content(self):
        """Should emit a Rich Markdown object."""
        from code_puppy.command_line.motd import print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=False):
            with patch("code_puppy.command_line.motd.emit_info") as mock_emit:
                with patch("code_puppy.command_line.motd.mark_motd_seen"):
                    with patch("rich.markdown.Markdown") as mock_markdown_class:
                        mock_markdown_instance = MagicMock()
                        mock_markdown_class.return_value = mock_markdown_instance
                        print_motd()

        # Verify Markdown was created and passed to emit_info
        mock_markdown_class.assert_called_once()
        mock_emit.assert_called_once_with(mock_markdown_instance)

    def test_console_parameter_is_accepted(self):
        """Console parameter should be accepted for backward compatibility."""
        from code_puppy.command_line.motd import print_motd

        mock_console = MagicMock()

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=True):
            # Should not raise even with console parameter
            result = print_motd(console=mock_console)

        assert result is False

    def test_marks_current_version_as_seen(self):
        """Should mark the current MOTD_VERSION as seen."""
        from code_puppy.command_line.motd import MOTD_VERSION, print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=False):
            with patch("code_puppy.command_line.motd.emit_info"):
                with patch("code_puppy.command_line.motd.mark_motd_seen") as mock_mark:
                    print_motd()

        mock_mark.assert_called_once_with(MOTD_VERSION)


class TestMotdConstants:
    """Tests for MOTD module constants."""

    def test_motd_version_is_string(self):
        """MOTD_VERSION should be a string."""
        from code_puppy.command_line.motd import MOTD_VERSION

        assert isinstance(MOTD_VERSION, str)
        assert len(MOTD_VERSION) > 0

    def test_motd_message_is_string(self):
        """MOTD_MESSAGE should be a non-empty string."""
        from code_puppy.command_line.motd import MOTD_MESSAGE

        assert isinstance(MOTD_MESSAGE, str)
        assert len(MOTD_MESSAGE) > 0

    def test_motd_track_file_ends_with_motd_txt(self):
        """MOTD_TRACK_FILE should end with motd.txt."""
        from code_puppy.command_line.motd import MOTD_TRACK_FILE

        # Just verify the filename - CONFIG_DIR is dynamic during tests
        assert MOTD_TRACK_FILE.endswith("motd.txt")
        assert ".code_puppy" in MOTD_TRACK_FILE or "code_puppy" in MOTD_TRACK_FILE
