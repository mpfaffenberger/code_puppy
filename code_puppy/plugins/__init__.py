import importlib
import importlib.util
import logging
import sys
import types
from pathlib import Path

from code_puppy.callbacks import clear_loading_context, set_loading_context

logger = logging.getLogger(__name__)

# User plugins directory
USER_PLUGINS_DIR = Path.home() / ".mist" / "plugins"
LEGACY_USER_PLUGINS_DIR = Path.home() / ".code_puppy" / "plugins"

# Track if plugins have already been loaded to prevent duplicate registration
_PLUGINS_LOADED = False

# Stores the loaded plugin names by tier after the first load_plugin_callbacks() call.
# Populated once, then read by get_loaded_plugins().
_loaded_plugin_names: dict[str, list[str]] = {"builtin": [], "user": [], "project": []}


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
                    set_loading_context(plugin_name)
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
                finally:
                    clear_loading_context()

    return loaded


def _scan_plugin_names(plugins_dir: Path) -> set[str]:
    """Return the set of plugin directory names under *plugins_dir*.

    Only performs a cheap filesystem scan — nothing is imported.  Used to
    pre-detect project plugin names so that ``_load_user_plugins`` can
    skip names that the project tier will supersede (project wins on
    collision, matching the agents dedup strategy).
    """
    names: set[str] = set()
    if not plugins_dir.is_dir():
        return names
    for item in plugins_dir.iterdir():
        if (
            item.is_dir()
            and not item.name.startswith("_")
            and not item.name.startswith(".")
        ):
            # Only count it if it actually has a loadable entry point
            if (item / "register_callbacks.py").exists() or (
                item / "__init__.py"
            ).exists():
                names.add(item.name)
    return names


def _load_user_plugins(
    user_plugins_dir: Path,
    skip_names: set[str] | None = None,
) -> list[str]:
    """Load user plugins from ~/.mist/plugins/.

    Each plugin should be a directory containing a register_callbacks.py file.
    Plugins are loaded by adding their parent to sys.path and importing them.

    *skip_names*, when provided, is a set of plugin names that will be loaded
    from a higher-precedence tier (project plugins).  User plugins whose name
    appears in this set are skipped so that only one copy registers callbacks
    (matching the agents dedup strategy).

    Returns list of successfully loaded plugin names.
    """
    loaded = []
    skip_names = set(skip_names or ())

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

            if plugin_name in skip_names:
                logger.info(
                    "Skipping user plugin '%s' because a higher-precedence "
                    "plugin with the same name is already loaded or scheduled",
                    plugin_name,
                )
                continue

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

                    set_loading_context(plugin_name)
                    try:
                        spec.loader.exec_module(module)
                    finally:
                        clear_loading_context()
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
                        set_loading_context(plugin_name)
                        try:
                            spec.loader.exec_module(module)
                        finally:
                            clear_loading_context()
                        loaded.append(plugin_name)

                    except Exception as e:
                        logger.error(
                            f"Unexpected error loading user plugin {plugin_name}: {e}",
                            exc_info=True,
                        )

    return loaded


_PROJECT_PLUGINS_NS = "project_plugins"


def _ensure_project_ns() -> None:
    """Create the synthetic ``project_plugins`` namespace package.

    Needed once so that ``project_plugins.<name>.register_callbacks`` can
    resolve relative imports (``from . import state``, etc.).  Without a
    parent package in ``sys.modules`` Python raises ``ModuleNotFoundError``
    when it encounters ``from .``.
    """
    if _PROJECT_PLUGINS_NS not in sys.modules:
        ns_pkg = types.ModuleType(_PROJECT_PLUGINS_NS)
        ns_pkg.__path__ = []  # namespace package
        ns_pkg.__package__ = _PROJECT_PLUGINS_NS
        sys.modules[_PROJECT_PLUGINS_NS] = ns_pkg


def _ensure_plugin_package(plugin_dir: Path, plugin_name: str) -> bool:
    """Register a synthetic package for *plugin_name* under the project namespace.

    If the plugin directory contains an ``__init__.py`` it is executed so
    that any package-level attributes (``__version__``, etc.) are available.
    Otherwise a bare namespace module is created with ``__path__`` pointing
    at the plugin directory — enough for the import machinery to locate
    sibling modules when ``register_callbacks.py`` does relative imports.

    Returns ``True`` if a real ``__init__.py`` was executed, ``False`` if a
    bare namespace fallback was used (no init, or spec/loader was ``None``).
    """
    pkg_name = f"{_PROJECT_PLUGINS_NS}.{plugin_name}"
    if pkg_name in sys.modules:
        return True

    init_file = plugin_dir / "__init__.py"
    if init_file.exists():
        spec_init = importlib.util.spec_from_file_location(
            pkg_name,
            init_file,
            submodule_search_locations=[str(plugin_dir)],
        )
        if spec_init is None or spec_init.loader is None:
            # Fallback: bare namespace (init exists but can't be loaded)
            pkg_mod = types.ModuleType(pkg_name)
            pkg_mod.__path__ = [str(plugin_dir)]
            pkg_mod.__package__ = pkg_name
            sys.modules[pkg_name] = pkg_mod
            return False

        pkg_mod = importlib.util.module_from_spec(spec_init)
        sys.modules[pkg_name] = pkg_mod
        spec_init.loader.exec_module(pkg_mod)
        return True
    else:
        pkg_mod = types.ModuleType(pkg_name)
        pkg_mod.__path__ = [str(plugin_dir)]
        pkg_mod.__package__ = pkg_name
        sys.modules[pkg_name] = pkg_mod
        return False


def _load_project_plugins(
    project_plugins_dir: Path,
    builtin_names: set[str],
    user_names: set[str],
) -> list[str]:
    """Load project plugins from <CWD>/.mist/plugins/.

    Mirrors _load_user_plugins() but uses a ``project_plugins.`` sys.modules
    namespace and warns on name collisions with builtin or user plugins.

    Before loading each plugin's ``register_callbacks.py``, a synthetic
    parent package is registered in ``sys.modules`` so that relative
    imports (``from . import state``, ``from .utils import …``) resolve
    correctly.

    Returns list of successfully loaded plugin names.
    """
    loaded = []

    if not project_plugins_dir.exists():
        return loaded

    if not project_plugins_dir.is_dir():
        logger.warning(
            f"Project plugins path is not a directory: {project_plugins_dir}"
        )
        return loaded

    project_plugins_str = str(project_plugins_dir)
    if project_plugins_str not in sys.path:
        sys.path.insert(0, project_plugins_str)

    # Create the top-level namespace package once
    _ensure_project_ns()

    for item in project_plugins_dir.iterdir():
        if (
            item.is_dir()
            and not item.name.startswith("_")
            and not item.name.startswith(".")
        ):
            plugin_name = item.name

            # Warn if a project plugin shadows a builtin (user collisions
            # are handled earlier by skipping the user plugin entirely).
            if plugin_name in builtin_names:
                logger.warning(
                    f"Project plugin '{plugin_name}' shadows builtin plugin of the same name"
                )

            callbacks_file = item / "register_callbacks.py"

            if callbacks_file.exists():
                try:
                    # Register parent package so relative imports resolve
                    _ensure_plugin_package(item, plugin_name)

                    module_name = (
                        f"{_PROJECT_PLUGINS_NS}.{plugin_name}.register_callbacks"
                    )
                    spec = importlib.util.spec_from_file_location(
                        module_name, callbacks_file
                    )
                    if spec is None or spec.loader is None:
                        logger.warning(
                            f"Could not create module spec for project plugin: {plugin_name}"
                        )
                        continue

                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    set_loading_context(plugin_name)
                    try:
                        spec.loader.exec_module(module)
                    finally:
                        clear_loading_context()
                    loaded.append(plugin_name)

                except ImportError as e:
                    logger.warning(
                        f"Failed to import callbacks from project plugin {plugin_name}: {e}"
                    )
                except Exception as e:
                    logger.error(
                        f"Unexpected error loading project plugin {plugin_name}: {e}",
                        exc_info=True,
                    )
            else:
                # Fallback to __init__.py (mirrors user plugin behavior)
                init_file = item / "__init__.py"
                if init_file.exists():
                    try:
                        set_loading_context(plugin_name)
                        try:
                            loaded_ok = _ensure_plugin_package(item, plugin_name)
                        finally:
                            clear_loading_context()
                        if loaded_ok:
                            loaded.append(plugin_name)
                        else:
                            logger.warning(
                                f"Could not load __init__.py for project plugin: {plugin_name}"
                            )

                    except Exception as e:
                        logger.error(
                            f"Unexpected error loading project plugin {plugin_name}: {e}",
                            exc_info=True,
                        )

    return loaded


def get_project_plugins_directory() -> Path | None:
    """Get the project-local plugins directory path.

    Looks for a .mist/plugins/ directory in the current working directory.
    Does NOT create the directory if it doesn't exist — the team must create it
    intentionally.

    Returns:
        Path to the project's plugins directory if it exists, or None.
    """
    project_plugins_dir = Path.cwd() / ".mist" / "plugins"
    if project_plugins_dir.is_dir():
        return project_plugins_dir
    legacy_plugins_dir = Path.cwd() / ".code_puppy" / "plugins"
    if legacy_plugins_dir.is_dir():
        return legacy_plugins_dir
    return None


def load_plugin_callbacks() -> dict[str, list[str]]:
    """Dynamically load register_callbacks.py from all plugin sources.

    Loads plugins from:
    1. Built-in plugins in the code_puppy/plugins/ directory
    2. User plugins in ~/.mist/plugins/
    3. Project plugins in <CWD>/.mist/plugins/

    Returns dict with 'builtin', 'user', and 'project' keys containing
    lists of loaded plugin names.

    NOTE: This function is idempotent - calling it multiple times will only
    load plugins once. Subsequent calls return empty lists.
    """
    global _PLUGINS_LOADED

    # Prevent duplicate loading - plugins register callbacks at import time,
    # so re-importing would cause duplicate registrations
    if _PLUGINS_LOADED:
        logger.debug("Plugins already loaded, skipping duplicate load")
        return {"builtin": [], "user": [], "project": []}

    from code_puppy.config import _migrate_legacy_storage

    _migrate_legacy_storage()

    plugins_dir = Path(__file__).parent

    # Pre-scan project plugin names so we can skip user plugins that the
    # project tier will supersede (project wins, matching agents dedup).
    project_plugins_dir = get_project_plugins_directory()
    if project_plugins_dir is not None:
        from code_puppy.project_trust import ensure_project_trusted

        project_root = project_plugins_dir.parent.parent
        if not ensure_project_trusted(project_root):
            logger.warning(
                "Skipping untrusted project plugins from %s. "
                "Use /trust project and restart to enable them.",
                project_plugins_dir,
            )
            project_plugins_dir = None
    project_plugin_names = (
        _scan_plugin_names(project_plugins_dir)
        if project_plugins_dir is not None
        else set()
    )

    builtin_loaded = _load_builtin_plugins(plugins_dir)
    user_skip_names = set(builtin_loaded) | project_plugin_names
    user_dir = (
        USER_PLUGINS_DIR if USER_PLUGINS_DIR.is_dir() else LEGACY_USER_PLUGINS_DIR
    )
    user_loaded = _load_user_plugins(user_dir, skip_names=user_skip_names)

    # Load project plugins last (highest precedence)
    project_loaded = []
    if project_plugins_dir is not None:
        logger.info(f"Loading project plugins from {project_plugins_dir}")
        project_loaded = _load_project_plugins(
            project_plugins_dir,
            builtin_names=set(builtin_loaded),
            user_names=set(user_loaded),
        )

    result = {
        "builtin": builtin_loaded,
        "user": user_loaded,
        "project": project_loaded,
    }

    _PLUGINS_LOADED = True
    _loaded_plugin_names.update(result)
    logger.debug(
        f"Loaded plugins: builtin={result['builtin']}, "
        f"user={result['user']}, project={result['project']}"
    )

    return result


def get_loaded_plugins() -> dict[str, list[str]]:
    """Return the loaded plugin names grouped by tier.

    Returns a dict with 'builtin', 'user', and 'project' keys, each
    containing a list of plugin names loaded during startup.  Safe to
    call at any time — returns empty lists before plugins are loaded.
    """
    return dict(_loaded_plugin_names)


def get_user_plugins_dir() -> Path:
    """Return the path to the user plugins directory."""
    return USER_PLUGINS_DIR


def ensure_user_plugins_dir() -> Path:
    """Create the user plugins directory if it doesn't exist.

    Returns the path to the directory.
    """
    USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return USER_PLUGINS_DIR
