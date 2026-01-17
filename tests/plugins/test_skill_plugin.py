"""Tests for the skills plugin registration and callbacks."""

from pathlib import Path
from textwrap import dedent
from typing import Any
from unittest.mock import patch

import pytest


class TestPluginImports:
    """Tests for plugin module imports."""

    def test_plugin_imports(self) -> None:
        """Test that plugin module can be imported."""
        # This will trigger callback registration
        from code_puppy.plugins.skills import register_callbacks  # noqa: F401

        # If we get here, import succeeded
        assert True

    def test_skill_manager_import(self) -> None:
        """Test that SkillManager can be imported."""
        from code_puppy.plugins.skills.skill_manager import SkillManager

        assert SkillManager is not None


class TestStartupCallback:
    """Tests for startup callback."""

    @pytest.fixture
    def skills_dir(self, tmp_path: Path) -> Path:
        """Create a temporary skills directory."""
        skills = tmp_path / "skills"
        skills.mkdir()
        return skills

    @pytest.fixture
    def populated_skills_dir(self, skills_dir: Path) -> Path:
        """Create skills directory with a test skill."""
        skill = skills_dir / "test-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            dedent("""
            ---
            name: test-skill
            description: A test skill for testing
            ---
            # Test
        """).strip(),
            encoding="utf-8",
        )
        return skills_dir

    @pytest.mark.asyncio
    async def test_startup_with_skills(self, populated_skills_dir: Path) -> None:
        """Test startup emits info when skills exist."""
        from code_puppy.plugins.skills.register_callbacks import _on_startup
        from code_puppy.plugins.skills.skill_manager import SkillManager

        with (
            patch(
                "code_puppy.plugins.skills.register_callbacks._skill_manager",
                SkillManager(populated_skills_dir),
            ),
            patch(
                "code_puppy.plugins.skills.register_callbacks.emit_info"
            ) as mock_emit,
        ):
            await _on_startup()

        mock_emit.assert_called_once()
        assert "1 skill" in mock_emit.call_args[0][0]

    @pytest.mark.asyncio
    async def test_startup_no_skills(self, skills_dir: Path) -> None:
        """Test startup is silent with no skills."""
        from code_puppy.plugins.skills.register_callbacks import _on_startup
        from code_puppy.plugins.skills.skill_manager import SkillManager

        with (
            patch(
                "code_puppy.plugins.skills.register_callbacks._skill_manager",
                SkillManager(skills_dir),
            ),
            patch(
                "code_puppy.plugins.skills.register_callbacks.emit_info"
            ) as mock_emit,
        ):
            await _on_startup()

        mock_emit.assert_not_called()


class TestSkillHelp:
    """Tests for the help callback."""

    def test_skill_help_entries(self) -> None:
        """Test help callback returns correct entries."""
        from code_puppy.plugins.skills.register_callbacks import _skill_help

        entries = _skill_help()

        assert isinstance(entries, list)
        assert len(entries) >= 5  # At least 5 help entries

        # Check that main entries exist
        names = [entry[0] for entry in entries]
        assert "skill" in names
        assert "skill list" in names
        assert "skill info <name>" in names


class TestSkillCommands:
    """Tests for command handling."""

    @pytest.fixture
    def skills_dir(self, tmp_path: Path) -> Path:
        """Create a temporary skills directory."""
        skills = tmp_path / "skills"
        skills.mkdir()
        return skills

    @pytest.fixture
    def populated_skills_dir(self, skills_dir: Path) -> Path:
        """Create skills directory with a test skill."""
        skill = skills_dir / "test-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            dedent("""
            ---
            name: test-skill
            description: A test skill for testing
            license: MIT
            ---

            # Test Skill

            This is the body.
        """).strip(),
            encoding="utf-8",
        )
        return skills_dir

    @pytest.fixture
    def mock_manager(self, populated_skills_dir: Path) -> Any:
        """Create a mock SkillManager using temp directory."""
        from code_puppy.plugins.skills.skill_manager import SkillManager

        return SkillManager(populated_skills_dir)

    def test_handle_skill_list(self, mock_manager: Any) -> None:
        """Test /skill list command."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_list

        result = _cmd_list(mock_manager)

        assert "Installed Skills" in result
        assert "test-skill" in result

    def test_handle_skill_info(self, mock_manager: Any) -> None:
        """Test /skill info command."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_info

        result = _cmd_info(mock_manager, "test-skill")

        assert "test-skill" in result
        assert "Description" in result
        assert "A test skill for testing" in result

    def test_handle_skill_info_not_found(self, mock_manager: Any) -> None:
        """Test /skill info for nonexistent skill."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_info

        result = _cmd_info(mock_manager, "nonexistent")

        assert "not found" in result

    def test_handle_skill_show(self, mock_manager: Any) -> None:
        """Test /skill show command."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_show

        result = _cmd_show(mock_manager, "test-skill")

        assert "SKILL.md" in result
        assert "# Test Skill" in result
        assert "This is the body" in result

    def test_handle_skill_show_not_found(self, mock_manager: Any) -> None:
        """Test /skill show for nonexistent skill."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_show

        result = _cmd_show(mock_manager, "nonexistent")

        assert "not found" in result

    def test_handle_skill_refresh(self, mock_manager: Any) -> None:
        """Test /skill refresh command."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_refresh

        result = _cmd_refresh(mock_manager)

        assert "Rescanned" in result
        assert "1 skill" in result

    def test_handle_skill_help(self) -> None:
        """Test /skill (no subcommand) shows help."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_help

        result = _cmd_help()

        assert "Skills Plugin" in result
        assert "/skill list" in result
        assert "/skill add" in result

    def test_handle_unknown_command_returns_none(self) -> None:
        """Test handling of non-skill commands (returns None)."""
        from code_puppy.plugins.skills.register_callbacks import _handle_skill_command

        # Should return None for non-skill commands
        result = _handle_skill_command("other command", "other")
        assert result is None

    def test_handle_skill_command_routes_to_list(self, mock_manager: Any) -> None:
        """Test /skill list routes correctly."""
        from code_puppy.plugins.skills.register_callbacks import _handle_skill_command

        with patch(
            "code_puppy.plugins.skills.register_callbacks._get_manager",
            return_value=mock_manager,
        ):
            result = _handle_skill_command("skill list", "skill")

        assert result is not None
        assert "Installed Skills" in result or "No skills" in result

    def test_handle_skill_command_default_to_help(self) -> None:
        """Test /skill with no subcommand shows help."""
        from code_puppy.plugins.skills.register_callbacks import _handle_skill_command

        result = _handle_skill_command("skill", "skill")

        assert result is not None
        assert "Skills Plugin" in result


class TestPromptInjection:
    """Tests for prompt injection callback."""

    @pytest.fixture
    def skills_dir(self, tmp_path: Path) -> Path:
        """Create a temporary skills directory."""
        skills = tmp_path / "skills"
        skills.mkdir()
        return skills

    @pytest.fixture
    def populated_skills_dir(self, skills_dir: Path) -> Path:
        """Create skills directory with test skills."""
        skill = skills_dir / "test-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            dedent("""
            ---
            name: test-skill
            description: A test skill
            ---
            # Test
        """).strip(),
            encoding="utf-8",
        )
        return skills_dir

    def test_prompt_injection_with_skills(self, populated_skills_dir: Path) -> None:
        """Test catalog is injected when skills exist."""
        from code_puppy.plugins.skills.register_callbacks import _inject_skill_catalog
        from code_puppy.plugins.skills.skill_manager import SkillManager

        # Patch the global manager
        with patch(
            "code_puppy.plugins.skills.register_callbacks._skill_manager",
            SkillManager(populated_skills_dir),
        ):
            result = _inject_skill_catalog()

        assert result is not None
        assert "Available Skills" in result
        assert "test-skill" in result

    def test_prompt_injection_no_skills(self, skills_dir: Path) -> None:
        """Test no injection when no skills."""
        from code_puppy.plugins.skills.register_callbacks import _inject_skill_catalog
        from code_puppy.plugins.skills.skill_manager import SkillManager

        # Patch with empty skills directory
        with patch(
            "code_puppy.plugins.skills.register_callbacks._skill_manager",
            SkillManager(skills_dir),
        ):
            result = _inject_skill_catalog()

        assert result is None


class TestAddRemoveCommands:
    """Tests for add and remove command handlers."""

    @pytest.fixture
    def skills_dir(self, tmp_path: Path) -> Path:
        """Create a temporary skills directory."""
        skills = tmp_path / "skills"
        skills.mkdir()
        return skills

    @pytest.fixture
    def source_skill(self, tmp_path: Path) -> Path:
        """Create a source skill to install."""
        source = tmp_path / "source-skill"
        source.mkdir()
        (source / "SKILL.md").write_text(
            dedent("""
            ---
            name: source-skill
            description: A skill to install
            ---
            # Source
        """).strip(),
            encoding="utf-8",
        )
        return source

    @pytest.fixture
    def manager(self, skills_dir: Path) -> Any:
        """Create a SkillManager with empty skills directory."""
        from code_puppy.plugins.skills.skill_manager import SkillManager

        return SkillManager(skills_dir)

    def test_cmd_add_success(self, manager: Any, source_skill: Path) -> None:
        """Test successful skill installation."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_add

        result = _cmd_add(manager, str(source_skill))

        assert "✅" in result
        assert "Installed" in result

    def test_cmd_add_not_found(self, manager: Any, tmp_path: Path) -> None:
        """Test add with nonexistent path."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_add

        result = _cmd_add(manager, str(tmp_path / "nonexistent"))

        assert "❌" in result
        assert "does not exist" in result

    def test_cmd_remove_success(self, manager: Any, source_skill: Path) -> None:
        """Test successful skill removal."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_add, _cmd_remove

        # Install first
        _cmd_add(manager, str(source_skill))

        # Remove
        result = _cmd_remove(manager, "source-skill")

        assert "✅" in result
        assert "Removed" in result

    def test_cmd_remove_not_found(self, manager: Any) -> None:
        """Test remove nonexistent skill."""
        from code_puppy.plugins.skills.register_callbacks import _cmd_remove

        result = _cmd_remove(manager, "nonexistent")

        assert "❌" in result
        assert "not found" in result
