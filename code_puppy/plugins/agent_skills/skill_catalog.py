"""Bundled skill catalog registry.

This module auto-discovers *bundled* skills shipped with the package under:
`code_puppy/bundled_skills/<Category>/<skill_id>/SKILL.md`

It is intentionally separate from user/project skill discovery (see
`code_puppy.plugins.agent_skills.discovery`).

Phase 1 goal: provide a read-only searchable catalog for `/skills install`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from code_puppy.plugins.agent_skills.metadata import parse_skill_metadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SkillCatalogEntry:
    """A single catalog entry for a bundled skill."""

    id: str
    name: str
    display_name: str
    description: str
    category: str
    tags: List[str]
    source_path: Path
    has_scripts: bool
    has_references: bool
    file_count: int


def _format_display_name(name: str) -> str:
    """Convert a skill name to a human-friendly display name.

    Examples:
        - "data-exploration" -> "Data Exploration"
        - "contract_review" -> "Contract Review"
        - "pdf" -> "PDF" (short acronym-ish tokens are uppercased)
    """

    normalized = name.replace("_", " ").replace("-", " ").strip()
    if not normalized:
        return ""

    parts: List[str] = []
    for token in normalized.split():
        if token.isalpha() and len(token) <= 3:
            parts.append(token.upper())
        else:
            parts.append(token[:1].upper() + token[1:])

    return " ".join(parts)


def _count_files_recursive(root: Path) -> int:
    """Count regular files under root (recursive)."""

    if not root.exists() or not root.is_dir():
        return 0

    try:
        return sum(1 for p in root.rglob("*") if p.is_file())
    except OSError as e:
        logger.warning(f"Failed counting files under {root}: {e}")
        return 0


def _get_bundled_skills_dir() -> Optional[Path]:
    """Best-effort locate `code_puppy/bundled_skills/` on disk.

    We prefer a `__file__`-relative path (works in editable installs and
    normal wheels). We also attempt `importlib.resources` to support other
    packaging layouts.

    Returns:
        Path to the bundled_skills directory, or None if not found.
    """

    # 1) __file__-relative (simple, reliable on disk)
    try:
        pkg_root = Path(__file__).resolve().parents[2]  # .../code_puppy
        candidate = pkg_root / "bundled_skills"
        if candidate.exists() and candidate.is_dir():
            return candidate
    except Exception as e:  # pragma: no cover - ultra defensive
        logger.debug(f"Failed resolving bundled_skills via __file__: {e}")

    # 2) importlib.resources fallback (filesystem-only)
    #
    # We intentionally *avoid* `resources.as_file()` here because it may extract
    # resources to a temporary directory that gets deleted when the context
    # manager exits  which would leave `source_path` entries pointing at
    # nothing. For Phase 1 we only support bundled skills that exist as real
    # files on disk.
    try:
        import importlib.resources as resources

        traversable = resources.files("code_puppy") / "bundled_skills"
        extracted_path = Path(traversable)  # Works when it's already on disk.

        if extracted_path.exists() and extracted_path.is_dir():
            return extracted_path
    except TypeError:
        # Not a filesystem path (e.g., zipimport). Ignore.
        pass
    except Exception as e:  # pragma: no cover - optional path
        logger.debug(f"Failed resolving bundled_skills via importlib.resources: {e}")

    return None


class SkillCatalog:
    """Registry for bundled skills shipped with code_puppy."""

    def __init__(self) -> None:
        self._entries: List[SkillCatalogEntry] = []
        self._by_id: Dict[str, SkillCatalogEntry] = {}
        self._by_category: Dict[str, List[SkillCatalogEntry]] = {}

        self._discover()

    def _discover(self) -> None:
        bundled_dir = _get_bundled_skills_dir()
        if bundled_dir is None:
            logger.info("No bundled_skills directory found; bundled catalog empty")
            return

        if not bundled_dir.exists() or not bundled_dir.is_dir():
            logger.info(
                f"bundled_skills path does not exist or is not a directory: {bundled_dir}"
            )
            return

        for category_dir in sorted(bundled_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            if category_dir.name.startswith("."):
                continue

            category = category_dir.name

            for skill_dir in sorted(category_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                if skill_dir.name.startswith("."):
                    continue

                skill_id = skill_dir.name
                metadata = parse_skill_metadata(skill_dir)
                if metadata is None:
                    # Parse already logs; keep catalog resilient.
                    continue

                name = metadata.name
                entry = SkillCatalogEntry(
                    id=skill_id,
                    name=name,
                    display_name=_format_display_name(name),
                    description=metadata.description,
                    category=category,
                    tags=list(metadata.tags),
                    source_path=skill_dir,
                    has_scripts=(skill_dir / "scripts").is_dir(),
                    has_references=(skill_dir / "references").is_dir(),
                    file_count=_count_files_recursive(skill_dir),
                )

                if entry.id in self._by_id:
                    logger.warning(
                        f"Duplicate bundled skill id '{entry.id}' found at {skill_dir}; "
                        "keeping the first occurrence"
                    )
                    continue

                self._entries.append(entry)
                self._by_id[entry.id] = entry
                self._by_category.setdefault(entry.category, []).append(entry)

        # Deterministic ordering for callers/tests.
        self._entries.sort(key=lambda e: (e.category.lower(), e.name.lower(), e.id))
        for entries in self._by_category.values():
            entries.sort(key=lambda e: (e.name.lower(), e.id))

        logger.info(f"Bundled skill catalog loaded: {len(self._entries)} skills")

    def list_categories(self) -> List[str]:
        """Return sorted unique category names."""

        return sorted(self._by_category.keys(), key=str.lower)

    def get_by_category(self, category: str) -> List[SkillCatalogEntry]:
        """Return skills in a category.

        Category matching is case-insensitive.
        """

        category_lower = category.lower().strip()
        for cat, entries in self._by_category.items():
            if cat.lower() == category_lower:
                return list(entries)
        return []

    def search(self, query: str) -> List[SkillCatalogEntry]:
        """Search by name/description/tags (case-insensitive)."""

        q = query.strip().lower()
        if not q:
            return []

        results: List[SkillCatalogEntry] = []
        for entry in self._entries:
            haystacks = [
                entry.id,
                entry.name,
                entry.display_name,
                entry.description,
                entry.category,
                " ".join(entry.tags),
            ]
            if any(q in (h or "").lower() for h in haystacks):
                results.append(entry)

        return results

    def get_by_id(self, skill_id: str) -> Optional[SkillCatalogEntry]:
        """Lookup a skill by id (folder name)."""

        return self._by_id.get(skill_id.strip())

    def get_all(self) -> List[SkillCatalogEntry]:
        """Return all catalog entries."""

        return list(self._entries)


# Singleton, mirroring the MCP catalog style.
catalog = SkillCatalog()
