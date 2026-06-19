"""Regression test for ripgrep fallback in _list_files.

When ripgrep is not installed, _list_files should fall back to
non-recursive os.listdir instead of returning an error.
"""

import os
import tempfile
from unittest.mock import patch

from code_puppy.tools.file_operations import _list_files


class TestListFilesRipgrepFallback:
    """_list_files should gracefully handle missing ripgrep."""

    def test_falls_back_when_ripgrep_not_found(self):
        """
        When ripgrep is not installed, _list_files should return
        a non-recursive listing instead of an error.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.py")
            with open(test_file, "w") as f:
                f.write("print('hello')")

            with patch("shutil.which", return_value=None):
                result = _list_files(None, tmpdir, recursive=True)

            # Should not return a hard error
            assert result.content is not None
            assert (
                "not found" not in (result.content or "").lower()
                or "falling back" in (result.content or "").lower()
            )
            # Should still return file listing
            assert "test.py" in result.content

    def test_returns_files_without_ripgrep(self):
        """
        Files in the directory should be listed even without ripgrep.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "myfile.py")
            with open(test_file, "w") as f:
                f.write("x = 1")

            with patch("shutil.which", return_value=None):
                result = _list_files(None, tmpdir, recursive=True)

            assert "myfile.py" in result.content
