"""Comprehensive tests for MOTD (Message of the Day) functionality.

Covers _read_seen_versions, has_seen_motd, mark_motd_seen, and print_motd
functions with proper mocking of file system operations.
"""

from unittest.mock import MagicMock, mock_open, patch


class TestReadSeenVersions:
    """Tests for _read_seen_versions helper."""

    def test_returns_empty_set_when_file_missing(self):
        from code_puppy.command_line.motd import _read_seen_versions

        with patch("code_puppy.command_line.motd.os.path.exists", return_value=False):
            assert _read_seen_versions() == set()

    def test_returns_versions_from_file(self):
        from code_puppy.command_line.motd import _read_seen_versions

        with patch("code_puppy.command_line.motd.os.path.exists", return_value=True):
            with patch(
                "builtins.open", mock_open(read_data="2025-12-01\n2026-01-01\n")
            ):
                result = _read_seen_versions()

        assert result == {"2025-12-01", "2026-01-01"}

    def test_strips_whitespace_and_ignores_blanks(self):
        from code_puppy.command_line.motd import _read_seen_versions

        with patch("code_puppy.command_line.motd.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="\n  2026-01-01  \n\n")):
                result = _read_seen_versions()

        assert result == {"2026-01-01"}


class TestHasSeenMotd:
    """Tests for has_seen_motd function."""

    def test_returns_false_when_file_does_not_exist(self):
        from code_puppy.command_line.motd import has_seen_motd

        with patch(
            "code_puppy.command_line.motd._read_seen_versions", return_value=set()
        ):
            assert has_seen_motd("2026-01-01") is False

    def test_returns_true_when_version_in_file(self):
        from code_puppy.command_line.motd import has_seen_motd

        with patch(
            "code_puppy.command_line.motd._read_seen_versions",
            return_value={"2025-", "2026-01-01"},
        ):
            assert has_seen_motd("2026-01-01") is True

    def test_returns_false_when_version_not_in_file(self):
        from code_puppy.command_line.motd import has_seen_motd

        with patch(
            "code_puppy.command_line.motd._read_seen_versions",
            return_value={"2025-12-01"},
        ):
            assert has_seen_motd("2026-01-01") is False


class TestMarkMotdSeen:
    """Tests for mark_motd_seen function."""

    def test_creates_directory_if_not_exists(self):
        from code_puppy.command_line.motd import mark_motd_seen

        with patch("code_puppy.command_line.motd.os.makedirs") as mock_makedirs:
            with patch(
                "code_puppy.command_line.motd._read_seen_versions", return_value=set()
            ):
                with patch("builtins.open", mock_open()):
                    mark_motd_seen("2026-01-01")

        mock_makedirs.assert_called_once()
        assert mock_makedirs.call_args[1]["exist_ok"] is True

    def test_appends_version_when_not_present(self):
        from code_puppy.command_line.motd import mark_motd_seen

        mock_file = mock_open()
        with patch("code_puppy.command_line.motd.os.makedirs"):
            with patch(
                "code_puppy.command_line.motd._read_seen_versions", return_value=set()
            ):
                with patch("builtins.open", mock_file):
                    mark_motd_seen("2026-01-01")

        mock_file().write.assert_called_with("2026-01-01\n")

    def test_does_not_duplicate_version(self):
        from code_puppy.command_line.motd import mark_motd_seen

        mock_file = mock_open()
        with patch("code_puppy.command_line.motd.os.makedirs"):
            with patch(
                "code_puppy.command_line.motd._read_seen_versions",
                return_value={"2026-01-01"},
            ):
                with patch("builtins.open", mock_file):
                    mark_motd_seen("2026-01-01")

        mock_file().write.assert_not_called()


class TestPrintMotd:
    """Tests for print_motd function."""

    def test_prints_motd_when_not_seen(self):
        from code_puppy.command_line.motd import print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=False):
            with patch("code_puppy.command_line.motd.emit_info") as mock_emit:
                with patch("code_puppy.command_line.motd.mark_motd_seen") as mock_mark:
                    result = print_motd()

        assert result is True
        mock_emit.assert_called_once()
        mock_mark.assert_called_once()

    def test_does_not_print_when_already_seen(self):
        from code_puppy.command_line.motd import print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=True):
            with patch("code_puppy.command_line.motd.emit_info") as mock_emit:
                with patch("code_puppy.command_line.motd.mark_motd_seen") as mock_mark:
                    result = print_motd()

        assert result is False
        mock_emit.assert_not_called()
        mock_mark.assert_not_called()

    def test_prints_when_force_is_true(self):
        from code_puppy.command_line.motd import print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=True):
            with patch("code_puppy.command_line.motd.emit_info") as mock_emit:
                with patch("code_puppy.command_line.motd.mark_motd_seen") as mock_mark:
                    result = print_motd(force=True)

        assert result is True
        mock_emit.assert_called_once()
        mock_mark.assert_called_once()

    def test_emits_markdown_content(self):
        from code_puppy.command_line.motd import print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=False):
            with patch("code_puppy.command_line.motd.emit_info") as mock_emit:
                with patch("code_puppy.command_line.motd.mark_motd_seen"):
                    with patch("rich.markdown.Markdown") as mock_md_cls:
                        mock_md_instance = MagicMock()
                        mock_md_cls.return_value = mock_md_instance
                        print_motd()

        mock_md_cls.assert_called_once()
        mock_emit.assert_called_once_with(mock_md_instance)

    def test_console_parameter_is_accepted(self):
        """Console parameter should be accepted for backward compatibility."""
        from code_puppy.command_line.motd import print_motd

        with patch("code_puppy.command_line.motd.has_seen_motd", return_value=True):
            result = print_motd(console=MagicMock())

        assert result is False


class TestMotdConstants:
    """Tests for MOTD module constants."""

    def test_motd_version_is_string(self):
        from code_puppy.command_line.motd import MOTD_VERSION

        assert isinstance(MOTD_VERSION, str)
        assert len(MOTD_VERSION) > 0

    def test_motd_message_is_string(self):
        from code_puppy.command_line.motd import MOTD_MESSAGE

        assert isinstance(MOTD_MESSAGE, str)
        assert len(MOTD_MESSAGE) > 0

    def test_motd_track_file_ends_with_motd_txt(self):
        from code_puppy.command_line.motd import MOTD_TRACK_FILE

        assert MOTD_TRACK_FILE.endswith("motd.txt")
        assert "code_puppy" in MOTD_TRACK_FILE
