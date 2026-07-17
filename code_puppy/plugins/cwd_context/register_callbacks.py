"""Inject a small cwd + file-index snapshot into the dynamic system prompt.

Why this exists
---------------
Mist's default system prompt tells the agent to "explore directories before
reading/modifying files", but it gives the agent no actual view of what's in
the working directory. When the user references a bare filename (``read
IN_PLACE_STATUS_PLAN.md``), the agent has to guess — and it often guesses
wrong, falling back to ``grep`` (a content search) when it should have used
``list_files`` or shell ``find`` (a name search).

This plugin fixes that by appending two short blocks to the runtime system
prompt on every turn:

1. The current working directory (absolute path).
2. A bounded, depth-2 file index of the cwd, with build artifacts / venvs /
   generated media filtered out. The index is capped at ``_MAX_INDEX_CHARS``
   (~1500 chars) so it can't blow the prompt budget, and it's regenerated only
   when the cwd's top-layer mtime changes.

The blocks land in the *dynamic* half of the prompt (see
``BaseAgent.get_prompt_sections``), so they recompute automatically when the
agent's cwd changes — which keeps them honest without extra invalidation
plumbing.

Cost
----
- On a typical 5k-entry repo this fragment is ~1k tokens.
- Tree walk is cached in-memory keyed by ``(cwd, signature)`` where
  ``signature`` is the max mtime across the top two levels. Cache hits are
  O(1). First walk of a large repo takes ~200ms; subsequent calls are free
  until the tree changes.
- Failures (permission denied, vanished dir, ENOSPC) degrade to a cwd-only
  fragment so a bad index never breaks the agent.
"""

from __future__ import annotations

import os

from code_puppy.callbacks import register_callback

from .file_index import build_file_index, get_tree_signature

# Bounded output so we never blow the 12k prompt ceiling. 1500 chars ≈ 375
# tokens at our ~4-chars-per-token heuristic. Big enough to surface the
# immediate `docs/`, `src/`, top-level plans — small enough that the dynamic
# prompt stays cheap even with puppy_kennel memory and other plugins active.
_MAX_INDEX_CHARS = 1500
_MAX_DEPTH = 2
_MAX_ENTRIES = 60

_cache: dict[str, tuple[float, str | None]] = {}


def _build_fragment(cwd: str) -> str | None:
    """Return the cwd + file-index fragment, or ``None`` to stay silent.

    The result is cached on ``(cwd, tree_signature)`` so we don't rewalk the
    tree on every turn.
    """
    try:
        signature = get_tree_signature(cwd, max_depth=_MAX_DEPTH)
    except Exception:
        # If the signature itself fails, fall back to no-index — but still
        # emit the cwd line so the agent at least knows where it is.
        return f"## Working directory\n`{cwd}`"

    cached = _cache.get(cwd)
    if cached is not None and cached[0] == signature:
        return cached[1]

    index = build_file_index(
        cwd,
        max_depth=_MAX_DEPTH,
        budget_chars=_MAX_INDEX_CHARS,
        max_entries=_MAX_ENTRIES,
    )
    if index is None:
        fragment = f"## Working directory\n`{cwd}`"
    else:
        body = index.render()
        fragment = (
            "## Working directory\n"
            f"`{index.cwd}`\n"
            "\n"
            "## File tree (top 2 levels, noise filtered)\n"
            "Use this to resolve bare filenames — don't reach for `grep` "
            "(it searches contents, not names). Re-run `list_files` if the "
            "tree looks stale.\n"
            "```\n"
            f"{body}\n"
            "```"
        )

    _cache[cwd] = (signature, fragment)
    return fragment


def _on_load_prompt() -> str | None:
    """``load_prompt`` callback — emit cwd context for the current turn."""
    try:
        cwd = os.getcwd()
    except OSError:
        return None
    try:
        return _build_fragment(cwd)
    except Exception:
        # Worst case: stay silent. A missing cwd block is much less harmful
        # than a crashed agent.
        return None


register_callback("load_prompt", _on_load_prompt)


def invalidate_cwd_cache(cwd: str | None = None) -> None:
    """Test/debug helper — drop cached entries for ``cwd`` (or all)."""
    if cwd is None:
        _cache.clear()
    else:
        _cache.pop(cwd, None)
