"""``import pydantic_clai2`` still works, without the deprecated alias package.

pax was ``pydantic-clai2`` until 2026-11-19. The alias package keeps the old
imports working, but each one is a *second* copy of the same files: under it,
``pydantic_clai2.plugins.Plugin`` is not ``pydantic_ai_pax.plugins.Plugin``.
``pydantic-claude-code`` 0.7.x imports the runtime under the old name, so its
``ClaudeCodePlugin`` was a ``Plugin`` pax had never seen, and pax refused it:
the plugin failed to load and every ``claude-code:`` model was unknown.

This module makes the old name *be* the new package instead. Both names then
resolve to one module object, so a class is one class. It answers the two names
``pydantic-claude-code`` imports, and nothing else: a third-party plugin that
needs another one is pointed at the new name by pax's own docs.

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

FORMER_MODULES = (
    FORMER_PACKAGE,
    f"{FORMER_PACKAGE}.commands",
    f"{FORMER_PACKAGE}.plugins",
)
"""The ``pydantic_clai2`` names ``pydantic-claude-code`` imports, and their parent."""

_installed = False


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
        return importlib.import_module(PACKAGE + spec.name[len(FORMER_PACKAGE) :])

    @staticmethod
    def exec_module(module: ModuleType) -> None:
        """Nothing: ``module`` is already the imported one."""


class _FormerName:
    """Answer ``FORMER_MODULES`` with the modules ``PACKAGE`` holds."""

    @staticmethod
    def find_spec(
        name: str, path: object = None, target: object = None
    ) -> ModuleSpec | None:
        if name not in FORMER_MODULES:
            return None
        return importlib.util.spec_from_loader(name, _SameModule)


def install() -> None:
    """Answer ``FORMER_MODULES`` with pax's own modules. Idempotent."""
    global _installed
    if _installed:
        return
    sys.meta_path.insert(0, _FormerName)
    _installed = True
