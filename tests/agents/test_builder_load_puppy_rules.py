"""Tests for load_puppy_rules() in code_puppy.agents._builder.

Covers the .code_puppy/ directory feature (PUP-34):
- Loading from .code_puppy/AGENTS.md (preferred)
- Precedence: .code_puppy/ over project root
- Backwards compatibility with root AGENTS.md
- Combining global + project rules
- Edge cases (dir is file, empty dir, etc.)

Also covers:
- @file reference expansion (one level deep)
- CLAUDE.md fallback when no AGENTS.md exists
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


class TestExpandAtReferences:
    """Tests for _expand_at_references() — @file inclusion."""

    def test_expands_at_reference(self, tmp_path):
        """@filename on its own line is replaced with file contents."""
        from code_puppy.agents._builder import _expand_at_references

        included = tmp_path / "rules.md"
        included.write_text("# Included content")

        result = _expand_at_references("@rules.md", base_dir=tmp_path)
        assert result == "# Included content"

    def test_expands_at_reference_in_context(self, tmp_path):
        """@ref surrounded by other text replaces only the @ref line."""
        from code_puppy.agents._builder import _expand_at_references

        included = tmp_path / "extra.md"
        included.write_text("extra stuff")

        text = "before\n@extra.md\nafter"
        result = _expand_at_references(text, base_dir=tmp_path)
        assert result == "before\nextra stuff\nafter"

    def test_missing_at_reference_left_intact(self, tmp_path):
        """Unknown @ref is left as-is so the agent can see it failed."""
        from code_puppy.agents._builder import _expand_at_references

        result = _expand_at_references("@nonexistent.md", base_dir=tmp_path)
        assert result == "@nonexistent.md"

    def test_only_one_level_deep(self, tmp_path):
        """@refs inside included files are NOT expanded (one level only)."""
        from code_puppy.agents._builder import _expand_at_references

        nested = tmp_path / "nested.md"
        nested.write_text("# nested")
        included = tmp_path / "included.md"
        included.write_text("@nested.md")

        result = _expand_at_references("@included.md", base_dir=tmp_path)
        # Should contain the literal text of included.md, NOT expand @nested.md
        assert result == "@nested.md"

    def test_at_ref_with_subdirectory_path(self, tmp_path):
        """@subdir/file.md resolves relative to base_dir."""
        from code_puppy.agents._builder import _expand_at_references

        subdir = tmp_path / "rules"
        subdir.mkdir()
        (subdir / "dev.md").write_text("# dev rules")

        result = _expand_at_references("@rules/dev.md", base_dir=tmp_path)
        assert result == "# dev rules"

    def test_at_ref_not_expanded_mid_line(self, tmp_path):
        """@ref mid-line (not at line start) is NOT expanded."""
        from code_puppy.agents._builder import _expand_at_references

        included = tmp_path / "rules.md"
        included.write_text("should not appear")

        result = _expand_at_references("see @rules.md for details", base_dir=tmp_path)
        assert result == "see @rules.md for details"

    def test_multiple_at_references(self, tmp_path):
        """Multiple @refs in the same file are all expanded."""
        from code_puppy.agents._builder import _expand_at_references

        (tmp_path / "a.md").write_text("# A")
        (tmp_path / "b.md").write_text("# B")

        result = _expand_at_references("@a.md\n@b.md", base_dir=tmp_path)
        assert result == "# A\n# B"


class TestClaudeMdFallback:
    """Tests for CLAUDE.md fallback when no AGENTS.md exists."""

    @pytest.fixture
    def temp_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        return tmp_path

    @pytest.fixture
    def mock_config_dir(self, tmp_path):
        config_dir = tmp_path / "global_config"
        config_dir.mkdir()
        return config_dir

    def test_falls_back_to_claude_md(self, temp_project, mock_config_dir):
        """CLAUDE.md is loaded when no AGENTS.md exists anywhere."""
        from code_puppy.agents._builder import load_puppy_rules

        (temp_project / "CLAUDE.md").write_text("# Claude fallback")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Claude fallback"

    def test_agents_md_takes_priority_over_claude_md(
        self, temp_project, mock_config_dir
    ):
        """AGENTS.md wins over CLAUDE.md when both exist."""
        from code_puppy.agents._builder import load_puppy_rules

        (temp_project / "AGENTS.md").write_text("# Agents wins")
        (temp_project / "CLAUDE.md").write_text("# Claude loses")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Agents wins"
        assert "Claude loses" not in (result or "")

    def test_claude_md_not_loaded_when_code_puppy_agents_md_exists(
        self, temp_project, mock_config_dir
    ):
        """.code_puppy/AGENTS.md prevents CLAUDE.md fallback."""
        from code_puppy.agents._builder import load_puppy_rules

        code_puppy_dir = temp_project / ".code_puppy"
        code_puppy_dir.mkdir()
        (code_puppy_dir / "AGENTS.md").write_text("# Preferred rules")
        (temp_project / "CLAUDE.md").write_text("# Should not load")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Preferred rules"
        assert "Should not load" not in (result or "")

    def test_claude_md_with_at_references(self, temp_project, mock_config_dir):
        """@refs in CLAUDE.md are expanded."""
        from code_puppy.agents._builder import load_puppy_rules

        rules_dir = temp_project / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "developer.md").write_text("# Dev rules")
        (temp_project / "CLAUDE.md").write_text("@.claude/rules/developer.md")

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result == "# Dev rules"

    def test_no_rules_anywhere_returns_none(self, temp_project, mock_config_dir):
        """Returns None when neither AGENTS.md nor CLAUDE.md exist."""
        from code_puppy.agents._builder import load_puppy_rules

        with patch("code_puppy.agents._builder.CONFIG_DIR", str(mock_config_dir)):
            result = load_puppy_rules()

        assert result is None
