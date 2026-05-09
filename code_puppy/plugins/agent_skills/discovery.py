"""Skill discovery - scans directories for valid skills.

Includes safety checks for symlink escapes, hidden directories,
SKILL.md size validation, and executable file awareness.
"""

import logging
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from code_puppy.plugins.agent_skills.config import get_skill_directories

logger = logging.getLogger(__name__)

# Max SKILL.md file size before we refuse to read (256 KiB)
MAX_SKILL_MD_BYTES = 256 * 1024

# Cap for skill content injected into model context (chars)
SKILL_CONTEXT_CAP = 64_000


@dataclass
class SkillInfo:
    """Basic skill information from discovery."""

    name: str
    path: Path
    has_skill_md: bool
    skill_md_size: Optional[int] = None
    skill_md_hash: Optional[str] = None
    source: Optional[str] = None
    trust: Optional[str] = None  # "builtin" | "user" | None


# Global cache for discovered skills
_skill_cache: Optional[List[SkillInfo]] = None


def _is_symlink_escape(child: Path, parent: Path) -> bool:
    """Return True if *child* resolves outside *parent* (symlink escape)."""
    try:
        child.resolve().relative_to(parent.resolve())
        return False
    except ValueError:
        return True


def _has_unexpected_executables(skill_dir: Path) -> bool:
    """Return True if *skill_dir* contains unexpected executable files.

    We expect only .md, .txt, .json, .yaml, .yml, .py, .toml files in
    skill directories. Anything with the execute bit set (beyond
    directory traversal) is flagged.
    """
    safe_extensions = {
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".py",
        ".toml",
        ".cfg",
        ".ini",
        ".rst",
        ".html",
        ".css",
        ".js",
    }
    try:
        for item in skill_dir.iterdir():
            if not item.is_file():
                continue
            # Skip symlinks that escape
            if item.is_symlink() and _is_symlink_escape(item, skill_dir):
                return True
            # Check for executable bit on non-standard files
            if item.suffix.lower() not in safe_extensions:
                try:
                    mode = item.stat().st_mode
                    if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                        logger.warning(
                            "Unexpected executable file in skill dir %s: %s",
                            skill_dir.name,
                            item.name,
                        )
                        return True
                except OSError:
                    pass
    except OSError:
        pass
    return False


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

    Also validates that SKILL.md is not oversized and that
    the directory does not contain unexpected executables.

    Args:
        path: Directory path to check.

    Returns:
        True if the directory is a valid skill directory, False otherwise.
    """
    if not path.is_dir():
        return False

    skill_md_path = path / "SKILL.md"
    if not skill_md_path.is_file():
        return False

    # Check for symlink escape on SKILL.md
    if _is_symlink_escape(skill_md_path, path):
        logger.warning("SKILL.md in %s is a symlink escape, skipping", path.name)
        return False

    # Validate SKILL.md size before we ever read it
    try:
        size = skill_md_path.stat().st_size
        if size > MAX_SKILL_MD_BYTES:
            logger.warning(
                "SKILL.md in %s is too large (%d bytes, max %d), skipping",
                path.name,
                size,
                MAX_SKILL_MD_BYTES,
            )
            return False
    except OSError:
        return False

    # Check for unexpected executable files
    if _has_unexpected_executables(path):
        logger.warning(
            "Skill directory %s contains unexpected executable files, skipping",
            path.name,
        )
        return False

    return True


def _compute_skill_md_hash(skill_md_path: Path) -> Optional[str]:
    """Compute SHA-256 hash of a SKILL.md file."""
    import hashlib

    try:
        content = skill_md_path.read_bytes()
        return hashlib.sha256(content).hexdigest()
    except OSError:
        return None


def _classify_skill_source(skill_dir: Path) -> str:
    """Classify a skill directory as 'builtin' or 'user'."""
    home_skills = Path.home() / ".code_puppy" / "skills"
    try:
        skill_dir.resolve().relative_to(home_skills.resolve())
        return "user"
    except ValueError:
        pass
    # Check if it's under CWD
    try:
        skill_dir.resolve().relative_to(Path.cwd().resolve())
        return "project"
    except ValueError:
        pass
    return "unknown"


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

    for directory in directories:
        if not directory.exists():
            logger.debug("Skill directory does not exist: %s", directory)
            continue

        if not directory.is_dir():
            logger.warning("Skill path is not a directory: %s", directory)
            continue

        # Scan subdirectories within the skill directory
        for skill_dir in directory.iterdir():
            if not skill_dir.is_dir():
                continue

            # Skip hidden directories
            if skill_dir.name.startswith(".") or skill_dir.name.startswith("_"):
                continue

            # Skip symlink escapes
            if _is_symlink_escape(skill_dir, directory):
                logger.warning(
                    "Skipping skill dir %s: symlink escape from %s",
                    skill_dir.name,
                    directory,
                )
                continue

            has_skill_md = is_valid_skill_directory(skill_dir)

            # Compute metadata for valid skills
            skill_md_size = None
            skill_md_hash = None
            if has_skill_md:
                skill_md_path = skill_dir / "SKILL.md"
                try:
                    skill_md_size = skill_md_path.stat().st_size
                except OSError:
                    pass
                skill_md_hash = _compute_skill_md_hash(skill_md_path)

            source = _classify_skill_source(skill_dir)
            # Built-in skills from the package are always trusted
            trust = "builtin" if source == "unknown" else source

            skill_info = SkillInfo(
                name=skill_dir.name,
                path=skill_dir,
                has_skill_md=has_skill_md,
                skill_md_size=skill_md_size,
                skill_md_hash=skill_md_hash,
                source=source,
                trust=trust,
            )
            discovered_skills.append(skill_info)

            if has_skill_md:
                logger.debug(
                    "Discovered valid skill: %s at %s", skill_dir.name, skill_dir
                )
            else:
                logger.debug(
                    "Found skill directory without SKILL.md: %s", skill_dir.name
                )

    # Update cache
    _skill_cache = discovered_skills

    logger.info(
        "Discovered %d skills from %d directories",
        len(discovered_skills),
        len(directories),
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


def cap_skill_content(content: str, cap: int = SKILL_CONTEXT_CAP) -> str:
    """Cap skill content to prevent model-context blowup.

    If content exceeds *cap* characters, it is truncated with a marker.
    """
    if len(content) <= cap:
        return content
    return content[:cap] + "\n... [skill content truncated]"
