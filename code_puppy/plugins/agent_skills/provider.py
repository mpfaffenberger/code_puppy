"""Core-facing provider backed by the agent_skills plugin's existing helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Set

from .config import get_disabled_skills, get_skills_enabled
from .enabled_skills import iter_enabled_skills, list_enabled_skill_metadata
from .metadata import get_skill_resources, load_full_skill_content
from .skill_catalog import catalog


class AgentSkillsProvider:
    """Adapt agent_skills internals to the neutral core provider contract."""

    def is_enabled(self) -> bool:
        return get_skills_enabled()

    def get_disabled_skill_names(self) -> Set[str]:
        return get_disabled_skills()

    def list_enabled_skills(self) -> List[dict[str, Any]]:
        return [
            {
                "name": metadata.name,
                "description": metadata.description,
                "path": str(metadata.path),
                "tags": metadata.tags,
                "version": metadata.version,
                "author": metadata.author,
            }
            for metadata in list_enabled_skill_metadata()
        ]

    def find_enabled_skill_path(self, skill_name: str) -> Optional[Path]:
        return next(
            (info.path for info in iter_enabled_skills() if info.name == skill_name),
            None,
        )

    def load_skill_content(self, skill_path: Path) -> Optional[str]:
        return load_full_skill_content(skill_path)

    def get_skill_resources(self, skill_path: Path) -> List[Path]:
        return get_skill_resources(skill_path)

    def get_catalog_skill_ids(self) -> List[str]:
        return [entry.id for entry in catalog.get_all()]


skill_provider = AgentSkillsProvider()
