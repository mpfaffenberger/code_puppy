"""Plugin loading system for Code Puppy.

This module provides a flexible plugin architecture that supports:

1. **Built-in plugins**: Shipped with Code Puppy in code_puppy/plugins/
2. **User plugins**: Installed in ~/.code_puppy/plugins/
3. **External plugins**: Registered via ~/.code_puppy/external_plugins.json

External plugins can live anywhere on the filesystem and register themselves
via a simple JSON registry, enabling plugins to be distributed as separate
git repositories.

Example external_plugins.json:
    {
        "version": 1,
        "plugins": [
            {
                "name": "my-plugin",
                "path": "/path/to/my-plugin",
                "enabled": true
            }
        ]
    }
"""

import importlib
import importlib.util
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

# User plugins directory
USER_PLUGINS_DIR = Path.home() / ".code_puppy" / "plugins"

# External plugins registry file
EXTERNAL_PLUGINS_REGISTRY = Path.home() / ".code_puppy" / "external_plugins.json"

# Current registry schema version
REGISTRY_VERSION = 1

# Track if plugins have already been loaded to prevent duplicate registration
_PLUGINS_LOADED = False


def _load_builtin_plugins(plugins_dir: Path) -> list[str]:
    """Load built-in plugins from the package plugins directory.

    Returns list of successfully loaded plugin names.
    """
    # Import safety permission check for shell_safety plugin
    from code_puppy.config import get_safety_permission_level

    loaded = []

    for item in plugins_dir.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            plugin_name = item.name
            callbacks_file = item / "register_callbacks.py"

            if callbacks_file.exists():
                # Skip shell_safety plugin unless safety_permission_level is "low" or "none"
                if plugin_name == "shell_safety":
                    safety_level = get_safety_permission_level()
                    if safety_level not in ("none", "low"):
                        logger.debug(
                            f"Skipping shell_safety plugin - safety_permission_level is '{safety_level}' (needs 'low' or 'none')"
                        )
                        continue

                try:
                    module_name = f"code_puppy.plugins.{plugin_name}.register_callbacks"
                    importlib.import_module(module_name)
                    loaded.append(plugin_name)
                except ImportError as e:
                    logger.warning(
                        f"Failed to import callbacks from built-in plugin {plugin_name}: {e}"
                    )
                except Exception as e:
                    logger.error(
                        f"Unexpected error loading built-in plugin {plugin_name}: {e}"
                    )

    return loaded


def _load_user_plugins(user_plugins_dir: Path) -> list[str]:
    """Load user plugins from ~/.code_puppy/plugins/.

    Each plugin should be a directory containing a register_callbacks.py file.
    Plugins are loaded by adding their parent to sys.path and importing them.

    Returns list of successfully loaded plugin names.
    """
    loaded = []

    if not user_plugins_dir.exists():
        return loaded

    if not user_plugins_dir.is_dir():
        logger.warning(f"User plugins path is not a directory: {user_plugins_dir}")
        return loaded

    # Add user plugins directory to sys.path if not already there
    user_plugins_str = str(user_plugins_dir)
    if user_plugins_str not in sys.path:
        sys.path.insert(0, user_plugins_str)

    for item in user_plugins_dir.iterdir():
        if (
            item.is_dir()
            and not item.name.startswith("_")
            and not item.name.startswith(".")
        ):
            plugin_name = item.name
            callbacks_file = item / "register_callbacks.py"

            if callbacks_file.exists():
                try:
                    # Load the plugin module directly from the file
                    module_name = f"{plugin_name}.register_callbacks"
                    spec = importlib.util.spec_from_file_location(
                        module_name, callbacks_file
                    )
                    if spec is None or spec.loader is None:
                        logger.warning(
                            f"Could not create module spec for user plugin: {plugin_name}"
                        )
                        continue

                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module

                    spec.loader.exec_module(module)
                    loaded.append(plugin_name)

                except ImportError as e:
                    logger.warning(
                        f"Failed to import callbacks from user plugin {plugin_name}: {e}"
                    )
                except Exception as e:
                    logger.error(
                        f"Unexpected error loading user plugin {plugin_name}: {e}",
                        exc_info=True,
                    )
            else:
                # Check if there's an __init__.py - might be a simple plugin
                init_file = item / "__init__.py"
                if init_file.exists():
                    try:
                        module_name = plugin_name
                        spec = importlib.util.spec_from_file_location(
                            module_name, init_file
                        )
                        if spec is None or spec.loader is None:
                            continue

                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                        loaded.append(plugin_name)

                    except Exception as e:
                        logger.error(
                            f"Unexpected error loading user plugin {plugin_name}: {e}",
                            exc_info=True,
                        )

    return loaded


class LoadedPluginsResult(TypedDict):
    """Type definition for the result of load_plugin_callbacks.

    Attributes:
        builtin: List of loaded built-in plugin names.
        user: List of loaded user plugin names.
        external: List of loaded external plugin names.
    """

    builtin: list[str]
    user: list[str]
    external: list[str]


def load_plugin_callbacks() -> LoadedPluginsResult:
    """Dynamically load register_callbacks.py from all plugin sources.

    Loads plugins from three sources in order:

    1. **Built-in plugins**: Shipped with Code Puppy in code_puppy/plugins/
    2. **User plugins**: Installed in ~/.code_puppy/plugins/
    3. **External plugins**: Registered in ~/.code_puppy/external_plugins.json

    External plugins can live anywhere on the filesystem, making it easy
    to develop and distribute plugins as separate git repositories.

    Returns:
        Dictionary with 'builtin', 'user', and 'external' keys containing
        lists of successfully loaded plugin names.

    Note:
        This function is idempotent. Calling it multiple times will only
        load plugins once. Subsequent calls return empty lists.

    Example:
        >>> result = load_plugin_callbacks()
        >>> print(f"Loaded {len(result['external'])} external plugins")
    """
    global _PLUGINS_LOADED

    # Prevent duplicate loading - plugins register callbacks at import time,
    # so re-importing would cause duplicate registrations
    if _PLUGINS_LOADED:
        logger.debug("Plugins already loaded, skipping duplicate load")
        return {"builtin": [], "user": [], "external": []}

    plugins_dir = Path(__file__).parent

    result: LoadedPluginsResult = {
        "builtin": _load_builtin_plugins(plugins_dir),
        "user": _load_user_plugins(USER_PLUGINS_DIR),
        "external": _load_external_plugins(),
    }

    _PLUGINS_LOADED = True

    total_loaded = (
        len(result["builtin"]) + len(result["user"]) + len(result["external"])
    )
    logger.debug(
        f"Loaded {total_loaded} plugins: "
        f"builtin={result['builtin']}, "
        f"user={result['user']}, "
        f"external={result['external']}"
    )

    return result


class ExternalPluginEntry(TypedDict, total=False):
    """Type definition for an external plugin registry entry.

    Attributes:
        name: Unique identifier for the plugin.
        path: Absolute path to the plugin directory.
        enabled: Whether the plugin should be loaded. Defaults to True.
        installed_at: ISO 8601 timestamp of when the plugin was registered.
        description: Optional human-readable description.
    """

    name: str
    path: str
    enabled: bool
    installed_at: str
    description: str


class ExternalPluginRegistry(TypedDict):
    """Type definition for the external plugins registry file.

    Attributes:
        version: Schema version for forward compatibility.
        plugins: List of registered external plugins.
    """

    version: int
    plugins: list[ExternalPluginEntry]


def _load_external_plugins() -> list[str]:
    """Load external plugins registered in ~/.code_puppy/external_plugins.json.

    External plugins can live anywhere on the filesystem. They register
    themselves by adding an entry to the registry JSON file. This enables
    plugins to be distributed as separate git repositories.

    Returns:
        List of successfully loaded plugin names.

    Raises:
        No exceptions are raised. All errors are logged and skipped.
    """
    loaded: list[str] = []

    if not EXTERNAL_PLUGINS_REGISTRY.exists():
        logger.debug("No external plugins registry found")
        return loaded

    try:
        registry = _read_external_registry()
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read external plugins registry: {e}")
        return loaded

    for plugin_entry in registry.get("plugins", []):
        plugin_name = plugin_entry.get("name", "unknown")

        if not plugin_entry.get("enabled", True):
            logger.debug(f"Skipping disabled external plugin: {plugin_name}")
            continue

        plugin_path = Path(plugin_entry.get("path", ""))

        if not plugin_path.exists():
            logger.warning(
                f"External plugin path does not exist: {plugin_name} -> {plugin_path}"
            )
            continue

        if not plugin_path.is_dir():
            logger.warning(
                f"External plugin path is not a directory: {plugin_name} -> {plugin_path}"
            )
            continue

        callbacks_file = plugin_path / "register_callbacks.py"

        if not callbacks_file.exists():
            logger.warning(
                f"External plugin missing register_callbacks.py: {plugin_name}"
            )
            continue

        try:
            # Add plugin directory to sys.path for imports
            plugin_path_str = str(plugin_path)
            if plugin_path_str not in sys.path:
                sys.path.insert(0, plugin_path_str)

            # Load the plugin module
            module_name = f"external_plugin_{plugin_name.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(module_name, callbacks_file)

            if spec is None or spec.loader is None:
                logger.warning(
                    f"Could not create module spec for external plugin: {plugin_name}"
                )
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            loaded.append(plugin_name)
            logger.info(f"Loaded external plugin: {plugin_name} from {plugin_path}")

        except ImportError as e:
            logger.warning(f"Failed to import external plugin {plugin_name}: {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error loading external plugin {plugin_name}: {e}",
                exc_info=True,
            )

    return loaded


def _read_external_registry() -> ExternalPluginRegistry:
    """Read and parse the external plugins registry file.

    Returns:
        Parsed registry data.

    Raises:
        json.JSONDecodeError: If the file contains invalid JSON.
        OSError: If the file cannot be read.
    """
    content = EXTERNAL_PLUGINS_REGISTRY.read_text(encoding="utf-8")
    data: ExternalPluginRegistry = json.loads(content)

    # Validate version for forward compatibility
    file_version = data.get("version", 1)
    if file_version > REGISTRY_VERSION:
        logger.warning(
            f"External plugins registry version {file_version} is newer than "
            f"supported version {REGISTRY_VERSION}. Some features may not work."
        )

    return data


def _write_external_registry(registry: ExternalPluginRegistry) -> None:
    """Write the external plugins registry to disk.

    Args:
        registry: The registry data to write.

    Raises:
        OSError: If the file cannot be written.
    """
    EXTERNAL_PLUGINS_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(registry, indent=2, ensure_ascii=False)
    EXTERNAL_PLUGINS_REGISTRY.write_text(content, encoding="utf-8")


def _create_empty_registry() -> ExternalPluginRegistry:
    """Create a new empty external plugins registry.

    Returns:
        Empty registry with current schema version.
    """
    return {"version": REGISTRY_VERSION, "plugins": []}


def register_external_plugin(
    name: str,
    path: str | Path,
    description: str = "",
    enabled: bool = True,
) -> bool:
    """Register an external plugin in the registry.

    This function is typically called by a plugin's setup script to add
    itself to the registry. If a plugin with the same name already exists,
    it will be updated with the new path and settings.

    Args:
        name: Unique identifier for the plugin (e.g., "my-awesome-plugin").
        path: Absolute path to the plugin directory containing register_callbacks.py.
        description: Optional human-readable description of the plugin.
        enabled: Whether the plugin should be loaded on startup.

    Returns:
        True if registration succeeded, False otherwise.

    Example:
        >>> register_external_plugin(
        ...     name="msgraph-agent",
        ...     path="/Users/trevor/repos/msgraph-plugin",
        ...     description="Microsoft Graph integration for Code Puppy",
        ... )
        True
    """
    try:
        plugin_path = Path(path).resolve()

        if not plugin_path.exists():
            logger.error(f"Plugin path does not exist: {plugin_path}")
            return False

        callbacks_file = plugin_path / "register_callbacks.py"
        if not callbacks_file.exists():
            logger.error(f"Plugin missing register_callbacks.py: {plugin_path}")
            return False

        # Load existing registry or create new one
        if EXTERNAL_PLUGINS_REGISTRY.exists():
            registry = _read_external_registry()
        else:
            registry = _create_empty_registry()

        # Remove existing entry with same name (update case)
        registry["plugins"] = [p for p in registry["plugins"] if p.get("name") != name]

        # Add new entry
        new_entry: ExternalPluginEntry = {
            "name": name,
            "path": str(plugin_path),
            "enabled": enabled,
            "installed_at": datetime.now().isoformat(),
        }
        if description:
            new_entry["description"] = description

        registry["plugins"].append(new_entry)

        _write_external_registry(registry)
        logger.info(f"Registered external plugin: {name} at {plugin_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to register external plugin {name}: {e}")
        return False


def unregister_external_plugin(name: str) -> bool:
    """Remove an external plugin from the registry.

    This function is typically called by a plugin's uninstall script.
    It only removes the registry entry; it does not delete any files.

    Args:
        name: The unique identifier of the plugin to remove.

    Returns:
        True if the plugin was found and removed, False otherwise.

    Example:
        >>> unregister_external_plugin("msgraph-agent")
        True
    """
    try:
        if not EXTERNAL_PLUGINS_REGISTRY.exists():
            logger.warning("No external plugins registry found")
            return False

        registry = _read_external_registry()
        original_count = len(registry["plugins"])

        registry["plugins"] = [p for p in registry["plugins"] if p.get("name") != name]

        if len(registry["plugins"]) == original_count:
            logger.warning(f"External plugin not found in registry: {name}")
            return False

        _write_external_registry(registry)
        logger.info(f"Unregistered external plugin: {name}")
        return True

    except Exception as e:
        logger.error(f"Failed to unregister external plugin {name}: {e}")
        return False


def list_external_plugins() -> list[ExternalPluginEntry]:
    """List all registered external plugins.

    Returns:
        List of external plugin entries from the registry.
        Returns an empty list if the registry doesn't exist or is invalid.

    Example:
        >>> plugins = list_external_plugins()
        >>> for p in plugins:
        ...     print(f"{p['name']}: {p['path']} (enabled={p.get('enabled', True)})")
    """
    if not EXTERNAL_PLUGINS_REGISTRY.exists():
        return []

    try:
        registry = _read_external_registry()
        return registry.get("plugins", [])
    except Exception as e:
        logger.error(f"Failed to list external plugins: {e}")
        return []


def get_user_plugins_dir() -> Path:
    """Return the path to the user plugins directory.

    Returns:
        Path to ~/.code_puppy/plugins/
    """
    return USER_PLUGINS_DIR


def get_external_plugins_registry_path() -> Path:
    """Return the path to the external plugins registry file.

    Returns:
        Path to ~/.code_puppy/external_plugins.json
    """
    return EXTERNAL_PLUGINS_REGISTRY


def ensure_user_plugins_dir() -> Path:
    """Create the user plugins directory if it doesn't exist.

    Returns:
        Path to the created or existing directory.
    """
    USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return USER_PLUGINS_DIR
