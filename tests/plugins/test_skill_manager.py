"""Tests for skill_manager module."""

from pathlib import Path
from textwrap import dedent

import pytest

from code_puppy.plugins.skills.skill_manager import SkillManager


class TestSkillManager:
    """Tests for SkillManager class."""

    @pytest.fixture
    def skills_dir(self, tmp_path: Path) -> Path:
        """Create a temporary skills directory."""
        skills = tmp_path / "skills"
        skills.mkdir()
        return skills

    @pytest.fixture
    def manager(self, skills_dir: Path) -> SkillManager:
        """Create a SkillManager with empty skills directory."""
        return SkillManager(skills_dir)

    @pytest.fixture
    def populated_skills_dir(self, skills_dir: Path) -> Path:
        """Create skills directory with test skills."""
        # Skill 1: pdf-tools
        pdf = skills_dir / "pdf-tools"
        pdf.mkdir()
        (pdf / "SKILL.md").write_text(
            dedent("""
            ---
            name: pdf-tools
            description: PDF manipulation toolkit for extracting text and creating PDFs
            license: MIT
            ---
            
            # PDF Tools
            
            Instructions for PDF operations.
        """).strip(),
            encoding="utf-8",
        )

        # Skill 2: docx-helper
        docx = skills_dir / "docx-helper"
        docx.mkdir()
        (docx / "SKILL.md").write_text(
            dedent("""
            ---
            name: docx-helper
            description: Word document creation and editing
            ---
            
            # DOCX Helper
            
            Instructions for Word docs.
        """).strip(),
            encoding="utf-8",
        )

        # Resources in pdf skill
        resources = pdf / "resources"
        resources.mkdir()
        (resources / "example.md").write_text("# Example\n", encoding="utf-8")

        return skills_dir

    @pytest.fixture
    def populated_manager(self, populated_skills_dir: Path) -> SkillManager:
        """Create a SkillManager with test skills."""
        return SkillManager(populated_skills_dir)

    def test_manager_init_creates_catalog(
        self, populated_manager: SkillManager
    ) -> None:
        """Test that manager scans skills on init."""
        assert populated_manager.get_skill_count() == 2
        assert populated_manager.get_skill("pdf-tools") is not None
        assert populated_manager.get_skill("docx-helper") is not None

    def test_manager_empty_directory(self, manager: SkillManager) -> None:
        """Test manager with no skills installed."""
        assert manager.get_skill_count() == 0
        assert manager.get_skill_catalog() == ""
        assert manager.list_skills() == []

    def test_manager_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test manager with nonexistent skills directory."""
        manager = SkillManager(tmp_path / "nonexistent")
        assert manager.get_skill_count() == 0

    def test_get_skill_catalog_format(self, populated_manager: SkillManager) -> None:
        """Test catalog string format for prompt injection."""
        catalog = populated_manager.get_skill_catalog()

        # Should be sorted alphabetically
        assert catalog.startswith("- **docx-helper**")
        assert "- **pdf-tools**" in catalog

        # Should contain descriptions
        assert "Word document" in catalog
        assert "PDF manipulation" in catalog

    def test_get_skill_catalog_truncates_long_descriptions(
        self, skills_dir: Path
    ) -> None:
        """Test that long descriptions are truncated."""
        long_desc = "A" * 100  # Longer than MAX_DESCRIPTION_LENGTH (80)

        skill = skills_dir / "long-desc"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            dedent(f"""
            ---
            name: long-desc
            description: {long_desc}
            ---
            
            # Long Description Skill
        """).strip(),
            encoding="utf-8",
        )

        manager = SkillManager(skills_dir)
        catalog = manager.get_skill_catalog()

        assert "..." in catalog
        assert len(catalog.split("\n")[0]) < 100 + len("- **long-desc**: ")

    def test_get_skill_by_name(self, populated_manager: SkillManager) -> None:
        """Test retrieving skill metadata by name."""
        skill = populated_manager.get_skill("pdf-tools")

        assert skill is not None
        assert skill.name == "pdf-tools"
        assert "PDF manipulation" in skill.description
        assert skill.license == "MIT"

    def test_get_skill_not_found(self, populated_manager: SkillManager) -> None:
        """Test handling of unknown skill name."""
        assert populated_manager.get_skill("nonexistent") is None

    def test_load_skill_body(self, populated_manager: SkillManager) -> None:
        """Test loading full SKILL.md content."""
        body = populated_manager.load_skill_body("pdf-tools")

        assert body is not None
        assert "# PDF Tools" in body
        assert "Instructions for PDF operations" in body

    def test_load_skill_body_not_found(self, populated_manager: SkillManager) -> None:
        """Test loading body for nonexistent skill."""
        assert populated_manager.load_skill_body("nonexistent") is None

    def test_get_resource(self, populated_manager: SkillManager) -> None:
        """Test loading a resource from a skill."""
        content = populated_manager.get_resource("pdf-tools", "resources/example.md")

        assert content is not None
        assert "# Example" in content

    def test_get_resource_skill_not_found(
        self, populated_manager: SkillManager
    ) -> None:
        """Test getting resource from nonexistent skill."""
        assert populated_manager.get_resource("nonexistent", "file.md") is None

    def test_list_skills(self, populated_manager: SkillManager) -> None:
        """Test listing all skills."""
        skills = populated_manager.list_skills()

        assert len(skills) == 2
        # Should be sorted alphabetically
        assert skills[0].name == "docx-helper"
        assert skills[1].name == "pdf-tools"

    def test_get_skill_info(self, populated_manager: SkillManager) -> None:
        """Test getting detailed skill info."""
        info = populated_manager.get_skill_info("pdf-tools")

        assert info is not None
        assert info["name"] == "pdf-tools"
        assert (
            info["description"]
            == "PDF manipulation toolkit for extracting text and creating PDFs"
        )
        assert info["license"] == "MIT"
        assert "path" in info

    def test_get_skill_info_not_found(self, populated_manager: SkillManager) -> None:
        """Test getting info for nonexistent skill."""
        assert populated_manager.get_skill_info("nonexistent") is None

    def test_refresh_catalog(
        self, populated_manager: SkillManager, populated_skills_dir: Path
    ) -> None:
        """Test rescanning skills directory."""
        # Add a new skill after manager creation
        new_skill = populated_skills_dir / "new-skill"
        new_skill.mkdir()
        (new_skill / "SKILL.md").write_text(
            dedent("""
            ---
            name: new-skill
            description: A newly added skill
            ---
            
            # New Skill
        """).strip(),
            encoding="utf-8",
        )

        # Should not be visible yet
        assert populated_manager.get_skill("new-skill") is None

        # Refresh and verify
        count = populated_manager.refresh()
        assert count == 3
        assert populated_manager.get_skill("new-skill") is not None


class TestSkillManagerAddRemove:
    """Tests for add_skill and remove_skill operations."""

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
            description: A skill to be installed
            ---
            
            # Source Skill
        """).strip(),
            encoding="utf-8",
        )
        return source

    @pytest.fixture
    def manager(self, skills_dir: Path) -> SkillManager:
        """Create a SkillManager with empty skills directory."""
        return SkillManager(skills_dir)

    def test_add_skill_from_directory(
        self, manager: SkillManager, source_skill: Path
    ) -> None:
        """Test installing skill from a path."""
        success, message = manager.add_skill(source_skill)

        assert success is True
        assert "Installed skill 'source-skill'" in message
        assert manager.get_skill("source-skill") is not None
        assert manager.get_skill_count() == 1

    def test_add_skill_nonexistent_source(
        self, manager: SkillManager, tmp_path: Path
    ) -> None:
        """Test adding from nonexistent path."""
        success, message = manager.add_skill(tmp_path / "nonexistent")

        assert success is False
        assert "does not exist" in message

    def test_add_skill_not_a_directory(
        self, manager: SkillManager, tmp_path: Path
    ) -> None:
        """Test adding a file instead of directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("not a skill", encoding="utf-8")

        success, message = manager.add_skill(file_path)

        assert success is False
        assert "not a directory" in message

    def test_add_skill_no_skill_md(self, manager: SkillManager, tmp_path: Path) -> None:
        """Test adding directory without SKILL.md."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        success, message = manager.add_skill(empty_dir)

        assert success is False
        assert "No SKILL.md" in message

    def test_add_skill_already_exists(
        self, manager: SkillManager, source_skill: Path
    ) -> None:
        """Test adding skill that already exists."""
        # Install first time
        manager.add_skill(source_skill)

        # Try to install again
        success, message = manager.add_skill(source_skill)

        assert success is False
        assert "already exists" in message

    def test_remove_skill(self, manager: SkillManager, source_skill: Path) -> None:
        """Test removing an installed skill."""
        # Install first
        manager.add_skill(source_skill)
        assert manager.get_skill_count() == 1

        # Remove
        success, message = manager.remove_skill("source-skill")

        assert success is True
        assert "Removed skill" in message
        assert manager.get_skill("source-skill") is None
        assert manager.get_skill_count() == 0

    def test_remove_skill_not_found(self, manager: SkillManager) -> None:
        """Test removing nonexistent skill."""
        success, message = manager.remove_skill("nonexistent")

        assert success is False
        assert "not found" in message
