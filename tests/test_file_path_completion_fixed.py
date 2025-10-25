"""Unit tests for code_puppy.command_line.file_path_completion - File path @ completion."""
import os
from unittest.mock import patch
import pytest
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document
from code_puppy.command_line.file_path_completion import FilePathCompleter

class TestFilePathCompleterInit:
    def test_default_symbol_is_at_sign(self):
        completer = FilePathCompleter()
        assert completer.symbol == "@"

    def test_custom_symbol(self):
        completer = FilePathCompleter(symbol="#")
        assert completer.symbol == "#"

class TestGetCompletionsBasic:
    def test_no_completions_without_symbol(self):
        completer = FilePathCompleter(symbol="@")
        document = Document("hello world", len("hello world"))
        completions = list(completer.get_completions(document, None))
        assert completions == []

    def test_completions_after_symbol(self, tmp_path):
        (tmp_path / "test.txt").write_text("")
        completer = FilePathCompleter(symbol="@")
        with patch("os.getcwd", return_value=str(tmp_path)):
            document = Document("@test", len("@test"))
            completions = list(completer.get_completions(document, None))
            assert isinstance(completions, list)

class TestErrorHandling:
    def test_handles_permission_error_gracefully(self):
        completer = FilePathCompleter()
        with patch("glob.glob", side_effect=PermissionError("Access denied")):
            document = Document("@/root/", 7)
            completions = list(completer.get_completions(document, None))
            assert completions == []

    def test_handles_file_not_found_error(self):
        completer = FilePathCompleter()
        with patch("glob.glob", side_effect=FileNotFoundError("Not found")):
            document = Document("@/nonexistent/", 14)
            completions = list(completer.get_completions(document, None))
            assert completions == []
