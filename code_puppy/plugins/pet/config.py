"""Plugin-local config for the desktop pet, persisted in ``puppy.cfg``.

Uses the generic ``get_value`` / ``set_config_value`` API so we never have to
edit core's ``get_config_keys`` -- arbitrary keys round-trip just fine.
"""

from __future__ import annotations

from typing import Optional

from code_puppy.config import get_value, set_config_value

KEY_ENABLED = "pet_enabled"
KEY_SPECIES = "pet_species"
KEY_NAME = "pet_name"

_TRUTHY = ("true", "1", "yes", "on")


def is_enabled() -> bool:
    val = get_value(KEY_ENABLED)
    return bool(val) and str(val).strip().lower() in _TRUTHY


def set_enabled(enabled: bool) -> None:
    set_config_value(KEY_ENABLED, "true" if enabled else "false")


def get_species() -> str:
    from code_puppy.plugins.pet.species import DOG_SPECIES

    sp = get_value(KEY_SPECIES)
    return sp if sp in DOG_SPECIES else "mutt"


def set_species(species: str) -> None:
    set_config_value(KEY_SPECIES, species)


def get_name() -> str:
    from code_puppy.plugins.pet.species import DOG_SPECIES

    return get_value(KEY_NAME) or DOG_SPECIES[get_species()].default_name


def set_name(name: Optional[str]) -> None:
    if name:
        set_config_value(KEY_NAME, name)
