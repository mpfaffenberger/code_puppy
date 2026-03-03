"""Tests for command_line/utils.py - 100% coverage."""

import os
import tempfile
from unittest.mock import patch

import pytest

from code_puppy.command_line.utils import (
    _reset_windows_console,
    list_directory,
    make_directory_table,
    safe_input,
)


class TestListDirectory:
    def test_default_cwd(self):
        dirs, files = list_directory()
        # Should return something from cwd
        assert isinstance(dirs, list)
        assert isinstance(files, list)

    def test_specific_path(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "subdir"))
            with open(os.path.join(td, "file.txt"), "w") as f:
                f.write("x")
            dirs, files = list_directory(td)
            assert "subdir" in dirs
            assert "file.txt" in files

    def test_error(self):
        with pytest.raises(RuntimeError, match="Error listing directory"):
            list_directory("/nonexistent_path_xyz_abc")


class TestMakeDirectoryTable:
    def test_default(self):
        table = make_directory_table()
        assert table is not None

    def test_specific_path(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "adir"))
            with open(os.path.join(td, "afile"), "w") as f:
                f.write("")
            table = make_directory_table(td)
            assert table is not None


class TestResetWindowsConsole:
    @patch("sys.platform", "linux")
    def test_non_windows(self):
        _reset_windows_console()  # Should return early

    @patch("sys.platform", "win32")
    def test_windows(self):
        # Should not crash even though ctypes.windll won't exist on non-windows
        _reset_windows_console()


class TestSafeInput:
    @patch("code_puppy.command_line.utils._reset_windows_console")
    @patch("builtins.input", return_value="  hello  ")
    def test_strips_input(self, mock_input, mock_reset):
        result = safe_input("prompt> ")
        assert result == "hello"
        mock_reset.assert_called_once()

    @patch("code_puppy.command_line.utils._reset_windows_console")
    @patch("builtins.input", return_value="")
    def test_empty_input(self, mock_input, mock_reset):
        result = safe_input()
        assert result == ""
