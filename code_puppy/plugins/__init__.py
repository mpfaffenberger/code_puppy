"""Find and load Code Puppy 0.0.x plugins.

A 0.0.x plugin is a ``register_callbacks.py`` that calls
``code_puppy.callbacks.register_callback`` when imported. Three tiers load, in
this order, exactly as before:

==========  ===================================================  ==============
Tier        Where                                                Trust
==========  ===================================================  ==============
installed   entry-point group ``code_puppy.plugins``             trusted
user        ``~/.code_puppy/plugins/<name>/``                    trusted
project     ``<cwd>/.code_puppy/plugins/<name>/``                opt-in, hashed
==========  ===================================================  ==============

Project plugins run repository code at import, so none load until accepted;
see ``trust``. On a name clash the project copy replaces the user one.

The retired ``code-puppy-core-plugins`` distribution is skipped: its plugins
were written against 0.0.x internals and have native replacements.

New plugins should be pydantic-ai-pax ``Plugin`` subclasses instead.
"""

from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path

from packaging.utils import canonicalize_name

from code_puppy import callbacks, identity
from code_puppy.plugins import source_only, trust

PLUGIN_ENTRY_POINT_GROUP = "code_puppy.plugins"
RETIRED_DISTRIBUTIONS = frozenset({"code-puppy-core-plugins"})
REGISTER_MODULE = "register_callbacks"
PROJECT_NAMESPACE = "project_plugins"
USER_PLUGINS_DIR = identity.config_dir() / "plugins"

TIERS = ("installed", "user", "project")


@dataclass(frozen=True, kw_only=True)
class PluginRecord:
    """One discovered 0.0.x plugin and what became of it."""

    name: str
    tier: str
    status: str
    """``loaded``, ``failed``, ``untrusted``, ``changed``, ``shadowed`` or ``retired``."""
    detail: str = ""


_records: dict[tuple[str, str], PluginRecord] = {}
_loaded = False


def get_user_plugins_dir() -> Path:
    return identity.config_dir() / "plugins"


def get_project_plugins_directory(project_root: Path | None = None) -> Path | None:
    """``<project>/.code_puppy/plugins`` when the repository has one."""
    folder = (project_root or Path.cwd()) / identity.PROJECT_DIR / "plugins"
    return folder if folder.is_dir() else None


def _scan(folder: Path | None) -> dict[str, Path]:
    """Plugin folders in ``folder``: those holding a ``register_callbacks.py``."""
    if folder is None or not folder.is_dir():
        return {}
    found: dict[str, Path] = {}
    for child in sorted(folder.iterdir()):
        name = child.name
        if name.startswith(("_", ".")) or not name.isidentifier():
            continue
        if (child / f"{REGISTER_MODULE}.py").is_file():
            found[name] = child
    return found


def _record(name: str, tier: str, status: str, detail: str = "") -> None:
    _records[(tier, name)] = PluginRecord(
        name=name, tier=tier, status=status, detail=detail
    )


def _import(owner: str, tier: str, module_name: str) -> bool:
    """Import a plugin's register module, attributing its callbacks to ``owner``."""
    try:
        with callbacks.owned_by(owner):
            importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - a broken plugin must not stop the rest
        callbacks.unregister_owner(owner)
        _record(owner, tier, "failed", f"{type(exc).__name__}: {exc}")
        return False
    _record(owner, tier, "loaded")
    return True


def _load_installed() -> None:
    for entry in sorted(
        entry_points(group=PLUGIN_ENTRY_POINT_GROUP), key=lambda e: e.name
    ):
        distribution = entry.dist.name if entry.dist is not None else ""
        if canonicalize_name(distribution) in RETIRED_DISTRIBUTIONS:
            _record(entry.name, "installed", "retired", distribution)
            continue
        _import(entry.name, "installed", entry.value.partition(":")[0])


def _load_user(folder: Path, skip: set[str]) -> None:
    plugins = _scan(folder)
    if plugins and str(folder) not in sys.path:
        # 0.0.x plugins import their own package by its top-level name.
        sys.path.insert(0, str(folder))
    for name in plugins:
        if name in skip:
            _record(name, "user", "shadowed", "replaced by the project plugin")
            continue
        _import(name, "user", f"{name}.{REGISTER_MODULE}")


def _project_namespace(folder: Path) -> None:
    """Import project plugins as ``project_plugins.<name>`` so names never collide.

    Through ``source_only``, so a repository's reviewed source is what runs:
    the namespace keeps no ``__path__`` of its own for the ordinary import
    machinery to search.
    """
    namespace = sys.modules.get(PROJECT_NAMESPACE)
    if namespace is None:
        namespace = types.ModuleType(PROJECT_NAMESPACE)
        namespace.__path__ = []
        sys.modules[PROJECT_NAMESPACE] = namespace
    source_only.install(PROJECT_NAMESPACE, folder)


def _trusted_project_plugins(project_root: Path) -> dict[str, Path]:
    """Project plugins the user accepted; the rest are recorded with their status."""
    accepted: dict[str, Path] = {}
    for name, path in _scan(get_project_plugins_directory(project_root)).items():
        status = trust.get_trust_status(project_root, name, path)
        if status == trust.TRUSTED:
            accepted[name] = path
        else:
            _record(name, "project", status)
    return accepted


def load_plugin_callbacks(project_root: Path | None = None) -> dict[str, list[str]]:
    """Load every tier once per process; the names loaded, by tier."""
    global _loaded
    if not _loaded:
        _loaded = True
        root = project_root or Path.cwd()
        project = _trusted_project_plugins(root)
        _load_installed()
        _load_user(get_user_plugins_dir(), skip=set(project))
        folder = get_project_plugins_directory(root)
        if project and folder is not None:
            _project_namespace(folder)
        for name in project:
            _import(name, "project", f"{PROJECT_NAMESPACE}.{name}.{REGISTER_MODULE}")
    return get_loaded_plugins()


def load_project_plugin_now(plugin_name: str, project_root: Path | None = None) -> bool:
    """Load one project plugin right after the user trusted it."""
    root = project_root or Path.cwd()
    folder = get_project_plugins_directory(root)
    path = _scan(folder).get(plugin_name)
    if folder is None or path is None:
        return False
    if not trust.is_plugin_trusted(root, plugin_name, path):
        return False
    _project_namespace(folder)
    return _import(
        plugin_name, "project", f"{PROJECT_NAMESPACE}.{plugin_name}.{REGISTER_MODULE}"
    )


def get_loaded_plugins() -> dict[str, list[str]]:
    loaded: dict[str, list[str]] = {tier: [] for tier in TIERS}
    for record in _records.values():
        if record.status == "loaded":
            loaded[record.tier].append(record.name)
    return loaded


def get_project_plugin_status() -> dict[str, str]:
    return {
        record.name: record.status
        for record in _records.values()
        if record.tier == "project"
    }


def get_plugin_records() -> list[PluginRecord]:
    """Every discovered plugin, loaded or not, for ``/puppy-plugins``."""
    return sorted(
        _records.values(), key=lambda record: (TIERS.index(record.tier), record.name)
    )


def reset_for_tests() -> None:
    """Forget what was loaded. Imported modules stay imported."""
    global _loaded
    _loaded = False
    _records.clear()
    source_only.uninstall(PROJECT_NAMESPACE)
