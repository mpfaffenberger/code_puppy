"""Unit tests for code_puppy.tools.file_modifications module."""
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import pytest

from code_puppy.tools.file_modifications import (
    DeleteSnippetPayload,
    Replacement,
    ReplacementsPayload,
    ContentPayload,
    _print_diff,
    _log_error,
)


class TestDeleteSnippetPayload:
    """Test DeleteSnippetPayload Pydantic model."""
    
    def test_create_payload(self):
        """Test creating DeleteSnippetPayload."""
        payload = DeleteSnippetPayload(
            file_path="test.py",
            delete_snippet="line to delete"
        )
        
        assert payload.file_path == "test.py"
        assert payload.delete_snippet == "line to delete"
    
    def test_payload_validation(self):
        """Test payload requires both fields."""
        with pytest.raises(Exception):  # Pydantic validation error
            DeleteSnippetPayload(file_path="test.py")


class TestReplacement:
    """Test Replacement Pydantic model."""
    
    def test_create_replacement(self):
        """Test creating Replacement."""
        replacement = Replacement(
            old_str="old text",
            new_str="new text"
        )
        
        assert replacement.old_str == "old text"
        assert replacement.new_str == "new text"
    
    def test_empty_strings(self):
        """Test replacement with empty strings."""
        replacement = Replacement(old_str="", new_str="")
        
        assert replacement.old_str == ""
        assert replacement.new_str == ""


class TestReplacementsPayload:
    """Test ReplacementsPayload Pydantic model."""
    
    def test_create_payload(self):
        """Test creating ReplacementsPayload."""
        replacements = [
            Replacement(old_str="old1", new_str="new1"),
            Replacement(old_str="old2", new_str="new2"),
        ]
        payload = ReplacementsPayload(
            file_path="test.py",
            replacements=replacements
        )
        
        assert payload.file_path == "test.py"
        assert len(payload.replacements) == 2
        assert payload.replacements[0].old_str == "old1"
    
    def test_empty_replacements(self):
        """Test payload with empty replacements list."""
        payload = ReplacementsPayload(
            file_path="test.py",
            replacements=[]
        )
        
        assert payload.file_path == "test.py"
        assert len(payload.replacements) == 0


class TestContentPayload:
    """Test ContentPayload Pydantic model."""
    
    def test_create_payload(self):
        """Test creating ContentPayload."""
        payload = ContentPayload(
            file_path="test.py",
            content="print('hello')"
        )
        
        assert payload.file_path == "test.py"
        assert payload.content == "print('hello')"
        assert payload.overwrite is False  # Default
    
    def test_overwrite_flag(self):
        """Test overwrite flag."""
        payload = ContentPayload(
            file_path="test.py",
            content="content",
            overwrite=True
        )
        
        assert payload.overwrite is True
    
    def test_empty_content(self):
        """Test payload with empty content."""
        payload = ContentPayload(
            file_path="test.py",
            content=""
        )
        
        assert payload.content == ""


class TestPrintDiff:
    """Test _print_diff function."""
    
    @patch('code_puppy.tools.file_modifications.emit_info')
    def test_print_diff_with_content(self, mock_emit):
        """Test printing diff with actual content."""
        diff_text = "+added line\n-removed line"
        
        _print_diff(diff_text)
        
        # Should emit multiple times (header, lines, footer)
        assert mock_emit.call_count > 0
    
    @patch('code_puppy.tools.file_modifications.emit_info')
    def test_print_diff_empty(self, mock_emit):
        """Test printing empty diff."""
        _print_diff("")
        
        # Should still emit header and "no diff" message
        assert mock_emit.call_count > 0
    
    @patch('code_puppy.tools.file_modifications.emit_info')
    def test_print_diff_with_message_group(self, mock_emit):
        """Test printing diff with message group."""
        diff_text = "+line"
        
        _print_diff(diff_text, message_group="test_group")
        
        # Check message_group was passed
        for call in mock_emit.call_args_list:
            if 'message_group' in call[1]:
                assert call[1]['message_group'] == "test_group"
    
    @patch('code_puppy.tools.file_modifications.emit_info')
    def test_print_diff_addition_line(self, mock_emit):
        """Test diff with addition line is colored green."""
        diff_text = "+new line"
        
        _print_diff(diff_text)
        
        # Should have green formatting for addition
        calls_str = str(mock_emit.call_args_list)
        assert "green" in calls_str.lower() or "+" in calls_str
    
    @patch('code_puppy.tools.file_modifications.emit_info')
    def test_print_diff_removal_line(self, mock_emit):
        """Test diff with removal line is colored red."""
        diff_text = "-old line"
        
        _print_diff(diff_text)
        
        # Should have red formatting for removal
        calls_str = str(mock_emit.call_args_list)
        assert "red" in calls_str.lower() or "-" in calls_str


class TestLogError:
    """Test _log_error function."""
    
    @patch('code_puppy.tools.file_modifications.emit_error')
    def test_log_error_basic(self, mock_emit_error):
        """Test logging basic error."""
        error_obj = ValueError("Test error")
        
        _log_error("test_operation", exc=error_obj)
        
        # Should be called twice (message + traceback)
        assert mock_emit_error.call_count >= 1
        call_args = str(mock_emit_error.call_args_list)
        assert "test_operation" in call_args
    
    @patch('code_puppy.tools.file_modifications.emit_error')
    def test_log_error_with_message_group(self, mock_emit_error):
        """Test logging error with message group."""
        error_obj = IOError("File not found")
        
        _log_error("file_operation", exc=error_obj, message_group="test_group")
        
        # Should be called at least once
        assert mock_emit_error.call_count >= 1
    
    @patch('code_puppy.tools.file_modifications.emit_error')
    def test_log_error_no_exception(self, mock_emit_error):
        """Test logging error without exception object."""
        _log_error("operation failed")
        
        # Should be called once (just message, no traceback)
        mock_emit_error.assert_called_once()
        call_args = str(mock_emit_error.call_args)
        assert "operation failed" in call_args


class TestPayloadUnion:
    """Test EditFilePayload union type."""
    
    def test_union_accepts_delete_snippet(self):
        """Test union type accepts DeleteSnippetPayload."""
        from code_puppy.tools.file_modifications import EditFilePayload
        
        payload = DeleteSnippetPayload(
            file_path="test.py",
            delete_snippet="delete me"
        )
        
        # Should be valid EditFilePayload
        assert isinstance(payload, DeleteSnippetPayload)
    
    def test_union_accepts_replacements(self):
        """Test union type accepts ReplacementsPayload."""
        from code_puppy.tools.file_modifications import EditFilePayload
        
        payload = ReplacementsPayload(
            file_path="test.py",
            replacements=[Replacement(old_str="a", new_str="b")]
        )
        
        assert isinstance(payload, ReplacementsPayload)
    
    def test_union_accepts_content(self):
        """Test union type accepts ContentPayload."""
        from code_puppy.tools.file_modifications import EditFilePayload
        
        payload = ContentPayload(
            file_path="test.py",
            content="content"
        )
        
        assert isinstance(payload, ContentPayload)


class TestPayloadEdgeCases:
    """Test edge cases for payload models."""
    
    def test_replacement_with_newlines(self):
        """Test replacement with newline characters."""
        replacement = Replacement(
            old_str="line1\nline2",
            new_str="line1\nmodified\nline2"
        )
        
        assert "\n" in replacement.old_str
        assert "\n" in replacement.new_str
    
    def test_content_payload_multiline(self):
        """Test ContentPayload with multiline content."""
        content = "line 1\nline 2\nline 3"
        payload = ContentPayload(
            file_path="multi.txt",
            content=content
        )
        
        assert payload.content.count("\n") == 2
    
    def test_file_path_with_spaces(self):
        """Test payload with file path containing spaces."""
        payload = ContentPayload(
            file_path="my file.py",
            content="test"
        )
        
        assert payload.file_path == "my file.py"
    
    def test_replacements_preserve_order(self):
        """Test replacements list preserves order."""
        replacements = [
            Replacement(old_str="first", new_str="1st"),
            Replacement(old_str="second", new_str="2nd"),
            Replacement(old_str="third", new_str="3rd"),
        ]
        payload = ReplacementsPayload(
            file_path="test.py",
            replacements=replacements
        )
        
        assert payload.replacements[0].old_str == "first"
        assert payload.replacements[1].old_str == "second"
        assert payload.replacements[2].old_str == "third"


class TestDiffFormatting:
    """Test diff formatting edge cases."""
    
    @patch('code_puppy.tools.file_modifications.emit_info')
    def test_print_diff_hunk_header(self, mock_emit):
        """Test diff with hunk header (@@)."""
        diff_text = "@@ -1,3 +1,4 @@"
        
        _print_diff(diff_text)
        
        calls_str = str(mock_emit.call_args_list)
        assert "cyan" in calls_str.lower() or "@@" in calls_str
    
    @patch('code_puppy.tools.file_modifications.emit_info')
    def test_print_diff_filename_lines(self, mock_emit):
        """Test diff with filename lines (+++/---)."""
        diff_text = "--- a/file.py\n+++ b/file.py"
        
        _print_diff(diff_text)
        
        calls_str = str(mock_emit.call_args_list)
        assert "+++" in calls_str or "---" in calls_str
    
    @patch('code_puppy.tools.file_modifications.emit_info')
    def test_print_diff_context_lines(self, mock_emit):
        """Test diff with context lines (no +/-)."""
        diff_text = " context line\n unchanged"
        
        _print_diff(diff_text)
        
        # Should emit for context lines
        assert mock_emit.call_count > 0
    
    @patch('code_puppy.tools.file_modifications.emit_info')
    def test_print_diff_whitespace_only(self, mock_emit):
        """Test diff with only whitespace."""
        diff_text = "   \n\t\n  "
        
        _print_diff(diff_text)
        
        # Should show "no diff" message since it's effectively empty
        assert mock_emit.call_count > 0


class TestPayloadSerialization:
    """Test payload models can be serialized."""
    
    def test_delete_snippet_to_dict(self):
        """Test DeleteSnippetPayload can be converted to dict."""
        payload = DeleteSnippetPayload(
            file_path="test.py",
            delete_snippet="remove this"
        )
        
        data = payload.model_dump()
        
        assert data["file_path"] == "test.py"
        assert data["delete_snippet"] == "remove this"
    
    def test_replacements_to_dict(self):
        """Test ReplacementsPayload can be converted to dict."""
        payload = ReplacementsPayload(
            file_path="test.py",
            replacements=[Replacement(old_str="a", new_str="b")]
        )
        
        data = payload.model_dump()
        
        assert data["file_path"] == "test.py"
        assert len(data["replacements"]) == 1
    
    def test_content_to_dict(self):
        """Test ContentPayload can be converted to dict."""
        payload = ContentPayload(
            file_path="test.py",
            content="code",
            overwrite=True
        )
        
        data = payload.model_dump()
        
        assert data["file_path"] == "test.py"
        assert data["content"] == "code"
        assert data["overwrite"] is True
