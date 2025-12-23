"""Skill manager - catalog management and skill operations."""

import logging
import shutil
from pathlib import Path
from typing import Any

from code_puppy.plugins.skills.skill_loader import SkillLoader
from code_puppy.plugins.skills.skill_types import SkillMetadata

logger = logging.getLogger(__name__)

# Default skills directory
DEFAULT_SKILLS_DIR = Path.home() / ".code_puppy" / "skills"

# Maximum description length for catalog display
MAX_DESCRIPTION_LENGTH = 80


class SkillManager:
    """Manage skill discovery, catalog, and operations.

    This manager handles:
    - Scanning and loading skills from disk
    - Providing a catalog for prompt injection
    - CRUD operations for skill management
    """

    def __init__(self, skills_dir: Path | None = None) -> None:
        """Initialize with skills directory.

        Args:
            skills_dir: Directory where skills are stored.
                        Defaults to ~/.code_puppy/skills/
        """
        if skills_dir is None:
            skills_dir = DEFAULT_SKILLS_DIR
        self.skills_dir = skills_dir
        self.loader = SkillLoader(skills_dir)
        self._catalog: dict[str, SkillMetadata] = {}
        self._refresh_catalog()

    def _refresh_catalog(self) -> None:
        """Scan skills directory and rebuild catalog."""
        self._catalog.clear()

        if not self.skills_dir.exists():
            logger.debug("Skills directory does not exist: %s", self.skills_dir)
            return

        if not self.skills_dir.is_dir():
            logger.warning("Skills path is not a directory: %s", self.skills_dir)
            return

        for item in self.skills_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith(".") or item.name.startswith("_"):
                continue

            skill_md = item / "SKILL.md"
            if not skill_md.exists():
                logger.debug("No SKILL.md in %s, skipping", item.name)
                continue

            metadata = self.loader.parse_frontmatter(skill_md)
            if metadata is not None:
                self._catalog[metadata.name] = metadata
                logger.debug("Loaded skill: %s", metadata.name)

    def refresh(self) -> int:
        """Rescan skills directory and rebuild catalog.

        Returns:
            Number of skills found after refresh
        """
        self._refresh_catalog()
        return len(self._catalog)

    def get_skill_catalog(self) -> str:
        """Generate catalog string for prompt injection.

        Returns:
            Formatted string with skill names and descriptions,
            or empty string if no skills are loaded.
        """
        if not self._catalog:
            return ""

        lines: list[str] = []
        for name in sorted(self._catalog.keys()):
            skill = self._catalog[name]
            description = skill.description
            if len(description) > MAX_DESCRIPTION_LENGTH:
                description = description[: MAX_DESCRIPTION_LENGTH - 3] + "..."
            lines.append(f"- **{name}**: {description}")

        return "\n".join(lines)

    def get_skill_count(self) -> int:
        """Return number of loaded skills."""
        return len(self._catalog)

    def get_skill(self, name: str) -> SkillMetadata | None:
        """Get skill metadata by name.

        Args:
            name: Skill identifier

        Returns:
            SkillMetadata if found, None otherwise
        """
        return self._catalog.get(name)

    def load_skill_body(self, skill_name: str) -> str | None:
        """Load full SKILL.md body by name.

        Args:
            skill_name: Skill identifier

        Returns:
            Markdown body content, or None if skill not found
        """
        skill = self.get_skill(skill_name)
        if skill is None:
            return None

        skill_md = skill.path / "SKILL.md"
        return self.loader.load_body(skill_md)

    def get_resource(self, skill_name: str, resource_path: str) -> str | None:
        """Load a resource from a skill.

        Args:
            skill_name: Skill identifier
            resource_path: Relative path to resource within skill directory

        Returns:
            Resource content, or None if not found
        """
        skill = self.get_skill(skill_name)
        if skill is None:
            return None

        return self.loader.get_resource(skill.path, resource_path)

    def list_skills(self) -> list[SkillMetadata]:
        """Return list of all skills sorted by name."""
        return [self._catalog[name] for name in sorted(self._catalog.keys())]

    def add_skill(self, source_path: Path | str) -> tuple[bool, str]:
        """Copy skill from source path to skills directory.

        Args:
            source_path: Path to skill directory to install

        Returns:
            Tuple of (success, message)
        """
        source_path = Path(source_path)

        if not source_path.exists():
            return False, f"Source path does not exist: {source_path}"

        if not source_path.is_dir():
            return False, f"Source path is not a directory: {source_path}"

        skill_md = source_path / "SKILL.md"
        if not skill_md.exists():
            return False, f"No SKILL.md found in {source_path}"

        # Parse to validate and get the name
        metadata = self.loader.parse_frontmatter(skill_md)
        if metadata is None:
            return False, f"Invalid SKILL.md in {source_path}"

        # Create skills directory if needed
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # Check if skill already exists
        dest_path = self.skills_dir / metadata.name
        if dest_path.exists():
            return False, f"Skill '{metadata.name}' already exists"

        try:
            shutil.copytree(source_path, dest_path)
        except OSError as e:
            return False, f"Failed to copy skill: {e}"

        # Refresh to pick up new skill
        self._refresh_catalog()
        return True, f"Installed skill '{metadata.name}'"

    def remove_skill(self, skill_name: str) -> tuple[bool, str]:
        """Remove a skill by name.

        Args:
            skill_name: Skill identifier

        Returns:
            Tuple of (success, message)
        """
        skill = self.get_skill(skill_name)
        if skill is None:
            return False, f"Skill '{skill_name}' not found"

        # Safety: Verify path is within skills directory
        try:
            skill.path.resolve().relative_to(self.skills_dir.resolve())
        except ValueError:
            logger.error("Skill path outside skills directory: %s", skill.path)
            return False, f"Invalid skill path for '{skill_name}'"

        try:
            shutil.rmtree(skill.path)
        except OSError as e:
            return False, f"Failed to remove skill: {e}"

        # Refresh catalog
        self._refresh_catalog()
        return True, f"Removed skill '{skill_name}'"

    def get_skill_info(self, skill_name: str) -> dict[str, Any] | None:
        """Get detailed information about a skill.

        Args:
            skill_name: Skill identifier

        Returns:
            Dict with skill details, or None if not found
        """
        skill = self.get_skill(skill_name)
        if skill is None:
            return None

        return {
            "name": skill.name,
            "description": skill.description,
            "path": str(skill.path),
            "license": skill.license,
        }
