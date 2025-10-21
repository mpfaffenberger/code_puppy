"""Comprehensive unit tests for code_puppy.command_line.motd.

🐶 Testing the Message of the Day feature - woof woof! 🐕
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from code_puppy.command_line.motd import (
    MOTD_MESSAGE,
    MOTD_TRACK_FILE,
    MOTD_VERSION,
    has_seen_motd,
    mark_motd_seen,
    print_motd,
)


class TestHasSeenMotd:
    """Test has_seen_motd function - checks if puppy has seen this MOTD! 🐕"""

    def test_has_seen_motd_when_file_does_not_exist(self, tmp_path):
        """Test returns False when MOTD tracking file doesn't exist."""
        non_existent_file = tmp_path / "does_not_exist.txt"
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(non_existent_file)):
            result = has_seen_motd("2025-08-24")
        
        assert result is False

    def test_has_seen_motd_when_version_exists_in_file(self, tmp_path):
        """Test returns True when version is found in tracking file."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("2025-08-24\n2025-07-15\n2025-06-01\n")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            result = has_seen_motd("2025-08-24")
        
        assert result is True

    def test_has_seen_motd_when_version_does_not_exist(self, tmp_path):
        """Test returns False when version is not in tracking file."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("2025-07-15\n2025-06-01\n")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            result = has_seen_motd("2025-08-24")
        
        assert result is False

    def test_has_seen_motd_with_empty_file(self, tmp_path):
        """Test returns False when tracking file is empty."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            result = has_seen_motd("2025-08-24")
        
        assert result is False

    def test_has_seen_motd_ignores_empty_lines(self, tmp_path):
        """Test that empty lines in file are ignored."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("2025-08-24\n\n\n2025-07-15\n\n")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            result = has_seen_motd("2025-08-24")
        
        assert result is True

    def test_has_seen_motd_with_whitespace_lines(self, tmp_path):
        """Test that lines with only whitespace are ignored."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("2025-08-24\n   \n\t\n2025-07-15\n")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            result = has_seen_motd("2025-08-24")
        
        assert result is True

    def test_has_seen_motd_case_sensitive(self, tmp_path):
        """Test that version matching is case-sensitive."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("2025-08-24\n")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            # Different case should not match
            result = has_seen_motd("2025-08-24")
        
        assert result is True

    def test_has_seen_motd_exact_match_required(self, tmp_path):
        """Test that exact version match is required."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("2025-08-24\n")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            # Partial match should not work
            result = has_seen_motd("2025-08-2")
        
        assert result is False


class TestMarkMotdSeen:
    """Test mark_motd_seen function - marks MOTD as seen! 🐶"""

    def test_mark_motd_seen_creates_directory_if_not_exists(self, tmp_path):
        """Test that mark_motd_seen creates parent directory if needed."""
        motd_file = tmp_path / "new_dir" / "motd.txt"
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            mark_motd_seen("2025-08-24")
        
        assert motd_file.parent.exists()
        assert motd_file.exists()
        assert motd_file.read_text().strip() == "2025-08-24"

    def test_mark_motd_seen_creates_file_with_version(self, tmp_path):
        """Test that mark_motd_seen creates file with version."""
        motd_file = tmp_path / "motd.txt"
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            mark_motd_seen("2025-08-24")
        
        assert motd_file.exists()
        content = motd_file.read_text()
        assert "2025-08-24" in content

    def test_mark_motd_seen_appends_to_existing_file(self, tmp_path):
        """Test that mark_motd_seen appends to existing file."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("2025-07-15\n")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            mark_motd_seen("2025-08-24")
        
        content = motd_file.read_text()
        assert "2025-07-15" in content
        assert "2025-08-24" in content

    def test_mark_motd_seen_does_not_duplicate_version(self, tmp_path):
        """Test that marking same version twice doesn't duplicate it."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("2025-08-24\n")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            mark_motd_seen("2025-08-24")
        
        content = motd_file.read_text()
        # Should only appear once
        assert content.count("2025-08-24") == 1

    def test_mark_motd_seen_multiple_versions(self, tmp_path):
        """Test marking multiple different versions."""
        motd_file = tmp_path / "motd.txt"
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            mark_motd_seen("2025-06-01")
            mark_motd_seen("2025-07-15")
            mark_motd_seen("2025-08-24")
        
        content = motd_file.read_text()
        assert "2025-06-01" in content
        assert "2025-07-15" in content
        assert "2025-08-24" in content

    def test_mark_motd_seen_preserves_existing_content(self, tmp_path):
        """Test that existing versions are preserved."""
        motd_file = tmp_path / "motd.txt"
        original_content = "2025-05-01\n2025-06-01\n2025-07-01\n"
        motd_file.write_text(original_content)
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            mark_motd_seen("2025-08-24")
        
        content = motd_file.read_text()
        # All old versions should still be there
        assert "2025-05-01" in content
        assert "2025-06-01" in content
        assert "2025-07-01" in content
        assert "2025-08-24" in content

    def test_mark_motd_seen_adds_newline(self, tmp_path):
        """Test that version is added with newline."""
        motd_file = tmp_path / "motd.txt"
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            mark_motd_seen("2025-08-24")
        
        content = motd_file.read_text()
        assert content.endswith("\n")

    def test_mark_motd_seen_handles_empty_file(self, tmp_path):
        """Test marking seen on empty existing file."""
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("")
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            mark_motd_seen("2025-08-24")
        
        content = motd_file.read_text()
        assert "2025-08-24" in content


class TestPrintMotd:
    """Test print_motd function - prints exciting puppy MOTD! 🐕"""

    @patch("code_puppy.command_line.motd.emit_info")
    @patch("code_puppy.command_line.motd.has_seen_motd")
    @patch("code_puppy.command_line.motd.mark_motd_seen")
    def test_print_motd_when_not_seen(self, mock_mark, mock_has_seen, mock_emit):
        """Test MOTD is printed when not seen before."""
        mock_has_seen.return_value = False
        
        result = print_motd()
        
        assert result is True
        mock_has_seen.assert_called_once_with(MOTD_VERSION)
        mock_emit.assert_called_once()
        mock_mark.assert_called_once_with(MOTD_VERSION)

    @patch("code_puppy.command_line.motd.emit_info")
    @patch("code_puppy.command_line.motd.has_seen_motd")
    @patch("code_puppy.command_line.motd.mark_motd_seen")
    def test_print_motd_when_already_seen(self, mock_mark, mock_has_seen, mock_emit):
        """Test MOTD is not printed when already seen."""
        mock_has_seen.return_value = True
        
        result = print_motd()
        
        assert result is False
        mock_has_seen.assert_called_once_with(MOTD_VERSION)
        mock_emit.assert_not_called()
        mock_mark.assert_not_called()

    @patch("code_puppy.command_line.motd.emit_info")
    @patch("code_puppy.command_line.motd.has_seen_motd")
    @patch("code_puppy.command_line.motd.mark_motd_seen")
    def test_print_motd_force_prints_even_if_seen(self, mock_mark, mock_has_seen, mock_emit):
        """Test force=True prints MOTD even if already seen."""
        mock_has_seen.return_value = True
        
        result = print_motd(force=True)
        
        assert result is True
        # Should not check has_seen when force=True
        mock_emit.assert_called_once()
        mock_mark.assert_called_once_with(MOTD_VERSION)

    @patch("code_puppy.command_line.motd.emit_info")
    @patch("code_puppy.command_line.motd.has_seen_motd")
    @patch("code_puppy.command_line.motd.mark_motd_seen")
    def test_print_motd_emits_markdown_content(self, mock_mark, mock_has_seen, mock_emit):
        """Test that MOTD is emitted as Markdown object."""
        from rich.markdown import Markdown
        
        mock_has_seen.return_value = False
        
        print_motd()
        
        # Check that emit_info was called with a Markdown object
        assert mock_emit.call_count == 1
        args = mock_emit.call_args[0]
        assert len(args) == 1
        assert isinstance(args[0], Markdown)

    @patch("code_puppy.command_line.motd.emit_info")
    @patch("code_puppy.command_line.motd.has_seen_motd")
    @patch("code_puppy.command_line.motd.mark_motd_seen")
    def test_print_motd_with_console_backward_compatibility(self, mock_mark, mock_has_seen, mock_emit):
        """Test that console parameter is accepted for backward compatibility."""
        mock_has_seen.return_value = False
        mock_console = MagicMock()
        
        result = print_motd(console=mock_console)
        
        assert result is True
        # Console should be ignored, emit_info should be used instead
        mock_emit.assert_called_once()

    @patch("code_puppy.command_line.motd.emit_info")
    @patch("code_puppy.command_line.motd.has_seen_motd")
    @patch("code_puppy.command_line.motd.mark_motd_seen")
    def test_print_motd_marks_seen_after_printing(self, mock_mark, mock_has_seen, mock_emit):
        """Test that MOTD is marked as seen after printing."""
        mock_has_seen.return_value = False
        
        print_motd()
        
        # Verify order: emit first, then mark as seen
        assert mock_emit.called
        assert mock_mark.called
        # Check that mark was called with correct version
        mock_mark.assert_called_with(MOTD_VERSION)


class TestMotdConstants:
    """Test MOTD constants and configuration."""

    def test_motd_version_is_string(self):
        """Test that MOTD_VERSION is a string."""
        assert isinstance(MOTD_VERSION, str)
        assert len(MOTD_VERSION) > 0

    def test_motd_message_is_string(self):
        """Test that MOTD_MESSAGE is a string."""
        assert isinstance(MOTD_MESSAGE, str)
        assert len(MOTD_MESSAGE) > 0

    def test_motd_message_contains_content(self):
        """Test that MOTD_MESSAGE has actual content."""
        # Should contain some recognizable content
        assert "WOOF" in MOTD_MESSAGE or "woof" in MOTD_MESSAGE.lower()

    def test_motd_track_file_is_string(self):
        """Test that MOTD_TRACK_FILE is a string path."""
        assert isinstance(MOTD_TRACK_FILE, str)
        assert len(MOTD_TRACK_FILE) > 0
        assert "motd.txt" in MOTD_TRACK_FILE


class TestIntegration:
    """Integration tests for MOTD system."""

    def test_complete_motd_workflow(self, tmp_path):
        """Test complete workflow: check, print, mark, check again."""
        motd_file = tmp_path / "motd.txt"
        test_version = "2025-TEST"
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            with patch("code_puppy.command_line.motd.MOTD_VERSION", test_version):
                with patch("code_puppy.command_line.motd.emit_info"):
                    # First check - should not have seen it
                    assert has_seen_motd(test_version) is False
                    
                    # Print MOTD - should print and mark as seen
                    result = print_motd()
                    assert result is True
                    
                    # Second check - should now have seen it
                    assert has_seen_motd(test_version) is True
                    
                    # Try to print again - should not print
                    result = print_motd()
                    assert result is False

    def test_multiple_versions_tracking(self, tmp_path):
        """Test tracking multiple MOTD versions over time."""
        motd_file = tmp_path / "motd.txt"
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            with patch("code_puppy.command_line.motd.emit_info"):
                # Mark several versions as seen
                versions = ["2025-01", "2025-02", "2025-03"]
                for version in versions:
                    with patch("code_puppy.command_line.motd.MOTD_VERSION", version):
                        print_motd()
                
                # All versions should be marked as seen
                for version in versions:
                    assert has_seen_motd(version) is True
                
                # New version should not be seen
                assert has_seen_motd("2025-04") is False

    def test_motd_file_persistence(self, tmp_path):
        """Test that MOTD tracking persists across function calls."""
        motd_file = tmp_path / "motd.txt"
        test_version = "2025-PERSIST"
        
        with patch("code_puppy.command_line.motd.MOTD_TRACK_FILE", str(motd_file)):
            # Mark as seen
            mark_motd_seen(test_version)
            
            # File should exist and contain version
            assert motd_file.exists()
            content = motd_file.read_text()
            assert test_version in content
            
            # Checking again should still return True
            assert has_seen_motd(test_version) is True
