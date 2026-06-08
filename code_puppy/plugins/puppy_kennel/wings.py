"""Wing namespacing — the convention that compartmentalizes memory.

Three namespaces, all stored in the same shared kennel:

* ``repo:<path>``   — project memory, shared between agents in that repo
* ``agent:<name>``  — per-agent diary, private by convention
* ``user:default``  — cross-cutting user preferences

Keep this module dependency-free; both recorder and retriever import it.
"""

from __future__ import annotations

import os
from pathlib import Path

USER_WING = "user:default"


def repo_wing(start: Path | str | None = None) -> str:
    """Return the ``repo:<path>`` wing for the given (or current) directory.

    Walks upward looking for a ``.git`` directory. If none is found, falls
    back to the resolved start directory itself — bare directories are still
    legitimate project scopes.
    """
    here = Path(start) if start else Path.cwd()
    here = here.resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return f"repo:{candidate}"
    return f"repo:{here}"


def agent_wing(agent_name: str) -> str:
    """Return the ``agent:<name>`` wing for a given agent."""
    safe = (agent_name or "unknown").strip() or "unknown"
    return f"agent:{safe}"


def default_recall_scope(agent_name: str, cwd: Path | str | None = None) -> list[str]:
    """The standard recall set: this repo + this agent + cross-user prefs."""
    return [repo_wing(cwd), agent_wing(agent_name), USER_WING]


def detect_cwd() -> Path:
    """Best-effort current working directory.

    Falls back to ``$HOME`` if cwd is somehow unavailable (rare but possible
    in some test environments).
    """
    try:
        return Path(os.getcwd())
    except OSError:
        return Path.home()
