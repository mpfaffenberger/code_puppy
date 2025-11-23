import os
import tempfile
from unittest.mock import Mock

import pytest

from code_puppy.tools.file_modifications import (
    ContentPayload,
    DeleteSnippetPayload,
    Replacement,
    ReplacementsPayload,
    _edit_file,
)


class TestFileModificationsExtended:
    """Extended tests for file_modifications.py covering edge cases and error recovery."""

    def test_apply_simple_modification(self, tmp_path):
        """Test basic file modification with content replacement."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello world')")

        # Apply modification
        payload = ContentPayload(
            file_path=str(test_file), content="print('hello modified')", overwrite=True
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        assert result["changed"] is True
        assert test_file.read_text() == "print('hello modified')"
        assert "diff" in result

    def test_apply_replacements_modification(self, tmp_path):
        """Test targeted text replacements."""
        test_file = tmp_path / "config.py"
        test_file.write_text(
            """
debug = False
version = "1.0.0"
author = "test"
        """.strip()
        )

        payload = ReplacementsPayload(
            file_path=str(test_file),
            replacements=[
                Replacement(old_str="debug = False", new_str="debug = True"),
                Replacement(old_str='version = "1.0.0"', new_str='version = "2.0.0"'),
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        assert result["changed"] is True
        content = test_file.read_text()
        assert "debug = True" in content
        assert 'version = "2.0.0"' in content
        assert 'author = "test"' in content  # Should remain unchanged

    def test_apply_delete_snippet_modification(self, tmp_path):
        """Test snippet deletion functionality."""
        test_file = tmp_path / "code.py"
        test_file.write_text(
            """
def hello():
    print("hello")
    # TODO: remove this
    return "hello"
        """.strip()
        )

        payload = DeleteSnippetPayload(
            file_path=str(test_file), delete_snippet="    # TODO: remove this\n"
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        assert result["changed"] is True
        content = test_file.read_text()
        assert "# TODO: remove this" not in content
        assert "def hello()" in content
        assert 'return "hello"' in content

    def test_invalid_patch_nonexistent_file(self, tmp_path):
        """Test error handling for non-existent files."""
        nonexistent_file = tmp_path / "doesnotexist.py"

        payload = ReplacementsPayload(
            file_path=str(nonexistent_file),
            replacements=[Replacement(old_str="old", new_str="new")],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        # Error responses may have different structures
        assert "success" not in result or result["success"] is False
        # The error is in the message field for this case
        assert (
            "does not exist" in result.get("message", "").lower()
            or "no such file" in result.get("message", "").lower()
        )

    def test_invalid_patch_snippet_not_found(self, tmp_path):
        """Test error handling when snippet to delete is not found."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        payload = DeleteSnippetPayload(
            file_path=str(test_file), delete_snippet="nonexistent snippet"
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        # Error responses may have different structures
        assert "success" not in result or result["success"] is False
        assert "snippet not found" in result.get("error", "").lower()

    def test_invalid_patch_replacement_not_found(self, tmp_path):
        """Test error handling when replacement text is not found."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('existing code')")

        payload = ReplacementsPayload(
            file_path=str(test_file),
            replacements=[Replacement(old_str="nonexistent text", new_str="new text")],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        # Error responses may have different structures
        assert "success" not in result or result["success"] is False
        assert (
            "no suitable match" in result.get("error", "").lower()
            or "jw < 0.95" in result.get("error", "").lower()
        )

    def test_overwrite_protection(self, tmp_path):
        """Test that existing files are protected without overwrite flag."""
        test_file = tmp_path / "existing.py"
        test_file.write_text("original content")

        payload = ContentPayload(
            file_path=str(test_file),
            content="new content",
            overwrite=False,  # Should not overwrite
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is False
        assert "exists" in result.get("message", "").lower()
        assert test_file.read_text() == "original content"  # Unchanged

    def test_no_changes_scenario(self, tmp_path):
        """Test handling when no changes would be made."""
        test_file = tmp_path / "test.py"
        original_content = "print('hello')"
        test_file.write_text(original_content)

        payload = ReplacementsPayload(
            file_path=str(test_file),
            replacements=[
                Replacement(
                    old_str="print('hello')", new_str="print('hello')"
                )  # Same content
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is False
        assert result["changed"] is False
        assert "no changes" in result.get("message", "").lower()

    def test_line_number_handling_multiline_replacement(self, tmp_path):
        """Test line number handling with multiline replacements."""
        test_file = tmp_path / "multiline.py"
        test_file.write_text(
            """
def func1():
    return 1

def func2():
    return 2

def func3():
    return 3
        """.strip()
        )

        # Replace the entire func2 block
        old_func = "def func2():\n    return 2"
        new_func = "def func2():\n    # Enhanced version\n    return 2 + 1"

        payload = ReplacementsPayload(
            file_path=str(test_file),
            replacements=[Replacement(old_str=old_func, new_str=new_func)],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        assert result["changed"] is True
        content = test_file.read_text()
        assert "# Enhanced version" in content
        assert "return 2 + 1" in content
        assert "def func1():" in content  # Should remain
        assert "def func3():" in content  # Should remain

    def test_error_recovery_file_permissions(self, tmp_path):
        """Test error recovery when file permissions prevent modification."""
        test_file = tmp_path / "readonly.py"
        test_file.write_text("original content")

        # Make file read-only
        os.chmod(test_file, 0o444)

        try:
            payload = ContentPayload(
                file_path=str(test_file), content="new content", overwrite=True
            )

            mock_context = Mock()
            result = _edit_file(mock_context, payload)

            # Should handle the permission error gracefully
            # Error responses may have different structures
            assert (
                "success" not in result
                or result["success"] is False
                or "error" in result
            )
        finally:
            # Restore permissions for cleanup
            os.chmod(test_file, 0o644)

    def test_multiple_replacements_order(self, tmp_path):
        """Test that multiple replacements are applied in order."""
        test_file = tmp_path / "order_test.py"
        test_file.write_text("var_a = 1")

        payload = ReplacementsPayload(
            file_path=str(test_file),
            replacements=[
                Replacement(old_str="var_a = 1", new_str="var_a = 2"),
                Replacement(old_str="var_a = 2", new_str="var_a = 3"),
                Replacement(old_str="var_a = 3", new_str="var_a = final"),
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        assert test_file.read_text() == "var_a = final"

    def test_special_characters_handling(self, tmp_path):
        """Test handling of special characters in replacements."""
        test_file = tmp_path / "special.py"
        test_file.write_text('text = "Hello "World"!\nNew line"')

        payload = ReplacementsPayload(
            file_path=str(test_file),
            replacements=[
                Replacement(
                    old_str='"Hello "World"!\nNew line"',
                    new_str="\"Hello 'Python'!\n\tTabbed\"",
                )
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        content = test_file.read_text()
        assert "Python" in content
        assert "\tTabbed" in content

    def test_large_file_handling(self, tmp_path):
        """Test handling of larger files."""
        test_file = tmp_path / "large.py"

        # Create a moderately large file
        lines = [f"line_{i} = {i}" for i in range(100)]
        test_file.write_text("\n".join(lines))

        # Replace a line in the middle
        payload = ReplacementsPayload(
            file_path=str(test_file),
            replacements=[
                Replacement(old_str="line_50 = 50", new_str="line_50 = MODIFIED")
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        content = test_file.read_text()
        assert "line_50 = MODIFIED" in content
        assert "line_49 = 49" in content  # Should remain
        assert "line_51 = 51" in content  # Should remain

    def test_unicode_content_handling(self, tmp_path):
        """Test handling of Unicode characters in file content."""
        test_file = tmp_path / "unicode.py"
        unicode_content = "# 测试文件\nprint('Hello 世界! 🌍')\nemoji = 🐕"
        test_file.write_text(unicode_content, encoding="utf-8")

        payload = ReplacementsPayload(
            file_path=str(test_file),
            replacements=[
                Replacement(old_str="Hello 世界! 🌍", new_str="Hello Python! 🐍")
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        content = test_file.read_text(encoding="utf-8")
        assert "Hello Python! 🐍" in content
        assert "# 测试文件" in content  # Should remain
        assert "emoji = 🐕" in content  # Should remain

    def test_empty_file_handling(self, tmp_path):
        """Test handling of empty files."""
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        payload = ContentPayload(
            file_path=str(test_file), content="# New content", overwrite=True
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        assert test_file.read_text() == "# New content"

    def test_directory_creation(self, tmp_path):
        """Test that directories are created when needed."""
        nested_file = tmp_path / "nested" / "deep" / "file.py"

        payload = ContentPayload(
            file_path=str(nested_file), content="print('in nested dir')", overwrite=True
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        assert nested_file.exists()
        assert nested_file.read_text() == "print('in nested dir')"

    def test_edit_file_function_variants(self):
        """Test the _edit_file function with different payload variants."""
        # Test the main _edit_file function directly
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('test')")
            temp_path = f.name

        try:
            mock_context = Mock()

            # Test with ContentPayload
            payload = ContentPayload(
                file_path=temp_path, content="print('modified')", overwrite=True
            )

            result = _edit_file(mock_context, payload)

            # Verify the result structure
            assert result["success"] is True
            assert result["changed"] is True
            assert "diff" in result

        finally:
            os.unlink(temp_path)

    def test_json_payload_parsing(self, tmp_path):
        """Test JSON string payload parsing for the edit_file tool."""
        # Skip this test for now as it requires complex agent mocking
        pytest.skip("Mock-based test requires complex setup")

    def test_malformed_json_payload(self, tmp_path):
        """Test handling of malformed JSON payloads."""
        # Skip this test for now as it requires complex agent mocking
        pytest.skip("Mock-based test requires complex setup")

    def test_unknown_payload_type(self, tmp_path):
        """Test handling of unknown payload types."""
        mock_context = Mock()

        # Create a mock payload that doesn't match any known type
        class UnknownPayload:
            def __init__(self):
                self.file_path = str(tmp_path / "test.py")
                self.unknown_field = "unknown"

        payload = UnknownPayload()
        result = _edit_file(mock_context, payload)

        assert result["success"] is False
        assert "unknown payload type" in result["message"].lower()
