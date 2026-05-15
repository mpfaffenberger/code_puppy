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
