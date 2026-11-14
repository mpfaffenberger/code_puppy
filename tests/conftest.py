"""Shared fixtures: every test runs against a throwaway home directory."""

from __future__ import annotations

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


@pytest.fixture
def installed_distribution() -> None:
    """clai2 running as Code Puppy, as ``main`` sets it up before the CLI starts."""
    from code_puppy import distribution

    distribution.install()
