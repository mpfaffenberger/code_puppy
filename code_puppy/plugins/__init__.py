import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import logging
import os
import sys
from importlib.metadata import entry_points
import types
from pathlib import Path

from code_puppy.callbacks import clear_loading_context, set_loading_context
from code_puppy.plugins import trust as _trust

logger = logging.getLogger(__name__)

# User plugins directory
USER_PLUGINS_DIR = Path.home() / ".code_puppy" / "plugins"

# Bytecode the *default* loader would emit for a project plugin's eager
# top-level sibling imports is redirected here, out of the project tree, so a
# clean load never leaves a __pycache__ entry the tripwire would refuse next
# session. The redirect is process-wide, so it is applied only around each
# plugin's exec and restored afterward (see _load_one_project_plugin); leaving
# it set would divert bytecode for every unrelated import in the process. The
# source-only loader compiles in memory and writes nothing, so the plugin's own
# modules never depend on it.
_PROJECT_PLUGIN_PYCACHE = str(Path.home() / ".code_puppy" / "plugin_bytecode_cache")


class _ProjectPluginLoader(importlib.machinery.SourceFileLoader):
    """Load project plugin source directly; never read or write ``.pyc`` caches.

    Compiling from source keeps a plugin executing exactly the file that was
    trusted, and writes no cache back. Within the ``project_plugins`` namespace
    this loader is the only one the finder hands out; a plugin directory that
    ships any bytecode is refused before it reaches here (see
    ``_load_one_project_plugin``).
    """

    def get_code(self, fullname):  # noqa: D102
        return compile(self.get_source(fullname), self.path, "exec", dont_inherit=True)


class _ProjectPluginFinder(importlib.abc.MetaPathFinder):
    """Serve ``project_plugins.*`` imports with :class:`_ProjectPluginLoader`.

    Installed at the front of ``sys.meta_path`` before any trusted project
    plugin is imported (see ``_install_project_plugin_finder``), so a plugin's
    own module and every sibling it imports resolve through the source-only
    loader. A ``project_plugins.*`` name backed only by planted bytecode
    (``<name>.pyc`` with no source) raises ``ImportError`` instead of falling
    through to the default path finder's ``SourcelessFileLoader``.
    """

    def find_spec(self, fullname, path=None, target=None):  # noqa: D102
        if not fullname.startswith(_PROJECT_PLUGINS_NS + "."):
            return None
        last = fullname.rsplit(".", 1)[-1]
        for entry in list(path or []):
            base = Path(entry)
            pkg_dir = base / last
            init_file = pkg_dir / "__init__.py"
            module_file = base / f"{last}.py"
            # A package: a directory carrying a real __init__.py source file.
            if init_file.is_file():
                if pkg_dir.is_symlink():
                    raise ImportError(
                        f"Refusing to import {fullname!r} through symlinked "
                        f"directory {pkg_dir} — the trust hash never saw its target"
                    )
                return importlib.util.spec_from_file_location(
                    fullname,
                    init_file,
                    loader=_ProjectPluginLoader(fullname, str(init_file)),
                    submodule_search_locations=[str(pkg_dir)],
                )
            # A module: <last>.py wins over a same-named directory, matching
            # CPython precedence (a source file beats a bare namespace portion).
            # The default finder does this too; inverting it here would let an
            # empty <last>/ dir silently shadow a trusted <last>.py.
            if module_file.is_file():
                return importlib.util.spec_from_file_location(
                    fullname,
                    module_file,
                    loader=_ProjectPluginLoader(fullname, str(module_file)),
                )
            # No source under this name, but a non-source artifact the default
            # finder would execute (planted bytecode or a compiled extension):
            # own the name and fail closed instead of falling through.
            for suffix in (".pyc", *importlib.machinery.EXTENSION_SUFFIXES):
                artifact = base / f"{last}{suffix}"
                if artifact.is_file():
                    raise ImportError(
                        f"Refusing to import {fullname!r} from non-source file "
                        f"{artifact} — project plugins load from source only"
                    )
            # Only now, with no source file and no planted artifact, honor a bare
            # namespace portion (a directory with no __init__.py).
            if pkg_dir.is_dir():
                if pkg_dir.is_symlink():
                    raise ImportError(
                        f"Refusing to import {fullname!r} through symlinked "
                        f"directory {pkg_dir} — the trust hash never saw its target"
                    )
                spec = importlib.machinery.ModuleSpec(fullname, None, is_package=True)
                spec.submodule_search_locations = [str(pkg_dir)]
                return spec
        return None


def _install_project_plugin_finder() -> None:
    """Register the project-plugin finder once, ahead of the path finder."""
    if not any(isinstance(finder, _ProjectPluginFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _ProjectPluginFinder())


PLUGIN_ENTRY_POINT_GROUP = "code_puppy.plugins"

# shell_safety implements the safety_permission_level threshold. Skip it only
# when the user opted into high/critical autonomy; the default (medium) must
# load it or the setting is a no-op.
_SHELL_SAFETY_SKIP_LEVELS = frozenset({"high", "critical"})


def _skip_shell_safety_plugin() -> bool:
    from code_puppy.config import get_safety_permission_level

    return get_safety_permission_level() in _SHELL_SAFETY_SKIP_LEVELS


# Track if plugins have already been loaded to prevent duplicate registration
_PLUGINS_LOADED = False

# Stores the loaded plugin names by tier after the first load_plugin_callbacks() call.
# Populated once, then read by get_loaded_plugins().
_loaded_plugin_names: dict[str, list[str]] = {"builtin": [], "user": [], "project": []}

# Discovered project-plugin status by name (loaded|untrusted|changed|disabled|error); read by /plugins UI.
_project_plugin_status: dict[str, str] = {}


def _load_installed_plugins() -> list[str]:
    """Load distribution-provided plugins advertised through entry points.

    Installed plugin bundles are the builtin tier: they load before user and
    project plugins, but remain physically independent from the core package.
    Entry points are sorted for deterministic startup and test behavior.
    """
    loaded: list[str] = []
    discovered = sorted(
        entry_points(group=PLUGIN_ENTRY_POINT_GROUP), key=lambda item: item.name
    )
    for entry_point in discovered:
        plugin_name = entry_point.name
        if plugin_name == "shell_safety" and _skip_shell_safety_plugin():
            logger.debug("Skipping shell_safety plugin due to safety permission level")
            continue
        try:
            set_loading_context(plugin_name)
            entry_point.load()
            loaded.append(plugin_name)
        except ImportError as exc:
            logger.warning("Failed to import installed plugin %s: %s", plugin_name, exc)
        except Exception as exc:
            logger.error(
                "Unexpected error loading installed plugin %s: %s",
                plugin_name,
                exc,
                exc_info=True,
            )
        finally:
            clear_loading_context()
    return loaded


def _load_builtin_plugins(
    plugins_dir: Path, skip_names: set[str] | None = None
) -> list[str]:
    """Load legacy plugins still bundled in the core package.

    ``skip_names`` prevents duplicate registration during the migration when
    the same plugin is both installed through an entry point and still present
    in an older core checkout.
    """
    # Import safety permission check for shell_safety plugin
    from code_puppy.config import get_safety_permission_level

    loaded = []
    skip_names = set(skip_names or ())

    for item in plugins_dir.iterdir():
        if item.is_dir() and not item.name.startswith("_"):
            plugin_name = item.name
            callbacks_file = item / "register_callbacks.py"

            if plugin_name in skip_names:
                continue

            if callbacks_file.exists():
                if plugin_name == "shell_safety" and _skip_shell_safety_plugin():
                    logger.debug(
                        "Skipping shell_safety plugin - safety_permission_level is %s",
                        get_safety_permission_level(),
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
    """Load user plugins from ~/.code_puppy/plugins/.

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
            loader=_ProjectPluginLoader(pkg_name, str(init_file)),
            submodule_search_locations=[str(plugin_dir)],
        )
        if spec_init is None or spec_init.loader is None:
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


def _find_plugin_bytecode(plugin_dir: Path) -> Path | None:
    """Return the first import artifact under *plugin_dir* that trust can't cover.

    ``compute_plugin_hash`` digests only source files, so bytecode (``.pyc`` /
    ``__pycache__``), compiled extensions (``.so`` / ``.pyd``), and symlinked
    subdirectories can slip past the trust digest yet still be imported by the
    machinery. Any of them beside a source plugin is treated as tampering.

    Walks with ``followlinks=False`` so a symlinked subdirectory is reported at
    its own level — its target lives outside the hashed tree — without being
    descended into (``rglob`` would silently skip it while ``find_spec`` follows
    it).
    """
    binary_suffixes = {".pyc", *importlib.machinery.EXTENSION_SUFFIXES}
    try:
        for root, dirnames, filenames in os.walk(plugin_dir, followlinks=False):
            root_path = Path(root)
            for dirname in dirnames:
                dir_path = root_path / dirname
                if dirname == "__pycache__" or dir_path.is_symlink():
                    return dir_path
            for filename in filenames:
                if Path(filename).suffix in binary_suffixes:
                    return root_path / filename
    except OSError:
        return None
    return None


def _find_path_entry_binary(path_entry: Path) -> Path | None:
    """Return the first sourceless import artifact directly under *path_entry*.

    *path_entry* is the directory a project plugin adds to ``sys.path`` (the
    plugins root, ``plugin_dir.parent``). A plugin's *top-level* ``import name``
    resolves against it through the **default** import machinery, which the
    source-only finder never sees — so loose ``.pyc``/``.so``/``.pyd`` there, or
    a same-named directory whose only ``__init__`` is bytecode/extension, would
    execute without ever touching the trust hash. ``_find_plugin_bytecode`` scans
    only inside each plugin, so this covers the shared import root it cannot.

    Only the direct children of *path_entry* are checked: those are exactly the
    top-level names an ``import name`` resolves there, and sibling plugin
    directories carry their own in-tree tripwire.
    """
    binary_suffixes = {".pyc", *importlib.machinery.EXTENSION_SUFFIXES}
    try:
        for child in path_entry.iterdir():
            if child.is_file() and child.suffix in binary_suffixes:
                return child
            if child.is_dir() and not (child / "__init__.py").is_file():
                for suffix in binary_suffixes:
                    init_artifact = child / f"__init__{suffix}"
                    if init_artifact.is_file():
                        return init_artifact
    except OSError:
        return None
    return None


def _load_one_project_plugin(plugin_dir: Path, plugin_name: str) -> bool:
    """Import a single (already trusted) project plugin.

    SECURITY: callers MUST verify trust before invoking this — executing
    ``register_callbacks.py`` / ``__init__.py`` is arbitrary code execution.

    The plugins directory is only added to ``sys.path`` here, i.e. after a
    trust decision, so an untrusted repo can never shadow stdlib/third-party
    modules just by existing.

    Returns True if the plugin executed successfully.
    """
    callbacks_file = plugin_dir / "register_callbacks.py"
    init_file = plugin_dir / "__init__.py"

    if not callbacks_file.exists() and not init_file.exists():
        return False

    # Fail closed at the trust boundary: a source plugin has no legitimate reason
    # to ship bytecode or compiled extensions, and the trust hash never covers
    # them, so any .pyc/__pycache__/.so/.pyd — or a symlinked subdir the digest
    # never followed — is treated as tampering and the whole plugin is refused.
    # The scan covers both the plugin's own tree and the plugins root placed on
    # sys.path below: a trusted plugin's top-level ``import helper`` resolves a
    # loose helper.pyc there through the default (non-source) loader, an import
    # path the meta-path finder never sees.
    binary = _find_plugin_bytecode(plugin_dir)
    if binary is None:
        binary = _find_path_entry_binary(plugin_dir.parent)
    if binary is not None:
        logger.warning(
            "Refusing to load project plugin '%s': found non-source import "
            "artifact at %s. Remove all .pyc/.so/.pyd files, __pycache__ "
            "directories, and symlinked subdirectories from the plugin directory "
            "and the plugins root, then reload.",
            plugin_name,
            binary,
        )
        return False

    # sys.path entry is earned by trust — inserted just-in-time so sibling
    # top-level imports inside the plugin resolve during exec below.
    parent_str = str(plugin_dir.parent)
    if parent_str not in sys.path:
        sys.path.insert(0, parent_str)

    # Route the plugin and every sibling it imports through the source-only
    # loader. The finder stays installed permanently — it is scoped to the
    # project_plugins.* namespace, so it is inert for all other imports. The
    # pycache_prefix redirect is process-wide, so it wraps only this plugin's own
    # exec and is restored in the finally below: it keeps bytecode the *default*
    # loader would emit for an eager top-level sibling import out of the project
    # tree. The source-only loader compiles in memory and writes no cache, so the
    # plugin's own modules never need the redirect to persist.
    _install_project_plugin_finder()
    prev_pycache_prefix = sys.pycache_prefix
    sys.pycache_prefix = _PROJECT_PLUGIN_PYCACHE

    try:
        if callbacks_file.exists():
            # Register parent package so relative imports resolve.
            _ensure_plugin_package(plugin_dir, plugin_name)

            module_name = f"{_PROJECT_PLUGINS_NS}.{plugin_name}.register_callbacks"
            spec = importlib.util.spec_from_file_location(
                module_name,
                callbacks_file,
                loader=_ProjectPluginLoader(module_name, str(callbacks_file)),
            )
            if spec is None or spec.loader is None:
                logger.warning(
                    f"Could not create module spec for project plugin: {plugin_name}"
                )
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            set_loading_context(plugin_name)
            try:
                spec.loader.exec_module(module)
            finally:
                clear_loading_context()
            return True

        # Fallback to __init__.py (mirrors user plugin behavior)
        set_loading_context(plugin_name)
        try:
            loaded_ok = _ensure_plugin_package(plugin_dir, plugin_name)
        finally:
            clear_loading_context()
        if not loaded_ok:
            logger.warning(
                f"Could not load __init__.py for project plugin: {plugin_name}"
            )
        return loaded_ok

    except ImportError as e:
        logger.warning(
            f"Failed to import callbacks from project plugin {plugin_name}: {e}"
        )
        return False
    except Exception as e:
        logger.error(
            f"Unexpected error loading project plugin {plugin_name}: {e}",
            exc_info=True,
        )
        return False
    finally:
        # Undo the process-wide redirect. Leaving it set diverts bytecode for
        # every unrelated import in the process (and never restores the original
        # cache), which is both a perf regression and a source of cross-test
        # global-state leaks.
        sys.pycache_prefix = prev_pycache_prefix


def _load_project_plugins(
    project_plugins_dir: Path,
    builtin_names: set[str],
    user_names: set[str],
) -> list[str]:
    """Load TRUSTED project plugins from <CWD>/.code_puppy/plugins/.

    Project plugins are disabled by default: a plugin is only imported when
    the user previously accepted the risk via the /plugins TUI ceremony AND
    its content hash still matches the accepted hash (see plugins.trust).
    Everything else is recorded in ``_project_plugin_status`` and skipped
    WITHOUT importing — import is code execution.

    NOTE: this is deliberately different from the ``disabled_plugins``
    mechanism used by builtin/user tiers (loaded but callbacks skipped).
    Do not "unify" them — non-enabled project plugins must never import.

    Returns list of successfully loaded plugin names.
    """
    from code_puppy.plugins.config import is_plugin_disabled

    loaded = []

    if not project_plugins_dir.exists():
        return loaded

    if not project_plugins_dir.is_dir():
        logger.warning(
            f"Project plugins path is not a directory: {project_plugins_dir}"
        )
        return loaded

    project_root = project_plugins_dir.parent.parent

    # Create the top-level namespace package once
    _ensure_project_ns()

    for item in project_plugins_dir.iterdir():
        if (
            item.is_dir()
            and not item.name.startswith("_")
            and not item.name.startswith(".")
        ):
            plugin_name = item.name

            if (
                not (item / "register_callbacks.py").exists()
                and not (item / "__init__.py").exists()
            ):
                continue

            # Trust gate — fail closed BEFORE any import machinery runs.
            status = _trust.get_trust_status(project_root, plugin_name, item)
            if status != _trust.TRUSTED:
                # Recorded here; surfaced by plugin_list's startup hook (orange banner).
                # logger.info only — warning would duplicate the banner above the logo.
                _project_plugin_status[plugin_name] = status
                logger.info(
                    "Skipping project plugin '%s' (%s). "
                    "Review and enable it in the /plugins TUI.",
                    plugin_name,
                    status,
                )
                continue

            if is_plugin_disabled(plugin_name):
                _project_plugin_status[plugin_name] = "disabled"
                logger.info(
                    "Project plugin '%s' is trusted but disabled — not loading",
                    plugin_name,
                )
                continue

            # Warn if a project plugin shadows a builtin (user collisions
            # are handled earlier by skipping the user plugin entirely).
            if plugin_name in builtin_names:
                logger.warning(
                    f"Project plugin '{plugin_name}' shadows builtin plugin of the same name"
                )

            if _load_one_project_plugin(item, plugin_name):
                loaded.append(plugin_name)
                _project_plugin_status[plugin_name] = "loaded"
            else:
                _project_plugin_status[plugin_name] = "error"

    return loaded


def get_project_plugins_directory() -> Path | None:
    """Get the project-local plugins directory path.

    Looks for a .code_puppy/plugins/ directory in the current working directory.
    Does NOT create the directory if it doesn't exist — the team must create it
    intentionally.

    Returns:
        Path to the project's plugins directory if it exists, or None.
    """
    project_plugins_dir = Path.cwd() / ".code_puppy" / "plugins"
    if not project_plugins_dir.is_dir():
        return None

    try:
        if project_plugins_dir.samefile(USER_PLUGINS_DIR):
            logger.debug(
                "Ignoring project plugins directory because it is the user plugins directory: %s",
                project_plugins_dir,
            )
            return None
    except OSError:
        # A missing/unreadable user directory cannot be the discovered project
        # directory, so retain normal project discovery.
        pass

    return project_plugins_dir


def load_plugin_callbacks() -> dict[str, list[str]]:
    """Dynamically load register_callbacks.py from all plugin sources.

    Loads plugins from:
    1. Installed ``code_puppy.plugins`` entry points (builtin tier)
    2. Legacy bundled directories, when present during migration
    3. User plugins in ~/.code_puppy/plugins/
    4. Project plugins in <CWD>/.code_puppy/plugins/

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

    plugins_dir = Path(__file__).parent

    # Pre-scan project plugin names so the project tier supersedes user plugins.
    # SECURITY: only TRUSTED project plugins dedup — an untrusted repo could otherwise
    # squat on user plugin names (e.g. force_push_guard).
    project_plugins_dir = get_project_plugins_directory()
    project_plugin_names: set[str] = set()
    if project_plugins_dir is not None:
        project_root = project_plugins_dir.parent.parent
        project_plugin_names = {
            name
            for name in _scan_plugin_names(project_plugins_dir)
            if _trust.is_plugin_trusted(project_root, name, project_plugins_dir / name)
        }

    installed_loaded = _load_installed_plugins()
    legacy_loaded = _load_builtin_plugins(plugins_dir, skip_names=set(installed_loaded))
    builtin_loaded = installed_loaded + legacy_loaded
    user_skip_names = set(builtin_loaded) | project_plugin_names
    user_loaded = _load_user_plugins(USER_PLUGINS_DIR, skip_names=user_skip_names)

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


def get_project_plugin_status() -> dict[str, str]:
    """Return status of every discovered project plugin.

    Maps plugin name to one of ``loaded``, ``untrusted``, ``changed``,
    ``disabled``, or ``error``.  Used by the /plugins UI to surface
    project plugins that were skipped by the trust gate.
    """
    return dict(_project_plugin_status)


def load_project_plugin_now(plugin_name: str) -> bool:
    """Hot-load a single project plugin after the user granted trust.

    Re-checks the trust store (fail closed) so callers can't accidentally
    load an unaccepted plugin.  Registers callbacks immediately — no
    restart required.
    """
    project_plugins_dir = get_project_plugins_directory()
    if project_plugins_dir is None:
        return False

    plugin_dir = project_plugins_dir / plugin_name
    if not plugin_dir.is_dir():
        return False

    project_root = project_plugins_dir.parent.parent
    if not _trust.is_plugin_trusted(project_root, plugin_name, plugin_dir):
        logger.warning(
            "Refusing to hot-load project plugin '%s' — not trusted", plugin_name
        )
        return False

    if plugin_name in _loaded_plugin_names["project"]:
        # Already imported this session; callbacks are registered.
        _project_plugin_status[plugin_name] = "loaded"
        return True

    _ensure_project_ns()
    if _load_one_project_plugin(plugin_dir, plugin_name):
        _loaded_plugin_names["project"].append(plugin_name)
        _project_plugin_status[plugin_name] = "loaded"
        return True

    _project_plugin_status[plugin_name] = "error"
    return False


def get_user_plugins_dir() -> Path:
    """Return the path to the user plugins directory."""
    return USER_PLUGINS_DIR


def ensure_user_plugins_dir() -> Path:
    """Create the user plugins directory if it doesn't exist.

    Returns the path to the directory.
    """
    USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return USER_PLUGINS_DIR
