"""Tests for skill_loader module."""

from pathlib import Path
from textwrap import dedent

import pytest

from code_puppy.plugins.skills.skill_loader import SkillLoader


class TestSkillLoader:
    """Tests for SkillLoader class."""

    @pytest.fixture
    def skills_dir(self, tmp_path: Path) -> Path:
        """Create a temporary skills directory."""
        skills = tmp_path / "skills"
        skills.mkdir()
        return skills

    @pytest.fixture
    def valid_skill(self, skills_dir: Path) -> Path:
        """Create a valid skill with SKILL.md."""
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            dedent("""
            ---
            name: test-skill
            description: A test skill for testing purposes
            license: MIT
            ---
            
            # Test Skill
            
            This is the body of the skill.
            
            ## Usage
            
            Instructions here.
        """).strip(),
            encoding="utf-8",
        )
        return skill_dir

    @pytest.fixture
    def skill_with_resources(self, skills_dir: Path) -> Path:
        """Create a skill with resources directory."""
        skill_dir = skills_dir / "resource-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            dedent("""
            ---
            name: resource-skill
            description: A skill with resources
            ---
            
            # Resource Skill
        """).strip(),
            encoding="utf-8",
        )

        # Create resources
        resources = skill_dir / "resources"
        resources.mkdir()
        (resources / "example.md").write_text("# Example Resource\n", encoding="utf-8")
        return skill_dir

    @pytest.fixture
    def loader(self, skills_dir: Path) -> SkillLoader:
        """Create a SkillLoader instance."""
        return SkillLoader(skills_dir)

    def test_parse_valid_frontmatter(
        self, loader: SkillLoader, valid_skill: Path
    ) -> None:
        """Test parsing a valid SKILL.md with name and description."""
        skill_md = valid_skill / "SKILL.md"
        metadata = loader.parse_frontmatter(skill_md)

        assert metadata is not None
        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill for testing purposes"
        assert metadata.license == "MIT"
        assert metadata.path == valid_skill

    def test_parse_missing_frontmatter(
        self, loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Test handling of file without --- markers."""
        skill_dir = skills_dir / "no-frontmatter"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Just Markdown\n\nNo frontmatter here.", encoding="utf-8")

        metadata = loader.parse_frontmatter(skill_md)
        assert metadata is None

    def test_parse_missing_name(self, loader: SkillLoader, skills_dir: Path) -> None:
        """Test handling of SKILL.md without name field."""
        skill_dir = skills_dir / "no-name"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            dedent("""
            ---
            description: Has description but no name
            ---
            
            # Missing Name
        """).strip(),
            encoding="utf-8",
        )

        metadata = loader.parse_frontmatter(skill_md)
        assert metadata is None

    def test_parse_missing_description(
        self, loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Test handling of SKILL.md without description field."""
        skill_dir = skills_dir / "no-desc"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            dedent("""
            ---
            name: no-description-skill
            ---
            
            # Missing Description
        """).strip(),
            encoding="utf-8",
        )

        metadata = loader.parse_frontmatter(skill_md)
        assert metadata is None

    def test_load_body(self, loader: SkillLoader, valid_skill: Path) -> None:
        """Test extracting markdown body after frontmatter."""
        skill_md = valid_skill / "SKILL.md"
        body = loader.load_body(skill_md)

        assert body is not None
        assert "# Test Skill" in body
        assert "This is the body of the skill." in body
        assert "---" not in body  # Frontmatter should be excluded
        assert "name:" not in body  # YAML should be excluded

    def test_get_resource_exists(
        self, loader: SkillLoader, skill_with_resources: Path
    ) -> None:
        """Test loading an existing resource file."""
        content = loader.get_resource(skill_with_resources, "resources/example.md")

        assert content is not None
        assert "# Example Resource" in content

    def test_get_resource_not_found(
        self, loader: SkillLoader, valid_skill: Path
    ) -> None:
        """Test handling of missing resource file."""
        content = loader.get_resource(valid_skill, "nonexistent.md")
        assert content is None

    def test_get_resource_path_traversal_blocked(
        self, loader: SkillLoader, valid_skill: Path
    ) -> None:
        """Test that path traversal attempts are blocked."""
        content = loader.get_resource(valid_skill, "../../../etc/passwd")
        assert content is None

    def test_parse_invalid_yaml(self, loader: SkillLoader, skills_dir: Path) -> None:
        """Test handling of invalid YAML in frontmatter."""
        skill_dir = skills_dir / "bad-yaml"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            dedent("""
            ---
            name: [invalid yaml
            description: unclosed bracket
            ---
            
            # Bad YAML
        """).strip(),
            encoding="utf-8",
        )

        metadata = loader.parse_frontmatter(skill_md)
        assert metadata is None

    def test_parse_nonexistent_file(self, loader: SkillLoader) -> None:
        """Test handling of nonexistent file."""
        metadata = loader.parse_frontmatter(Path("/nonexistent/SKILL.md"))
        assert metadata is None

    def test_empty_frontmatter(self, loader: SkillLoader, skills_dir: Path) -> None:
        """Test handling of empty frontmatter markers."""
        skill_dir = skills_dir / "empty-fm"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\n---\n# Body", encoding="utf-8")

        metadata = loader.parse_frontmatter(skill_md)
        assert metadata is None

    def test_frontmatter_is_list_not_dict(
        self, loader: SkillLoader, skills_dir: Path
    ) -> None:
        """Test handling of YAML frontmatter that's a list instead of dict."""
        skill_dir = skills_dir / "list-yaml"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            dedent("""
            ---
            - item1
            - item2
            ---
            
            # Body
        """).strip(),
            encoding="utf-8",
        )

        metadata = loader.parse_frontmatter(skill_md)
        assert metadata is None

    def test_load_body_nonexistent_file(self, loader: SkillLoader) -> None:
        """Test load_body with nonexistent file."""
        body = loader.load_body(Path("/nonexistent/SKILL.md"))
        assert body is None


class TestExtractYamlAndBody:
    """Tests for the _extract_yaml_and_body method."""

    @pytest.fixture
    def loader(self, tmp_path: Path) -> SkillLoader:
        """Create a SkillLoader instance."""
        return SkillLoader(tmp_path)

    def test_no_frontmatter(self, loader: SkillLoader) -> None:
        """Test content without frontmatter markers."""
        content = "# Just Markdown\n\nNo frontmatter."
        yaml_data, body = loader._extract_yaml_and_body(content)

        assert yaml_data is None
        assert body == content

    def test_unclosed_frontmatter(self, loader: SkillLoader) -> None:
        """Test content with only opening --- marker."""
        content = "---\nname: test\n# No closing marker"
        yaml_data, body = loader._extract_yaml_and_body(content)

        assert yaml_data is None
        assert body == content

    def test_valid_frontmatter(self, loader: SkillLoader) -> None:
        """Test valid frontmatter extraction."""
        content = dedent("""
            ---
            name: my-skill
            description: Test
            ---
            
            # Body here
        """).strip()

        yaml_data, body = loader._extract_yaml_and_body(content)

        assert yaml_data is not None
        assert yaml_data["name"] == "my-skill"
        assert yaml_data["description"] == "Test"
        assert "# Body here" in body
