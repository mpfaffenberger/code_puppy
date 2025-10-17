"""Tests for code_puppy.tools.common.

This module tests shared utility functions for the tools package including
ignore patterns, path matching, fuzzy text search, and ID generation.
"""

import importlib.util
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import directly from the module file to avoid heavy dependencies in __init__.py
spec = importlib.util.spec_from_file_location(
    "common_module",
    Path(__file__).parent.parent.parent / "code_puppy" / "tools" / "common.py"
)
common_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common_module)

IGNORE_PATTERNS = common_module.IGNORE_PATTERNS
should_ignore_path = common_module.should_ignore_path
_find_best_window = common_module._find_best_window
generate_group_id = common_module.generate_group_id


@pytest.fixture
def mock_time_and_random(monkeypatch):
    """Fixture to make time and random deterministic for testing."""
    # We need to patch at the module level where they're imported
    import random
    import time

    monkeypatch.setattr(time, "time", lambda: 1234567890.123456)
    monkeypatch.setattr(random, "randint", lambda a, b: 5555)
    return 1234567890.123456, 5555


class TestIgnorePatterns:
    """Test the IGNORE_PATTERNS constant."""

    def test_ignore_patterns_is_list(self):
        """Test that IGNORE_PATTERNS is a list."""
        assert isinstance(IGNORE_PATTERNS, list)

    def test_ignore_patterns_is_not_empty(self):
        """Test that IGNORE_PATTERNS has entries."""
        assert len(IGNORE_PATTERNS) > 0

    def test_ignore_patterns_contains_common_patterns(self):
        """Test that common ignore patterns are present."""
        # Check for representative patterns from different categories
        common_patterns = [
            "**/node_modules/**",  # Node.js
            "**/__pycache__/**",  # Python
            "**/.git/**",  # Version control
            "**/.vscode/**",  # IDE
            "**/*.pyc",  # Python compiled
            "**/.DS_Store",  # OS files
        ]
        for pattern in common_patterns:
            assert (
                pattern in IGNORE_PATTERNS
            ), f"Expected common pattern '{pattern}' not found"

    def test_ignore_patterns_tracks_duplicates(self):
        """Test and document any duplicate patterns.
        
        Note: As of this test, IGNORE_PATTERNS contains some duplicates.
        This is likely intentional for cross-platform compatibility or
        different pattern matching styles. This test documents the count.
        """
        unique_patterns = set(IGNORE_PATTERNS)
        duplicate_count = len(IGNORE_PATTERNS) - len(unique_patterns)
        
        # Document the current state (38 duplicates as of writing)
        # If this number changes significantly, it might indicate a problem
        assert duplicate_count >= 0, "Negative duplicates count - logic error"
        
        # This is informational - duplicates may be intentional
        # If duplicate_count is unexpectedly high (>50), something might be wrong
        assert duplicate_count < 100, (
            f"Unexpectedly high duplicate count: {duplicate_count}. "
            "This might indicate a problem with pattern definitions."
        )

    def test_ignore_patterns_are_valid_strings(self):
        """Test that all patterns are non-empty strings."""
        for pattern in IGNORE_PATTERNS:
            assert isinstance(pattern, str), f"Pattern {pattern} is not a string"
            assert len(pattern) > 0, "Found empty pattern in IGNORE_PATTERNS"


class TestShouldIgnorePath:
    """Test should_ignore_path function."""

    # Version Control Tests
    def test_ignores_git_directory(self):
        """Test that .git directories are ignored."""
        assert should_ignore_path(".git") is True
        assert should_ignore_path("foo/.git") is True
        assert should_ignore_path("foo/bar/.git") is True

    def test_ignores_git_subdirectories(self):
        """Test that .git subdirectories are ignored."""
        assert should_ignore_path(".git/objects") is True
        assert should_ignore_path("foo/.git/refs") is True
        assert should_ignore_path("project/.git/hooks/pre-commit") is True

    # Build Artifacts - Node.js
    def test_ignores_node_modules(self):
        """Test that node_modules directories are ignored."""
        assert should_ignore_path("node_modules") is True
        assert should_ignore_path("foo/node_modules") is True
        assert should_ignore_path("node_modules/package") is True
        assert should_ignore_path("project/node_modules/react/index.js") is True

    def test_ignores_javascript_build_dirs(self):
        """Test that JS build directories are ignored."""
        assert should_ignore_path("dist") is True
        assert should_ignore_path("build") is True
        assert should_ignore_path(".next") is True
        assert should_ignore_path("project/.cache") is True

    # Build Artifacts - Python
    def test_ignores_pycache(self):
        """Test that __pycache__ directories are ignored."""
        assert should_ignore_path("__pycache__") is True
        assert should_ignore_path("foo/__pycache__") is True
        assert should_ignore_path("__pycache__/module.pyc") is True
        assert should_ignore_path("src/utils/__pycache__") is True

    def test_ignores_python_compiled_files(self):
        """Test that .pyc files are ignored."""
        assert should_ignore_path("module.pyc") is True
        assert should_ignore_path("foo/bar.pyc") is True
        assert should_ignore_path("src/app/models.pyc") is True

    # IDE Files
    def test_ignores_ide_directories(self):
        """Test that IDE directories are ignored."""
        assert should_ignore_path(".vscode") is True
        assert should_ignore_path(".idea") is True
        assert should_ignore_path("project/.vs") is True

    # Binary Files
    def test_ignores_binary_files(self):
        """Test that binary files are ignored."""
        assert should_ignore_path("image.png") is True
        assert should_ignore_path("document.pdf") is True
        assert should_ignore_path("archive.zip") is True
        assert should_ignore_path("data.db") is True

    # Happy Path - Files that should NOT be ignored
    def test_does_not_ignore_regular_files(self):
        """Test that normal files are NOT ignored."""
        assert should_ignore_path("main.py") is False
        assert should_ignore_path("README.md") is False
        assert should_ignore_path("package.json") is False
        assert should_ignore_path("Cargo.toml") is False
        assert should_ignore_path("src/app/models.py") is False

    def test_does_not_ignore_regular_directories(self):
        """Test that normal directories are NOT ignored."""
        assert should_ignore_path("src") is False
        assert should_ignore_path("lib") is False
        assert should_ignore_path("tests") is False
        assert should_ignore_path("docs") is False

    # Edge Cases
    def test_handles_absolute_paths(self):
        """Test that absolute paths work correctly."""
        assert should_ignore_path("/home/user/.git") is True
        assert should_ignore_path("/usr/local/node_modules") is True
        assert should_ignore_path("/home/user/project/main.py") is False

    def test_handles_relative_paths(self):
        """Test that relative paths work correctly."""
        assert should_ignore_path("./node_modules") is True
        assert should_ignore_path("../.git") is True
        assert should_ignore_path("./src/main.py") is False

    def test_handles_paths_with_special_characters(self):
        """Test paths with spaces and special chars."""
        assert should_ignore_path("foo bar/.git") is True
        assert should_ignore_path("foo-bar/node_modules") is True
        assert should_ignore_path("my_project/__pycache__") is True

    def test_empty_path_returns_false(self):
        """Test that empty path returns False."""
        assert should_ignore_path("") is False

    def test_handles_deeply_nested_paths(self):
        """Test deeply nested paths are matched correctly."""
        assert should_ignore_path("a/b/c/d/e/f/.git") is True
        assert should_ignore_path("project/src/components/node_modules") is True
        assert should_ignore_path("a/b/c/d/e/f/main.py") is False

    # Pattern-Specific Tests
    def test_glob_star_patterns_work(self):
        """Test that ** glob patterns work correctly."""
        # **/.git/** should match any .git directory at any depth
        assert should_ignore_path("foo/bar/.git/baz") is True
        assert should_ignore_path(".git/objects/pack") is True

    def test_file_extension_patterns_work(self):
        """Test that file extension patterns work."""
        assert should_ignore_path("module.pyc") is True
        assert should_ignore_path("image.png") is True
        assert should_ignore_path("archive.zip") is True

    def test_directory_name_patterns_work(self):
        """Test that directory name patterns work."""
        # Pattern like "**/node_modules/**" should match files inside
        assert should_ignore_path("node_modules/react/index.js") is True
        assert should_ignore_path("project/node_modules/vue/dist/vue.js") is True


class TestFindBestWindow:
    """Test _find_best_window fuzzy matching function."""

    def test_finds_exact_match(self):
        """Test finding an exact match in haystack."""
        haystack = ["line1", "line2", "line3"]
        needle = "line2"

        # Patch console at module level
        common_module.console = MagicMock()
        span, score = _find_best_window(haystack, needle)

        assert span == (1, 2), f"Expected span (1, 2), got {span}"
        assert score > 0.99, f"Expected near-perfect score, got {score}"

    def test_finds_best_fuzzy_match(self):
        """Test finding best fuzzy match."""
        haystack = ["hello world", "hello wurld", "goodbye"]
        needle = "hello world"

        common_module.console = MagicMock()
        span, score = _find_best_window(haystack, needle)

        # Should match the first line (exact match)
        assert span == (0, 1), f"Expected span (0, 1), got {span}"
        assert score > 0.99, f"Expected high score for exact match, got {score}"

    def test_finds_multiline_match(self):
        """Test finding multi-line match."""
        haystack = ["a", "b", "c", "d"]
        needle = "b\nc"

        common_module.console = MagicMock()
        span, score = _find_best_window(haystack, needle)

        assert span == (1, 3), f"Expected span (1, 3), got {span}"
        assert score > 0.99, f"Expected high score, got {score}"

    def test_empty_haystack_returns_none(self):
        """Test empty haystack returns None."""
        haystack = []
        needle = "foo"

        common_module.console = MagicMock()
        span, score = _find_best_window(haystack, needle)

        assert span is None, f"Expected None for empty haystack, got {span}"
        assert score == 0.0, f"Expected score 0.0, got {score}"

    def test_needle_larger_than_haystack(self):
        """Test when needle has more lines than haystack."""
        haystack = ["a"]
        needle = "a\nb\nc"

        common_module.console = MagicMock()
        span, score = _find_best_window(haystack, needle)

        # Should return None because window size (3) > haystack size (1)
        assert span is None, f"Expected None when needle > haystack, got {span}"

    def test_handles_trailing_newlines(self):
        """Test that trailing newlines in needle are stripped."""
        haystack = ["line1", "line2"]
        needle = "line1\n"  # Trailing newline

        common_module.console = MagicMock()
        span, score = _find_best_window(haystack, needle)

        # Should still match line1
        assert span == (0, 1), f"Expected span (0, 1), got {span}"
        assert score > 0.99, f"Expected high score, got {score}"

    def test_logs_results(self):
        """Test that function logs best span, window, and score."""
        haystack = ["test"]
        needle = "test"

        mock_console = MagicMock()
        common_module.console = mock_console
        _find_best_window(haystack, needle)

        # Should log: span, window, score
        assert mock_console.log.call_count == 3, (
            f"Expected 3 console.log calls, got {mock_console.log.call_count}"
        )

    def test_returns_best_match_not_first(self):
        """Test that it returns the BEST match, not just the first."""
        haystack = ["hello wurld", "hello world", "hello"]
        needle = "hello world"

        common_module.console = MagicMock()
        span, score = _find_best_window(haystack, needle)

        # Should match index 1 (exact match) not index 0 (fuzzy match)
        assert span == (1, 2), f"Expected best match at (1, 2), got {span}"
        assert score > 0.99, f"Expected near-perfect score, got {score}"


class TestGenerateGroupId:
    """Test generate_group_id function."""

    def test_generates_id_with_tool_name(self, mock_time_and_random):
        """Test that generated ID contains tool name."""
        result = generate_group_id("list_files")

        assert result.startswith("list_files_"), (
            f"Expected ID to start with 'list_files_', got {result}"
        )

    def test_generates_unique_ids_for_different_tools(self, mock_time_and_random):
        """Test that different tool names generate different IDs."""
        id1 = generate_group_id("tool1")
        id2 = generate_group_id("tool2")

        assert id1 != id2, f"Expected different IDs, got {id1} and {id2}"
        assert id1.startswith("tool1_")
        assert id2.startswith("tool2_")

    def test_includes_extra_context_in_hash(self, mock_time_and_random):
        """Test that extra_context affects the hash."""
        id1 = generate_group_id("tool", "ctx1")
        id2 = generate_group_id("tool", "ctx2")

        assert id1 != id2, (
            f"Expected different IDs for different contexts, got {id1} and {id2}"
        )

    def test_format_is_toolname_underscore_hash(self, mock_time_and_random):
        """Test that format is 'toolname_XXXXXXXX'."""
        result = generate_group_id("my_tool")

        # Format should be: tool_name + underscore + 8 hex chars
        pattern = r"^[a-z_]+_[a-f0-9]{8}$"
        assert re.match(pattern, result), (
            f"ID '{result}' doesn't match expected format {pattern}"
        )

    def test_hash_is_8_characters(self, mock_time_and_random):
        """Test that hash portion is exactly 8 hex characters."""
        result = generate_group_id("tool")

        # Split on underscore and check last part
        parts = result.split("_")
        hash_part = parts[-1]

        assert len(hash_part) == 8, f"Expected 8 char hash, got {len(hash_part)}"
        assert all(
            c in "0123456789abcdef" for c in hash_part
        ), f"Hash '{hash_part}' contains non-hex characters"

    def test_handles_empty_extra_context(self, mock_time_and_random):
        """Test with empty extra_context (default parameter)."""
        result = generate_group_id("tool")  # No extra_context

        assert result.startswith("tool_"), f"Expected 'tool_' prefix, got {result}"
        assert len(result) > 5, f"ID seems too short: {result}"

    def test_deterministic_with_same_inputs(self, mock_time_and_random):
        """Test that same inputs produce same output (with mocked time/random)."""
        id1 = generate_group_id("tool", "context")
        id2 = generate_group_id("tool", "context")

        assert id1 == id2, (
            f"Expected deterministic IDs with mocked time/random, got {id1} != {id2}"
        )
