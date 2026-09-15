"""Neutral provider seam for optional Agent Skills integrations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Protocol, Set

from code_puppy.callbacks import on_register_skills


class SkillProvider(Protocol):
    """Core-facing operations supplied by a skills plugin."""

    def is_enabled(self) -> bool: ...

    def get_disabled_skill_names(self) -> Set[str]: ...

    def list_enabled_skills(self) -> List[dict[str, Any]]: ...

    def find_enabled_skill_path(self, skill_name: str) -> Optional[Path]: ...

    def load_skill_content(self, skill_path: Path) -> Optional[str]: ...

    def get_skill_resources(self, skill_path: Path) -> List[Path]: ...

    def get_catalog_skill_ids(self) -> List[str]: ...


def get_skill_provider() -> Optional[SkillProvider]:
    """Return the first enabled plugin's registered skills provider.

    Callback order is registration order, matching the existing precedence
    rules for plugin capabilities. Providers are deliberately resolved on each
    call so disabling a plugin takes effect immediately and no stale provider
    survives a configuration change.
    """
    for result in on_register_skills():
        entries = result if isinstance(result, list) else [result]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            provider = entry.get("provider")
            if provider is not None:
                return provider
    return None
