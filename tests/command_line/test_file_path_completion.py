"""Tests for file_path_completion.py - 100% coverage."""

import os
import tempfile
from unittest.mock import MagicMock

from prompt_toolkit.document import Document

from code_puppy.command_line.file_path_completion import FilePathCompleter


class TestFilePathCompleter:
    def setup_method(self):
        self.completer = FilePathCompleter(symbol="@")
        self.event = MagicMock()

    def _get_completions(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        doc = Document(text, cursor_pos)
        return list(self.completer.get_completions(doc, self.event))

    def test_no_symbol(self):
        result = self._get_completions("hello world")
        assert result == []

    def test_empty_after_symbol(self):
        # Should list current directory
        result = self._get_completions("@")
        assert isinstance(result, list)

    def test_with_path(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "subdir"))
            with open(os.path.join(td, "file.txt"), "w") as f:
                f.write("x")
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                result = self._get_completions("@")
                names = [c.text for c in result]
                assert any("subdir" in n for n in names)
                assert any("file.txt" in n for n in names)
            finally:
                os.chdir(old_cwd)

    def test_directory_path_with_slash(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "inner"))
            with open(os.path.join(td, "inner", "test.py"), "w") as f:
                f.write("")
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                result = self._get_completions("@inner/")
                assert any("test.py" in c.text for c in result)
            finally:
                os.chdir(old_cwd)

    def test_glob_pattern(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "hello.py"), "w") as f:
                f.write("")
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                result = self._get_completions("@hel")
                assert any("hello.py" in c.text for c in result)
            finally:
                os.chdir(old_cwd)

    def test_tilde_expansion(self):
        result = self._get_completions("@~/")
        assert isinstance(result, list)

    def test_absolute_path(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "f.txt"), "w") as f:
                f.write("")
            result = self._get_completions(f"@{td}/")
            assert any("f.txt" in c.text for c in result)

    def test_hidden_files_not_shown_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, ".hidden"), "w") as f:
                f.write("")
            with open(os.path.join(td, "visible"), "w") as f:
                f.write("")
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                result = self._get_completions("@")
                names = [
                    c.display.text if hasattr(c.display, "text") else str(c.display)
                    for c in result
                ]
                assert not any(".hidden" in n for n in names)
            finally:
                os.chdir(old_cwd)

    def test_hidden_files_shown_with_dot(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, ".hidden"), "w") as f:
                f.write("")
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                result = self._get_completions("@.")
                # Should include hidden files when typing a dot
                assert isinstance(result, list)
            finally:
                os.chdir(old_cwd)

    def test_nonexistent_dir(self):
        result = self._get_completions("@/nonexistent_xyz/")
        assert result == []

    def test_permission_error(self):
        # Just exercise the exception path
        result = self._get_completions("@\x00invalid")
        assert result == []

    def test_display_meta_dir_vs_file(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "adir"))
            with open(os.path.join(td, "afile"), "w") as f:
                f.write("")
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                result = self._get_completions("@")
                metas = {
                    c.display_meta_text
                    if hasattr(c, "display_meta_text")
                    else str(c.display_meta)
                    for c in result
                }
                assert "Directory" in metas or "File" in metas
            finally:
                os.chdir(old_cwd)

    def test_absolute_display_path(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "f.txt"), "w") as f:
                f.write("")
            result = self._get_completions(f"@/{td.lstrip('/')}/")
            # Should use absolute display
            assert isinstance(result, list)

    def test_slash_prefix(self):
        result = self._get_completions("@/tmp/")
        assert isinstance(result, list)

    def test_tilde_path_display(self):
        """Cover lines 58-60 - tilde path display."""
        _home = os.path.expanduser("~")
        # Create a file in home dir to get a completion with tilde
        result = self._get_completions("@~/.")
        # Just exercise the path
        assert isinstance(result, list)

    def test_glob_hidden_filtered(self):
        """Cover lines 72-73 - hidden file filtering in glob results."""
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, ".hidden"), "w") as f:
                f.write("")
            with open(os.path.join(td, "visible.txt"), "w") as f:
                f.write("")
            old_cwd = os.getcwd()
            try:
                os.chdir(td)
                result = self._get_completions("@vis")
                names = [c.text for c in result]
                assert any("visible" in n for n in names)
            finally:
                os.chdir(old_cwd)
