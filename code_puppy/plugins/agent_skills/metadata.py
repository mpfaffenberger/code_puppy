"""Skill metadata parsing - extracts info from SKILL.md frontmatter.

Includes size validation before reading and content capping for
model-context injection.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from code_puppy.plugins.agent_skills.discovery import (
    MAX_SKILL_MD_BYTES,
    cap_skill_content,
)

logger = logging.getLogger(__name__)

# Regex pattern to match YAML frontmatter between --- delimiters
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Regex patterns for parsing simple key-value pairs from YAML-like frontmatter
KEY_VALUE_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", re.MULTILINE)
LIST_PATTERN = re.compile(r"^\s+-\s+(.+)$", re.MULTILINE)


@dataclass
class SkillMetadata:
    """Parsed skill metadata from SKILL.md frontmatter."""

    name: str
    description: str
    path: Path
    version: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    source: Optional[str] = None
    trust: Optional[str] = None
    skill_md_hash: Optional[str] = None
    skill_md_size: Optional[int] = None


def _unquote(value: str) -> str:
    """Remove quotes from a YAML string value if present."""
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def parse_yaml_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from SKILL.md content.

    Frontmatter is between --- delimiters at the start of file.
    Uses simple regex parsing to avoid heavy yaml dependency.

    Args:
        content: The full content of the SKILL.md file.

    Returns:
        Dictionary containing parsed frontmatter key-value pairs.
        Returns empty dict if no frontmatter found or parsing fails.
    """
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        logger.debug("No frontmatter found in content")
        return {}

    frontmatter = match.group(1)
    result: dict = {}
    current_key: Optional[str] = None
    current_list: List[str] = []

    for line in frontmatter.split("\n"):
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Check if this is a list item
        list_match = LIST_PATTERN.match(line)
        if list_match and current_key:
            current_list.append(_unquote(list_match.group(1)))
            continue

        # Check if this is a key-value pair
        kv_match = KEY_VALUE_PATTERN.match(line)
        if kv_match:
            # Save any accumulated list items from previous key
            if current_key and current_list:
                result[current_key] = current_list
                current_list = []

            key, value = kv_match.groups()
            key = key.strip()
            value = value.strip()

            # If value is empty, this might be a list start
            if not value:
                current_key = key
                result[key] = []  # Initialize as empty list
            else:
                result[key] = _unquote(value)
                current_key = None

    # Handle case where list items were at the end
    if current_key and current_list:
        result[current_key] = current_list

    return result


def parse_skill_metadata(skill_path: Path) -> Optional[SkillMetadata]:
    """Parse metadata from a skill's SKILL.md file.

    Args:
        skill_path: Path to the skill directory (not the SKILL.md file)

    Returns:
        SkillMetadata if successful, None if parsing fails.
    """
    if not skill_path.exists():
        logger.warning(f"Skill path does not exist: {skill_path}")
        return None

    skill_md_path = skill_path / "SKILL.md"
    if not skill_md_path.exists():
        logger.debug(f"SKILL.md not found in skill directory: {skill_path}")
        return None

    # Validate size before reading
    try:
        file_size = skill_md_path.stat().st_size
        if file_size > MAX_SKILL_MD_BYTES:
            logger.warning(
                "SKILL.md at %s is too large (%d bytes, max %d), skipping",
                skill_md_path,
                file_size,
                MAX_SKILL_MD_BYTES,
            )
            return None
    except OSError as e:
        logger.error("Failed to stat SKILL.md at %s: %s", skill_md_path, e)
        return None

    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to read SKILL.md at %s: %s", skill_md_path, e)
        return None

    # Compute hash for trust/source tracking
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    frontmatter = parse_yaml_frontmatter(content)
    if not frontmatter:
        logger.debug(f"No valid frontmatter found in {skill_md_path}")
        return None

    # Required fields
    name = frontmatter.get("name")
    if not name:
        logger.debug(
            f"'name' is required in frontmatter but not found in {skill_md_path}"
        )
        return None

    description = frontmatter.get("description")
    if not description:
        logger.debug(
            f"'description' is required in frontmatter but not found in {skill_md_path}"
        )
        return None

    # Handle tags - could be a list or a comma-separated string
    tags: List[str] = []
    raw_tags = frontmatter.get("tags", [])
    if isinstance(raw_tags, list):
        tags = raw_tags
    elif isinstance(raw_tags, str):
        tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]

    # Classify source/trust
    source = _classify_skill_source(skill_path)
    trust = source  # user/project/unknown

    return SkillMetadata(
        name=name,
        description=description,
        path=skill_path,
        version=frontmatter.get("version"),
        author=frontmatter.get("author"),
        tags=tags,
        source=source,
        trust=trust,
        skill_md_hash=content_hash,
        skill_md_size=file_size,
    )


def _classify_skill_source(skill_path: Path) -> str:
    """Classify a skill directory as 'user', 'project', or 'unknown'."""
    home_skills = Path.home() / ".code_puppy" / "skills"
    try:
        skill_path.resolve().relative_to(home_skills.resolve())
        return "user"
    except ValueError:
        pass
    try:
        skill_path.resolve().relative_to(Path.cwd().resolve())
        return "project"
    except ValueError:
        pass
    return "unknown"


def load_full_skill_content(skill_path: Path) -> Optional[str]:
    """Load the complete SKILL.md content for activation.

    Validates file size before reading and caps content to
    prevent model-context blowup.

    Args:
        skill_path: Path to the skill directory

    Returns:
        Full file content as string (capped), or None if not found.
    """
    if not skill_path.exists():
        logger.warning("Skill path does not exist: %s", skill_path)
        return None

    skill_md_path = skill_path / "SKILL.md"
    if not skill_md_path.exists():
        logger.warning("SKILL.md not found in skill directory: %s", skill_path)
        return None

    # Validate size before reading
    try:
        file_size = skill_md_path.stat().st_size
        if file_size > MAX_SKILL_MD_BYTES:
            logger.warning(
                "SKILL.md at %s is too large (%d bytes, max %d)",
                skill_md_path,
                file_size,
                MAX_SKILL_MD_BYTES,
            )
            return None
    except OSError:
        return None

    try:
        content = skill_md_path.read_text(encoding="utf-8")
        # Cap content for model-context injection
        return cap_skill_content(content)
    except Exception as e:
        logger.error("Failed to read SKILL.md at %s: %s", skill_md_path, e)
        return None


def get_skill_resources(skill_path: Path) -> List[Path]:
    """List all resource files bundled with a skill.

    Returns paths to all non-SKILL.md files in the skill directory.

    Args:
        skill_path: Path to the skill directory

    Returns:
        List of paths to resource files (excluding SKILL.md).
    """
    if not skill_path.exists():
        logger.warning(f"Skill path does not exist: {skill_path}")
        return []

    if not skill_path.is_dir():
        logger.warning(f"Skill path is not a directory: {skill_path}")
        return []

    resources: List[Path] = []
    try:
        for item in skill_path.iterdir():
            if item.is_file() and item.name != "SKILL.md":
                resources.append(item)
    except Exception as e:
        logger.error(f"Failed to list resources in {skill_path}: {e}")
        return []

    return sorted(resources)  # Sort for consistent ordering
