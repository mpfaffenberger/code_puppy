"""Theme management for Code Puppy's messaging system.

This module provides the ThemeManager class for managing visual themes
that control the colors and styling of different message types.

Themes are stored as JSON files in the themes directory and can be loaded,
saved, and applied at runtime.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_puppy.config import CONFIG_DIR, get_value, set_config_value
from code_puppy.themes.presets import (
    PRESET_THEME_DESCRIPTIONS,
    PRESET_THEMES,
    list_preset_themes,
)
from code_puppy.themes.theme import Theme, validate_theme_name

# =============================================================================
# Theme Directory
# =============================================================================

THEME_DIR = Path(CONFIG_DIR) / "themes"


# =============================================================================
# Lazy Messaging Imports (to avoid circular import)
# =============================================================================


def _emit_error(message: str) -> None:
    """Emit an error message (lazy import to avoid circular dependency)."""
    try:
        from code_puppy.messaging import emit_error as _emit

        _emit(message)
    except ImportError:
        # Fallback to print if messaging system is not available
        print(f"Error: {message}")


def _emit_warning(message: str) -> None:
    """Emit a warning message (lazy import to avoid circular dependency)."""
    try:
        from code_puppy.messaging import emit_warning as _emit

        _emit(message)
    except ImportError:
        # Fallback to print if messaging system is not available
        print(f"Warning: {message}")


def _emit_info(message: str) -> None:
    """Emit an info message (lazy import to avoid circular dependency)."""
    try:
        from code_puppy.messaging import emit_info as _emit

        _emit(message)
    except ImportError:
        # Fallback to print if messaging system is not available
        print(f"Info: {message}")


# =============================================================================
# Default Theme
# =============================================================================

# Default theme matching the DEFAULT_STYLES from rich_renderer.py
DEFAULT_THEME = Theme(
    error_color="bold red",
    warning_color="yellow",
    success_color="green",
    info_color="white",
    debug_color="dim",
    tool_output_color="cyan",
    agent_reasoning_color="magenta",
    agent_response_color="blue",
    system_color="bright_black",
)


# =============================================================================
# Theme Manager
# =============================================================================


class ThemeManager:
    """Manager for loading, saving, and applying themes.

    The ThemeManager handles the lifecycle of themes:
    - Loading themes from JSON files
    - Saving themes to JSON files
    - Applying themes to the messaging system
    - Listing available themes
    - Managing the current active theme

    Example:
        >>> manager = ThemeManager()
        >>> manager.load_theme("dark")
        >>> manager.apply_theme()
        >>> manager.save_theme(manager.get_current_theme(), "my_theme")
    """

    def __init__(self, theme_dir: Optional[Path] = None) -> None:
        """Initialize the ThemeManager.

        Args:
            theme_dir: Directory to store/load themes from. Defaults to
                      CONFIG_DIR/themes
        """
        self._theme_dir = Path(theme_dir) if theme_dir else THEME_DIR
        self._ensure_theme_dir()
        self._current_theme: Optional[Theme] = None

    def _ensure_theme_dir(self) -> None:
        """Ensure the theme directory exists with proper permissions.

        Handles errors gracefully and falls back to using the config directory
        if the theme directory cannot be created or accessed.
        """
        try:
            self._theme_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

            # Ensure the directory has the right permissions even if it already existed
            if self._theme_dir.exists():
                self._theme_dir.chmod(0o700)
        except PermissionError as e:
            _emit_error(
                f"Permission denied accessing theme directory '{self._theme_dir}': {e}"
            )
            _emit_warning("Theme directory may not have correct permissions.")
        except OSError as e:
            _emit_error(f"Failed to create theme directory '{self._theme_dir}': {e}")
            _emit_warning("Custom themes may not be saved correctly.")

    def _get_theme_path(self, theme_name: str) -> Path:
        """Get the file path for a theme.

        Args:
            theme_name: Name of the theme (without .json extension)

        Returns:
            Path to the theme JSON file
        """
        # Sanitize theme name to prevent directory traversal
        safe_name = theme_name.replace("..", "").replace("/", "").replace("", "")
        return self._theme_dir / f"{safe_name}.json"

    def _get_backup_path(self, theme_name: str) -> Path:
        """Get the backup file path for a theme.

        Args:
            theme_name: Name of the theme

        Returns:
            Path to the backup JSON file
        """
        safe_name = theme_name.replace("..", "").replace("/", "").replace("", "")
        return self._theme_dir / f"{safe_name}.json.backup"

    def _create_backup(self, theme_path: Path) -> Optional[Path]:
        """Create a backup of an existing theme file.

        Args:
            theme_path: Path to the theme file to backup

        Returns:
            Path to the backup file if backup was created, None otherwise
        """
        if not theme_path.exists():
            return None

        backup_path = theme_path.with_suffix(".json.backup")
        try:
            shutil.copy2(theme_path, backup_path)
            return backup_path
        except PermissionError as e:
            _emit_warning(f"Permission denied creating backup: {e}")
            return None
        except (OSError, IOError) as e:
            _emit_warning(f"Failed to create backup: {e}")
            return None

    def _validate_theme_json(self, data: Dict[str, Any], theme_name: str) -> List[str]:
        """Validate the JSON structure of a theme file.

        Args:
            data: Parsed JSON data
            theme_name: Name of the theme (for error messages)

        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[str] = []

        # Check for colors key (new format) or direct color fields (old format)
        if "colors" in data:
            colors = data["colors"]
            if not isinstance(colors, dict):
                errors.append(f"'colors' must be an object in theme '{theme_name}'")
                return errors
        else:
            colors = data  # Old format: colors are at the top level

        # Required color fields
        required_fields = [
            "error_color",
            "warning_color",
            "success_color",
            "info_color",
            "debug_color",
            "tool_output_color",
            "agent_reasoning_color",
            "agent_response_color",
            "system_color",
        ]

        for field in required_fields:
            if field not in colors:
                errors.append(
                    f"Missing required field '{field}' in theme '{theme_name}'"
                )
            elif not isinstance(colors[field], str):
                errors.append(
                    f"Field '{field}' must be a string in theme '{theme_name}'"
                )

        # Validate optional metadata fields
        if "name" in data and not isinstance(data["name"], str):
            errors.append(f"'name' must be a string in theme '{theme_name}'")

        if "description" in data and not isinstance(data["description"], str):
            errors.append(f"'description' must be a string in theme '{theme_name}'")

        if "created_at" in data and not isinstance(data["created_at"], str):
            errors.append(
                f"'created_at' must be a string (ISO timestamp) in theme '{theme_name}'"
            )

        if (
            "author" in data
            and data["author"] is not None
            and not isinstance(data["author"], str)
        ):
            errors.append(f"'author' must be a string in theme '{theme_name}'")

        if (
            "version" in data
            and data["version"] is not None
            and not isinstance(data["version"], str)
        ):
            errors.append(f"'version' must be a string in theme '{theme_name}'")

        if "tags" in data:
            if not isinstance(data["tags"], list):
                errors.append(f"'tags' must be a list in theme '{theme_name}'")
            else:
                for i, tag in enumerate(data["tags"]):
                    if not isinstance(tag, str):
                        errors.append(
                            f"'tags[{i}]' must be a string in theme '{theme_name}'"
                        )

        return errors

    def load_theme(self, theme_name: str) -> Theme:
        """Load a theme from presets or a custom JSON file.

        First tries to load from preset themes, then from custom JSON files.
        Includes comprehensive error handling and always falls back to
        default theme on errors.

        Args:
            theme_name: Name of the theme to load

        Returns:
            The loaded Theme instance, or DEFAULT_THEME if loading fails

        Note:
            This method will log errors and return DEFAULT_THEME instead of
            raising exceptions, ensuring the system never crashes due to
            invalid theme files.
        """
        # First check if it's a preset theme
        normalized_name = theme_name.lower().strip()
        if normalized_name in PRESET_THEMES:
            return PRESET_THEMES[normalized_name]

        # Then try to load from custom JSON file
        theme_path = self._get_theme_path(theme_name)

        if not theme_path.exists():
            available_presets = ", ".join(list_preset_themes())
            custom_themes = self.list_custom_themes()
            if custom_themes:
                custom_list = ", ".join(custom_themes)
                message = (
                    f"Theme '{theme_name}' not found. "
                    f"Available presets: {available_presets}. "
                    f"Custom themes: {custom_list}"
                )
            else:
                message = (
                    f"Theme '{theme_name}' not found. "
                    f"Available presets: {available_presets}"
                )
            _emit_error(message)
            _emit_info("Falling back to default theme.")
            return DEFAULT_THEME

        # Read the theme file
        try:
            with open(theme_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except PermissionError as e:
            _emit_error(f"Permission denied reading theme file '{theme_path}': {e}")
            _emit_info("Falling back to default theme.")
            return DEFAULT_THEME
        except json.JSONDecodeError as e:
            _emit_error(
                f"Invalid JSON in theme file '{theme_path}': {e.msg} (line {e.lineno})"
            )
            _emit_info("Falling back to default theme.")
            return DEFAULT_THEME
        except OSError as e:
            _emit_error(f"Failed to read theme file '{theme_path}': {e}")
            _emit_info("Falling back to default theme.")
            return DEFAULT_THEME
        except Exception as e:
            _emit_error(f"Unexpected error loading theme '{theme_name}': {e}")
            _emit_info("Falling back to default theme.")
            return DEFAULT_THEME

        # Validate JSON structure
        json_errors = self._validate_theme_json(data, theme_name)
        if json_errors:
            error_msg = f"Invalid theme file '{theme_name}': {'; '.join(json_errors)}"
            _emit_error(error_msg)
            _emit_info("Falling back to default theme.")
            return DEFAULT_THEME

        # Create Theme instance from data
        try:
            theme = Theme.from_dict(data)
        except Exception as e:
            _emit_error(f"Failed to create theme from data: {e}")
            _emit_info("Falling back to default theme.")
            return DEFAULT_THEME

        # Validate the loaded theme colors
        color_errors = theme.validate_colors()
        if color_errors:
            error_msg = (
                f"Invalid colors in theme '{theme_name}': {'; '.join(color_errors)}"
            )
            _emit_error(error_msg)
            _emit_info("Falling back to default theme.")
            return DEFAULT_THEME

        return theme

    def save_theme(
        self,
        theme: Theme,
        name: str,
        description: Optional[str] = None,
        author: Optional[str] = None,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Save a theme to a JSON file with metadata.

        Args:
            theme: The Theme instance to save
            name: Name to save the theme as
            description: Optional description for the theme
            author: Optional author name for the theme
            version: Optional version string for the theme
            tags: Optional list of tags for the theme

        Raises:
            ValueError: If the theme name is invalid or theme has validation errors
            OSError: If the file cannot be written

        Note:
            This method validates both the theme name and theme colors before
            saving. Invalid theme names will be rejected with a helpful error message.
        """
        # Validate theme name
        if not validate_theme_name(name):
            raise ValueError(
                f"Invalid theme name '{name}'. "
                f"Theme names must be 1-50 characters and contain only letters, "
                f"numbers, hyphens, and underscores. No spaces or special characters."
            )

        # Validate theme colors before saving
        errors = theme.validate_colors()
        if errors:
            raise ValueError(
                f"Cannot save theme '{name}' with invalid colors: {'; '.join(errors)}"
            )

        theme_path = self._get_theme_path(name)
        temp_path = theme_path.with_suffix(".json.tmp")

        # Create backup if file already exists
        self._create_backup(theme_path)

        # Build the theme data with metadata
        theme_data = {
            "name": name,
            "description": description or "Custom theme",
            "created_at": datetime.now().isoformat(),
            "author": author,
            "version": version,
            "tags": tags or [],
        }

        # Add colors
        theme_data.update(theme.to_dict())

        # Write with restricted permissions
        try:
            # Write to a temporary file first, then rename for atomicity
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(theme_data, f, indent=2)

            # Set proper permissions on the temp file
            temp_path.chmod(0o600)

            # Atomic rename
            temp_path.replace(theme_path)

            # Ensure final file has correct permissions
            theme_path.chmod(0o600)

            _emit_info(f"Theme '{name}' saved successfully.")
        except PermissionError as e:
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            _emit_error(f"Permission denied saving theme '{name}': {e}")
            raise OSError(f"Failed to save theme '{name}': {e}") from e
        except OSError as e:
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            _emit_error(f"Failed to save theme '{name}': {e}")
            raise OSError(f"Failed to save theme '{name}': {e}") from e
        except Exception as e:
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            _emit_error(f"Unexpected error saving theme '{name}': {e}")
            raise OSError(f"Failed to save theme '{name}': {e}") from e

    def apply_theme(
        self, theme: Optional[Theme] = None, theme_name: Optional[str] = None
    ) -> bool:
        """Apply a theme as the current active theme.

        Args:
            theme: Theme to apply. If None, uses the current theme.
                  If no current theme, uses DEFAULT_THEME.
            theme_name: Optional name of the theme to save to config.
                       If provided, saves the theme name to puppy.cfg.

        Returns:
            True if theme was applied successfully, False otherwise

        Note:
            This method validates the theme before applying it. If the theme
            is invalid, it will not be applied and an error message will be shown.
            The current theme (if any) will be preserved.
        """
        # Determine which theme to apply
        if theme is None:
            theme = self._current_theme or DEFAULT_THEME
        else:
            # Validate the theme before applying
            errors = theme.validate_colors()
            if errors:
                _emit_error(f"Cannot apply invalid theme: {'; '.join(errors)}")
                _emit_warning("Current theme preserved.")
                return False

        # Apply the theme
        try:
            self._current_theme = theme

            # Save theme name to config if provided
            if theme_name is not None:
                # Validate theme name before saving to config
                if validate_theme_name(theme_name):
                    set_theme_name(theme_name)
                else:
                    _emit_warning(
                        f"Invalid theme name '{theme_name}' - not saving to config. "
                        f"Use only letters, numbers, hyphens, and underscores."
                    )

            _emit_info(f"Theme '{theme_name or 'custom'}' applied successfully.")
            return True
        except Exception as e:
            _emit_error(f"Failed to apply theme: {e}")
            _emit_warning("Current theme preserved.")
            return False

        # Note: The actual application of theme colors to the messaging system
        # will be handled by the renderer. This method just stores the current
        # theme for the renderer to query.

    def get_current_theme(self) -> Theme:
        """Get the currently active theme.

        Loads the theme from config if not already loaded.
        Defaults to 'default' theme if no theme is configured.
        Always returns a valid theme (never None or raises exceptions).

        Returns:
            The current Theme instance (defaults to DEFAULT_THEME if none set)
        """
        if self._current_theme is not None:
            return self._current_theme

        # Try to load theme from config
        theme_name = get_theme_name()
        if theme_name is None:
            theme_name = "default"

        # Load the theme (load_theme handles errors internally and returns DEFAULT_THEME)
        self._current_theme = self.load_theme(theme_name)

        return self._current_theme

    def list_available_themes(self) -> List[str]:
        """List all available theme names (both presets and custom).

        Returns:
            Sorted list of theme names (presets first, then custom themes)

        Note:
            This method handles errors gracefully and will return an empty
            list if the theme directory cannot be accessed.
        """
        # Get preset themes
        themes = set(list_preset_themes())

        # Get custom themes from JSON files (excluding backups)
        try:
            if self._theme_dir.exists():
                for path in self._theme_dir.glob("*.json"):
                    # Skip backup files
                    if path.name.endswith(".backup"):
                        continue
                    themes.add(path.stem)
        except PermissionError as e:
            _emit_warning(f"Permission denied accessing theme directory: {e}")
            _emit_info("Only preset themes will be available.")
        except OSError as e:
            _emit_warning(f"Error accessing theme directory: {e}")
            _emit_info("Only preset themes will be available.")

        return sorted(themes)

    def list_custom_themes(self) -> List[str]:
        """List only custom themes (excludes presets).

        Scans the themes directory for .json files and returns their names.
        Backup files (*.json.backup) are excluded.

        Returns:
            Sorted list of custom theme names

        Note:
            This method handles errors gracefully and will return an empty
            list if the theme directory cannot be accessed.
        """
        custom_themes: List[str] = []

        try:
            if not self._theme_dir.exists():
                return custom_themes

            for path in self._theme_dir.glob("*.json"):
                # Skip backup files
                if path.name.endswith(".backup"):
                    continue
                custom_themes.append(path.stem)
        except PermissionError as e:
            _emit_warning(f"Permission denied accessing theme directory: {e}")
        except OSError as e:
            _emit_warning(f"Error accessing theme directory: {e}")

        return sorted(custom_themes)

    def delete_theme(self, theme_name: str) -> bool:
        """Delete a custom theme.

        Args:
            theme_name: Name of the theme to delete

        Returns:
            True if theme was deleted successfully, False otherwise

        Raises:
            ValueError: If the theme name is invalid or theme is a preset theme

        Note:
            This method validates the theme name and handles errors gracefully.
            Preset themes cannot be deleted.
        """
        # Validate theme name
        if not validate_theme_name(theme_name):
            raise ValueError(
                f"Invalid theme name '{theme_name}'. "
                f"Theme names must be 1-50 characters and contain only letters, "
                f"numbers, hyphens, and underscores."
            )

        # Check if it's a preset theme
        normalized_name = theme_name.lower().strip()
        if normalized_name in PRESET_THEMES:
            raise ValueError(
                f"Cannot delete preset theme '{theme_name}'. "
                "Only custom themes can be deleted."
            )

        theme_path = self._get_theme_path(theme_name)

        if not theme_path.exists():
            available_custom = self.list_custom_themes()
            if available_custom:
                custom_list = ", ".join(available_custom)
                raise ValueError(
                    f"Custom theme '{theme_name}' does not exist. "
                    f"Available custom themes: {custom_list}"
                )
            else:
                raise ValueError(
                    f"Custom theme '{theme_name}' does not exist. "
                    f"No custom themes are available."
                )

        try:
            # Delete the main theme file
            theme_path.unlink()

            # Also delete the backup file if it exists
            backup_path = self._get_backup_path(theme_name)
            if backup_path.exists():
                backup_path.unlink()

            _emit_info(f"Theme '{theme_name}' deleted successfully.")
            return True
        except PermissionError as e:
            _emit_error(f"Permission denied deleting theme '{theme_name}': {e}")
            return False
        except OSError as e:
            _emit_error(f"Failed to delete theme '{theme_name}': {e}")
            return False
        except Exception as e:
            _emit_error(f"Unexpected error deleting theme '{theme_name}': {e}")
            return False

    def export_theme(self, theme_name: str, path: str) -> bool:
        """Export a theme to a file.

        Args:
            theme_name: Name of the theme to export
            path: Path to export the theme to

        Returns:
            True if export was successful, False otherwise

        Note:
            This method handles errors gracefully and will not crash the
            system if the export fails.
        """
        # Load the theme (works for both presets and custom themes)
        theme = self.load_theme(theme_name)

        # Check if we got the default theme (which means loading failed)
        available_themes = self.list_available_themes()
        if theme_name not in available_themes:
            _emit_error(
                f"Theme '{theme_name}' not found. "
                f"Available themes: {', '.join(available_themes)}"
            )
            return False

        export_path = Path(path)

        # Build export data with metadata
        export_data = {
            "name": theme_name,
            "description": getattr(
                theme, "_description", f"Exported theme: {theme_name}"
            ),
            "exported_at": datetime.now().isoformat(),
        }
        export_data.update(theme.to_dict())

        # Ensure parent directory exists
        try:
            export_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            _emit_error(
                f"Permission denied creating directory '{export_path.parent}': {e}"
            )
            return False
        except OSError as e:
            _emit_error(f"Failed to create directory '{export_path.parent}': {e}")
            return False

        # Write the export file
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            _emit_info(f"Theme '{theme_name}' exported to '{path}'.")
            return True
        except PermissionError as e:
            _emit_error(f"Permission denied writing to '{path}': {e}")
            return False
        except OSError as e:
            _emit_error(f"Failed to export theme '{theme_name}' to '{path}': {e}")
            return False
        except Exception as e:
            _emit_error(f"Unexpected error exporting theme '{theme_name}': {e}")
            return False

    def import_theme(self, path: str, name: Optional[str] = None) -> Optional[str]:
        """Import a theme from a file.

        Args:
            path: Path to the theme file to import
            name: Name to save the theme as. If None, uses the name from the file
                 or derives it from the filename

        Returns:
            The name the theme was imported as, or None if import failed

        Note:
            This method validates the theme name and handles errors gracefully.
            Invalid theme files will not crash the system.
        """
        import_path = Path(path)

        # Check if file exists
        try:
            if not import_path.exists():
                _emit_error(f"Theme file not found: '{path}'")
                return None
        except OSError as e:
            _emit_error(f"Error accessing theme file '{path}': {e}")
            return None

        # Read and parse the theme file
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except PermissionError as e:
            _emit_error(f"Permission denied reading theme file '{path}': {e}")
            return None
        except json.JSONDecodeError as e:
            _emit_error(
                f"Invalid JSON in theme file '{path}': {e.msg} (line {e.lineno})"
            )
            return None
        except OSError as e:
            _emit_error(f"Failed to read theme file '{path}': {e}")
            return None
        except Exception as e:
            _emit_error(f"Unexpected error reading theme file '{path}': {e}")
            return None

        # Determine the theme name
        if name is None:
            # Try to get name from the file
            name = data.get("name")
            if name is None:
                # Derive from filename
                name = import_path.stem

        if not name or not isinstance(name, str):
            _emit_error("Theme name must be a non-empty string")
            return None

        # Validate theme name
        if not validate_theme_name(name):
            _emit_error(
                f"Invalid theme name '{name}'. "
                f"Theme names must be 1-50 characters and contain only letters, "
                f"numbers, hyphens, and underscores."
            )
            return None

        # Validate JSON structure
        json_errors = self._validate_theme_json(data, name)
        if json_errors:
            _emit_error(
                f"Imported theme has invalid JSON structure: {'; '.join(json_errors)}"
            )
            return None

        # Create Theme instance and validate colors
        try:
            theme = Theme.from_dict(data)
        except Exception as e:
            _emit_error(f"Failed to create theme from imported data: {e}")
            return None

        color_errors = theme.validate_colors()
        if color_errors:
            _emit_error(f"Imported theme has invalid colors: {'; '.join(color_errors)}")
            return None

        # Save the theme
        try:
            description = data.get("description")
            self.save_theme(theme, name, description=description)
            return name
        except (ValueError, OSError) as e:
            _emit_error(f"Failed to save imported theme '{name}': {e}")
            return None
        except Exception as e:
            _emit_error(f"Unexpected error saving imported theme '{name}': {e}")
            return None


# =============================================================================
# Config Integration Functions
# =============================================================================


def get_theme_name() -> Optional[str]:
    """Get the current theme name from puppy.cfg config.

    Returns:
        The theme name if set, None otherwise

    Example:
        >>> from code_puppy.themes import get_theme_name
        >>> theme_name = get_theme_name()
        >>> print(theme_name)
        'midnight'
    """
    return get_value("theme")


def set_theme_name(theme_name: str) -> None:
    """Save the theme name to puppy.cfg config.

    Args:
        theme_name: Name of the theme to save

    Example:
        >>> from code_puppy.themes import set_theme_name
        >>> set_theme_name("midnight")
    """
    set_config_value("theme", theme_name)


# =============================================================================
# Helper Functions
# =============================================================================


def get_all_themes() -> Dict[str, Theme]:
    """Get all available themes (presets and custom).

    Returns:
        Dictionary mapping theme names to Theme instances

    Note:
        This method handles errors gracefully and will skip invalid
        custom themes rather than crashing.

    Example:
        >>> from code_puppy.themes import get_all_themes
        >>> themes = get_all_themes()
        >>> for name, theme in themes.items():
        ...     print(f"{name}: {theme.error_color}")
    """
    themes: Dict[str, Theme] = {}

    # Add preset themes
    themes.update(PRESET_THEMES)

    # Add custom themes from JSON files
    manager = ThemeManager()
    for theme_name in manager.list_available_themes():
        normalized_name = theme_name.lower().strip()
        if normalized_name not in themes:  # Don't override presets
            try:
                themes[normalized_name] = manager.load_theme(theme_name)
            except Exception:
                # Skip invalid custom themes - load_theme already logs errors
                continue

    return themes


def is_preset_theme(name: str) -> bool:
    """Check if a theme is a preset theme.

    Args:
        name: Name of the theme to check (case-insensitive)

    Returns:
        True if the theme is a preset, False otherwise

    Example:
        >>> from code_puppy.themes import is_preset_theme
        >>> is_preset_theme("midnight")
        True
        >>> is_preset_theme("my_custom_theme")
        False
    """
    normalized_name = name.lower().strip()
    return normalized_name in PRESET_THEMES


def get_theme_info(
    name: str, theme_dir: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Get theme metadata (name, description, author, version, tags, is_preset).

    Args:
        name: Name of the theme (case-insensitive)
        theme_dir: Optional directory to look for custom themes.
                   Defaults to the default theme directory.

    Returns:
        Dictionary with theme info or None if theme doesn't exist.
        Keys: 'name', 'description', 'author', 'version', 'tags', 'is_preset'

    Note:
        This method handles errors gracefully and will return None if the
        theme file cannot be read.

    Example:
        >>> from code_puppy.themes import get_theme_info
        >>> info = get_theme_info("midnight")
        >>> print(info['description'])
        Deep blues and purples - mysterious and elegant for night coding
    """
    normalized_name = name.lower().strip()

    # Check if it's a preset theme
    if normalized_name in PRESET_THEMES:
        theme = PRESET_THEMES[normalized_name]
        return {
            "name": normalized_name,
            "description": getattr(
                theme,
                "_description",
                PRESET_THEME_DESCRIPTIONS.get(
                    normalized_name, "No description available"
                ),
            ),
            "author": getattr(theme, "_author", None),
            "version": getattr(theme, "_version", None),
            "tags": getattr(theme, "_tags", []),
            "is_preset": True,
        }

    # Check if it's a custom theme
    manager = ThemeManager(theme_dir=theme_dir)
    theme_path = manager._get_theme_path(name)
    if theme_path.exists():
        try:
            with open(theme_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "name": normalized_name,
                "description": data.get("description", "Custom theme"),
                "author": data.get("author"),
                "version": data.get("version"),
                "tags": data.get("tags", []),
                "is_preset": False,
            }
        except PermissionError:
            _emit_warning(f"Permission denied reading theme file: {theme_path}")
            return None
        except json.JSONDecodeError:
            _emit_warning(f"Invalid JSON in theme file: {theme_path}")
            return None
        except (OSError, IOError):
            _emit_warning(f"Error reading theme file: {theme_path}")
            return None

    # Theme doesn't exist
    return None


# =============================================================================
# Global Theme Manager Instance
# =============================================================================

# Global instance for convenience
_global_theme_manager: Optional[ThemeManager] = None


def get_theme_manager() -> ThemeManager:
    """Get the global ThemeManager instance.

    Creates the instance on first call and reuses it for subsequent calls.

    Returns:
        The global ThemeManager instance
    """
    global _global_theme_manager
    if _global_theme_manager is None:
        _global_theme_manager = ThemeManager()
    return _global_theme_manager
