"""``import pydantic_clai2`` still works, without the deprecated alias package.

pax was ``pydantic-clai2`` until 2026-11-19. The alias package keeps the old
imports working, but each one is a *second* copy of the same files: under it,
``pydantic_clai2.plugins.Plugin`` is not ``pydantic_ai_pax.plugins.Plugin``.
``pydantic-claude-code`` 0.7.x imports the runtime under the old name, so its
``ClaudeCodePlugin`` was a ``Plugin`` pax had never seen, and pax refused it:
the plugin failed to load and every ``claude-code:`` model was unknown.

This module makes the old name *be* the new package instead. Both names then
resolve to one module object, so a class is one class. It answers the names
``pydantic-claude-code`` imports, and refuses every other old name with an
error that gives the new one: as a package, ``pydantic_clai2`` is pax's own,
so without the refusal Python would find ``pydantic_clai2.config`` in pax's
folder and run it a second time.

Installed by ``code_puppy.main`` before any pax import, and again by
``code_puppy.distribution.install`` for callers that never went through it.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from importlib.machinery import ModuleSpec
from types import ModuleType

FORMER_PACKAGE = "pydantic_clai2"
"""The runtime's name before 2026-11-19; ``pydantic-claude-code`` still uses it."""

PACKAGE = "pydantic_ai_pax"
"""What it is called now."""

IMPORTED = (
    "commands",
    "plugins",
    "ui.menus.field_menu",
    "ui.menus.menu_worker",
    "ui.prompt.line_input",
)
"""What ``pydantic-claude-code`` 0.7.x imports under the old name."""

FORMER_MODULES = frozenset(
    ".".join((FORMER_PACKAGE, *parts[:depth]))
    for parts in (name.split(".") for name in IMPORTED)
    for depth in range(len(parts) + 1)
)
"""Every old name answered: ``IMPORTED`` and the packages above each."""


class _SameModule:
    """A loader whose module is the one ``PACKAGE`` already holds.

    ``create_module`` imports the current module and hands Python that object,
    so ``sys.modules`` holds one module under both names and ``exec_module``
    has nothing left to do. Re-executing the file instead would build a second
    set of classes. Importing here, rather than in ``find_spec``, is what keeps
    a module that imports the old name while it is being imported from
    recursing back into this finder.
    """

    @staticmethod
    def create_module(spec: ModuleSpec) -> ModuleType:
        module = importlib.import_module(PACKAGE + spec.name[len(FORMER_PACKAGE) :])
        spec.loader_state = module.__spec__
        return module

    @staticmethod
    def exec_module(module: ModuleType) -> None:
        """Put back the module's own spec; there is nothing to execute.

        Python sets ``__spec__`` on the module ``create_module`` returned, which
        would leave pax's module describing the old name and this loader, and
        ``importlib.reload`` of it running nothing.
        """
        module.__spec__ = module.__spec__.loader_state


class _FormerName:
    @staticmethod
    def find_spec(
        name: str, path: object = None, target: object = None
    ) -> ModuleSpec | None:
        if name in FORMER_MODULES:
            return importlib.util.spec_from_loader(name, _SameModule)
        if name.startswith(f"{FORMER_PACKAGE}."):
            current = PACKAGE + name[len(FORMER_PACKAGE) :]
            raise ModuleNotFoundError(
                f"No module named {name!r}; import {current!r} instead", name=name
            )
        return None


def install() -> None:
    """Answer ``FORMER_MODULES`` with pax's own modules. Idempotent."""
    if _FormerName not in sys.meta_path:
        sys.meta_path.insert(0, _FormerName)
