"""Skill loader - parses SKILL.md files and extracts metadata."""

import logging
from pathlib import Path
from typing import Any

import yaml

from code_puppy.plugins.skills.skill_types import SkillMetadata

logger = logging.getLogger(__name__)


class SkillLoaderError(Exception):
    """Raised when a skill cannot be loaded."""


class SkillLoader:
    """Load and parse SKILL.md files.

    This loader handles Claude Code-compatible skill files with YAML frontmatter.

    Expected SKILL.md format:
        ---
        name: skill-name
        description: What the skill does
        license: Optional license
        ---

        # Skill Body

        Instructions and documentation...
    """

    def __init__(self, skills_dir: Path) -> None:
        """Initialize loader with base skills directory.

        Args:
            skills_dir: Base directory where skills are stored.
                        Stored for future use by SkillManager.
        """
        self.skills_dir = skills_dir

    def parse_frontmatter(self, skill_md: Path) -> SkillMetadata | None:
        """Parse YAML frontmatter from SKILL.md file.

        Args:
            skill_md: Path to the SKILL.md file

        Returns:
            SkillMetadata if valid, None if parsing failed
        """
        try:
            content = skill_md.read_text(encoding="utf-8")
            yaml_data, _ = self._extract_yaml_and_body(content)

            if yaml_data is None:
                logger.warning("No YAML frontmatter found in %s", skill_md)
                return None

            name = yaml_data.get("name")
            description = yaml_data.get("description")

            if not name:
                logger.warning("Missing 'name' field in %s", skill_md)
                return None
            if not description:
                logger.warning("Missing 'description' field in %s", skill_md)
                return None

            return SkillMetadata(
                name=name,
                description=description,
                path=skill_md.parent,
                license=yaml_data.get("license"),
            )

        except yaml.YAMLError as e:
            logger.error("YAML parse error in %s: %s", skill_md, e)
            return None
        except OSError as e:
            logger.error("Failed to read %s: %s", skill_md, e)
            return None
        except ValueError as e:
            logger.warning("Invalid skill metadata in %s: %s", skill_md, e)
            return None

    def load_body(self, skill_md: Path) -> str | None:
        """Load the markdown body (excluding frontmatter).

        Args:
            skill_md: Path to the SKILL.md file

        Returns:
            Markdown body content, or None if file cannot be read
        """
        try:
            content = skill_md.read_text(encoding="utf-8")
            _, body = self._extract_yaml_and_body(content)
            return body
        except OSError as e:
            logger.error("Failed to read %s: %s", skill_md, e)
            return None

    def get_resource(self, skill_path: Path, resource: str) -> str | None:
        """Load a resource file from the skill directory.

        Args:
            skill_path: Path to the skill directory
            resource: Relative path to the resource file

        Returns:
            Resource content, or None if not found
        """
        resource_path = skill_path / resource

        # Security: Prevent path traversal using is_relative_to (Python 3.9+)
        try:
            resolved_resource = resource_path.resolve()
            resolved_skill = skill_path.resolve()
            # Check that resolved path is within skill directory
            resolved_resource.relative_to(resolved_skill)
        except (ValueError, OSError):
            logger.warning("Path traversal attempt blocked: %s", resource)
            return None

        try:
            return resolved_resource.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to read resource %s: %s", resource, e)
            return None

    def _extract_yaml_and_body(self, content: str) -> tuple[dict[str, Any] | None, str]:
        """Split content into YAML dict and body string.

        Args:
            content: Full SKILL.md content

        Returns:
            Tuple of (yaml_dict or None, body_string)
        """
        # Check for frontmatter markers
        if not content.startswith("---"):
            return None, content

        # Find the closing ---
        lines = content.split("\n")
        end_marker = -1
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_marker = i
                break

        if end_marker == -1:
            # No closing marker found
            return None, content

        # Extract YAML and body
        yaml_content = "\n".join(lines[1:end_marker])
        body = "\n".join(lines[end_marker + 1 :]).strip()

        try:
            yaml_data = yaml.safe_load(yaml_content)
            if not isinstance(yaml_data, dict):
                return None, content
            return yaml_data, body
        except yaml.YAMLError:
            return None, content
