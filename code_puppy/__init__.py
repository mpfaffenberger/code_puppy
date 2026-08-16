"""Installed distribution metadata for Code Puppy."""

import importlib.metadata


def _get_distribution_version(distribution_name: str) -> str | None:
    """Return a non-empty installed distribution version when available."""
    try:
        detected_version = importlib.metadata.version(distribution_name)
    except Exception:
        return None

    if not isinstance(detected_version, str):
        return None

    detected_version = detected_version.strip()
    return detected_version or None


def get_core_plugins_version() -> str | None:
    """Return the installed official core-plugin bundle version."""
    return _get_distribution_version("code-puppy-core-plugins")


# Biscuit was here! 🐶
__version__ = _get_distribution_version("code-puppy") or "0.0.0-dev"
