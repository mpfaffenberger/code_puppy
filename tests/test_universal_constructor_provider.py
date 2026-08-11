"""Tests for the Universal Constructor provider seam."""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from code_puppy import universal_constructor_provider as ucp
from code_puppy.universal_constructor_provider import (
    get_universal_constructor_provider,
    register_universal_constructor_provider,
    unregister_universal_constructor_provider,
)


@pytest.fixture
def isolated_provider():
    """Restore the process registration after a test mutates the singleton."""
    original = ucp._registration
    ucp._registration = None
    yield
    ucp._registration = original


def test_core_surfaces_import_when_uc_plugin_is_unavailable():
    """Core must not import the optional plugin, even through a lazy shim."""
    script = r"""
import importlib.abc
import sys


class BlockUniversalConstructor(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("code_puppy.plugins.universal_constructor"):
            raise ImportError(f"blocked optional plugin: {fullname}")
        return None


sys.meta_path.insert(0, BlockUniversalConstructor())
import code_puppy.tools
import code_puppy.tools.universal_constructor
import code_puppy.agents.json_agent
import code_puppy.agents.agent_creator_agent
import code_puppy.command_line.uc_menu

assert "universal_constructor" not in code_puppy.tools.TOOL_REGISTRY
loaded = [
    name for name in sys.modules
    if name.startswith("code_puppy.plugins.universal_constructor")
]
assert loaded == [], loaded
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.anyio
async def test_no_provider_returns_clear_tool_error(isolated_provider):
    from code_puppy.tools.universal_constructor import universal_constructor_impl

    with patch("code_puppy.tools.universal_constructor.get_message_bus"):
        result = await universal_constructor_impl(MagicMock(), "list")

    assert result.success is False
    assert result.error == "Universal Constructor provider is not available"


@pytest.mark.anyio
async def test_registered_provider_drives_list_action(isolated_provider):
    from code_puppy.tools.universal_constructor import universal_constructor_impl

    tool = MagicMock()
    tool.meta.enabled = True
    provider = MagicMock()
    provider.list_tools.return_value = [tool]
    register_universal_constructor_provider(provider)

    with patch("code_puppy.tools.universal_constructor.get_message_bus"):
        result = await universal_constructor_impl(MagicMock(), "list")

    provider.list_tools.assert_called_once_with(include_disabled=True)
    assert result.success is True
    assert result.list_result.total_count == 1
    assert result.list_result.enabled_count == 1


def test_uc_menu_returns_empty_without_provider(isolated_provider):
    from code_puppy.command_line.uc_menu import _get_tool_entries

    assert _get_tool_entries() == []


def test_registration_captures_plugin_loading_owner(isolated_provider):
    from code_puppy.callbacks import clear_loading_context, set_loading_context

    set_loading_context("universal_constructor")
    try:
        registration = register_universal_constructor_provider(MagicMock())
    finally:
        clear_loading_context()

    assert registration.owner == "universal_constructor"


def test_disabled_owner_makes_loaded_provider_inactive(isolated_provider, monkeypatch):
    provider = MagicMock()
    registration = register_universal_constructor_provider(
        provider, owner="universal_constructor"
    )
    monkeypatch.setattr(
        "code_puppy.plugins.config.get_disabled_plugins",
        lambda: {"universal_constructor"},
    )

    assert registration.owner == "universal_constructor"
    assert get_universal_constructor_provider() is None

    monkeypatch.setattr(
        "code_puppy.plugins.config.get_disabled_plugins",
        lambda: set(),
    )
    assert get_universal_constructor_provider() is provider


def test_explicit_unregister_restores_no_provider_fallback(isolated_provider):
    registration = register_universal_constructor_provider(MagicMock())

    assert unregister_universal_constructor_provider(registration) is True
    assert get_universal_constructor_provider() is None
    assert unregister_universal_constructor_provider(registration) is False


def test_reregistration_replaces_provider_and_stale_unregister_is_safe(
    isolated_provider,
):
    first = MagicMock(name="first")
    first_registration = register_universal_constructor_provider(first)
    second = MagicMock(name="second")
    second_registration = register_universal_constructor_provider(second)

    assert get_universal_constructor_provider() is second
    assert unregister_universal_constructor_provider(first_registration) is False
    assert get_universal_constructor_provider() is second
    assert unregister_universal_constructor_provider(second_registration) is True
    assert get_universal_constructor_provider() is None


def test_plugin_callbacks_register_provider_and_tool():
    from code_puppy.plugins.universal_constructor import register_callbacks

    assert get_universal_constructor_provider() is not None
    contributions = register_callbacks._register_tools()
    assert [item["name"] for item in contributions] == ["universal_constructor"]
    assert callable(contributions[0]["register_func"])
