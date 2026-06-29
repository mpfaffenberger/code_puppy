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


def _resolve_worktree_root(git_path: Path) -> Path | None:
    """Resolve main repo root from a worktree ``.git`` file.

    Worktrees store ``.git`` as a file with a ``gitdir: ...`` pointer that
    targets ``<main-repo>/.git/worktrees/<name>`` (absolute or relative).
    This helper parses and resolves that pointer, then walks upward until it
    finds the real ``.git`` directory and returns its parent repo root.
    """
    try:
        content = git_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return None

    gitdir_raw: str | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.lower().startswith("gitdir:"):
            gitdir_raw = line[len("gitdir:") :].strip()
            break

    if not gitdir_raw:
        return None

    try:
        gitdir_path = Path(gitdir_raw)
        if not gitdir_path.is_absolute():
            gitdir_path = git_path.parent / gitdir_path
        gitdir_path = gitdir_path.resolve()
    except (OSError, ValueError):
        return None

    # Only resolve worktrees, not submodules. Worktree gitdir paths contain
    # a "worktrees" component (e.g. <main>/.git/worktrees/<name>), whereas
    # submodules point to <superproject>/.git/modules/<name>. Submodules are
    # distinct repos and should keep their own wing.
    if "worktrees" not in gitdir_path.parts:
        return None

    for parent in (gitdir_path, *gitdir_path.parents):
        if parent.name == ".git" and parent.is_dir():
            return parent.parent

    return None


def repo_wing(start: Path | str | None = None) -> str:
    """Return the ``repo:<path>`` wing for the given (or current) directory.

    Walks upward looking for ``.git``. For normal repos, ``.git`` is a
    directory and that candidate directory is used. For git worktrees,
    ``.git`` is a file; in that case this resolves the linked main repo root
    and uses it so all worktrees share one repo wing. If none is found, falls
    back to the resolved start directory itself — bare directories are still
    legitimate project scopes.
    """
    here = Path(start) if start else Path.cwd()
    here = here.resolve()
    for candidate in (here, *here.parents):
        git_path = candidate / ".git"
        if not git_path.exists():
            continue

        if git_path.is_file():
            worktree_root = _resolve_worktree_root(git_path)
            if worktree_root is not None:
                return f"repo:{worktree_root}"

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
