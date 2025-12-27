import importlib
import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# User plugins directory
USER_PLUGINS_DIR = Path.home() / ".code_puppy" / "plugins"

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


def load_plugin_callbacks() -> dict[str, list[str]]:
    """Dynamically load register_callbacks.py from all plugin sources.

    Loads plugins from:
    1. Built-in plugins in the code_puppy/plugins/ directory
    2. User plugins in ~/.code_puppy/plugins/

    Returns dict with 'builtin' and 'user' keys containing lists of loaded plugin names.

    NOTE: This function is idempotent - calling it multiple times will only
    load plugins once. Subsequent calls return empty lists.
    """
    global _PLUGINS_LOADED

    # Prevent duplicate loading - plugins register callbacks at import time,
    # so re-importing would cause duplicate registrations
    if _PLUGINS_LOADED:
        logger.debug("Plugins already loaded, skipping duplicate load")
        return {"builtin": [], "user": []}

    plugins_dir = Path(__file__).parent

    result = {
        "builtin": _load_builtin_plugins(plugins_dir),
        "user": _load_user_plugins(USER_PLUGINS_DIR),
    }

    _PLUGINS_LOADED = True
    logger.debug(f"Loaded plugins: builtin={result['builtin']}, user={result['user']}")

    return result


def get_user_plugins_dir() -> Path:
    """Return the path to the user plugins directory."""
    return USER_PLUGINS_DIR


def ensure_user_plugins_dir() -> Path:
    """Create the user plugins directory if it doesn't exist.

    Returns the path to the directory.
    """
    USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return USER_PLUGINS_DIR
