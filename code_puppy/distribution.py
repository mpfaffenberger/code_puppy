"""Make pydantic-ai-pax run as Code Puppy.

Code Puppy 1.0 is a distribution of pydantic-ai-pax: pax owns the agent loop,
the terminal UI, sessions and plugins. pax has no way for a distribution to
supply its identity, so the names below are replaced on its modules at
startup. (pax was named pydantic-clai2 until 2026-11-19.)

The startup splash is Code Puppy's own (``code_puppy.splash``); nothing of
pax's splash is replaced.

Every replacement lives in this file and nowhere else. Each one is temporary:
it goes away when pax grows the matching seam, and
``tests/test_distribution_contract.py`` fails if a pax upgrade moves or
renames a symbol this file relies on.

==========================================  =====================================
pax symbol                                  Seam that would replace it
==========================================  =====================================
``settings_store.config_dir/state_dir``     configurable config and state roots
``credential_store._SERVICE``               configurable keyring service
``credential_store.credentials_path``       credentials under the config root
``self_update.*``, ``cli._update``          pluggable update source
``install.command_name``                    configurable command name
``branding``, ``welcome``                   pluggable branding
``theme`` colours                           a distribution-supplied default theme
``builtins.DEFAULT_PLUGINS/STOCK_PLUGINS``  distribution-supplied default plugins
``app.create_stock_agent``                  configurable agent name and docs capability
``app.chat``                                a hook before an interactive session starts
``imported_sessions.IMPORT_SOURCES``        registering a session import source
``ProcessPlugins._discover``                pluggable drop-in discovery
==========================================  =====================================

The 0.0.x session source is also added to ``imported_sessions._SOURCES`` and to
the session browser's ``_FILTERS``, beside pax's own entries.

pax modules bind these names with ``from x import y``. :func:`_replace`
therefore swaps a name on its owning module *and* on every pax module that
already imported it, so the result does not depend on import order. Modules
imported afterwards pick up the replacement from the owning module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from code_puppy import former_name, identity

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic_ai.models import Model
    from pydantic_ai_pax.runtime.session import StockAgent
    from rich.console import Console

P = ParamSpec("P")
T = TypeVar("T")

LEGACY_PLUGIN_MARKER = "register_callbacks.py"
"""A plugins folder containing this file is a 0.0.x plugin, loaded by the compat bridge."""

RUNTIME_PACKAGE = "pydantic_ai_pax"

_installed = False


def _replace(owner: ModuleType, name: str, new: object) -> None:
    """Swap ``owner.name`` for ``new`` everywhere pax already holds the old object.

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


def _install_theme() -> None:
    """Paint pax's default theme in Code Puppy's colours.

    Runs before any other pax module is imported: several bind
    theme colours at import time, in dicts and default arguments that
    :func:`_replace` cannot reach.
    """
    from pydantic_ai_pax.ui.rendering import theme

    from code_puppy import colors

    for name, shade in colors.SHADES.items():
        setattr(theme, name, shade.colour)
    for name, value in colors.ROLES.items():
        setattr(theme, name, value)
    theme._SLOTS = colors.SLOTS
    theme._BASIC = colors.BASIC


def _naming_first(start_chat: Callable[P, T]) -> Callable[P, T]:
    """pax's terminal session, after the puppy has a name.

    The result takes exactly what ``start_chat`` takes and hands it all on.

    Deliberately not ``async``: the questions are asked when the session's
    coroutine is created, before the event loop that runs it exists, so
    Ctrl-C at a question behaves as it does at any plain prompt.

    ``chat`` is the one launch path with a person at the keyboard; ``-p``,
    ``--web`` and subcommands never call it. ``load_plugins=False`` is a
    caller-supplied agent, which gets no persona to name.
    """

    def chat(*args: P.args, **options: P.kwargs) -> T:
        from pydantic_ai_pax.config.settings_store import SettingsStore

        from code_puppy import first_run

        store = options.get("store")
        if (
            isinstance(store, SettingsStore)
            and options.get("load_plugins", True)
            and first_run.at_a_terminal()
        ):
            try:
                first_run.welcome(store)
            except Exception as exc:  # noqa: BLE001 - naming must never stop pup
                print(
                    f"Skipped naming the puppy ({type(exc).__name__}: {exc}). "
                    f"Use {first_run.CONFIGURE} instead.",
                    file=sys.stderr,
                )
        return start_chat(*args, **options)

    return chat


def _install_first_run() -> None:
    from pydantic_ai_pax import app

    _replace(app, "chat", _naming_first(app.chat))


def install() -> None:
    """Apply every replacement. Idempotent; call before importing the pax CLI."""
    global _installed
    if _installed:
        return
    former_name.install()
    _install_theme()
    _install_paths()
    _install_credentials()
    _install_updates()
    _install_branding()
    _install_plugins()
    _install_agent()
    _install_first_run()
    _install_sessions()
    _installed = True


def _install_paths() -> None:
    from pydantic_ai_pax.config import settings_store

    _replace(settings_store, "config_dir", identity.config_dir)
    _replace(settings_store, "state_dir", identity.runtime_state_dir)


def _install_credentials() -> None:
    from pydantic_ai_pax.config import credential_store

    upstream_path = credential_store.credentials_path

    def credentials_path(*, account: str = credential_store._ACCOUNT) -> Path:
        """pax's file name for ``account``, in Code Puppy's config folder."""
        return identity.config_dir() / upstream_path(account=account).name

    credential_store._SERVICE = identity.KEYRING_SERVICE
    _replace(credential_store, "credentials_path", credentials_path)


def _install_updates() -> None:
    from pydantic_ai_pax.cli import self_update

    from code_puppy import update

    self_update.DISTRIBUTION = identity.DISTRIBUTION
    self_update.PYPI_URL = update.PYPI_URL
    _replace(self_update, "installed", update.installed)
    _replace(self_update, "latest", update.latest)
    _replace(self_update, "find_update", update.find_update)
    _replace(self_update, "tool_executable", update.tool_executable)
    _replace(self_update, "Update", update.PuppyUpdate)
    _replace(self_update, "Updates", update.PuppyUpdates)

    from pydantic_ai_pax.cli import install as tool_install

    # Read by the `/update` menu's wording and by `herdr` to relaunch a session.
    _replace(tool_install, "command_name", update.command_name)

    from pydantic_ai_pax.cli import cli

    _replace(cli, "_update", update.cli_update)


def _install_branding() -> None:
    from pydantic_ai_pax.ui.rendering import branding as upstream_branding

    from code_puppy import branding

    from pydantic_ai_pax.ui.rendering import welcome

    _replace(upstream_branding, "print_banner", branding.print_banner)
    _replace(welcome, "print_welcome", branding.print_welcome)


def _install_agent() -> None:
    from pydantic_ai_pax import app
    from pydantic_ai_pax.runtime.session import StockAgent

    def create_stock_agent(model: Model | str | None = None) -> StockAgent[None, str]:
        """pax's stock agent under Code Puppy's name, without pax's docs capability.

        That capability lets the model read pax's own docs to answer questions
        about "CLAI itself". They describe pax's commands and folders, not
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


def _install_sessions() -> None:
    """Offer 0.0.x sessions in ``/resume``, as Claude Code's and Codex's are."""
    from pydantic_ai_pax.runtime import imported_sessions
    from pydantic_ai_pax.ui.menus import session_browser

    from code_puppy import legacy_sessions as legacy

    source = legacy.SOURCE
    imported_sessions._SOURCES[source] = imported_sessions._Source(
        label=legacy.LABEL,
        home=legacy.home,
        files=legacy.files,
        find=legacy.find,
        titles=legacy.titles,
        header=legacy.header,
        messages=legacy.messages,
        tasks=legacy.tasks,
    )
    _replace(
        imported_sessions,
        "IMPORT_SOURCES",
        (*imported_sessions.IMPORT_SOURCES, source),
    )
    # Built from IMPORT_SOURCES when the browser was imported, so extend it too.
    _replace(session_browser, "_FILTERS", (*session_browser._FILTERS, source))


def is_legacy_plugin(entry: Path) -> bool:
    """Whether a discovered drop-in is really a 0.0.x plugin folder."""
    return (
        entry.name == "__init__.py" and (entry.parent / LEGACY_PLUGIN_MARKER).is_file()
    )


def _install_plugins() -> None:
    from pydantic_ai_pax.config import builtins
    from pydantic_ai_pax.plugins import process_plugins

    from code_puppy.builtin_plugins import CLAUDE_CODE_NO_UPDATE_CHECK, PUPPY_PLUGINS

    os.environ.setdefault(CLAUDE_CODE_NO_UPDATE_CHECK, "1")

    _replace(builtins, "DEFAULT_PLUGINS", (*builtins.DEFAULT_PLUGINS, *PUPPY_PLUGINS))
    _replace(builtins, "STOCK_PLUGINS", (*builtins.STOCK_PLUGINS, *PUPPY_PLUGINS))

    upstream_discover = process_plugins.ProcessPlugins._discover

    def _discover(
        self: process_plugins.ProcessPlugins, console: Console
    ) -> dict[str, Path]:
        """pax's drop-in scan, minus 0.0.x plugin folders that share the directory."""
        found = upstream_discover(self, console)
        return {
            name: path for name, path in found.items() if not is_legacy_plugin(path)
        }

    process_plugins.ProcessPlugins._discover = _discover
