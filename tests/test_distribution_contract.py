"""The contract between Code Puppy and the pydantic-ai-pax it is pinned to.

``code_puppy.distribution`` replaces a handful of pax names at startup. These
tests fail when a pax upgrade moves one of them, and prove that the
replacements actually take effect where pax reads them.
"""

from __future__ import annotations

import importlib
import inspect
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from code_puppy.colors import ROLES, SHADES

REPLACED = [
    ("pydantic_ai_pax.config.settings_store", "config_dir"),
    ("pydantic_ai_pax.config.settings_store", "state_dir"),
    ("pydantic_ai_pax.config.credential_store", "_SERVICE"),
    ("pydantic_ai_pax.config.credential_store", "_ACCOUNT"),
    ("pydantic_ai_pax.config.credential_store", "credentials_path"),
    ("pydantic_ai_pax.cli.self_update", "DISTRIBUTION"),
    ("pydantic_ai_pax.cli.self_update", "PYPI_URL"),
    ("pydantic_ai_pax.cli.self_update", "installed"),
    ("pydantic_ai_pax.cli.self_update", "latest"),
    ("pydantic_ai_pax.cli.self_update", "find_update"),
    ("pydantic_ai_pax.cli.self_update", "tool_executable"),
    ("pydantic_ai_pax.cli.self_update", "Update"),
    ("pydantic_ai_pax.cli.self_update", "Updates"),
    ("pydantic_ai_pax.cli.cli", "_update"),
    ("pydantic_ai_pax.cli.install", "command_name"),
    *(
        ("pydantic_ai_pax.ui.rendering.theme", name)
        for name in (*SHADES, *ROLES, "_SLOTS", "_BASIC")
    ),
    ("pydantic_ai_pax.ui.rendering.branding", "print_banner"),
    ("pydantic_ai_pax.ui.rendering.welcome", "print_welcome"),
    ("pydantic_ai_pax.ui.rendering.welcome", "_report_project"),
    ("pydantic_ai_pax.config.builtins", "DEFAULT_PLUGINS"),
    ("pydantic_ai_pax.config.builtins", "STOCK_PLUGINS"),
    ("pydantic_ai_pax.plugins.process_plugins", "ProcessPlugins"),
    ("pydantic_ai_pax.app", "create_stock_agent"),
    ("pydantic_ai_pax.app", "chat"),
    ("pydantic_ai_pax.runtime.imported_sessions", "IMPORT_SOURCES"),
    ("pydantic_ai_pax.runtime.imported_sessions", "_SOURCES"),
    ("pydantic_ai_pax.runtime.imported_sessions", "_Source"),
    ("pydantic_ai_pax.runtime.imported_sessions", "ImportCatalog"),
    ("pydantic_ai_pax.runtime.imported_sessions", "save_import"),
    ("pydantic_ai_pax.runtime.imported_history", "framed"),
    ("pydantic_ai_pax.ui.menus.session_browser", "_FILTERS"),
    ("pydantic_ai_pax.runtime.session", "StockAgent"),
    ("pydantic_ai_pax.runtime.reloading", "_reload"),
]


@pytest.mark.parametrize(("module", "name"), REPLACED)
def test_pax_still_has_the_symbol(module: str, name: str) -> None:
    assert hasattr(importlib.import_module(module), name), f"{module}.{name} moved"


def test_discover_is_still_a_method() -> None:
    from pydantic_ai_pax.plugins.process_plugins import ProcessPlugins

    assert callable(ProcessPlugins._discover)


def test_settings_live_in_code_puppys_folder(
    installed_distribution: None, home: Path
) -> None:
    from pydantic_ai_pax.config.settings_store import SettingsStore

    store = SettingsStore()
    assert store.path == home / ".code_puppy" / "config.db"
    assert store.plugins_dir == home / ".code_puppy" / "plugins"


def test_modules_that_bound_the_names_early_see_code_puppys(
    installed_distribution: None, home: Path
) -> None:
    """pax imports these with ``from x import y``; the binding must be ours."""
    from pydantic_ai_pax.mcp.store import MCPStore
    from pydantic_ai_pax.runtime import live_registry, session_runtime
    from pydantic_ai_pax.ui.menus import update_menu
    from pydantic_ai_pax.ui.rendering import spinners, welcome

    from code_puppy import branding, update

    root = home / ".code_puppy"
    assert MCPStore().path == root / "mcp.json"
    assert spinners.config_dir() == root
    assert live_registry.state_dir() == root / "state"
    assert session_runtime.Updates is update.PuppyUpdates
    assert welcome.print_welcome is branding.print_welcome
    assert welcome.installed is update.installed
    # The `/update` menu names the command to the user.
    assert update_menu.command_name is update.command_name


def test_credentials_use_code_puppys_folder_and_service(
    installed_distribution: None, home: Path
) -> None:
    from pydantic_ai_pax.config import credential_store

    path = credential_store.credentials_path(account="gateway/openai@work")
    assert path.parent == home / ".code_puppy"
    assert path.name.startswith("credentials-gateway") and "/" not in path.name
    assert credential_store._SERVICE == "code-puppy-v1"
    assert (
        credential_store._files(account="x", fallback=None)[1].parent
        == home / ".code_puppy"
    )


def test_default_plugin_sets_keep_their_identity(installed_distribution: None) -> None:
    """pax's ``chat`` compares the plugin tuples with ``is``."""
    from pydantic_ai_pax import app
    from pydantic_ai_pax.config import builtins

    from code_puppy.builtin_plugins import PUPPY_PLUGINS

    assert app.DEFAULT_PLUGINS is builtins.DEFAULT_PLUGINS
    assert app.STOCK_PLUGINS is builtins.STOCK_PLUGINS
    ids = [plugin.id for plugin in builtins.STOCK_PLUGINS]
    assert ids[0] == "coder" and len(ids) == len(set(ids))
    assert all(plugin in builtins.STOCK_PLUGINS for plugin in PUPPY_PLUGINS)


def test_the_stock_agent_is_built_as_code_puppy(installed_distribution: None) -> None:
    from pydantic_ai_pax import app
    from pydantic_ai_pax.cli import headless
    from pydantic_ai_pax.runtime.session import StockAgent

    agent = app.create_stock_agent("test")
    assert isinstance(agent, StockAgent) and agent.name == "code-puppy"
    # The headless CLI imported the factory under another name; it must be ours too.
    assert headless.create_agent is app.create_stock_agent


def test_legacy_plugin_folders_are_left_to_the_compat_bridge(
    installed_distribution: None, tmp_path: Path
) -> None:
    from pydantic_ai_pax.plugins.process_plugins import ProcessPlugins

    plugins = tmp_path / "plugins"
    (plugins / "legacy").mkdir(parents=True)
    (plugins / "legacy" / "__init__.py").write_text("")
    (plugins / "legacy" / "register_callbacks.py").write_text("")
    (plugins / "native_pkg").mkdir()
    (plugins / "native_pkg" / "__init__.py").write_text("")
    (plugins / "native_file.py").write_text("")

    fake = SimpleNamespace(store=SimpleNamespace(plugins_dir=plugins))
    found = ProcessPlugins._discover(fake, console=None)  # type: ignore[arg-type]
    assert sorted(found) == ["native_file", "native_pkg"]


def test_pax_only_stops_the_splash() -> None:
    """Code Puppy's splash stands in for pax's, which ``run`` only ever stops."""
    from pydantic_ai_pax.cli import cli

    assert "splash: Splash | None" in inspect.getsource(cli.run)
    assert set(re.findall(r"splash\.(\w+)", inspect.getsource(cli))) == {"stop"}


def test_cli_runs_as_code_puppy_in_a_fresh_home(home: Path) -> None:
    """End to end: a real process writes to ~/.code_puppy and nowhere else."""
    env = {**os.environ, "CODE_PUPPY_NO_SPLASH": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "code_puppy", "config", "show"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"update_channel": "stable"' in result.stdout
    assert (home / ".code_puppy" / "config.db").is_file()
    assert not (home / ".config").exists()
    assert not (home / ".local").exists()
