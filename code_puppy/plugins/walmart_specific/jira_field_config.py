"""Configurable Jira field mappings.

Jira custom field IDs vary between instances. This module provides
configurable field mappings with sensible defaults for Walmart's Jira.

Configuration file: ~/.code_puppy/jira_fields.json

Example config:
    {
        "epic_link": "customfield_10007",
        "sprint": "customfield_10005",
        "story_points": "customfield_10002"
    }

If the config file doesn't exist, defaults are used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_puppy.config import CONFIG_DIR


# =============================================================================
# DEFAULT FIELD MAPPINGS (Walmart Jira)
# =============================================================================

DEFAULT_FIELD_MAPPINGS: dict[str, str] = {
    "epic_link": "customfield_10007",
    "sprint": "customfield_10005",
    "story_points": "customfield_10002",
}

# Config file path
FIELD_CONFIG_FILE = Path(CONFIG_DIR) / "jira_fields.json"

# Cached field mappings (loaded once)
_field_mappings: dict[str, str] | None = None


# =============================================================================
# CONFIGURATION LOADING
# =============================================================================


def _load_field_config() -> dict[str, str]:
    """Load field mappings from config file, falling back to defaults.

    Returns:
        Dictionary mapping logical field names to Jira custom field IDs.
    """
    mappings = DEFAULT_FIELD_MAPPINGS.copy()

    if FIELD_CONFIG_FILE.exists():
        try:
            with open(FIELD_CONFIG_FILE) as f:
                user_config = json.load(f)

            if isinstance(user_config, dict):
                # Only override known fields
                for key in DEFAULT_FIELD_MAPPINGS:
                    if key in user_config and isinstance(user_config[key], str):
                        mappings[key] = user_config[key]

        except (json.JSONDecodeError, OSError):
            # Silently fall back to defaults on error
            pass

    return mappings


def get_field_mappings() -> dict[str, str]:
    """Get the current field mappings (cached).

    Returns:
        Dictionary mapping logical field names to Jira custom field IDs.
    """
    global _field_mappings
    if _field_mappings is None:
        _field_mappings = _load_field_config()
    return _field_mappings


def reload_field_mappings() -> dict[str, str]:
    """Force reload field mappings from config file.

    Returns:
        Dictionary mapping logical field names to Jira custom field IDs.
    """
    global _field_mappings
    _field_mappings = _load_field_config()
    return _field_mappings


# =============================================================================
# FIELD ID GETTERS
# =============================================================================


def get_epic_link_field() -> str:
    """Get the custom field ID for Epic Link."""
    return get_field_mappings()["epic_link"]


def get_sprint_field() -> str:
    """Get the custom field ID for Sprint."""
    return get_field_mappings()["sprint"]


def get_story_points_field() -> str:
    """Get the custom field ID for Story Points."""
    return get_field_mappings()["story_points"]


# =============================================================================
# CONFIG FILE MANAGEMENT
# =============================================================================


def save_field_config(mappings: dict[str, str]) -> bool:
    """Save field mappings to config file.

    Args:
        mappings: Dictionary of field mappings to save.

    Returns:
        True if saved successfully, False otherwise.
    """
    try:
        # Merge with existing config to preserve any extra fields
        existing: dict[str, Any] = {}
        if FIELD_CONFIG_FILE.exists():
            try:
                with open(FIELD_CONFIG_FILE) as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        existing.update(mappings)

        with open(FIELD_CONFIG_FILE, "w") as f:
            json.dump(existing, f, indent=2)

        # Reload cache
        reload_field_mappings()
        return True

    except OSError:
        return False


def show_current_config() -> str:
    """Get a formatted string showing current field configuration.

    Returns:
        Formatted string with current field mappings.
    """
    mappings = get_field_mappings()
    config_source = "config file" if FIELD_CONFIG_FILE.exists() else "defaults"

    lines = [
        f"Jira Field Mappings (from {config_source}):",
        f"  Epic Link:    {mappings['epic_link']}",
        f"  Sprint:       {mappings['sprint']}",
        f"  Story Points: {mappings['story_points']}",
        "",
        f"Config file: {FIELD_CONFIG_FILE}",
    ]
    return "\n".join(lines)
