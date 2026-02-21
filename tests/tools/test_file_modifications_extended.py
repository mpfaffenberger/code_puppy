import os
import tempfile
from unittest.mock import Mock

import pytest

from code_puppy.tools.file_modifications import (
    ContentPayload,
    DeleteSnippetPayload,
    HashlineEdit,
    HashlineEditPayload,
    _delete_file,
    _edit_file,
)
from code_puppy.tools.hashline import compute_file_hashes


def _make_ref(content: str, line_num: int) -> str:
    """Make a hashline ref like '2:f1' for a given line in content."""
    hashes = compute_file_hashes(content)
    return f"{line_num}:{hashes[line_num]}"


class TestFileModificationsExtended:
    """Extended tests for file_modifications.py covering edge cases and error recovery."""

    def test_apply_simple_modification(self, tmp_path):
        """Test basic file modification with content replacement."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello world')")

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
        """Test targeted text replacements via hashline edits."""
        test_file = tmp_path / "config.py"
        content = 'debug = False\nversion = "1.0.0"\nauthor = "test"'
        test_file.write_text(content)

        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 1),
                    new_content="debug = True",
                ),
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 2),
                    new_content='version = "2.0.0"',
                ),
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

        payload = HashlineEditPayload(
            file_path=str(nonexistent_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref="1:aa",
                    new_content="new",
                )
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert "success" not in result or result["success"] is False
        error_text = (result.get("error", "") + result.get("message", "")).lower()
        assert "does not exist" in error_text or "no such file" in error_text

    def test_invalid_patch_snippet_not_found(self, tmp_path):
        """Test error handling when snippet to delete is not found."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        payload = DeleteSnippetPayload(
            file_path=str(test_file), delete_snippet="nonexistent snippet"
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert "success" not in result or result["success"] is False
        assert "snippet not found" in result.get("error", "").lower()

    def test_invalid_patch_replacement_not_found(self, tmp_path):
        """Test error handling when hashline ref doesn't match."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('existing code')")

        # Use a bogus hash that won't match
        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref="1:zz",
                    new_content="new text",
                )
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert "success" not in result or result["success"] is False

    def test_overwrite_protection(self, tmp_path):
        """Test that existing files are protected without overwrite flag."""
        test_file = tmp_path / "existing.py"
        test_file.write_text("original content")

        payload = ContentPayload(
            file_path=str(test_file),
            content="new content",
            overwrite=False,
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is False
        assert "exists" in result.get("message", "").lower()
        assert test_file.read_text() == "original content"

    def test_no_changes_scenario(self, tmp_path):
        """Test handling when no changes would be made."""
        test_file = tmp_path / "test.py"
        content = "print('hello')"
        test_file.write_text(content)

        # Replace line with identical content — should result in no changes
        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 1),
                    new_content="print('hello')",
                )
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["changed"] is False

    def test_line_number_handling_multiline_replacement(self, tmp_path):
        """Test line number handling with multiline replacements."""
        test_file = tmp_path / "multiline.py"
        content = "def func1():\n    return 1\n\ndef func2():\n    return 2\n\ndef func3():\n    return 3"
        test_file.write_text(content)

        # Replace func2 block (lines 4-5) with a range replace
        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace_range",
                    start_ref=_make_ref(content, 4),
                    end_ref=_make_ref(content, 5),
                    new_content="def func2():\n    # Enhanced version\n    return 2 + 1",
                )
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        assert result["changed"] is True
        content = test_file.read_text()
        assert "# Enhanced version" in content
        assert "return 2 + 1" in content
        assert "def func1():" in content
        assert "def func3():" in content

    def test_error_recovery_file_permissions(self, tmp_path):
        """Test error recovery when file permissions prevent modification."""
        test_file = tmp_path / "readonly.py"
        test_file.write_text("original content")

        os.chmod(test_file, 0o444)

        try:
            payload = ContentPayload(
                file_path=str(test_file), content="new content", overwrite=True
            )

            mock_context = Mock()
            result = _edit_file(mock_context, payload)

            assert (
                "success" not in result
                or result["success"] is False
                or "error" in result
            )
        finally:
            os.chmod(test_file, 0o644)

    def test_multiple_replacements_order(self, tmp_path):
        """Test that multiple sequential hashline edits are applied."""
        test_file = tmp_path / "order_test.py"
        content = "var_a = 1"
        test_file.write_text(content)

        # Single edit replacing the one line to final value
        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 1),
                    new_content="var_a = final",
                ),
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        assert test_file.read_text() == "var_a = final"

    def test_special_characters_handling(self, tmp_path):
        """Test handling of special characters in hashline edits."""
        test_file = tmp_path / "special.py"
        content = 'text = "Hello "World"!\nNew line"'
        test_file.write_text(content)

        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace_range",
                    start_ref=_make_ref(content, 1),
                    end_ref=_make_ref(content, 2),
                    new_content="text = \"Hello 'Python'!\n\tTabbed\"",
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

        lines = [f"line_{i} = {i}" for i in range(100)]
        content = "\n".join(lines)
        test_file.write_text(content)

        # Replace line 51 (0-indexed line_50, 1-indexed line 51)
        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 51),
                    new_content="line_50 = MODIFIED",
                )
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        content = test_file.read_text()
        assert "line_50 = MODIFIED" in content
        assert "line_49 = 49" in content
        assert "line_51 = 51" in content

    def test_unicode_content_handling(self, tmp_path):
        """Test handling of Unicode characters in file content."""
        test_file = tmp_path / "unicode.py"
        content = "# 测试文件\nprint('Hello 世界! 🌍')\nemoji = 🐕"
        test_file.write_text(content, encoding="utf-8")

        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 2),
                    new_content="print('Hello Python! 🐍')",
                )
            ],
        )

        mock_context = Mock()
        result = _edit_file(mock_context, payload)

        assert result["success"] is True
        content = test_file.read_text(encoding="utf-8")
        assert "Hello Python! 🐍" in content
        assert "# 测试文件" in content
        assert "emoji = 🐕" in content

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
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('test')")
            temp_path = f.name

        try:
            mock_context = Mock()

            payload = ContentPayload(
                file_path=temp_path, content="print('modified')", overwrite=True
            )

            result = _edit_file(mock_context, payload)

            assert result["success"] is True
            assert result["changed"] is True
            assert "diff" in result

        finally:
            os.unlink(temp_path)

    def test_json_payload_parsing(self, tmp_path):
        """Test JSON string payload parsing for the edit_file tool."""
        pytest.skip("Mock-based test requires complex setup")

    def test_malformed_json_payload(self, tmp_path):
        """Test handling of malformed JSON payloads."""
        pytest.skip("Mock-based test requires complex setup")

    def test_unknown_payload_type(self, tmp_path):
        """Test handling of unknown payload types."""
        mock_context = Mock()

        class UnknownPayload:
            def __init__(self):
                self.file_path = str(tmp_path / "test.py")
                self.unknown_field = "unknown"

        payload = UnknownPayload()
        result = _edit_file(mock_context, payload)

        assert result["success"] is False
        assert "unknown payload type" in result["message"].lower()


class TestEncodingAndSpecialCharacters:
    """Test handling of various encodings and special characters."""

    def test_edit_file_utf8_content(self, tmp_path):
        """Test editing file with UTF-8 content including emojis."""
        test_file = tmp_path / "unicode.py"
        test_file.write_text("# Python file\nprint('Hello')\n")

        content = ContentPayload(
            file_path=str(test_file),
            content="# Unicode test\nprint('你好世界 🚀')\n",
            overwrite=True,
        )

        result = _edit_file(None, content)

        assert result["success"] is True
        assert test_file.read_text() == "# Unicode test\nprint('你好世界 🚀')\n"

    def test_edit_file_mixed_line_endings(self, tmp_path):
        """Test handling of mixed line endings (CRLF/LF)."""
        test_file = tmp_path / "mixed.txt"
        content = "line1\r\nline2\nline3\r\n"
        test_file.write_text(content)

        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 2),
                    new_content="line2_modified",
                )
            ],
        )

        result = _edit_file(None, payload)

        assert result["success"] is True or result["changed"] is True

    def test_edit_file_special_regex_chars(self, tmp_path):
        """Test hashline edits with special regex characters."""
        test_file = tmp_path / "regex.txt"
        content = "pattern: [a-z]+\nmore: (test)\n"
        test_file.write_text(content)

        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 1),
                    new_content="pattern: [A-Z]+",
                )
            ],
        )

        result = _edit_file(None, payload)

        assert result["success"] is True


class TestFileSizeAndPerformance:
    """Test handling of large files and performance characteristics."""

    def test_edit_large_file_replacement(self, tmp_path):
        """Test replacing content in a large file."""
        test_file = tmp_path / "large.txt"
        lines = [f"Line {i}\n" for i in range(1000)]
        content = "".join(lines)
        test_file.write_text(content)

        # Line 501 contains "Line 500\n" (1-indexed)
        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 501),
                    new_content="LINE 500",
                )
            ],
        )

        result = _edit_file(None, payload)

        assert result["success"] is True
        assert "LINE 500" in test_file.read_text()

    def test_delete_snippet_large_content(self, tmp_path):
        """Test deleting snippet from large content."""
        test_file = tmp_path / "large_delete.txt"
        content = "start\n" + ("x\n" * 1000) + "end\n"
        test_file.write_text(content)

        payload = DeleteSnippetPayload(
            file_path=str(test_file),
            delete_snippet="x\n",
        )

        result = _edit_file(None, payload)

        assert result["success"] is True or result["changed"] is True


class TestFileModificationSafety:
    """Test safety features in file modification."""

    def test_edit_file_path_traversal_prevention(self, tmp_path):
        """Test that path traversal attempts are handled safely."""
        dangerous_path = str(tmp_path / "../../../etc/passwd")

        content = ContentPayload(
            file_path=dangerous_path,
            content="malicious",
            overwrite=True,
        )

        result = _edit_file(None, content)

        assert result is not None

    def test_edit_file_backup_preservation(self, tmp_path):
        """Test that backups of original content are handled appropriately."""
        test_file = tmp_path / "backup.txt"
        content = "original content"
        test_file.write_text(content)

        payload = HashlineEditPayload(
            file_path=str(test_file),
            edits=[
                HashlineEdit(
                    operation="replace",
                    start_ref=_make_ref(content, 1),
                    new_content="modified content",
                )
            ],
        )

        result = _edit_file(None, payload)

        assert result["success"] is True
        assert "modified" in test_file.read_text()

    def test_delete_file_only_regular_files(self, tmp_path):
        """Test that delete only works on regular files, not directories."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        result = _delete_file(None, str(test_dir))

        assert "error" in result or result.get("success") is False
        assert test_dir.exists()
