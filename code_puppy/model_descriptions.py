"""Helpers for safe model description overlays.

Model configs are assembled from multiple sources using shallow updates.
These helpers keep description updates surgical so we don't clobber
provider endpoints or other model settings.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_MODEL_DESCRIPTION = "No description available."


def apply_description_overlays(
    models_config: dict[str, dict[str, Any]],
    *overlays: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Apply description overlays to an existing merged models config.

    Rules:
    - Never create new models.
    - Never overwrite non-description fields.
    - Only set ``description`` when missing or blank.
    """
    for overlay in overlays:
        for model_name, description in overlay.items():
            if model_name not in models_config:
                continue
            if not isinstance(models_config.get(model_name), dict):
                continue
            if not isinstance(description, str):
                continue

            desc = description.strip()
            if not desc:
                continue

            existing = models_config[model_name].get("description")
            if isinstance(existing, str) and existing.strip():
                continue

            models_config[model_name]["description"] = desc

    return models_config


def get_model_description(
    models_config: Mapping[str, Mapping[str, Any]],
    model_name: str,
    *,
    default: str = DEFAULT_MODEL_DESCRIPTION,
) -> str:
    """Get a display-safe model description with fallback text."""
    model_config = models_config.get(model_name, {})
    description = (
        model_config.get("description") if isinstance(model_config, Mapping) else None
    )
    if isinstance(description, str) and description.strip():
        return description.strip()
    return default
