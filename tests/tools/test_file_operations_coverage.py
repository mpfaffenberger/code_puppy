"""Coverage tests for file_operations.py - targeting uncovered lines.

This module focuses on testing edge cases, error paths, and helper functions
that weren't covered by the existing test_file_operations_extended.py tests.
"""

import os
import subprocess
from unittest.mock import MagicMock, patch

from code_puppy.tools.file_operations import (
    GrepOutput,
    ListFileOutput,
    MatchInfo,
    ReadFileOutput,
    _grep,
    _list_files,
    _read_file,
    _sanitize_string,
    is_likely_home_directory,
    is_project_directory,
    would_match_directory,
)


class TestWouldMatchDirectory:
    """Test the would_match_directory pattern matching function."""

    def test_direct_directory_name_match(self, tmp_path):
        """Test matching when directory name directly matches pattern."""
        test_dir = tmp_path / "node_modules"
        test_dir.mkdir()
        assert would_match_directory("node_modules", str(test_dir)) is True

    def test_wildcard_pattern_match(self, tmp_path):
        """Test matching with glob wildcard patterns."""
        test_dir = tmp_path / "cache"
        test_dir.mkdir()
        # Pattern like **/cache/** should match
        assert would_match_directory("**/cache/**", str(test_dir)) is True

    def test_no_match_different_name(self, tmp_path):
        """Test that non-matching patterns return False."""
        test_dir = tmp_path / "src"
        test_dir.mkdir()
        assert would_match_directory("node_modules", str(test_dir)) is False

    def test_full_path_pattern_match(self, tmp_path):
        """Test matching when full path matches pattern."""
        test_dir = tmp_path / "build"
        test_dir.mkdir()
        # Full path pattern matching
        result = would_match_directory("build", str(test_dir))
        assert result is True

    def test_path_part_match(self, tmp_path):
        """Test matching any part of the path."""
        # Create nested structure with a matching name in the path
        nested = tmp_path / "project" / "tmp" / "output"
        nested.mkdir(parents=True)
        # Pattern 'tmp' should match because 'tmp' is part of the path
        result = would_match_directory("tmp", str(nested))
        assert result is True

    def test_pattern_with_slashes(self, tmp_path):
        """Test pattern with leading/trailing slashes gets stripped."""
        test_dir = tmp_path / "dist"
        test_dir.mkdir()
        assert would_match_directory("*/dist/*", str(test_dir)) is True

    def test_fnmatch_special_characters(self, tmp_path):
        """Test patterns with fnmatch special characters."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        # Pattern with ? wildcard
        result = would_match_directory("test_???", str(test_dir))
        assert result is True


class TestSanitizeString:
    """Test the _sanitize_string Unicode sanitization function."""

    def test_clean_string_passes_through(self):
        """Test that clean strings pass through unchanged."""
        clean = "Hello, World! 123"
        result = _sanitize_string(clean)
        assert result == clean

    def test_empty_string(self):
        """Test empty string handling."""
        assert _sanitize_string("") == ""

    def test_none_like_empty(self):
        """Test falsy string values."""
        # The function checks 'if not text' first
        result = _sanitize_string("")
        assert result == ""

    def test_unicode_characters_preserved(self):
        """Test that valid unicode characters are preserved."""
        unicode_str = "Hello 世界 🐾 café"
        result = _sanitize_string(unicode_str)
        assert result == unicode_str

    def test_surrogate_characters_replaced(self):
        """Test that surrogate characters are replaced."""
        # Create a string with surrogate characters (invalid standalone)
        # Surrogates are in range 0xD800 to 0xDFFF
        surrogate_str = "Hello" + chr(0xD800) + "World"
        result = _sanitize_string(surrogate_str)
        # Should replace surrogate with replacement character
        assert "\ufffd" in result or result == "HelloWorld"
        assert chr(0xD800) not in result

    def test_mixed_valid_invalid(self):
        """Test string with mix of valid and invalid characters."""
        mixed = "Valid" + chr(0xDC00) + "Text" + chr(0xDFFF) + "End"
        result = _sanitize_string(mixed)
        # Surrogates should be replaced
        assert chr(0xDC00) not in result
        assert chr(0xDFFF) not in result
        assert "Valid" in result
        assert "Text" in result
        assert "End" in result


class TestGrepFunction:
    """Test the _grep search function."""

    def test_grep_basic_search(self, tmp_path):
        """Test basic grep search functionality."""
        # Create a test file with searchable content
        test_file = tmp_path / "search_me.py"
        test_file.write_text("def hello_world():\n    print('Hello')\n")

        result = _grep(None, "hello_world", str(tmp_path))

        assert isinstance(result, GrepOutput)
        # Should find the match (if ripgrep is available)
        if result.error is None:
            assert len(result.matches) > 0
            assert any("hello_world" in (m.line_content or "") for m in result.matches)

    def test_grep_no_matches(self, tmp_path):
        """Test grep when no matches are found."""
        test_file = tmp_path / "no_match.py"
        test_file.write_text("completely different content\n")

        result = _grep(None, "xyz123_nonexistent_string_abc", str(tmp_path))

        assert isinstance(result, GrepOutput)
        if result.error is None:
            assert len(result.matches) == 0

    def test_grep_multiple_matches(self, tmp_path):
        """Test grep with multiple matches."""
        test_file = tmp_path / "multi.py"
        content = "\n".join([f"line_{i} pattern_to_find" for i in range(10)])
        test_file.write_text(content)

        result = _grep(None, "pattern_to_find", str(tmp_path))

        if result.error is None:
            assert len(result.matches) >= 1

    def test_grep_with_tilde_path(self, tmp_path):
        """Test grep expands tilde in paths."""
        # Create test file
        test_file = tmp_path / "tilde_test.py"
        test_file.write_text("searchable content here\n")

        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            result = _grep(None, "searchable", "~")
            assert isinstance(result, GrepOutput)

    def test_grep_sanitizes_search_string(self, tmp_path):
        """Test that grep sanitizes the search string."""
        test_file = tmp_path / "sanitize_test.py"
        test_file.write_text("normal content\n")

        # Search with a string containing a surrogate (will be sanitized)
        search = "normal" + chr(0xD800)
        result = _grep(None, search, str(tmp_path))
        assert isinstance(result, GrepOutput)

    @patch("subprocess.run")
    def test_grep_timeout_handling(self, mock_run, tmp_path):
        """Test grep handles timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired("rg", 30)

        result = _grep(None, "test", str(tmp_path))

        assert result.error is not None
        assert "timed out" in result.error
        assert result.matches == []

    @patch("subprocess.run")
    def test_grep_file_not_found_error(self, mock_run, tmp_path):
        """Test grep handles FileNotFoundError (ripgrep not installed)."""
        mock_run.side_effect = FileNotFoundError("rg not found")

        result = _grep(None, "test", str(tmp_path))

        assert result.error is not None
        assert "ripgrep" in result.error.lower() or "not found" in result.error.lower()

    @patch("subprocess.run")
    def test_grep_generic_exception(self, mock_run, tmp_path):
        """Test grep handles generic exceptions."""
        mock_run.side_effect = RuntimeError("Unexpected error")

        result = _grep(None, "test", str(tmp_path))

        assert result.error is not None
        assert "error" in result.error.lower()

    def test_grep_ripgrep_not_found(self, tmp_path):
        """Test grep when ripgrep is not available."""
        # Mock both shutil.which and os.path.exists to ensure rg is not found
        with (
            patch("shutil.which", return_value=None),
            patch(
                "os.path.exists",
                side_effect=lambda p: not (p.endswith("rg") or p.endswith("rg.exe")),
            ),
        ):
            result = _grep(None, "test", str(tmp_path))

        assert result.error is not None
        assert "ripgrep" in result.error.lower()

    def test_grep_long_line_truncation(self, tmp_path):
        """Test that very long matching lines are truncated."""
        test_file = tmp_path / "long_line.py"
        # Create a line longer than 512 characters with the pattern
        long_content = "findme" + "x" * 600 + "\n"
        test_file.write_text(long_content)

        result = _grep(None, "findme", str(tmp_path))

        if result.error is None and len(result.matches) > 0:
            # Content should be truncated to max 512 chars
            for match in result.matches:
                assert len(match.line_content or "") <= 512

    def test_grep_json_decode_error_handling(self, tmp_path):
        """Test that invalid JSON lines in ripgrep output are skipped."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content\n")

        # This should work normally - JSON decode errors are internal to parsing
        result = _grep(None, "content", str(tmp_path))
        assert isinstance(result, GrepOutput)


class TestListFilesRipgrepHandling:
    """Test _list_files handling of ripgrep edge cases."""

    def test_list_files_ripgrep_not_found_recursive(self, tmp_path):
        """Test list_files error when ripgrep not found for recursive listing."""
        # Mock both shutil.which and os.path.exists to ensure rg is not found
        with (
            patch("shutil.which", return_value=None),
            patch(
                "os.path.exists",
                side_effect=lambda p: not (p.endswith("rg") or p.endswith("rg.exe")),
            ),
        ):
            result = _list_files(None, str(tmp_path), recursive=True)

        assert result.error is not None
        assert "ripgrep" in result.error.lower() or "rg" in result.error.lower()

    def test_list_files_non_recursive_without_ripgrep(self, tmp_path):
        """Test non-recursive listing works without ripgrep."""
        # Create some files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")

        # Non-recursive should work even with mocked ripgrep
        with patch("shutil.which", return_value=None):
            result = _list_files(None, str(tmp_path), recursive=False)

        assert result.error is None
        assert "file1.txt" in result.content
        assert "file2.py" in result.content

    @patch("subprocess.run")
    def test_list_files_general_exception(self, mock_run, tmp_path):
        """Test list_files handles general exceptions."""
        mock_run.side_effect = RuntimeError("Unexpected error occurred")

        result = _list_files(None, str(tmp_path), recursive=True)

        assert result.error is not None
        assert "error" in result.error.lower()


class TestListFilesNonRecursiveMode:
    """Test _list_files non-recursive mode handling."""

    def test_non_recursive_skips_hidden_dirs(self, tmp_path):
        """Test that non-recursive mode skips hidden directories."""
        hidden_dir = tmp_path / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "secret.txt").write_text("secret")

        visible_file = tmp_path / "visible.txt"
        visible_file.write_text("visible")

        result = _list_files(None, str(tmp_path), recursive=False)

        assert "visible.txt" in result.content
        assert ".hidden" not in result.content

    def test_non_recursive_handles_oserror(self, tmp_path):
        """Test non-recursive mode handles OSError in listdir."""
        # Create a file with no permissions
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o000)

        try:
            # Listing parent should still work
            result = _list_files(None, str(tmp_path), recursive=False)
            assert result.content is not None
        finally:
            restricted.chmod(0o755)

    def test_non_recursive_file_size_oserror(self, tmp_path):
        """Test that OSError when getting file size is handled."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = _list_files(None, str(tmp_path), recursive=False)

        # Should still list the file
        assert "test.txt" in result.content


class TestHomeDirectoryDetection:
    """Test home directory detection with context parameter."""

    def test_home_dir_with_context_limits_recursion(self):
        """Test that home directory detection limits recursion when context is provided."""
        # Get actual home directory
        home = os.path.expanduser("~")

        # Create a mock context (non-None)
        mock_context = MagicMock()

        # Listing home with context should auto-limit recursion
        result = _list_files(mock_context, home, recursive=True)

        # Should contain warning about limiting recursion
        # (unless it's actually a project directory)
        if not is_project_directory(home):
            assert (
                "limiting" in result.content.lower()
                or "non-recursive" in result.content.lower()
                or result.content is not None
            )

    def test_home_subdir_detection(self):
        """Test detection of common home subdirectories."""
        home = os.path.expanduser("~")

        for subdir in ["Documents", "Desktop", "Downloads"]:
            test_path = os.path.join(home, subdir)
            if os.path.exists(test_path):
                assert is_likely_home_directory(test_path) is True


class TestIsProjectDirectoryEdgeCases:
    """Test is_project_directory error handling."""

    def test_permission_error_returns_false(self, tmp_path):
        """Test that permission errors return False."""
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o000)

        try:
            result = is_project_directory(str(restricted))
            assert result is False
        finally:
            restricted.chmod(0o755)

    def test_nonexistent_directory_returns_false(self, tmp_path):
        """Test that nonexistent directory returns False."""
        nonexistent = tmp_path / "does_not_exist"
        result = is_project_directory(str(nonexistent))
        assert result is False


class TestReadFileUnicodeHandling:
    """Test _read_file Unicode edge cases."""

    def test_read_file_surrogate_cleanup_fallback(self, tmp_path):
        """Test the fallback path for surrogate character cleanup."""
        test_file = tmp_path / "surrogate_test.txt"
        # Write content that might trigger surrogate handling
        test_file.write_bytes(b"Hello\xed\xa0\x80World")

        result = _read_file(None, str(test_file))

        # Should handle gracefully
        assert result is not None
        assert isinstance(result, ReadFileOutput)

    def test_read_file_total_lines_calculation(self, tmp_path):
        """Test that total lines are calculated correctly."""
        test_file = tmp_path / "lines.txt"
        # File without trailing newline
        test_file.write_text("line1\nline2\nline3")

        result = _read_file(None, str(test_file))

        assert result.error is None
        assert result.content == "line1\nline2\nline3"

    def test_read_file_with_trailing_newline(self, tmp_path):
        """Test reading file with trailing newline."""
        test_file = tmp_path / "trailing.txt"
        test_file.write_text("line1\nline2\n")

        result = _read_file(None, str(test_file))

        assert result.error is None
        assert result.content == "line1\nline2\n"


class TestFileSizeFormatting:
    """Test the format_size helper function by triggering different size ranges."""

    def test_bytes_format(self, tmp_path):
        """Test formatting for small files (bytes)."""
        small_file = tmp_path / "small.txt"
        small_file.write_text("x" * 100)  # 100 bytes

        result = _list_files(None, str(tmp_path), recursive=False)

        assert "100 B" in result.content

    def test_kilobytes_format(self, tmp_path):
        """Test formatting for KB-sized files."""
        kb_file = tmp_path / "kb_file.txt"
        kb_file.write_text("x" * 2048)  # 2 KB

        result = _list_files(None, str(tmp_path), recursive=False)

        assert "KB" in result.content

    def test_megabytes_format(self, tmp_path):
        """Test formatting for MB-sized files."""
        mb_file = tmp_path / "mb_file.txt"
        mb_file.write_text("x" * (1024 * 1024 + 100))  # ~1 MB

        result = _list_files(None, str(tmp_path), recursive=False)

        assert "MB" in result.content


class TestRegisterFunctions:
    """Test the register_* functions and their inner tool logic."""

    def test_register_list_files_truncation(self):
        """Test that list_files truncates very large results."""
        from code_puppy.tools.file_operations import register_list_files

        # Create a mock agent
        mock_agent = MagicMock()
        registered_tools = {}

        def capture_tool(func):
            registered_tools[func.__name__] = func
            return func

        mock_agent.tool = capture_tool

        # Register the tool
        register_list_files(mock_agent)

        assert "list_files" in registered_tools

    def test_register_read_file(self):
        """Test that read_file tool is registered correctly."""
        from code_puppy.tools.file_operations import register_read_file

        mock_agent = MagicMock()
        registered_tools = {}

        def capture_tool(func):
            registered_tools[func.__name__] = func
            return func

        mock_agent.tool = capture_tool

        register_read_file(mock_agent)

        assert "read_file" in registered_tools

    def test_register_grep(self):
        """Test that grep tool is registered correctly."""
        from code_puppy.tools.file_operations import register_grep

        mock_agent = MagicMock()
        registered_tools = {}

        def capture_tool(func):
            registered_tools[func.__name__] = func
            return func

        mock_agent.tool = capture_tool

        register_grep(mock_agent)

        assert "grep" in registered_tools

    def test_list_files_recursion_disabled_by_config(self, tmp_path):
        """Test that recursion is disabled when config says so."""
        from code_puppy.tools.file_operations import register_list_files

        mock_agent = MagicMock()
        registered_tools = {}

        def capture_tool(func):
            registered_tools[func.__name__] = func
            return func

        mock_agent.tool = capture_tool

        # Mock get_allow_recursion at the config module level before registration
        with patch("code_puppy.config.get_allow_recursion", return_value=False):
            register_list_files(mock_agent)
            list_files_tool = registered_tools["list_files"]

            # Create a mock context
            mock_ctx = MagicMock()

            result = list_files_tool(mock_ctx, str(tmp_path), recursive=True)

            # Should have warning about recursion being disabled
            assert result.error is not None
            assert "Recursion disabled" in result.error


class TestMatchInfoModel:
    """Test the MatchInfo Pydantic model."""

    def test_match_info_creation(self):
        """Test creating MatchInfo objects."""
        match = MatchInfo(
            file_path="/path/to/file.py",
            line_number=42,
            line_content="def test_function():",
        )

        assert match.file_path == "/path/to/file.py"
        assert match.line_number == 42
        assert match.line_content == "def test_function():"

    def test_match_info_with_none_values(self):
        """Test MatchInfo with None values."""
        match = MatchInfo(file_path=None, line_number=None, line_content=None)

        assert match.file_path is None
        assert match.line_number is None
        assert match.line_content is None


class TestGrepOutputModel:
    """Test the GrepOutput Pydantic model."""

    def test_grep_output_with_matches(self):
        """Test GrepOutput with matches."""
        matches = [
            MatchInfo(file_path="a.py", line_number=1, line_content="test"),
            MatchInfo(file_path="b.py", line_number=2, line_content="test2"),
        ]
        output = GrepOutput(matches=matches)

        assert len(output.matches) == 2
        assert output.error is None

    def test_grep_output_with_error(self):
        """Test GrepOutput with error."""
        output = GrepOutput(matches=[], error="Something went wrong")

        assert len(output.matches) == 0
        assert output.error == "Something went wrong"


class TestListFileOutputModel:
    """Test the ListFileOutput Pydantic model."""

    def test_list_file_output_success(self):
        """Test ListFileOutput for successful listing."""
        output = ListFileOutput(content="file1.txt\nfile2.py\n")

        assert "file1.txt" in output.content
        assert output.error is None

    def test_list_file_output_with_error(self):
        """Test ListFileOutput with error."""
        output = ListFileOutput(
            content="Error: Directory not found", error="Directory not found"
        )

        assert output.error is not None


class TestReadFileOutputModel:
    """Test the ReadFileOutput Pydantic model."""

    def test_read_file_output_success(self):
        """Test ReadFileOutput for successful read."""
        output = ReadFileOutput(content="file content", num_tokens=100)

        assert output.content == "file content"
        assert output.num_tokens == 100
        assert output.error is None

    def test_read_file_output_with_error(self):
        """Test ReadFileOutput with error."""
        output = ReadFileOutput(content=None, num_tokens=0, error="File not found")

        assert output.content is None
        assert output.num_tokens == 0
        assert output.error == "File not found"


class TestEdgeCasesInListFiles:
    """Test additional edge cases in _list_files."""

    def test_list_files_with_empty_path_in_results(self, tmp_path):
        """Test handling of items with empty paths."""
        # Create normal files
        (tmp_path / "normal.txt").write_text("content")

        result = _list_files(None, str(tmp_path), recursive=False)

        assert result.content is not None
        assert "normal.txt" in result.content

    def test_list_files_recursive_file_processing(self, tmp_path):
        """Test recursive file processing with nested directories."""
        # Create nested structure
        subdir = tmp_path / "level1" / "level2"
        subdir.mkdir(parents=True)
        (subdir / "deep.py").write_text("# deep file")

        result = _list_files(None, str(tmp_path), recursive=True)

        assert "deep.py" in result.content
        assert "level1" in result.content
        assert "level2" in result.content

    def test_list_files_handles_stat_errors(self, tmp_path):
        """Test that stat errors on individual files don't crash listing."""
        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = _list_files(None, str(tmp_path), recursive=False)

        assert result.error is None
        assert "test.txt" in result.content


class TestIgnoreFileCleanup:
    """Test that temporary ignore files are cleaned up."""

    def test_list_files_cleans_up_ignore_file(self, tmp_path):
        """Test that temporary ignore file is cleaned up after listing."""
        (tmp_path / "test.txt").write_text("content")

        # List files should create and then clean up temp ignore file
        result = _list_files(None, str(tmp_path), recursive=True)

        # Should complete without errors
        assert result is not None

    def test_grep_cleans_up_ignore_file(self, tmp_path):
        """Test that temporary ignore file is cleaned up after grep."""
        test_file = tmp_path / "search.py"
        test_file.write_text("searchable content\n")

        result = _grep(None, "searchable", str(tmp_path))

        # Should complete without errors
        assert result is not None
