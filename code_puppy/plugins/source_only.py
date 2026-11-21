"""Import project plugins from their source alone.

A project plugin is code from a cloned repository, which runs once the user
has read it and accepted it in ``/puppy-plugins``. What they read is the
``.py`` files, and those are exactly what :func:`trust.compute_plugin_hash`
covers.

Python's own import machinery would not hold to that. Beside a module it
prefers ``__pycache__/<module>.pyc``, and an *unchecked hash-based* one
(:pep:`552`) is run without ever looking at the source it claims to come
from. It also loads a sourceless ``.pyc`` or an extension ``.so``/``.pyd``
outright, and follows symlinks. A repository could therefore ship
reviewed-looking source and have something else run, leaving the trust hash,
and so the plugin's status, unchanged.

So project plugins are imported through the finder below instead: only
``.py`` files, compiled in memory, with no bytecode cache read or written,
and nothing reached through a symlink.

Two parts of that are load-bearing:

* **Every name in the namespace is resolved here, or the import raises.**
  Returning ``None`` would pass the name on to ``PathFinder``, which reads
  exactly the files above from the plugin's directory.
* **A package's ``submodule_search_locations`` is empty.** ``PathFinder``
  consults it only for finders that returned ``None``; empty makes that
  unreachability explicit instead of assumed.
"""

from __future__ import annotations

import sys
from importlib.machinery import ModuleSpec, SourceFileLoader
from importlib.util import spec_from_file_location
from pathlib import Path
from types import CodeType, ModuleType


class SourceOnlyLoader(SourceFileLoader):
    """Runs the module's own source; no bytecode cache is read or written."""

    def get_code(self, fullname: str) -> CodeType:
        source = self.get_source(fullname)
        return compile(source, self.path, "exec", dont_inherit=True)


def reached_without_symlink(root: Path, target: Path) -> bool:
    """Whether ``target`` is inside ``root`` with no symlink on the way.

    ``root`` itself may be one: it is the user's own project directory.
    """
    try:
        relative = target.relative_to(root)
    except ValueError:
        return False
    walked = root
    for part in relative.parts:
        walked = walked / part
        if walked.is_symlink():
            return False
    return True


class ProjectPluginFinder:
    """Finds ``<namespace>.<plugin>...`` under the folders it is given.

    Installed on ``sys.meta_path``, where it is asked before the import
    machinery that would read a cached or planted ``.pyc``.
    """

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.folders: list[Path] = []

    def add(self, folder: Path) -> None:
        if folder not in self.folders:
            self.folders.append(folder)

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        prefix = f"{self.namespace}."
        if fullname != self.namespace and not fullname.startswith(prefix):
            return None
        if fullname == self.namespace:
            return self._package_spec(fullname)
        parts = fullname[len(prefix) :].split(".")
        for folder in self.folders:
            spec = self._spec(folder, fullname, parts)
            if spec is not None:
                return spec
        # Not "not here": a hard stop. Returning None would let PathFinder
        # load a `.pyc`, `.so` or symlink from the very directory just refused.
        raise ModuleNotFoundError(
            f"{fullname} is not importable from {self.namespace}: only real "
            "`.py` files inside a trusted project plugin are loaded."
        )

    def _spec(self, folder: Path, fullname: str, parts: list[str]) -> ModuleSpec | None:
        directory = folder.joinpath(*parts)
        if directory.is_dir() and reached_without_symlink(folder, directory):
            return self._package(directory, fullname)
        module = directory.with_name(f"{directory.name}.py")
        if module.is_file() and reached_without_symlink(folder, module):
            return spec_from_file_location(
                fullname, module, loader=SourceOnlyLoader(fullname, str(module))
            )
        return None

    def _package(self, directory: Path, fullname: str) -> ModuleSpec:
        """The plugin's folder, with or without an ``__init__.py``.

        Submodules resolve through ``find_spec``, never through a search path.
        """
        init = directory / "__init__.py"
        if not (init.is_file() and reached_without_symlink(directory, init)):
            return self._package_spec(fullname)
        return spec_from_file_location(
            fullname,
            init,
            loader=SourceOnlyLoader(fullname, str(init)),
            submodule_search_locations=[],
        )

    @staticmethod
    def _package_spec(fullname: str) -> ModuleSpec:
        spec = ModuleSpec(fullname, None, is_package=True)
        spec.submodule_search_locations = []
        return spec


def install(namespace: str, folder: Path) -> ProjectPluginFinder:
    """Import ``namespace.*`` from ``folder``'s source; the finder in use."""
    finder = next(
        iter(
            [
                found
                for found in sys.meta_path
                if isinstance(found, ProjectPluginFinder)
                and found.namespace == namespace
            ]
        ),
        None,
    )
    if finder is None:
        finder = ProjectPluginFinder(namespace)
        # Ahead of the machinery that would prefer a `.pyc`.
        sys.meta_path.insert(0, finder)
    finder.add(folder)
    return finder


def uninstall(namespace: str) -> None:
    """Stop importing ``namespace.*``; for tests, which build a new project each time."""
    sys.meta_path[:] = [
        found
        for found in sys.meta_path
        if not (isinstance(found, ProjectPluginFinder) and found.namespace == namespace)
    ]
