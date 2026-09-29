"""Keep tool discovery cheap without changing registration behavior."""

import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from code_puppy.tools._lazy import lazy_registration


def test_registration_defers_import_and_forwards_arguments(monkeypatch):
    implementation = Mock(return_value="registered")
    importer = Mock(return_value=SimpleNamespace(register_example=implementation))
    monkeypatch.setattr("code_puppy.tools._lazy.import_module", importer)
    register = lazy_registration("example.tools", "register_example")
    importer.assert_not_called()
    assert register.__name__ == "register_example"
    agent = object()
    assert register(agent, option=True) == "registered"
    importer.assert_called_once_with("example.tools")
    implementation.assert_called_once_with(agent, option=True)


def test_listing_tools_does_not_import_browser_implementations():
    # A fresh process avoids modules preloaded by pytest/conftest masking
    # an accidental eager import. No fragile wall-clock threshold.
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from code_puppy.tools import TOOL_REGISTRY
assert 'browser_initialize' in TOOL_REGISTRY
assert all(callable(value) for value in TOOL_REGISTRY.values())
assert 'code_puppy.tools.browser.browser_manager' not in sys.modules
assert 'playwright.async_api' not in sys.modules
""",
        ],
        check=True,
        timeout=30,
    )


def test_all_lazy_registrations_resolve():
    from importlib import import_module

    from code_puppy.tools import TOOL_REGISTRY

    for register in TOOL_REGISTRY.values():
        if register.__module__ != "code_puppy.tools._lazy":
            continue
        closed = dict(zip(register.__code__.co_freevars, register.__closure__))
        module = import_module(closed["module"].cell_contents)
        assert callable(getattr(module, closed["name"].cell_contents))
