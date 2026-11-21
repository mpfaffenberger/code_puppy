"""Where Code Puppy keeps its files."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_puppy import identity


def test_everything_lives_in_dot_code_puppy_by_default(home: Path) -> None:
    root = home / ".code_puppy"
    assert identity.config_dir() == root
    assert identity.data_dir() == root
    assert identity.cache_dir() == root
    assert identity.state_dir() == root
    # The runtime's own folders stay out of the user-facing ones.
    assert identity.runtime_state_dir() == root / "state"


def test_xdg_variables_win_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert identity.config_dir() == tmp_path / "cfg" / "code_puppy"
    assert identity.state_dir() == tmp_path / "state" / "code_puppy"
    assert identity.runtime_state_dir() == tmp_path / "state" / "code_puppy"
    # Unset ones keep the legacy folder.
    assert identity.data_dir() == home / ".code_puppy"


def test_empty_xdg_variable_is_ignored(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    assert identity.config_dir() == home / ".code_puppy"


def test_version_is_the_installed_distribution() -> None:
    from importlib import metadata

    assert identity.version() == metadata.version("code-puppy")
