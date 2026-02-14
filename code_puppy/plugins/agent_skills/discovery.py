"""Skill discovery - scans directories for valid skills."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

from code_puppy.plugins.agent_skills.config import get_skill_directories

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Basic skill information from discovery."""

    name: str
    path: Path
    has_skill_md: bool


# Global cache for discovered skills
_skill_cache: Optional[List[SkillInfo]] = None


def get_default_skill_directories() -> List[Path]:
    """Return default directories to scan for skills.

    Returns:
        - ~/.code_puppy/skills (user skills)
        - ./.code_puppy/skills (project config skills)
        - ./skills (project skills)
    """
    return [
        Path.home() / ".code_puppy" / "skills",
        Path.cwd() / ".code_puppy" / "skills",
        Path.cwd() / "skills",
    ]


def is_valid_skill_directory(path: Path) -> bool:
    """Check if a directory contains a valid SKILL.md file.

    Args:
        path: Directory path to check.

    Returns:
        True if the directory is a valid skill directory, False otherwise.
    """
    if not path.is_dir():
        return False

    skill_md_path = path / "SKILL.md"
    return skill_md_path.is_file()


def discover_skills(directories: Optional[List[Path]] = None) -> List[SkillInfo]:
    """Scan directories for valid skills.

    Args:
        directories: Directories to scan. If None, uses configured
                     directories (which includes user-added ones from /skills menu).

    Returns:
        List of discovered SkillInfo objects.
    """
    global _skill_cache

    if directories is None:
        # Use configured directories (respects user-added dirs from /skills menu)
        # then merge with defaults to ensure we always check the standard locations
        configured = [Path(d) for d in get_skill_directories()]
        defaults = get_default_skill_directories()
        # Merge: configured first, then any defaults not already covered
        seen = {p.resolve() for p in configured}
        directories = list(configured)
        for d in defaults:
            if d.resolve() not in seen:
                directories.append(d)

    discovered_skills: List[SkillInfo] = []
    # Deduplicate skills across all scanned directories.
    # Keyed by resolved path so symlinks / duplicate directory entries collapse.
    seen_skills: Set[Path] = set()

    for directory in directories:
        if not directory.exists():
            logger.debug(f"Skill directory does not exist: {directory}")
            continue

        if not directory.is_dir():
            logger.warning(f"Skill path is not a directory: {directory}")
            continue

        # Scan subdirectories within the skill directory
        for skill_dir in directory.iterdir():
            if not skill_dir.is_dir():
                continue

            # Skip hidden directories
            if skill_dir.name.startswith("."):
                continue

            try:
                resolved_skill_dir = skill_dir.resolve()
            except OSError:
                # Best-effort: still dedup within this run without crashing discovery.
                resolved_skill_dir = skill_dir.absolute()

            if resolved_skill_dir in seen_skills:
                logger.debug(
                    f"Skipping duplicate skill directory: {skill_dir} (resolved: {resolved_skill_dir})"
                )
                continue
            seen_skills.add(resolved_skill_dir)

            has_skill_md = is_valid_skill_directory(skill_dir)

            # Include if it has SKILL.md (valid skill) or just for discovery
            skill_info = SkillInfo(
                name=skill_dir.name, path=skill_dir, has_skill_md=has_skill_md
            )
            discovered_skills.append(skill_info)

            if has_skill_md:
                logger.debug(f"Discovered valid skill: {skill_dir.name} at {skill_dir}")
            else:
                logger.debug(
                    f"Found skill directory without SKILL.md: {skill_dir.name}"
                )

    # Update cache
    _skill_cache = discovered_skills

    logger.info(
        f"Discovered {len(discovered_skills)} skills from {len(directories)} directories"
    )
    return discovered_skills


def refresh_skill_cache() -> List[SkillInfo]:
    """Force re-discovery of all skills.

    This clears the cache and performs a fresh scan of all default
    skill directories.

    Returns:
        List of freshly discovered SkillInfo objects.
    """
    global _skill_cache
    _skill_cache = None
    return discover_skills()
