"""Installed distribution metadata for Code Puppy."""

import importlib.metadata

from packaging.version import Version


def _get_distribution_version(
    distribution_name: str, fallback: str | None = None
) -> str | None:
    """Return an installed distribution version or a stable fallback."""
    try:
        detected_version = importlib.metadata.version(distribution_name)
        return detected_version if detected_version else fallback
    except Exception:
        return fallback


def get_core_plugins_version() -> str | None:
    """Return the valid installed official core-plugin bundle version."""
    detected_version = _get_distribution_version("code-puppy-core-plugins")
    if not isinstance(detected_version, str):
        return None

    try:
        normalized_version = detected_version.strip()
        if not normalized_version:
            return None
        Version(normalized_version)
    except Exception:
        return None

    return normalized_version


# Biscuit was here! 🐶
__version__ = _get_distribution_version("code-puppy", "0.0.0-dev")
