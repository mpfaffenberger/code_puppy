"""Tests for P2-04: fuzzy replacement fallback limits in file_modifications.py."""

from __future__ import annotations


import pytest

from code_puppy.tools.file_modifications import (
    MAX_FUZZY_FILE_LINES,
    MAX_FUZZY_OLD_SNIPPET_CHARS,
    MAX_FUZZY_REPLACEMENT_COUNT,
    _replace_in_file,
)


@pytest.fixture(autouse=True)
def _allow_file_permissions(monkeypatch):
    """Bypass interactive file-permission prompts during tests."""
    monkeypatch.setattr(
        "code_puppy.callbacks.on_file_permission", lambda *args, **kwargs: [True]
    )


@pytest.fixture(autouse=True)
def _chdir_tmp_path(tmp_path, monkeypatch):
    """Make tmp_path the workspace root so path policy allows writes."""
    monkeypatch.chdir(tmp_path)


class TestFuzzyReplacementLimits:
    """P2-04: fuzzy fallback is skipped on large inputs with actionable errors."""

    def test_replace_large_file_skips_fuzzy_fallback(self, tmp_path):
        """When a file exceeds MAX_FUZZY_FILE_LINES, fuzzy is skipped."""
        test_file = tmp_path / "big.py"
        # Create a file with > 20k lines
        lines = [f"# line {i}" for i in range(MAX_FUZZY_FILE_LINES + 100)]
        test_file.write_text("\n".join(lines))

        # Use a near-match old_str that would trigger fuzzy
        result = _replace_in_file(
            None,
            str(test_file),
            [{"old_str": "# line 50", "new_str": "# CHANGED"}],
        )
        # The exact match would succeed on a small file, but here we test
        # the *fuzzy* path specifically by providing a non-exact match.
        # Let's use a slightly off snippet so exact match fails.
        result = _replace_in_file(
            None,
            str(test_file),
            [{"old_str": "# line 50x", "new_str": "# CHANGED"}],
        )
        assert result.get("fuzzy_skipped") is True
        assert "fuzzy fallback skipped" in result.get("error", "").lower()

    def test_replace_large_old_snippet_skips_fuzzy_fallback(self, tmp_path):
        """When old_str exceeds MAX_FUZZY_OLD_SNIPPET_CHARS, fuzzy is skipped."""
        test_file = tmp_path / "medium.py"
        # Small file (well under line limit), but huge old_snippet
        test_file.write_text("x = 1\ny = 2\nz = 3\n")

        huge_old = "a" * (MAX_FUZZY_OLD_SNIPPET_CHARS + 1)
        result = _replace_in_file(
            None,
            str(test_file),
            [{"old_str": huge_old, "new_str": "replaced"}],
        )
        assert result.get("fuzzy_skipped") is True
        assert "old_str is" in result.get("error", "")
        assert f"{MAX_FUZZY_OLD_SNIPPET_CHARS}" in result.get("error", "")

    def test_replace_small_file_still_uses_fuzzy_fallback(self, tmp_path):
        """Small files with small snippets should still use fuzzy matching."""
        test_file = tmp_path / "small.py"
        test_file.write_text("def hello():\n    return 'world'\n")

        # Provide a slightly-off match (extra trailing space) that requires fuzzy
        result = _replace_in_file(
            None,
            str(test_file),
            [
                {
                    "old_str": "def hello(): \n    return 'world'",
                    "new_str": "def greet():\n    return 'world'",
                }
            ],
        )
        # Fuzzy should still run — no fuzzy_skipped key
        assert "fuzzy_skipped" not in result
        # If JW score is high enough, it succeeds; if < 0.95 it gives JW error
        # Either way, fuzzy was attempted (not blocked by limits)
        if result.get("success") is True:
            assert "greet" in test_file.read_text()
        else:
            # The fuzzy was attempted but score was too low — that's fine
            assert (
                "jw" in result.get("error", "").lower()
                or "no suitable match" in result.get("error", "").lower()
            )

    def test_replace_fuzzy_skip_error_is_actionable(self, tmp_path):
        """When fuzzy is skipped, the error message should tell the user what to do."""
        test_file = tmp_path / "big.py"
        lines = [f"# line {i}" for i in range(MAX_FUZZY_FILE_LINES + 100)]
        test_file.write_text("\n".join(lines))

        result = _replace_in_file(
            None,
            str(test_file),
            [{"old_str": "nonexistent_exact_text", "new_str": "replaced"}],
        )
        assert result.get("fuzzy_skipped") is True
        error = result.get("error", "")
        # Must contain actionable guidance
        assert "exact text" in error.lower() or "smaller chunk" in error.lower()

    def test_replace_over_max_replacement_count_rejected(self, tmp_path):
        """Replacing more than MAX_FUZZY_REPLACEMENT_COUNT items is rejected."""
        test_file = tmp_path / "many.py"
        test_file.write_text("x = 1\n")

        too_many = [
            {"old_str": f"never_match_{i}", "new_str": f"new_{i}"}
            for i in range(MAX_FUZZY_REPLACEMENT_COUNT + 1)
        ]
        result = _replace_in_file(None, str(test_file), too_many)
        assert "too many replacements" in result.get("error", "").lower()
        assert str(MAX_FUZZY_REPLACEMENT_COUNT) in result.get("error", "")

    def test_exact_match_succeeds_on_large_file(self, tmp_path):
        """Large files should still allow exact matches (fuzzy isn't needed)."""
        test_file = tmp_path / "exact_big.py"
        lines = [f"# line {i}" for i in range(MAX_FUZZY_FILE_LINES + 100)]
        test_file.write_text("\n".join(lines))

        result = _replace_in_file(
            None,
            str(test_file),
            [{"old_str": "# line 50", "new_str": "# CHANGED"}],
        )
        # Exact match should work fine regardless of file size
        assert result.get("success") is True
        assert "# CHANGED" in test_file.read_text()

    def test_replacement_count_exactly_at_limit_accepted(self, tmp_path):
        """Exactly MAX_FUZZY_REPLACEMENT_COUNT replacements should be allowed."""
        test_file = tmp_path / "at_limit.py"
        content_lines = [f"var_{i} = {i}" for i in range(MAX_FUZZY_REPLACEMENT_COUNT)]
        test_file.write_text("\n".join(content_lines))

        replacements = [
            {"old_str": f"var_{i} = {i}", "new_str": f"var_{i} = {i}_new"}
            for i in range(MAX_FUZZY_REPLACEMENT_COUNT)
        ]
        result = _replace_in_file(None, str(test_file), replacements)
        # Should NOT be rejected for count
        assert "too many replacements" not in result.get("error", "").lower()
