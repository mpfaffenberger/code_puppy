"""Single source of truth for `enabled skills with parsed frontmatter`.

Everywhere we want to surface skills to the model (prompt injection, the
``list_or_search_skills`` tool, per-skill slash commands) we follow the same
three-step dance:

1. discover skills on disk + plugin-registered ones,
2. filter out disabled skills (and skills missing ``SKILL.md``),
3. parse frontmatter for the survivors.

Centralising it here guarantees we **never** read frontmatter for a disabled
skill — and removes the temptation to reimplement the dance a fourth time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Optional

# Import modules (not names) so monkeypatching at `<module>.attr` reaches us.
from . import config as _config
from . import discovery as _discovery
from . import metadata as _metadata
from .discovery import SkillInfo
from .metadata import SkillMetadata


def iter_enabled_skill_metadata(
    *, directories: Optional[List[Path]] = None
) -> Iterator[SkillMetadata]:
    """Yield ``SkillMetadata`` for every enabled, valid skill.

    Frontmatter is only read for skills that survive the disabled check —
    so this function is also the cheapest way to ask "what's actually live?".

    If skills integration is globally disabled, yields nothing.

    Args:
        directories: Optional explicit list of directories to scan. Defaults
            to the configured + default skill directories (the standard path).
    """
    if not _config.get_skills_enabled():
        return

    if directories is None:
        directories = [Path(d) for d in _config.get_skill_directories()]

    disabled = _config.get_disabled_skills()

    for info in _discovery.discover_skills(directories):
        if not info.has_skill_md:
            continue
        if info.name in disabled:
            continue
        meta = _metadata.parse_skill_metadata(info.path)
        if meta is not None:
            yield meta


def list_enabled_skill_metadata(
    *, directories: Optional[List[Path]] = None
) -> List[SkillMetadata]:
    """Materialised list version of :func:`iter_enabled_skill_metadata`."""
    return list(iter_enabled_skill_metadata(directories=directories))


def iter_enabled_skills(
    *, directories: Optional[List[Path]] = None
) -> Iterator[SkillInfo]:
    """Yield ``SkillInfo`` for enabled skills *without* parsing frontmatter.

    Useful when a caller only needs the path/name (e.g. to load the full
    ``SKILL.md`` body) and doesn't want to pay the YAML-parse cost.
    """
    if not _config.get_skills_enabled():
        return

    if directories is None:
        directories = [Path(d) for d in _config.get_skill_directories()]

    disabled = _config.get_disabled_skills()

    for info in _discovery.discover_skills(directories):
        if not info.has_skill_md:
            continue
        if info.name in disabled:
            continue
        yield info
