#!/usr/bin/env python3
"""Test script to verify file permission prompts work correctly."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_puppy.tools.file_modifications import (
    prompt_for_file_permission,
    delete_snippet_from_file,
    write_to_file,
    replace_in_file,
    _delete_file,
)


class TestFilePermissions(unittest.TestCase):
    """Test cases for file permission prompts."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, "w") as f:
            f.write("Hello, world!\nThis is a test file.\n")

    def tearDown(self):
        """Clean up test environment."""
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        os.rmdir(self.temp_dir)

    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    @patch("sys.stdin.isatty")
    @patch("builtins.input")
    def test_prompt_for_file_permission_granted(
        self, mock_input, mock_isatty, mock_yolo
    ):
        """Test that permission is granted when user enters 'y'."""
        mock_yolo.return_value = False
        mock_isatty.return_value = True
        mock_input.return_value = "y"

        result = prompt_for_file_permission(self.test_file, "edit")
        self.assertTrue(result)

    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    @patch("sys.stdin.isatty")
    @patch("builtins.input")
    def test_prompt_for_file_permission_denied(
        self, mock_input, mock_isatty, mock_yolo
    ):
        """Test that permission is denied when user enters 'n'."""
        mock_yolo.return_value = False
        mock_isatty.return_value = True
        mock_input.return_value = "n"

        result = prompt_for_file_permission(self.test_file, "edit")
        self.assertFalse(result)

    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    def test_prompt_for_file_permission_yolo_mode(self, mock_yolo):
        """Test that permission is automatically granted in yolo mode."""
        mock_yolo.return_value = True

        result = prompt_for_file_permission(self.test_file, "edit")
        self.assertTrue(result)

    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    @patch("sys.stdin.isatty")
    def test_prompt_for_file_permission_non_tty(self, mock_isatty, mock_yolo):
        """Test that permission is automatically granted for non-TTY."""
        mock_yolo.return_value = False
        mock_isatty.return_value = False

        result = prompt_for_file_permission(self.test_file, "edit")
        self.assertTrue(result)

    @patch("code_puppy.tools.file_modifications.prompt_for_file_permission")
    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    def test_write_to_file_with_permission_denied(self, mock_yolo, mock_prompt):
        """Test write_to_file when permission is denied."""
        mock_yolo.return_value = False
        mock_prompt.return_value = False

        context = MagicMock()
        result = write_to_file(context, self.test_file, "New content", True)

        self.assertFalse(result["success"])
        self.assertIn("cancelled by user", result["message"])
        self.assertFalse(result["changed"])

    @patch("code_puppy.tools.file_modifications.prompt_for_file_permission")
    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    def test_write_to_file_with_permission_granted(self, mock_yolo, mock_prompt):
        """Test write_to_file when permission is granted."""
        mock_yolo.return_value = False
        mock_prompt.return_value = True

        context = MagicMock()
        result = write_to_file(context, self.test_file, "New content", True)

        self.assertTrue(result["success"])
        self.assertTrue(result["changed"])

        # Verify file was actually written
        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "New content")

    @patch("code_puppy.tools.file_modifications.prompt_for_file_permission")
    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    def test_write_to_file_in_yolo_mode(self, mock_yolo, mock_prompt):
        """Test write_to_file in yolo mode (no permission prompt)."""
        mock_yolo.return_value = True

        context = MagicMock()
        result = write_to_file(context, self.test_file, "Yolo content", True)

        self.assertTrue(result["success"])
        self.assertTrue(result["changed"])

        # Verify file was actually written
        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "Yolo content")

        # Verify prompt was not called
        mock_prompt.assert_not_called()

    @patch("code_puppy.tools.file_modifications.prompt_for_file_permission")
    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    def test_delete_snippet_with_permission_denied(self, mock_yolo, mock_prompt):
        """Test delete_snippet_from_file when permission is denied."""
        mock_yolo.return_value = False
        mock_prompt.return_value = False

        context = MagicMock()
        result = delete_snippet_from_file(context, self.test_file, "Hello, world!")

        self.assertFalse(result["success"])
        self.assertIn("cancelled by user", result["message"])
        self.assertFalse(result["changed"])

    @patch("code_puppy.tools.file_modifications.prompt_for_file_permission")
    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    def test_replace_in_file_with_permission_denied(self, mock_yolo, mock_prompt):
        """Test replace_in_file when permission is denied."""
        mock_yolo.return_value = False
        mock_prompt.return_value = False

        context = MagicMock()
        replacements = [{"old_str": "world", "new_str": "universe"}]
        result = replace_in_file(context, self.test_file, replacements)

        self.assertFalse(result["success"])
        self.assertIn("cancelled by user", result["message"])
        self.assertFalse(result["changed"])

    @patch("code_puppy.tools.file_modifications.prompt_for_file_permission")
    @patch("code_puppy.tools.file_modifications.get_yolo_mode")
    def test_delete_file_with_permission_denied(self, mock_yolo, mock_prompt):
        """Test _delete_file when permission is denied."""
        mock_yolo.return_value = False
        mock_prompt.return_value = False

        context = MagicMock()
        result = _delete_file(context, self.test_file)

        self.assertFalse(result["success"])
        self.assertIn("cancelled by user", result["message"])
        self.assertFalse(result["changed"])

        # Verify file still exists
        self.assertTrue(os.path.exists(self.test_file))


if __name__ == "__main__":
    unittest.main()
