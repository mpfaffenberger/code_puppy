"""
Tests for the copy button component.
"""

from unittest.mock import MagicMock, patch

from code_puppy.tui.components.copy_button import CopyButton


class TestCopyButton:
    """Test cases for the CopyButton widget."""

    def test_copy_button_creation(self):
        """Test that a copy button can be created with text."""
        test_text = "Hello, World!"
        button = CopyButton(test_text)

        assert button.text_to_copy == test_text
        assert button.label == "📋 Copy"

    def test_update_text_to_copy(self):
        """Test updating the text to copy."""
        button = CopyButton("Initial text")
        new_text = "Updated text"

        button.update_text_to_copy(new_text)

        assert button.text_to_copy == new_text

    @patch("subprocess.run")
    def test_copy_to_clipboard_macos_success(self, mock_run):
        """Test successful clipboard copy on macOS."""
        mock_run.return_value = MagicMock(returncode=0)

        with patch("sys.platform", "darwin"):
            button = CopyButton("test content")
            success, error = button.copy_to_clipboard("test content")

            assert success is True
            assert error is None
            mock_run.assert_called_once_with(
                ["pbcopy"],
                input="test content",
                text=True,
                check=True,
                capture_output=True,
            )

    @patch("subprocess.run")
    def test_copy_to_clipboard_windows_success(self, mock_run):
        """Test successful clipboard copy on Windows."""
        mock_run.return_value = MagicMock(returncode=0)

        with patch("sys.platform", "win32"):
            button = CopyButton("test content")
            success, error = button.copy_to_clipboard("test content")

            assert success is True
            assert error is None
            mock_run.assert_called_once_with(
                ["clip"],
                input="test content",
                text=True,
                check=True,
                capture_output=True,
            )

    @patch("subprocess.run")
    def test_copy_to_clipboard_linux_success(self, mock_run):
        """Test successful clipboard copy on Linux with xclip."""
        mock_run.return_value = MagicMock(returncode=0)

        with patch("sys.platform", "linux"):
            button = CopyButton("test content")
            success, error = button.copy_to_clipboard("test content")

            assert success is True
            assert error is None
            mock_run.assert_called_once_with(
                ["xclip", "-selection", "clipboard"],
                input="test content",
                text=True,
                check=True,
                capture_output=True,
            )

    @patch("subprocess.run")
    def test_copy_to_clipboard_linux_xsel_fallback(self, mock_run):
        """Test Linux clipboard copy falls back to xsel when xclip fails."""
        # First call (xclip) fails, second call (xsel) succeeds
        mock_run.side_effect = [
            FileNotFoundError("xclip not found"),
            MagicMock(returncode=0),
        ]

        with patch("sys.platform", "linux"):
            button = CopyButton("test content")
            success, error = button.copy_to_clipboard("test content")

            assert success is True
            assert error is None
            assert mock_run.call_count == 2
            # Check that xsel was called as fallback
            mock_run.assert_any_call(
                ["xsel", "--clipboard", "--input"],
                input="test content",
                text=True,
                check=True,
                capture_output=True,
            )

    @patch("subprocess.run")
    def test_copy_to_clipboard_failure(self, mock_run):
        """Test clipboard copy failure handling."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "pbcopy", "Command failed")

        with patch("sys.platform", "darwin"):
            button = CopyButton("test content")
            success, error = button.copy_to_clipboard("test content")

            assert success is False
            assert "Clipboard command failed" in error

    @patch("subprocess.run")
    def test_copy_to_clipboard_no_utility(self, mock_run):
        """Test clipboard copy when utility is not found."""
        mock_run.side_effect = FileNotFoundError("Command not found")

        with patch("sys.platform", "linux"):
            button = CopyButton("test content")
            success, error = button.copy_to_clipboard("test content")

            assert success is False
            assert "Clipboard utilities not found" in error

    def test_copy_button_labels(self):
        """Test that copy button has correct labels."""
        button = CopyButton("test")

        assert button._original_label == "📋 Copy"
        assert button._copied_label == "✅ Copied!"

    def test_copy_completed_message(self):
        """Test CopyCompleted message creation."""
        # Test success message
        success_msg = CopyButton.CopyCompleted(True)
        assert success_msg.success is True
        assert success_msg.error is None

        # Test error message
        error_msg = CopyButton.CopyCompleted(False, "Test error")
        assert error_msg.success is False
        assert error_msg.error == "Test error"

    @patch.object(CopyButton, "copy_to_clipboard")
    @patch.object(CopyButton, "post_message")
    def test_action_press_success(self, mock_post_message, mock_copy):
        """Test action_press method with successful copy."""
        mock_copy.return_value = (True, None)

        button = CopyButton("test content")
        button.action_press()

        mock_copy.assert_called_once_with("test content")
        mock_post_message.assert_called_once()
        # Note: timer is currently commented out in implementation

        # Check that the message posted is a CopyCompleted with success=True
        call_args = mock_post_message.call_args[0][0]
        assert isinstance(call_args, CopyButton.CopyCompleted)
        assert call_args.success is True

    @patch.object(CopyButton, "copy_to_clipboard")
    @patch.object(CopyButton, "post_message")
    def test_action_press_failure(self, mock_post_message, mock_copy):
        """Test action_press method with failed copy."""
        mock_copy.return_value = (False, "Test error")

        button = CopyButton("test content")
        button.action_press()

        mock_copy.assert_called_once_with("test content")
        mock_post_message.assert_called_once()

        # Check that the message posted is a CopyCompleted with success=False
        call_args = mock_post_message.call_args[0][0]
        assert isinstance(call_args, CopyButton.CopyCompleted)
        assert call_args.success is False
        assert call_args.error == "Test error"
