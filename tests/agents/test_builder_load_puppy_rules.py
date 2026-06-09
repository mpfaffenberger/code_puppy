"""Tests for load_puppy_rules() in code_puppy.agents._builder.

Covers the .code_puppy/ directory feature (PUP-34):
- Loading from .code_puppy/AGENTS.md (preferred)
- Precedence: .code_puppy/ over project root
- Backwards compatibility with root AGENTS.md
- Combining global + project rules
- Edge cases (dir is file, empty dir, etc.)
"""

from unittest.mock import patch

import pytest


class TestLoadPuppyRulesCodePuppyDir:
    """Tests for .code_puppy/ directory support in load_puppy_rules()."""

    @pytest.fixture
    def temp_project(self, tmp_path, monkeypatch):
        """Set up a temporary project directory and cd into it."""
        monkeypatch.chdir(tmp_path)
        return tmp_path

    @pytest.fixture
    def mock_config_dir(self, tmp_path):
        """Create a mock global config directory."""
        config_dir = tmp_path / "global_config"
        config_dir.mkdir()
        return config_dir

    def test_load_from_code_puppy_dir(self, temp_project, mock_config_dir):
        """Load AGENTS.md from .code_puppy/ directory."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create .code_puppy/AGENTS.md
        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        agents_file = code_puppy_dir / "AGENTS.md"
        agents_file.write_text("# Rules from .code_puppy dir")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Rules from .code_puppy dir"

    def test_precedence_code_puppy_over_root(self, temp_project, mock_config_dir):
        """Files in .code_puppy/ take precedence over project root."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create both locations
        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("# Preferred rules")
        (temp_project / "AGENTS.md").write_text("# Root rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Should use .code_puppy/ version, NOT root
        assert result == "# Preferred rules"
        assert "Root rules" not in (result or "")

    def test_fallback_to_root(self, temp_project, mock_config_dir):
        """Fall back to root AGENTS.md if .code_puppy/ doesn't exist."""
        from code_puppy.agents._builder import load_puppy_rules

        # Only create root AGENTS.md
        (temp_project / "AGENTS.md").write_text("# Root rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Root rules"

    def test_global_and_code_puppy_combined(self, temp_project, mock_config_dir):
        """Global rules and .code_puppy rules are combined."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create global rules
        (mock_config_dir / "AGENTS.md").write_text("# Global rules")

        # Create .code_puppy rules
        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("# Project rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Both should be present, global first
        assert "# Global rules" in result
        assert "# Project rules" in result
        assert result.index("# Global rules") < result.index("# Project rules")

    def test_global_and_root_combined(self, temp_project, mock_config_dir):
        """Global rules + root rules work together."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create global rules
        (mock_config_dir / "AGENTS.md").write_text("# Global rules")

        # Create root rules
        (temp_project / "AGENTS.md").write_text("# Root rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Both should be combined
        assert "# Global rules" in result
        assert "# Root rules" in result

    def test_code_puppy_is_file_not_dir(self, temp_project, mock_config_dir):
        """If .code_puppy is a file (not directory), fall back to root."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create .code_puppy as a FILE, not directory
        (temp_project / ".code_puppy").write_text("I'm a file, not a dir!")

        # Create root AGENTS.md as fallback
        (temp_project / "AGENTS.md").write_text("# Root fallback")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Should use root fallback
        assert result == "# Root fallback"

    def test_code_puppy_dir_exists_but_empty(self, temp_project, mock_config_dir):
        """Empty .code_puppy/ dir falls back to root AGENTS.md."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create empty .code_puppy directory
        (temp_project / ".code_puppy").mkdir()

        # Create root AGENTS.md as fallback
        (temp_project / "AGENTS.md").write_text("# Root fallback")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        # Should use root fallback
        assert result == "# Root fallback"

    def test_no_agents_files_anywhere(self, temp_project, mock_config_dir):
        """Returns None if no AGENTS.md files exist anywhere."""
        from code_puppy.agents._builder import load_puppy_rules

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is None

    def test_agent_md_variant_in_code_puppy_dir(self, temp_project, mock_config_dir):
        """Also supports AGENT.md (singular) in .code_puppy/."""
        from code_puppy.agents._builder import load_puppy_rules

        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        # Use singular AGENT.md instead of AGENTS.md
        (code_puppy_dir / "AGENT.md").write_text("# Singular agent rules")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Singular agent rules"

    def test_agents_md_takes_precedence_over_agent_md(
        self, temp_project, mock_config_dir
    ):
        """AGENTS.md (plural) takes precedence over AGENT.md (singular)."""
        from code_puppy.agents._builder import load_puppy_rules

        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("# Plural wins")
        (code_puppy_dir / "AGENT.md").write_text("# Singular loses")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Plural wins"

    def test_only_global_rules(self, temp_project, mock_config_dir):
        """Only global rules loaded when no project rules exist."""
        from code_puppy.agents._builder import load_puppy_rules

        # Create only global rules
        (mock_config_dir / "AGENTS.md").write_text("# Global only")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Global only"


class TestTruncation:
    """Tests for the AGENTS.md character-cap behaviour.

    Each AGENTS.md file (global and project) is independently capped at
    ``AGENTS_MD_MAX_CHARS``. Overflowing files keep the first N chars
    verbatim and have a labelled warning notice appended; under-limit
    files are returned untouched.
    """

    @pytest.fixture
    def temp_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        return tmp_path

    @pytest.fixture
    def mock_config_dir(self, tmp_path):
        config_dir = tmp_path / "global_config"
        config_dir.mkdir()
        return config_dir

    # --- direct unit tests on the pure helper -----------------------------

    def test_helper_under_limit_returns_verbatim(self):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            _truncate_agents_md,
        )

        content = "x" * (AGENTS_MD_MAX_CHARS - 1)
        assert _truncate_agents_md(content, source="test") == content

    def test_helper_at_limit_returns_verbatim(self):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            _truncate_agents_md,
        )

        content = "x" * AGENTS_MD_MAX_CHARS
        result = _truncate_agents_md(content, source="test")
        assert result == content
        assert "truncated" not in result

    def test_helper_over_limit_truncates_with_warning(self):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            _truncate_agents_md,
        )

        original_len = AGENTS_MD_MAX_CHARS + 5_000
        content = "y" * original_len
        result = _truncate_agents_md(content, source="global ~/x/AGENTS.md")

        # First N chars verbatim from the original.
        assert result[:AGENTS_MD_MAX_CHARS] == content[:AGENTS_MD_MAX_CHARS]
        # Notice present and addressed to the agent.
        assert "--- AGENTS.md truncated ---" in result
        assert "--- end truncation notice ---" in result
        # Source label propagated so the agent can name the offending file.
        assert "global ~/x/AGENTS.md" in result
        # Counts present (thousands-separated, since that's what the notice uses).
        assert f"{original_len:,}" in result
        assert f"{original_len - AGENTS_MD_MAX_CHARS:,}" in result

    # --- end-to-end through load_puppy_rules ------------------------------

    def test_under_limit_unchanged(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import load_puppy_rules

        (temp_project / "AGENTS.md").write_text("a" * 5_000)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "a" * 5_000
        assert "truncated" not in result

    def test_exactly_at_limit_unchanged(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        (temp_project / "AGENTS.md").write_text("a" * AGENTS_MD_MAX_CHARS)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "a" * AGENTS_MD_MAX_CHARS
        assert "truncated" not in result

    def test_over_limit_truncated_with_warning(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        original_len = 15_000
        content = "b" * original_len
        (temp_project / "AGENTS.md").write_text(content)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        # First N chars are verbatim from the original.
        assert result[:AGENTS_MD_MAX_CHARS] == content[:AGENTS_MD_MAX_CHARS]
        # Notice block follows.
        assert "--- AGENTS.md truncated ---" in result
        # Numbers reported correctly.
        assert f"{original_len:,}" in result
        assert f"{original_len - AGENTS_MD_MAX_CHARS:,}" in result
        # Source label includes the file path so the agent can name it.
        assert "AGENTS.md" in result
        assert "project" in result

    def test_truncation_per_file_global_only(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        # Fat global, small project. Per-file truncation must keep the
        # project file fully intact.
        (mock_config_dir / "AGENTS.md").write_text("g" * 15_000)
        (temp_project / "AGENTS.md").write_text("# Project rules (short)")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        # Project file landed untouched.
        assert "# Project rules (short)" in result
        # Global file got truncated with a labelled notice.
        assert "--- AGENTS.md truncated ---" in result
        assert "global" in result
        # The 15k of 'g' was capped at AGENTS_MD_MAX_CHARS: a contiguous
        # block of exactly N g's survives, but a block of N+1 does not.
        assert "g" * AGENTS_MD_MAX_CHARS in result
        assert "g" * (AGENTS_MD_MAX_CHARS + 1) not in result

    def test_truncation_per_file_project_only(self, temp_project, mock_config_dir):
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        # Small global, fat project. Global must land untouched.
        (mock_config_dir / "AGENTS.md").write_text("# Global rules (short)")
        (temp_project / "AGENTS.md").write_text("p" * 15_000)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        assert "# Global rules (short)" in result
        assert "--- AGENTS.md truncated ---" in result
        assert "project" in result
        assert "p" * AGENTS_MD_MAX_CHARS in result
        assert "p" * (AGENTS_MD_MAX_CHARS + 1) not in result

    def test_warning_identifies_source_when_both_truncated(
        self, temp_project, mock_config_dir
    ):
        """When both files overflow, the agent must be able to tell them apart."""
        from code_puppy.agents._builder import load_puppy_rules

        (mock_config_dir / "AGENTS.md").write_text("g" * 15_000)
        (temp_project / "AGENTS.md").write_text("p" * 15_000)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        # Two distinct truncation notices.
        assert result.count("--- AGENTS.md truncated ---") == 2
        # Both source classes are named so the agent can disambiguate.
        assert "global" in result
        assert "project" in result

    def test_truncation_via_preferred_code_puppy_dir(
        self, temp_project, mock_config_dir
    ):
        """Closes branch-coverage parity: truncation also fires from .code_puppy/."""
        from code_puppy.agents._builder import (
            AGENTS_MD_MAX_CHARS,
            load_puppy_rules,
        )

        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("q" * 15_000)

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is not None
        assert "--- AGENTS.md truncated ---" in result
        assert ".code_puppy" in result  # source label names the preferred path
        assert "q" * AGENTS_MD_MAX_CHARS in result
        assert "q" * (AGENTS_MD_MAX_CHARS + 1) not in result

    def test_friendly_path_collapses_home(self, tmp_path, monkeypatch):
        """Paths under $HOME render as ~/...; paths outside fall back to absolute."""
        from pathlib import Path

        from code_puppy.agents._builder import _friendly_path

        fake_home = tmp_path / "home" / "user"
        fake_home.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        under_home = fake_home / ".code_puppy" / "AGENTS.md"
        assert _friendly_path(under_home) == "~/.code_puppy/AGENTS.md"

        outside_home = tmp_path / "elsewhere" / "AGENTS.md"
        assert _friendly_path(outside_home) == str(outside_home)
