"""
Comprehensive tests for the file permission handler plugin.

Tests cover permission prompts, preview generation, thread-safety,
user feedback handling, and YOLO mode support.
"""

import os
import tempfile
import threading
from unittest.mock import Mock, patch

from code_puppy.plugins.file_permission_handler.register_callbacks import (
    _generate_preview_from_operation_data,
    _preview_delete_file,
    _preview_delete_snippet,
    _preview_replace_in_file,
    _preview_write_to_file,
    _set_user_feedback,
    clear_diff_shown_flag,
    clear_user_feedback,
    get_file_permission_prompt_additions,
    get_last_user_feedback,
    get_permission_handler_help,
    handle_delete_file_permission,
    handle_edit_file_permission,
    handle_file_permission,
    prompt_for_file_permission,
    set_diff_already_shown,
    was_diff_already_shown,
)


class TestThreadLocalStorage:
    """Test thread-local storage for user feedback and diff tracking."""

    def test_set_and_get_user_feedback(self):
        """Test setting and retrieving user feedback."""
        clear_user_feedback()
        assert get_last_user_feedback() is None

        _set_user_feedback("User feedback here")
        assert get_last_user_feedback() == "User feedback here"

    def test_clear_user_feedback(self):
        """Test clearing user feedback."""
        _set_user_feedback("Some feedback")
        assert get_last_user_feedback() == "Some feedback"

        clear_user_feedback()
        assert get_last_user_feedback() is None

    def test_user_feedback_thread_isolation(self):
        """Test that user feedback is isolated per thread."""
        clear_user_feedback()
        _set_user_feedback("Main thread feedback")

        results = {}

        def other_thread():
            # Other thread should not see main thread's feedback
            results["initial"] = get_last_user_feedback()
            _set_user_feedback("Other thread feedback")
            results["after_set"] = get_last_user_feedback()

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()

        # Other thread should have seen None initially
        assert results["initial"] is None
        assert results["after_set"] == "Other thread feedback"

        # Main thread feedback should be unchanged
        assert get_last_user_feedback() == "Main thread feedback"

    def test_diff_shown_flag(self):
        """Test diff-already-shown flag."""
        clear_diff_shown_flag()
        assert was_diff_already_shown() is False

        set_diff_already_shown(True)
        assert was_diff_already_shown() is True

        clear_diff_shown_flag()
        assert was_diff_already_shown() is False

    def test_diff_flag_thread_isolation(self):
        """Test that diff flag is isolated per thread."""
        clear_diff_shown_flag()
        set_diff_already_shown(True)

        results = {}

        def other_thread():
            results["initial"] = was_diff_already_shown()
            set_diff_already_shown(False)
            results["after_set"] = was_diff_already_shown()

        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join()

        # Other thread should see default False
        assert results["initial"] is False
        assert results["after_set"] is False

        # Main thread flag should still be True
        assert was_diff_already_shown() is True


class TestPreviewDeletion:
    """Test preview generation for delete operations."""

    def test_preview_delete_snippet_basic(self):
        """Test basic snippet deletion preview."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("def hello():\n    print('hello')\n    pass\n")
            f.flush()

            try:
                preview = _preview_delete_snippet(f.name, "    pass\n")
                assert preview is not None
                assert "-" in preview  # Should have diff markers
                assert "pass" in preview
            finally:
                os.unlink(f.name)

    def test_preview_delete_snippet_not_found(self):
        """Test deletion preview when snippet doesn't exist."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("def hello():\n    print('hello')\n")
            f.flush()

            try:
                preview = _preview_delete_snippet(f.name, "not_in_file")
                assert preview is None
            finally:
                os.unlink(f.name)

    def test_preview_delete_snippet_nonexistent_file(self):
        """Test deletion preview with nonexistent file."""
        preview = _preview_delete_snippet("/nonexistent/file.py", "snippet")
        assert preview is None

    def test_preview_delete_file_basic(self):
        """Test basic file deletion preview."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('content')\n")
            f.flush()

            try:
                preview = _preview_delete_file(f.name)
                assert preview is not None
                assert "-" in preview  # Should have diff markers
                assert "print" in preview
            finally:
                os.unlink(f.name)

    def test_preview_delete_file_nonexistent(self):
        """Test deletion preview for nonexistent file."""
        preview = _preview_delete_file("/nonexistent/file.py")
        assert preview is None

    def test_preview_delete_file_directory(self):
        """Test deletion preview when path is directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            preview = _preview_delete_file(tmpdir)
            assert preview is None


class TestPreviewWriting:
    """Test preview generation for write operations."""

    def test_preview_write_new_file(self):
        """Test writing to a new file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "new_file.py")
            content = "print('hello')\n"

            preview = _preview_write_to_file(file_path, content, overwrite=False)
            assert preview is not None
            assert "print" in preview
            assert "+" in preview  # Should have diff markers

    def test_preview_write_existing_file_with_overwrite(self):
        """Test overwriting an existing file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("old content\n")
            f.flush()

            try:
                new_content = "new content\n"
                preview = _preview_write_to_file(f.name, new_content, overwrite=True)
                assert preview is not None
                assert "new content" in preview
            finally:
                os.unlink(f.name)

    def test_preview_write_existing_file_no_overwrite(self):
        """Test writing to existing file without overwrite flag."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("existing content\n")
            f.flush()

            try:
                new_content = "new content\n"
                preview = _preview_write_to_file(f.name, new_content, overwrite=False)
                assert preview is None
            finally:
                os.unlink(f.name)

    def test_preview_write_multiline_content(self):
        """Test writing multiline content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "multi.py")
            content = "def func():\n    pass\n\nprint('done')\n"

            preview = _preview_write_to_file(file_path, content)
            assert preview is not None
            assert "func" in preview
            assert "done" in preview


class TestPreviewReplacements:
    """Test preview generation for replacement operations."""

    def test_preview_replace_basic(self):
        """Test basic text replacement preview."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("def old_name():\n    return 42\n")
            f.flush()

            try:
                replacements = [{"old_str": "old_name", "new_str": "new_name"}]
                preview = _preview_replace_in_file(f.name, replacements)
                assert preview is not None
                assert "new_name" in preview
                assert "-" in preview or "+" in preview
            finally:
                os.unlink(f.name)

    def test_preview_replace_multiple(self):
        """Test multiple text replacements."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("old_var = 1\nold_func()\n")
            f.flush()

            try:
                replacements = [
                    {"old_str": "old_var", "new_str": "new_var"},
                    {"old_str": "old_func", "new_str": "new_func"},
                ]
                preview = _preview_replace_in_file(f.name, replacements)
                assert preview is not None
            finally:
                os.unlink(f.name)

    def test_preview_replace_not_found(self):
        """Test replacement when text doesn't exist."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("existing content\n")
            f.flush()

            try:
                replacements = [{"old_str": "not_found", "new_str": "new"}]
                preview = _preview_replace_in_file(f.name, replacements)
                assert preview is None
            finally:
                os.unlink(f.name)

    def test_preview_replace_no_changes(self):
        """Test replacement that doesn't change content."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("content\n")
            f.flush()

            try:
                replacements = [{"old_str": "content", "new_str": "content"}]
                preview = _preview_replace_in_file(f.name, replacements)
                assert preview is None
            finally:
                os.unlink(f.name)

    def test_preview_replace_empty_replacements(self):
        """Test replacement with empty list."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("content\n")
            f.flush()

            try:
                preview = _preview_replace_in_file(f.name, [])
                assert preview is None
            finally:
                os.unlink(f.name)


class TestPermissionPrompt:
    """Test permission prompt functionality."""

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode"
    )
    def test_prompt_yolo_mode_enabled(self, mock_yolo):
        """Test that YOLO mode skips permission prompt."""
        mock_yolo.return_value = True

        confirmed, feedback = prompt_for_file_permission("/tmp/file.py", "edit")

        assert confirmed is True
        assert feedback is None

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_user_approval"
    )
    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode"
    )
    def test_prompt_user_approves(self, mock_yolo, mock_approval):
        """Test permission prompt when user approves."""
        mock_yolo.return_value = False
        mock_approval.return_value = (True, None)

        confirmed, feedback = prompt_for_file_permission("/tmp/file.py", "edit")

        assert confirmed is True

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_user_approval"
    )
    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode"
    )
    def test_prompt_user_denies(self, mock_yolo, mock_approval):
        """Test permission prompt when user denies."""
        mock_yolo.return_value = False
        mock_approval.return_value = (False, None)

        confirmed, feedback = prompt_for_file_permission("/tmp/file.py", "edit")

        assert confirmed is False

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_user_approval"
    )
    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode"
    )
    def test_prompt_with_feedback(self, mock_yolo, mock_approval):
        """Test permission prompt with user feedback."""
        mock_yolo.return_value = False
        mock_approval.return_value = (False, "Add error handling")

        confirmed, feedback = prompt_for_file_permission("/tmp/file.py", "edit")

        assert confirmed is False
        assert feedback == "Add error handling"

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_user_approval"
    )
    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode"
    )
    def test_prompt_with_preview(self, mock_yolo, mock_approval):
        """Test permission prompt with preview."""
        mock_yolo.return_value = False
        mock_approval.return_value = (True, None)

        preview = "- old line\n+ new line\n"
        confirmed, feedback = prompt_for_file_permission(
            "/tmp/file.py", "edit", preview=preview
        )

        assert confirmed is True
        mock_approval.assert_called_once()
        call_kwargs = mock_approval.call_args[1]
        assert call_kwargs["preview"] == preview


class TestHandleEditFilePermission:
    """Test edit file permission handling."""

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission"
    )
    def test_handle_write_operation(self, mock_prompt):
        """Test handling write operation."""
        mock_prompt.return_value = (True, None)

        context = Mock()
        file_path = "/tmp/file.py"
        operation_data = {"content": "print('hello')\n", "overwrite": False}

        confirmed = handle_edit_file_permission(
            context, file_path, "write", operation_data
        )

        assert confirmed is True
        mock_prompt.assert_called_once()

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission"
    )
    def test_handle_replace_operation(self, mock_prompt):
        """Test handling replace operation."""
        mock_prompt.return_value = (True, None)

        context = Mock()
        file_path = "/tmp/file.py"
        operation_data = {"replacements": [{"old_str": "old", "new_str": "new"}]}

        confirmed = handle_edit_file_permission(
            context, file_path, "replace", operation_data
        )

        assert confirmed is True

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission"
    )
    def test_handle_delete_snippet_operation(self, mock_prompt):
        """Test handling delete snippet operation."""
        mock_prompt.return_value = (True, None)

        context = Mock()
        file_path = "/tmp/file.py"
        operation_data = {"delete_snippet": "to_delete"}

        confirmed = handle_edit_file_permission(
            context, file_path, "delete_snippet", operation_data
        )

        assert confirmed is True

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission"
    )
    def test_handle_stores_user_feedback(self, mock_prompt):
        """Test that feedback is stored in thread-local storage."""
        clear_user_feedback()
        mock_prompt.return_value = (False, "Fix the code")

        context = Mock()
        file_path = "/tmp/file.py"
        operation_data = {"content": "code"}

        confirmed = handle_edit_file_permission(
            context, file_path, "write", operation_data
        )

        assert confirmed is False
        assert get_last_user_feedback() == "Fix the code"


class TestHandleDeleteFilePermission:
    """Test delete file permission handling."""

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission"
    )
    def test_handle_delete_file(self, mock_prompt):
        """Test handling delete file operation."""
        mock_prompt.return_value = (True, None)

        context = Mock()
        file_path = "/tmp/file.py"

        confirmed = handle_delete_file_permission(context, file_path)

        assert confirmed is True
        mock_prompt.assert_called_once()

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission"
    )
    def test_handle_delete_file_denied(self, mock_prompt):
        """Test handling denied delete file operation."""
        mock_prompt.return_value = (False, "Keep the file")

        context = Mock()
        file_path = "/tmp/file.py"

        confirmed = handle_delete_file_permission(context, file_path)

        assert confirmed is False
        assert get_last_user_feedback() == "Keep the file"


class TestHandleFilePermission:
    """Test generic file permission handler."""

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission"
    )
    def test_handle_with_operation_data(self, mock_prompt):
        """Test handler with operation data."""
        mock_prompt.return_value = (True, None)

        context = Mock()
        file_path = "/tmp/file.py"
        operation_data = {"content": "print('test')\n"}

        confirmed = handle_file_permission(
            context, file_path, "write", operation_data=operation_data
        )

        assert confirmed is True

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.prompt_for_file_permission"
    )
    def test_handle_with_preview(self, mock_prompt):
        """Test handler with explicit preview."""
        mock_prompt.return_value = (True, None)

        context = Mock()
        file_path = "/tmp/file.py"
        preview = "+ added line\n"

        confirmed = handle_file_permission(context, file_path, "edit", preview=preview)

        assert confirmed is True
        mock_prompt.assert_called_once()


class TestGeneratePreview:
    """Test preview generation from operation data."""

    def test_generate_preview_delete_operation(self):
        """Test preview generation for delete operation."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("content\n")
            f.flush()

            try:
                preview = _generate_preview_from_operation_data(f.name, "delete", {})
                assert preview is not None
            finally:
                os.unlink(f.name)

    def test_generate_preview_write_operation(self):
        """Test preview generation for write operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "new.py")
            operation_data = {"content": "print('hello')\n", "overwrite": False}

            preview = _generate_preview_from_operation_data(
                file_path, "write", operation_data
            )
            assert preview is not None

    def test_generate_preview_unknown_operation(self):
        """Test preview generation for unknown operation."""
        preview = _generate_preview_from_operation_data("/tmp/file.py", "unknown", {})
        assert preview is None


class TestHelpFunctions:
    """Test help and documentation functions."""

    def test_get_permission_handler_help(self):
        """Test getting help information."""
        help_text = get_permission_handler_help()
        assert isinstance(help_text, str)
        assert "File Permission" in help_text
        assert "permission" in help_text.lower()

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode"
    )
    def test_get_prompt_additions_yolo_mode_off(self, mock_yolo):
        """Test prompt additions when YOLO mode is off."""
        mock_yolo.return_value = False

        additions = get_file_permission_prompt_additions()
        assert isinstance(additions, str)
        assert len(additions) > 0
        assert "USER FEEDBACK" in additions or "feedback" in additions.lower()

    @patch(
        "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode"
    )
    def test_get_prompt_additions_yolo_mode_on(self, mock_yolo):
        """Test prompt additions when YOLO mode is on."""
        mock_yolo.return_value = True

        additions = get_file_permission_prompt_additions()
        assert additions == ""


class TestPreviewEdgeCases:
    """Test edge cases in preview generation."""

    def test_preview_with_unicode_content(self):
        """Test preview with unicode characters."""
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".py", encoding="utf-8"
        ) as f:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write("message = '你好世界'\n")
            f.flush()

            try:
                replacements = [{"old_str": "你好", "new_str": "Hello"}]
                preview = _preview_replace_in_file(f.name, replacements)
                # Should handle unicode gracefully
                assert preview is None or isinstance(preview, str)
            finally:
                os.unlink(f.name)

    def test_preview_with_large_file(self):
        """Test preview generation with large file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            # Write 1000 lines
            for i in range(1000):
                f.write(f"line_{i}\n")
            f.flush()

            try:
                replacements = [{"old_str": "line_500", "new_str": "replaced"}]
                preview = _preview_replace_in_file(f.name, replacements)
                assert preview is not None
            finally:
                os.unlink(f.name)

    def test_preview_with_binary_file_content(self):
        """Test preview generation with binary content."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"\x00\x01\x02\x03")
            f.flush()

            try:
                # Should handle gracefully
                preview = _preview_delete_file(f.name)
                # Either None or a string (surrogate handling)
                assert preview is None or isinstance(preview, str)
            finally:
                os.unlink(f.name)
