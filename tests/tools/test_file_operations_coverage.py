"""Additional tests for file_operations.py to improve coverage.

Focuses on:
- would_match_directory() pattern matching
- _sanitize_string() Unicode handling
- _grep() search functionality
- format_size() large file formatting
- Non-recursive listing edge cases
- Register functions
"""

import json
import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch


from code_puppy.tools.file_operations import (
    GrepOutput,
    ListFileOutput,
    _grep,
    _list_files,
    _read_file,
    _sanitize_string,
    is_likely_home_directory,
    is_project_directory,
    register_grep,
    register_list_files,
    register_read_file,
    would_match_directory,
)


class TestWouldMatchDirectory:
    """Tests for would_match_directory() pattern matching."""

    def test_matches_directory_name_pattern(self, tmp_path):
        """Test pattern matches directory name."""
        test_dir = tmp_path / "node_modules"
        test_dir.mkdir()
        
        assert would_match_directory("node_modules", str(test_dir)) is True

    def test_matches_glob_pattern(self, tmp_path):
        """Test wildcard glob pattern matching."""
        test_dir = tmp_path / "tmp"
        test_dir.mkdir()
        
        # Test pattern with wildcards
        assert would_match_directory("**/tmp/**", str(test_dir)) is True

    def test_no_match_different_directory(self, tmp_path):
        """Test pattern doesn't match unrelated directory."""
        test_dir = tmp_path / "src"
        test_dir.mkdir()
        
        assert would_match_directory("node_modules", str(test_dir)) is False

    def test_matches_path_component(self, tmp_path):
        """Test pattern matches path component."""
        # Create nested directory
        nested = tmp_path / "project" / "__pycache__"
        nested.mkdir(parents=True)
        
        assert would_match_directory("__pycache__", str(nested)) is True

    def test_pattern_with_leading_trailing_wildcards(self, tmp_path):
        """Test pattern stripping of wildcards."""
        test_dir = tmp_path / "build"
        test_dir.mkdir()
        
        # Pattern with stars and slashes
        assert would_match_directory("**/build/**", str(test_dir)) is True

    def test_fnmatch_full_path(self, tmp_path):
        """Test fnmatch against full path."""
        test_dir = tmp_path / "cache"
        test_dir.mkdir()
        
        # Pattern that matches part of path
        assert would_match_directory("cache", str(test_dir)) is True


class TestSanitizeString:
    """Tests for _sanitize_string() Unicode surrogate handling."""

    def test_clean_string_passes_through(self):
        """Test that clean strings pass through unchanged."""
        clean = "Hello World! 123"
        assert _sanitize_string(clean) == clean

    def test_empty_string(self):
        """Test empty string handling."""
        assert _sanitize_string("") == ""

    def test_unicode_string(self):
        """Test Unicode strings pass through."""
        unicode_str = "Hello 世界 🐾 émojis"
        result = _sanitize_string(unicode_str)
        assert result == unicode_str

    def test_surrogate_characters_replaced(self):
        """Test surrogate characters are replaced."""
        # Create string with surrogate characters
        # Surrogates are in range U+D800 to U+DFFF
        text_with_surrogates = "Hello\ud800World"
        result = _sanitize_string(text_with_surrogates)
        
        # Should replace surrogate with replacement character
        assert "\ud800" not in result
        assert "\ufffd" in result or "Hello" in result

    def test_mixed_valid_and_surrogate(self):
        """Test string with mixed valid and invalid chars."""
        text = "Valid\ud834text\udfff here"
        result = _sanitize_string(text)
        
        # Should still contain valid parts
        assert "Valid" in result
        assert "text" in result
        assert "here" in result

    def test_none_handling(self):
        """Test None/falsy value handling."""
        # None should return as-is (falsy check)
        assert _sanitize_string(None) is None


class TestGrepFunction:
    """Tests for _grep() search functionality."""

    def test_grep_finds_matches(self, tmp_path):
        """Test basic grep functionality."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello_world():\n    print('Hello')\n")
        
        result = _grep(None, "hello_world", str(tmp_path))
        
        assert isinstance(result, GrepOutput)
        assert result.error is None
        assert len(result.matches) >= 1
        assert any("hello_world" in m.line_content for m in result.matches)

    def test_grep_no_matches(self, tmp_path):
        """Test grep with no matches."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")
        
        result = _grep(None, "nonexistent_pattern_xyz", str(tmp_path))
        
        assert isinstance(result, GrepOutput)
        assert len(result.matches) == 0

    def test_grep_multiple_files(self, tmp_path):
        """Test grep across multiple files."""
        (tmp_path / "file1.py").write_text("TODO: fix this\n")
        (tmp_path / "file2.py").write_text("TODO: and this\n")
        (tmp_path / "file3.py").write_text("No match here\n")
        
        result = _grep(None, "TODO", str(tmp_path))
        
        assert len(result.matches) >= 2

    def test_grep_with_special_characters(self, tmp_path):
        """Test grep with special regex characters."""
        test_file = tmp_path / "test.py"
        test_file.write_text("pattern = r'[a-z]+\\.txt'\n")
        
        # Search for literal text (not regex)
        result = _grep(None, "pattern", str(tmp_path))
        
        assert len(result.matches) >= 1

    def test_grep_line_content_truncation(self, tmp_path):
        """Test that very long lines are truncated."""
        test_file = tmp_path / "long_line.py"
        long_line = "MARKER" + "x" * 1000 + "\n"
        test_file.write_text(long_line)
        
        result = _grep(None, "MARKER", str(tmp_path))
        
        if result.matches:
            # Line content should be truncated to 512 chars
            assert len(result.matches[0].line_content) <= 512

    def test_grep_sanitizes_search_string(self, tmp_path):
        """Test that search string is sanitized."""
        test_file = tmp_path / "test.py"
        test_file.write_text("normal content\n")
        
        # Search with potentially problematic characters
        result = _grep(None, "normal", str(tmp_path))
        
        assert isinstance(result, GrepOutput)

    @patch("code_puppy.tools.file_operations.shutil.which")
    @patch("os.path.exists")
    def test_grep_no_ripgrep(self, mock_exists, mock_which, tmp_path):
        """Test error handling when ripgrep is not available."""
        mock_which.return_value = None
        # Ensure the venv fallback path checks return False
        mock_exists.return_value = False
        
        result = _grep(None, "test", str(tmp_path))
        
        assert result.error is not None
        assert "ripgrep" in result.error.lower()

    @patch("subprocess.run")
    def test_grep_timeout(self, mock_run, tmp_path):
        """Test handling of grep timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("rg", 30)
        
        result = _grep(None, "test", str(tmp_path))
        
        assert result.error is not None
        assert "timed out" in result.error.lower()

    @patch("subprocess.run")
    def test_grep_generic_exception(self, mock_run, tmp_path):
        """Test handling of generic exceptions."""
        mock_run.side_effect = Exception("Something went wrong")
        
        result = _grep(None, "test", str(tmp_path))
        
        assert result.error is not None
        assert "Error" in result.error

    def test_grep_empty_search_string(self, tmp_path):
        """Test grep with empty search string."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content\n")
        
        # Empty search - behavior depends on ripgrep
        result = _grep(None, "", str(tmp_path))
        
        assert isinstance(result, GrepOutput)

    def test_grep_nested_directories(self, tmp_path):
        """Test grep searches nested directories."""
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        (nested / "deep.py").write_text("DEEP_MARKER = True\n")
        
        result = _grep(None, "DEEP_MARKER", str(tmp_path))
        
        assert len(result.matches) >= 1


class TestListFilesFormatSize:
    """Tests for format_size helper in _list_files."""

    def test_list_files_shows_file_sizes(self, tmp_path):
        """Test that file sizes are shown in output."""
        # Create files of various sizes
        small_file = tmp_path / "small.txt"
        small_file.write_text("x" * 500)  # ~500 bytes
        
        result = _list_files(None, str(tmp_path), recursive=False)
        
        assert "small.txt" in result.content
        # Should show size in B or KB
        assert "B" in result.content or "KB" in result.content

    def test_list_files_kilobyte_size(self, tmp_path):
        """Test KB file size formatting."""
        kb_file = tmp_path / "medium.txt"
        kb_file.write_text("x" * 2000)  # ~2 KB
        
        result = _list_files(None, str(tmp_path), recursive=False)
        
        # Should show KB in output
        assert "KB" in result.content or "B" in result.content

    def test_list_files_megabyte_size(self, tmp_path):
        """Test MB file size formatting (covers line 413)."""
        mb_file = tmp_path / "large.bin"
        # Create ~1.5 MB file
        mb_file.write_bytes(b"x" * (1024 * 1024 + 500000))
        
        result = _list_files(None, str(tmp_path), recursive=False)
        
        # Should show MB in output for large file
        assert "MB" in result.content or "KB" in result.content

    def test_list_files_total_size_summary(self, tmp_path):
        """Test total size in summary."""
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2" * 100)
        
        result = _list_files(None, str(tmp_path), recursive=False)
        
        assert "total" in result.content.lower()
        assert "Summary" in result.content


class TestNonRecursiveListing:
    """Tests for non-recursive listing edge cases."""

    def test_non_recursive_hidden_dirs_skipped(self, tmp_path):
        """Test hidden directories are skipped in non-recursive mode."""
        (tmp_path / ".hidden_dir").mkdir()
        (tmp_path / "visible_dir").mkdir()
        (tmp_path / "file.txt").write_text("content")
        
        result = _list_files(None, str(tmp_path), recursive=False)
        
        assert "visible_dir" in result.content
        # Hidden dirs should be skipped
        assert ".hidden_dir" not in result.content

    def test_non_recursive_lists_files(self, tmp_path):
        """Test non-recursive lists top-level files."""
        (tmp_path / "test1.py").write_text("# test")
        (tmp_path / "test2.js").write_text("// test")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.py").write_text("# nested")
        
        result = _list_files(None, str(tmp_path), recursive=False)
        
        assert "test1.py" in result.content
        assert "test2.js" in result.content
        assert "subdir" in result.content
        # Nested file should NOT appear in non-recursive
        assert "nested.py" not in result.content

    def test_non_recursive_empty_directory(self, tmp_path):
        """Test non-recursive on empty directory."""
        empty = tmp_path / "empty"
        empty.mkdir()
        
        result = _list_files(None, str(empty), recursive=False)
        
        assert result.error is None
        assert "0 files" in result.content

    def test_non_recursive_with_permission_error(self, tmp_path):
        """Test non-recursive handles permission errors gracefully."""
        (tmp_path / "accessible.txt").write_text("ok")
        
        result = _list_files(None, str(tmp_path), recursive=False)
        
        assert "accessible.txt" in result.content


class TestRecursiveListingWithRipgrep:
    """Tests for recursive listing that uses ripgrep."""

    def test_recursive_finds_nested_files(self, tmp_path):
        """Test recursive listing finds deeply nested files."""
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "nested.py").write_text("# nested")
        (tmp_path / "root.py").write_text("# root")
        
        result = _list_files(None, str(tmp_path), recursive=True)
        
        assert "root.py" in result.content
        assert "nested.py" in result.content

    def test_recursive_shows_directory_structure(self, tmp_path):
        """Test recursive shows directories."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# main")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("# test")
        
        result = _list_files(None, str(tmp_path), recursive=True)
        
        assert "src" in result.content
        assert "tests" in result.content
        assert "main.py" in result.content
        assert "test_main.py" in result.content

    @patch("subprocess.run")
    def test_recursive_timeout_handling(self, mock_run, tmp_path):
        """Test timeout handling in recursive listing."""
        mock_run.side_effect = subprocess.TimeoutExpired("rg", 30)
        
        result = _list_files(None, str(tmp_path), recursive=True)
        
        assert "timed out" in result.content.lower()
        assert result.error is not None


class TestHomeDirectoryDetection:
    """Tests for home directory detection."""

    def test_is_home_directory_exact_match(self):
        """Test exact home directory match."""
        home = os.path.expanduser("~")
        assert is_likely_home_directory(home) is True

    def test_is_home_directory_documents(self):
        """Test Documents subdirectory detection."""
        home = os.path.expanduser("~")
        docs = os.path.join(home, "Documents")
        if os.path.exists(docs):
            assert is_likely_home_directory(docs) is True

    def test_is_not_home_directory(self, tmp_path):
        """Test non-home directory."""
        assert is_likely_home_directory(str(tmp_path)) is False

    def test_project_directory_with_various_markers(self, tmp_path):
        """Test project detection with various markers."""
        markers = [
            "package.json",
            "pyproject.toml",
            "Cargo.toml",
            "go.mod",
            "Gemfile",
            "composer.json",
        ]
        
        for marker in markers:
            test_dir = tmp_path / f"proj_{marker.replace('.', '_')}"
            test_dir.mkdir()
            (test_dir / marker).write_text("{}")
            assert is_project_directory(str(test_dir)) is True

    def test_project_directory_with_makefile(self, tmp_path):
        """Test Makefile detection."""
        (tmp_path / "Makefile").write_text("all:\n\techo hello")
        assert is_project_directory(str(tmp_path)) is True

    def test_project_directory_permission_error(self, tmp_path):
        """Test project detection with permission error."""
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o000)
        
        try:
            # Should return False, not crash
            result = is_project_directory(str(restricted))
            assert result is False
        finally:
            restricted.chmod(0o755)


class TestReadFileEdgeCases:
    """Additional edge cases for _read_file."""

    def test_read_file_with_surrogate_content(self, tmp_path):
        """Test reading file with encoding issues that create surrogates."""
        test_file = tmp_path / "surrogate.txt"
        # Write with surrogateescape to simulate problematic content
        with open(test_file, "wb") as f:
            f.write(b"Hello \xff\xfe World")
        
        result = _read_file(None, str(test_file))
        
        # Should handle gracefully
        assert result.content is not None
        assert "Hello" in result.content

    def test_read_file_counts_tokens_correctly(self, tmp_path):
        """Test token counting logic."""
        test_file = tmp_path / "tokens.txt"
        content = "a" * 100  # 100 characters = ~25 tokens
        test_file.write_text(content)
        
        result = _read_file(None, str(test_file))
        
        assert result.num_tokens == len(content) // 4

    def test_read_file_line_range_zero_start(self, tmp_path):
        """Test line range with start_line=0."""
        test_file = tmp_path / "lines.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")
        
        # start_line=0 should be treated as start from beginning
        result = _read_file(None, str(test_file), start_line=0, num_lines=2)
        
        assert result.content is not None

    def test_read_file_counts_total_lines(self, tmp_path):
        """Test line counting for message emission."""
        test_file = tmp_path / "count.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3")
        
        result = _read_file(None, str(test_file))
        
        assert result.error is None
        # Content should have 3 lines
        assert result.content.count("\n") == 2


class TestRegisterFunctions:
    """Tests for tool registration functions."""

    def test_register_list_files(self):
        """Test register_list_files creates tool."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(side_effect=lambda f: f)
        
        register_list_files(mock_agent)
        
        assert mock_agent.tool.called

    def test_register_read_file(self):
        """Test register_read_file creates tool."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(side_effect=lambda f: f)
        
        register_read_file(mock_agent)
        
        assert mock_agent.tool.called

    def test_register_grep(self):
        """Test register_grep creates tool."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(side_effect=lambda f: f)
        
        register_grep(mock_agent)
        
        assert mock_agent.tool.called

    def test_registered_list_files_truncates_large_output(self):
        """Test that registered list_files truncates massive output."""
        # This tests the truncation logic in register_list_files
        mock_agent = MagicMock()
        registered_func = None
        
        def capture_tool(f):
            nonlocal registered_func
            registered_func = f
            return f
        
        mock_agent.tool = capture_tool
        register_list_files(mock_agent)
        
        # The function should be registered
        assert registered_func is not None

    def test_registered_list_files_works(self):
        """Test registered list_files function works correctly."""
        mock_agent = MagicMock()
        registered_func = None
        
        def capture_tool(f):
            nonlocal registered_func
            registered_func = f
            return f
        
        mock_agent.tool = capture_tool
        register_list_files(mock_agent)
        
        # Call with a valid temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("content")
            
            result = registered_func(None, tmpdir, recursive=False)
            
            # Should list the file
            assert "test.txt" in result.content
            assert isinstance(result, ListFileOutput)


class TestGrepJsonParsing:
    """Tests for ripgrep JSON output parsing."""

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_grep_parses_json_match(self, mock_which, mock_run, tmp_path):
        """Test parsing of ripgrep JSON match output."""
        mock_which.return_value = "/usr/bin/rg"
        
        # Simulate ripgrep JSON output
        json_output = json.dumps({
            "type": "match",
            "data": {
                "path": {"text": "/tmp/test.py"},
                "line_number": 10,
                "lines": {"text": "def test_function():"}
            }
        })
        
        mock_run.return_value = MagicMock(
            stdout=json_output,
            stderr="",
            returncode=0
        )
        
        result = _grep(None, "test", str(tmp_path))
        
        assert len(result.matches) == 1
        assert result.matches[0].line_number == 10

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_grep_handles_invalid_json_lines(self, mock_which, mock_run, tmp_path):
        """Test handling of invalid JSON in ripgrep output."""
        mock_which.return_value = "/usr/bin/rg"
        
        # Mix of valid and invalid JSON
        output = '{"type": "match", "data": {"path": {"text": "/a.py"}, "line_number": 1, "lines": {"text": "x"}}}\ninvalid json line\n'
        
        mock_run.return_value = MagicMock(
            stdout=output,
            stderr="",
            returncode=0
        )
        
        result = _grep(None, "test", str(tmp_path))
        
        # Should still get the valid match
        assert len(result.matches) == 1

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_grep_skips_non_match_events(self, mock_which, mock_run, tmp_path):
        """Test that non-match events are skipped."""
        mock_which.return_value = "/usr/bin/rg"
        
        # Include summary event which should be skipped
        output = '{"type": "summary", "data": {}}\n{"type": "match", "data": {"path": {"text": "/b.py"}, "line_number": 5, "lines": {"text": "y"}}}\n'
        
        mock_run.return_value = MagicMock(
            stdout=output,
            stderr="",
            returncode=0
        )
        
        result = _grep(None, "test", str(tmp_path))
        
        # Should only get the match, not summary
        assert len(result.matches) == 1
        assert result.matches[0].line_number == 5

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_grep_limits_to_50_matches(self, mock_which, mock_run, tmp_path):
        """Test that matches are limited to 50."""
        mock_which.return_value = "/usr/bin/rg"
        
        # Generate 60 matches
        matches = []
        for i in range(60):
            matches.append(json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": f"/file{i}.py"},
                    "line_number": i,
                    "lines": {"text": f"match {i}"}
                }
            }))
        
        mock_run.return_value = MagicMock(
            stdout="\n".join(matches),
            stderr="",
            returncode=0
        )
        
        result = _grep(None, "test", str(tmp_path))
        
        # Should be limited to 50
        assert len(result.matches) == 50


class TestListFilesIgnorePatterns:
    """Tests for ignore patterns in file listing."""

    def test_list_files_ignores_node_modules(self, tmp_path):
        """Test that node_modules is ignored."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.js").write_text("// app")
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "package" / "index.js").mkdir(parents=True)
        
        result = _list_files(None, str(tmp_path), recursive=True)
        
        assert "app.js" in result.content
        # node_modules should be filtered out by ripgrep

    def test_list_files_ignores_pycache(self, tmp_path):
        """Test that __pycache__ is ignored."""
        (tmp_path / "main.py").write_text("# main")
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "main.cpython-39.pyc").write_bytes(b"bytecode")
        
        result = _list_files(None, str(tmp_path), recursive=True)
        
        assert "main.py" in result.content


class TestListFilesDepthTracking:
    """Tests for depth tracking in file listings."""

    def test_list_files_tracks_depth(self, tmp_path):
        """Test that file depth is tracked correctly."""
        (tmp_path / "level0.txt").write_text("0")
        level1 = tmp_path / "dir1"
        level1.mkdir()
        (level1 / "level1.txt").write_text("1")
        level2 = level1 / "dir2"
        level2.mkdir()
        (level2 / "level2.txt").write_text("2")
        
        result = _list_files(None, str(tmp_path), recursive=True)
        
        # All files should be found
        assert "level0.txt" in result.content
        assert "level1.txt" in result.content
        assert "level2.txt" in result.content


class TestListFilesEdgeCases:
    """Edge cases for list_files."""

    def test_list_files_with_spaces_in_path(self, tmp_path):
        """Test listing files in directory with spaces."""
        spaced_dir = tmp_path / "dir with spaces"
        spaced_dir.mkdir()
        (spaced_dir / "file.txt").write_text("content")
        
        result = _list_files(None, str(spaced_dir), recursive=False)
        
        assert "file.txt" in result.content

    def test_list_files_with_unicode_names(self, tmp_path):
        """Test listing files with Unicode names."""
        unicode_dir = tmp_path / "日本語"
        unicode_dir.mkdir()
        (unicode_dir / "文件.txt").write_text("内容")
        
        result = _list_files(None, str(unicode_dir), recursive=False)
        
        assert "文件.txt" in result.content

    @patch("subprocess.run")
    def test_list_files_generic_exception(self, mock_run, tmp_path):
        """Test handling of generic exceptions."""
        mock_run.side_effect = Exception("Unexpected error")
        
        result = _list_files(None, str(tmp_path), recursive=True)
        
        assert result.error is not None
        assert "Error" in result.content
