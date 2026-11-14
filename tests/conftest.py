"""Shared fixtures: every test runs against a throwaway home directory."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

XDG_VARIABLES = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
)


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at a temp folder so no test touches real user files."""
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    for name in XDG_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return folder


@pytest.fixture(autouse=True)
def no_os_keyring() -> Iterator[None]:
    """Keep tests out of the real OS keyring; credentials fall back to files."""
    import keyring
    from keyring.backends.fail import Keyring

    previous = keyring.get_keyring()
    keyring.set_keyring(Keyring())
    try:
        yield
    finally:
        keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def clean_legacy_state(tmp_path: Path) -> Iterator[None]:
    """0.0.x compat state is process-global; give every test a clean copy.

    Only modules imported from the test's own temp folder are unloaded: the
    runtime's modules must stay loaded, or they would lose Code Puppy's identity.
    """
    import sys

    from code_puppy import callbacks, messaging, plugins

    path = list(sys.path)
    callbacks.clear_callbacks()
    plugins.reset_for_tests()
    try:
        yield
    finally:
        callbacks.clear_callbacks()
        plugins.reset_for_tests()
        messaging.set_console(None)
        root = str(tmp_path)
        for name, module in list(sys.modules.items()):
            origin = getattr(module, "__file__", None) or ""
            if origin.startswith(root) or name == plugins.PROJECT_NAMESPACE:
                del sys.modules[name]
        sys.path[:] = path


@pytest.fixture
def installed_distribution() -> None:
    """clai2 running as Code Puppy, as ``main`` sets it up before the CLI starts."""
    from code_puppy import distribution

    distribution.install()
