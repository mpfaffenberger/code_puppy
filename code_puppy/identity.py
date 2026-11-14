"""Who Code Puppy is: its names and where its files live.

Stdlib-only on purpose. ``main`` imports this before the splash is on screen,
so nothing here may pull in the agent runtime.

Directory rule (unchanged from 0.0.x): an ``XDG_*_HOME`` variable the user set
wins and gets a ``code_puppy`` folder; otherwise everything lives in
``~/.code_puppy``.
"""

from __future__ import annotations

import os
from importlib import metadata
from pathlib import Path

DISPLAY_NAME = "Code Puppy"
DISTRIBUTION = "code-puppy"
AGENT_NAME = "code-puppy"
"""The stock agent's name: what its run spans carry in telemetry."""
COMMANDS = ("pup", "code-puppy")
"""Console scripts this distribution installs, preferred first."""

KEYRING_SERVICE = "code-puppy-v1"
"""Keyring service for 1.0 credentials.

0.0.x stores secrets under ``code-puppy``. A separate service lets a release
candidate and a 0.0.x install share one machine without touching each other's
entries.
"""

PROJECT_DIR = ".code_puppy"
"""Per-repository folder for agents, skills and legacy project plugins."""

_HOME_DIR = ".code_puppy"
_XDG_DIR = "code_puppy"


def _root(env_var: str) -> Path:
    base = os.environ.get(env_var)
    return Path(base) / _XDG_DIR if base else Path.home() / _HOME_DIR


def config_dir() -> Path:
    """Settings, saved sessions, credentials, plugins."""
    return _root("XDG_CONFIG_HOME")


def data_dir() -> Path:
    """Agents and skills (and 0.0.x model catalogs)."""
    return _root("XDG_DATA_HOME")


def cache_dir() -> Path:
    """Disposable files (0.0.x autosaves live here)."""
    return _root("XDG_CACHE_HOME")


def state_dir() -> Path:
    """State that is not a preference (0.0.x command history lives here)."""
    return _root("XDG_STATE_HOME")


def runtime_state_dir() -> Path:
    """Where the runtime keeps its own state folders (``live``, ``workspaces``).

    Without XDG everything shares ``~/.code_puppy``, so the runtime gets a
    ``state`` subfolder to keep its folder names apart from user-facing ones.
    """
    root = state_dir()
    return root if os.environ.get("XDG_STATE_HOME") else root / "state"


def version() -> str:
    """The installed Code Puppy version, or ``0.0.0+unknown`` outside an install."""
    try:
        return metadata.version(DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"
