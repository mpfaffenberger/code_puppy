"""Tests for skill_types module."""

from pathlib import Path

import pytest

from code_puppy.plugins.skills.skill_types import SkillMetadata


class TestSkillMetadata:
    """Tests for SkillMetadata dataclass."""

    def test_skill_metadata_creation(self) -> None:
        """Test creating a SkillMetadata with required fields."""
        metadata = SkillMetadata(
            name="test-skill",
            description="A test skill for testing",
            path=Path("/tmp/skills/test-skill"),
        )
        assert metadata.name == "test-skill"
        assert metadata.description == "A test skill for testing"
        assert metadata.path == Path("/tmp/skills/test-skill")
        assert metadata.license is None

    def test_skill_metadata_with_license(self) -> None:
        """Test creating a SkillMetadata with optional license field."""
        metadata = SkillMetadata(
            name="licensed-skill",
            description="A skill with a license",
            path=Path("/tmp/skills/licensed"),
            license="MIT",
        )
        assert metadata.license == "MIT"

    def test_skill_metadata_path_type(self) -> None:
        """Test that path is always a Path object."""
        # String path should be converted to Path
        metadata = SkillMetadata(
            name="path-test",
            description="Testing path conversion",
            path="/tmp/skills/path-test",  # type: ignore[arg-type]
        )
        assert isinstance(metadata.path, Path)
        assert metadata.path == Path("/tmp/skills/path-test")

    def test_skill_metadata_empty_name_raises(self) -> None:
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            SkillMetadata(
                name="",
                description="Valid description",
                path=Path("/tmp"),
            )

    def test_skill_metadata_empty_description_raises(self) -> None:
        """Test that empty description raises ValueError."""
        with pytest.raises(ValueError, match="description cannot be empty"):
            SkillMetadata(
                name="valid-name",
                description="",
                path=Path("/tmp"),
            )

    def test_skill_metadata_whitespace_name_raises(self) -> None:
        """Test that whitespace-only name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            SkillMetadata(
                name="   ",
                description="Valid description",
                path=Path("/tmp"),
            )

    def test_skill_metadata_whitespace_description_raises(self) -> None:
        """Test that whitespace-only description raises ValueError."""
        with pytest.raises(ValueError, match="description cannot be empty"):
            SkillMetadata(
                name="valid-name",
                description="   \t\n  ",
                path=Path("/tmp"),
            )
