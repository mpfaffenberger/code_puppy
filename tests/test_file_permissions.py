#!/usr/bin/env python3
"""Test script to verify file permission prompts work correctly."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_puppy.callbacks import on_file_permission
from code_puppy.tools.file_modifications import (
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

    @patch("code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission")
    def test_prompt_for_file_permission_granted(
        self, mock_prompt
    ):
        """Test that permission is granted when user enters 'y'."""
        mock_prompt.return_value = True

        result = on_file_permission(None, self.test_file, "edit")
        # Should return [True] from the mocked plugin
        self.assertEqual(result, [True])

    @patch("code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission")
    def test_prompt_for_file_permission_denied(
        self, mock_prompt
    ):
        """Test that permission is denied when user enters 'n'."""
        mock_prompt.return_value = False

        result = on_file_permission(None, self.test_file, "edit")
        # Should return [False] from the mocked plugin
        self.assertEqual(result, [False])

    def test_prompt_for_file_permission_no_plugins(self):
        """Test that permission is automatically granted when no plugins registered."""
        # Temporarily unregister plugins
        from code_puppy.callbacks import _callbacks
        original_callbacks = _callbacks["file_permission"].copy()
        _callbacks["file_permission"] = []
        
        try:
            result = on_file_permission(None, self.test_file, "edit")
            self.assertEqual(result, [])  # Should return empty list when no plugins
        finally:
            # Restore callbacks
            _callbacks["file_permission"] = original_callbacks

    @patch("code_puppy.callbacks.on_file_permission")
    def test_write_to_file_with_permission_denied(self, mock_permission):
        """Test write_to_file when permission is denied."""
        mock_permission.return_value = [False]

        context = MagicMock()
        result = write_to_file(context, self.test_file, "New content", True)

        self.assertFalse(result["success"])
        self.assertIn("USER REJECTED", result["message"])
        self.assertFalse(result["changed"])
        self.assertTrue(result["user_rejection"])
        self.assertEqual(result["rejection_type"], "explicit_user_denial")
        self.assertIn("Modify your approach", result["guidance"])

    @patch("code_puppy.callbacks.on_file_permission")
    def test_write_to_file_with_permission_granted(self, mock_permission):
        """Test write_to_file when permission is granted."""
        mock_permission.return_value = [True]

        context = MagicMock()
        result = write_to_file(context, self.test_file, "New content", True)

        self.assertTrue(result["success"])
        self.assertTrue(result["changed"])

        # Verify file was actually written
        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "New content")

    @patch("code_puppy.config.get_yolo_mode")
    def test_write_to_file_in_yolo_mode(self, mock_yolo):
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



    @patch("code_puppy.callbacks.on_file_permission")
    def test_delete_snippet_with_permission_denied(self, mock_permission):
        """Test delete_snippet_from_file when permission is denied."""
        mock_permission.return_value = [False]

        context = MagicMock()
        result = delete_snippet_from_file(context, self.test_file, "Hello, world!")

        self.assertFalse(result["success"])
        self.assertIn("USER REJECTED", result["message"])
        self.assertFalse(result["changed"])
        self.assertTrue(result["user_rejection"])
        self.assertEqual(result["rejection_type"], "explicit_user_denial")
        self.assertIn("Modify your approach", result["guidance"])

    @patch("code_puppy.callbacks.on_file_permission")
    def test_replace_in_file_with_permission_denied(self, mock_permission):
        """Test replace_in_file when permission is denied."""
        mock_permission.return_value = [False]

        context = MagicMock()
        replacements = [{"old_str": "world", "new_str": "universe"}]
        result = replace_in_file(context, self.test_file, replacements)

        self.assertFalse(result["success"])
        self.assertIn("USER REJECTED", result["message"])
        self.assertFalse(result["changed"])
        self.assertTrue(result["user_rejection"])
        self.assertEqual(result["rejection_type"], "explicit_user_denial")
        self.assertIn("Modify your approach", result["guidance"])

    @patch("code_puppy.callbacks.on_file_permission")
    def test_delete_file_with_permission_denied(self, mock_permission):
        """Test _delete_file when permission is denied."""
        mock_permission.return_value = [False]

        context = MagicMock()
        result = _delete_file(context, self.test_file)

        self.assertFalse(result["success"])
        self.assertIn("USER REJECTED", result["message"])
        self.assertFalse(result["changed"])
        self.assertTrue(result["user_rejection"])
        self.assertEqual(result["rejection_type"], "explicit_user_denial")
        self.assertIn("Modify your approach", result["guidance"])

        # Verify file still exists
        self.assertTrue(os.path.exists(self.test_file))


if __name__ == "__main__":
    unittest.main()
