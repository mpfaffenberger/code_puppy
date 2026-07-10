#!/usr/bin/env python3
"""Test script to verify file permission prompts work correctly."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pytest

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_puppy.callbacks import on_file_permission
from code_puppy.tools.file_modifications import (
    _delete_file,
    delete_snippet_from_file,
    replace_in_file,
    write_to_file,
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

    def test_prompt_for_file_permission_granted(self):
        """Test that permission is granted when user enters 'y'."""
        from code_puppy.callbacks import _callbacks

        # Create a mock callback that returns True
        def mock_callback(
            context,
            file_path,
            operation,
            preview=None,
            message_group=None,
            operation_data=None,
        ):
            return True

        # Register the mock callback
        original_callbacks = _callbacks["file_permission"].copy()
        _callbacks["file_permission"] = [mock_callback]

        try:
            result = on_file_permission(None, self.test_file, "edit")
            # Should return [True] from the mocked callback
            self.assertEqual(result, [True])
        finally:
            # Restore original callbacks
            _callbacks["file_permission"] = original_callbacks

    def test_prompt_for_file_permission_denied(self):
        """Test that permission is denied when user enters 'n'."""
        from code_puppy.callbacks import _callbacks

        # Create a mock callback that returns False
        def mock_callback(
            context,
            file_path,
            operation,
            preview=None,
            message_group=None,
            operation_data=None,
        ):
            return False

        # Register the mock callback
        original_callbacks = _callbacks["file_permission"].copy()
        _callbacks["file_permission"] = [mock_callback]

        try:
            result = on_file_permission(None, self.test_file, "edit")
            # Should return [False] from the mocked callback
            self.assertEqual(result, [False])
        finally:
            # Restore original callbacks
            _callbacks["file_permission"] = original_callbacks

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

        # Verify file still exists
        self.assertTrue(os.path.exists(self.test_file))


if __name__ == "__main__":
    unittest.main()


@pytest.fixture(autouse=True)
def _clear_file_permission_callbacks():
    from code_puppy.callbacks import clear_callbacks

    clear_callbacks("file_permission")
    yield
    clear_callbacks("file_permission")


@pytest.mark.asyncio
async def test_write_to_file_async_with_async_permission_granted(tmp_path):
    from code_puppy.callbacks import register_callback
    from code_puppy.tools.file_modifications import write_to_file_async

    target = tmp_path / "allowed.txt"

    async def approve(
        context,
        file_path,
        operation,
        preview=None,
        message_group=None,
        operation_data=None,
    ):
        return True

    register_callback("file_permission", approve)

    result = await write_to_file_async(MagicMock(), str(target), "allowed", False)

    assert result["success"] is True
    assert result["changed"] is True
    assert target.read_text() == "allowed"


@pytest.mark.asyncio
async def test_write_to_file_async_with_async_permission_denied(tmp_path):
    from code_puppy.callbacks import register_callback
    from code_puppy.tools.file_modifications import write_to_file_async

    target = tmp_path / "denied.txt"
    target.write_text("original")

    async def deny(
        context,
        file_path,
        operation,
        preview=None,
        message_group=None,
        operation_data=None,
    ):
        return False

    register_callback("file_permission", deny)

    result = await write_to_file_async(MagicMock(), str(target), "changed", True)

    assert result["success"] is False
    assert result["user_rejection"] is True
    assert target.read_text() == "original"


@pytest.mark.asyncio
async def test_write_to_file_async_false_denies_even_with_true_and_none(tmp_path):
    from code_puppy.callbacks import register_callback
    from code_puppy.tools.file_modifications import write_to_file_async

    target = tmp_path / "mixed.txt"
    target.write_text("original")

    def no_op(
        context,
        file_path,
        operation,
        preview=None,
        message_group=None,
        operation_data=None,
    ):
        return None

    async def approve(
        context,
        file_path,
        operation,
        preview=None,
        message_group=None,
        operation_data=None,
    ):
        return True

    async def deny(
        context,
        file_path,
        operation,
        preview=None,
        message_group=None,
        operation_data=None,
    ):
        return False

    register_callback("file_permission", no_op)
    register_callback("file_permission", approve)
    register_callback("file_permission", deny)

    result = await write_to_file_async(MagicMock(), str(target), "changed", True)

    assert result["success"] is False
    assert target.read_text() == "original"


@pytest.mark.asyncio
async def test_write_to_file_async_none_only_does_not_deny(tmp_path):
    from code_puppy.callbacks import register_callback
    from code_puppy.tools.file_modifications import write_to_file_async

    target = tmp_path / "none.txt"

    async def no_op(
        context,
        file_path,
        operation,
        preview=None,
        message_group=None,
        operation_data=None,
    ):
        return None

    register_callback("file_permission", no_op)

    result = await write_to_file_async(MagicMock(), str(target), "created", False)

    assert result["success"] is True
    assert target.read_text() == "created"


@pytest.mark.asyncio
async def test_replace_and_delete_async_permission_paths(tmp_path):
    from code_puppy.callbacks import register_callback
    from code_puppy.tools.file_modifications import (
        _delete_file_async,
        delete_snippet_from_file_async,
        replace_in_file_async,
    )

    target = tmp_path / "ops.txt"
    target.write_text("hello world\nremove me\n")

    async def approve(
        context,
        file_path,
        operation,
        preview=None,
        message_group=None,
        operation_data=None,
    ):
        return True

    register_callback("file_permission", approve)

    replace_result = await replace_in_file_async(
        MagicMock(), str(target), [{"old_str": "world", "new_str": "there"}]
    )
    assert replace_result["success"] is True
    assert "hello there" in target.read_text()

    delete_snippet_result = await delete_snippet_from_file_async(
        MagicMock(), str(target), "remove me\n"
    )
    assert delete_snippet_result["success"] is True
    assert "remove me" not in target.read_text()

    delete_file_result = await _delete_file_async(MagicMock(), str(target))
    assert delete_file_result["success"] is True
    assert not target.exists()
