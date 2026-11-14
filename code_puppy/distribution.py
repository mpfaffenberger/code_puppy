"""Make pydantic-clai2 run as Code Puppy.

Code Puppy 1.0 is a distribution of pydantic-clai2: clai2 owns the agent loop,
the terminal UI, sessions and plugins. clai2 0.68 has no way for a
distribution to supply its identity, so the names below are replaced on its
modules at startup.

Every replacement lives in this file and nowhere else. Each one is temporary:
it goes away when clai2 grows the matching seam, and
``tests/test_distribution_contract.py`` fails if a clai2 upgrade moves or
renames a symbol this file relies on.

==========================================  =====================================
clai2 symbol                                Seam that would replace it
==========================================  =====================================
``settings_store.config_dir/state_dir``     configurable config and state roots
``credential_store._SERVICE``               configurable keyring service
``credential_store.credentials_path``       credentials under the config root
``self_update.*``, ``cli._update``          pluggable update source
``splash_art``, ``branding``, ``welcome``   pluggable branding
``builtins.DEFAULT_PLUGINS/STOCK_PLUGINS``  distribution-supplied default plugins
``app.create_stock_agent``                  configurable agent name and docs capability
``ProcessPlugins._discover``                pluggable drop-in discovery
==========================================  =====================================

clai2 modules bind these names with ``from x import y``. :func:`_replace`
therefore swaps a name on its owning module *and* on every clai2 module that
already imported it, so the result does not depend on import order. Modules
imported afterwards pick up the replacement from the owning module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from code_puppy import identity

if TYPE_CHECKING:
    from rich.console import Console

LEGACY_PLUGIN_MARKER = "register_callbacks.py"
"""A plugins folder containing this file is a 0.0.x plugin, loaded by the compat bridge."""

RUNTIME_PACKAGE = "pydantic_clai2"

_splash_installed = False
_installed = False


def _replace(owner: ModuleType, name: str, new: object) -> None:
    """Swap ``owner.name`` for ``new`` everywhere clai2 already holds the old object.

    Only for functions, classes and tuples, which are matched by identity.
    Strings are set on the owning module directly: identity says nothing
    about an interned string.
    """
    old = getattr(owner, name)
    setattr(owner, name, new)
    for module_name, module in list(sys.modules.items()):
        if module is None or module is owner:
            continue
        if module_name != RUNTIME_PACKAGE and not module_name.startswith(
            RUNTIME_PACKAGE + "."
        ):
            continue
        for key, value in list(vars(module).items()):
            if value is old:
                setattr(module, key, new)


def install_splash() -> None:
    """Give the startup splash Code Puppy's art. Light enough to run first."""
    global _splash_installed
    if _splash_installed:
        return
    from pydantic_clai2.ui.rendering import splash_art

    from code_puppy import _art

    _replace(splash_art, "PYRAMID", _art.PAW)
    _replace(splash_art, "LABEL", _art.LABEL)
    _splash_installed = True


def install() -> None:
    """Apply every replacement. Idempotent; call before importing the clai2 CLI."""
    global _installed
    if _installed:
        return
    install_splash()
    _install_paths()
    _install_credentials()
    _install_updates()
    _install_branding()
    _install_plugins()
    _install_agent()
    _installed = True


def _install_paths() -> None:
    from pydantic_clai2.config import settings_store

    _replace(settings_store, "config_dir", identity.config_dir)
    _replace(settings_store, "state_dir", identity.runtime_state_dir)


def _install_credentials() -> None:
    from pydantic_clai2.config import credential_store

    upstream_path = credential_store.credentials_path

    def credentials_path(*, account: str = credential_store._ACCOUNT) -> Path:
        """clai2's file name for ``account``, in Code Puppy's config folder."""
        return identity.config_dir() / upstream_path(account=account).name

    credential_store._SERVICE = identity.KEYRING_SERVICE
    _replace(credential_store, "credentials_path", credentials_path)


def _install_updates() -> None:
    from pydantic_clai2.cli import self_update

    from code_puppy import update

    self_update.DISTRIBUTION = identity.DISTRIBUTION
    self_update.PYPI_URL = update.PYPI_URL
    _replace(self_update, "installed", update.installed)
    _replace(self_update, "latest", update.latest)
    _replace(self_update, "find_update", update.find_update)
    _replace(self_update, "tool_executable", update.tool_executable)
    _replace(self_update, "Update", update.PuppyUpdate)
    _replace(self_update, "Updates", update.PuppyUpdates)

    from pydantic_clai2.cli import cli

    _replace(cli, "_update", update.cli_update)


def _install_branding() -> None:
    from pydantic_clai2.ui.rendering import branding as upstream_branding

    from code_puppy import branding

    from pydantic_clai2.ui.rendering import welcome

    _replace(upstream_branding, "print_banner", branding.print_banner)
    _replace(welcome, "print_welcome", branding.print_welcome)


def _install_agent() -> None:
    from pydantic_clai2 import app
    from pydantic_clai2.runtime.session import StockAgent

    def create_stock_agent(model: Any = None) -> Any:
        """clai2's stock agent under Code Puppy's name, without clai2's docs capability.

        That capability lets the model read clai2's own docs to answer questions
        about "CLAI itself". They describe clai2's commands and folders, not
        Code Puppy's, and put the name CLAI in every system prompt.
        """
        return StockAgent(
            model,
            deps_type=type(None),
            output_type=str,
            capabilities=[],
            name=identity.AGENT_NAME,
        )

    _replace(app, "create_stock_agent", create_stock_agent)


def is_legacy_plugin(entry: Path) -> bool:
    """Whether a discovered drop-in is really a 0.0.x plugin folder."""
    return (
        entry.name == "__init__.py" and (entry.parent / LEGACY_PLUGIN_MARKER).is_file()
    )


def _install_plugins() -> None:
    from pydantic_clai2.config import builtins
    from pydantic_clai2.plugins import process_plugins

    from code_puppy.builtin_plugins import CLAUDE_CODE_NO_UPDATE_CHECK, PUPPY_PLUGINS

    os.environ.setdefault(CLAUDE_CODE_NO_UPDATE_CHECK, "1")

    _replace(builtins, "DEFAULT_PLUGINS", (*builtins.DEFAULT_PLUGINS, *PUPPY_PLUGINS))
    _replace(builtins, "STOCK_PLUGINS", (*builtins.STOCK_PLUGINS, *PUPPY_PLUGINS))

    upstream_discover = process_plugins.ProcessPlugins._discover

    def _discover(
        self: process_plugins.ProcessPlugins, console: Console
    ) -> dict[str, Path]:
        """clai2's drop-in scan, minus 0.0.x plugin folders that share the directory."""
        found = upstream_discover(self, console)
        return {
            name: path for name, path in found.items() if not is_legacy_plugin(path)
        }

    process_plugins.ProcessPlugins._discover = _discover
