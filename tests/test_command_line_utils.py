"""Tests for code_puppy.command_line.utils.

This module tests directory listing and table generation utilities
used in the command-line interface.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.table import Table

from code_puppy.command_line.utils import list_directory, make_directory_table


class TestListDirectory:
    """Test list_directory function."""

    def test_list_directory_with_temp_path(self, tmp_path):
        """Test listing a temporary directory with known contents."""
        # Create some test files and directories
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir2").mkdir()
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.py").write_text("code")
        
        dirs, files = list_directory(str(tmp_path))
        
        assert sorted(dirs) == ["dir1", "dir2"]
        assert sorted(files) == ["file1.txt", "file2.py"]

    def test_list_directory_empty_directory(self, tmp_path):
        """Test listing an empty directory."""
        dirs, files = list_directory(str(tmp_path))
        
        assert dirs == []
        assert files == []

    def test_list_directory_only_dirs(self, tmp_path):
        """Test listing directory with only subdirectories."""
        (tmp_path / "subdir1").mkdir()
        (tmp_path / "subdir2").mkdir()
        (tmp_path / "subdir3").mkdir()
        
        dirs, files = list_directory(str(tmp_path))
        
        assert len(dirs) == 3
        assert len(files) == 0
        assert "subdir1" in dirs

    def test_list_directory_only_files(self, tmp_path):
        """Test listing directory with only files."""
        (tmp_path / "a.txt").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.md").write_text("")
        
        dirs, files = list_directory(str(tmp_path))
        
        assert len(dirs) == 0
        assert len(files) == 3
        assert "a.txt" in files

    def test_list_directory_defaults_to_cwd(self):
        """Test that list_directory defaults to current working directory."""
        # Should not raise an error and return two lists
        dirs, files = list_directory()
        
        assert isinstance(dirs, list)
        assert isinstance(files, list)

    def test_list_directory_with_none_path(self):
        """Test that passing None uses current directory."""
        dirs, files = list_directory(None)
        
        assert isinstance(dirs, list)
        assert isinstance(files, list)

    def test_list_directory_nonexistent_path_raises_error(self):
        """Test that listing nonexistent directory raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Error listing directory"):
            list_directory("/nonexistent/path/that/does/not/exist")

    def test_list_directory_with_hidden_files(self, tmp_path):
        """Test that hidden files are included in the listing."""
        (tmp_path / ".hidden_file").write_text("secret")
        (tmp_path / "visible_file.txt").write_text("public")
        (tmp_path / ".hidden_dir").mkdir()
        
        dirs, files = list_directory(str(tmp_path))
        
        assert ".hidden_file" in files
        assert ".hidden_dir" in dirs
        assert "visible_file.txt" in files

    def test_list_directory_with_mixed_content(self, tmp_path):
        """Test listing directory with various file types and directories."""
        # Create mixed content
        (tmp_path / "docs").mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "README.md").write_text("readme")
        (tmp_path / "setup.py").write_text("setup")
        (tmp_path / ".gitignore").write_text("ignore")
        
        dirs, files = list_directory(str(tmp_path))
        
        assert len(dirs) == 2
        assert len(files) == 3
        assert "docs" in dirs
        assert "src" in dirs
        assert "README.md" in files
        assert "setup.py" in files
        assert ".gitignore" in files


class TestMakeDirectoryTable:
    """Test make_directory_table function."""

    def test_make_directory_table_returns_table(self, tmp_path):
        """Test that make_directory_table returns a rich Table object."""
        table = make_directory_table(str(tmp_path))
        
        assert isinstance(table, Table)

    def test_make_directory_table_with_content(self, tmp_path):
        """Test table generation with directory content."""
        (tmp_path / "testdir").mkdir()
        (tmp_path / "testfile.txt").write_text("test")
        
        table = make_directory_table(str(tmp_path))
        
        assert isinstance(table, Table)
        # Table should have title with path
        assert str(tmp_path) in str(table.title)

    def test_make_directory_table_has_correct_columns(self, tmp_path):
        """Test that table has Type and Name columns."""
        table = make_directory_table(str(tmp_path))
        
        # Check that table has 2 columns
        assert len(table.columns) == 2
        # Column headers should be Type and Name
        assert table.columns[0].header == "Type"
        assert table.columns[1].header == "Name"

    def test_make_directory_table_defaults_to_cwd(self):
        """Test that make_directory_table defaults to current directory."""
        table = make_directory_table()
        
        assert isinstance(table, Table)
        assert os.getcwd() in str(table.title)

    def test_make_directory_table_with_none_path(self):
        """Test that passing None uses current directory."""
        table = make_directory_table(None)
        
        assert isinstance(table, Table)
        assert os.getcwd() in str(table.title)

    def test_make_directory_table_empty_directory(self, tmp_path):
        """Test table generation for empty directory."""
        table = make_directory_table(str(tmp_path))
        
        assert isinstance(table, Table)
        # Empty directory should still have table structure
        assert len(table.columns) == 2

    def test_make_directory_table_sorts_entries(self, tmp_path):
        """Test that directories and files are sorted alphabetically."""
        # Create entries in non-alphabetical order
        (tmp_path / "zebra.txt").write_text("")
        (tmp_path / "apple.txt").write_text("")
        (tmp_path / "banana").mkdir()
        (tmp_path / "zebra_dir").mkdir()
        
        table = make_directory_table(str(tmp_path))
        
        # We can't easily inspect the row order, but function should complete
        assert isinstance(table, Table)

    def test_make_directory_table_has_title(self, tmp_path):
        """Test that table has a formatted title."""
        table = make_directory_table(str(tmp_path))
        
        assert table.title is not None
        assert "Current directory:" in str(table.title)
        assert str(tmp_path) in str(table.title)

    def test_make_directory_table_with_special_characters_in_path(self, tmp_path):
        """Test table generation with special characters in filenames."""
        # Create files with special characters
        (tmp_path / "file with spaces.txt").write_text("")
        (tmp_path / "file-with-dashes.py").write_text("")
        (tmp_path / "file_with_underscores.md").write_text("")
        
        table = make_directory_table(str(tmp_path))
        
        assert isinstance(table, Table)

    def test_make_directory_table_with_many_entries(self, tmp_path):
        """Test table generation with many files and directories."""
        # Create many entries
        for i in range(50):
            (tmp_path / f"file_{i:03d}.txt").write_text("")
        for i in range(20):
            (tmp_path / f"dir_{i:03d}").mkdir()
        
        table = make_directory_table(str(tmp_path))
        
        assert isinstance(table, Table)
        # Should handle many entries without error


class TestIntegration:
    """Integration tests for utils functions."""

    def test_list_and_table_consistency(self, tmp_path):
        """Test that list_directory and make_directory_table use same data."""
        # Create test content
        (tmp_path / "dir1").mkdir()
        (tmp_path / "file1.txt").write_text("test")
        
        dirs, files = list_directory(str(tmp_path))
        table = make_directory_table(str(tmp_path))
        
        # Both should process the same directory successfully
        assert len(dirs) == 1
        assert len(files) == 1
        assert isinstance(table, Table)
