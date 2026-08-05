"""Fuzzy ``@file`` completion for the prompt.

Style cribbed from `pi`'s coding-agent: when the user types ``@query`` (no
slashes), we fuzzy-rank against a project-wide file index built with ripgrep
(``rg --files``), using a tiny tiered scorer. When the query *does* look like
a path (``@dir/``, ``@./x``, ``@~/x``, ``@/abs/x``), we keep the original
glob-based directory-navigation behavior — that's strictly better for "drill
into this folder" than fuzzy.

Fallback chain so nothing ever feels broken:
    1. directory-nav prefixes  -> glob (original behavior)
    2. fuzzy hits from index   -> ranked, top 20
    3. no fuzzy hits           -> glob in cwd (covers fresh sessions before
       the background index has populated)
"""

from __future__ import annotations

import glob
import os
from typing import Iterable, List, Tuple

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from code_puppy.command_line import file_index

# Cap how many fuzzy results we surface; UX gets miserable past ~20.
MAX_FUZZY_RESULTS = 20


# --------------------------------------------------------------------- scoring


def _score(basename_lower: str, path_lower: str, query_lower: str) -> int:
    """Tiered substring score, pi-style. 0 means 'no match'.

    Higher is better. Cheap and predictable — no Levenshtein, no fuse.js.
    """
    if not query_lower:
        return 1  # everything is a "match" for an empty query
    if basename_lower == query_lower:
        return 100
    if basename_lower.startswith(query_lower):
        return 80
    if query_lower in basename_lower:
        return 50
    if query_lower in path_lower:
        return 30
    return 0


# ---------------------------------------------------------------- index helper


def _ensure_index_for_cwd() -> None:
    """Kick off an (async) reindex if the snapshot is stale for current cwd.

    Cheap to call every keystroke — :func:`file_index.reindex` no-ops if a
    build is already in flight, and returns immediately when not blocking.
    """
    snap = file_index.get_index()
    cwd = os.path.abspath(os.getcwd())
    if snap.root != cwd:
        file_index.reindex(cwd, blocking=False)


# -------------------------------------------------------------- fuzzy results


def _fuzzy_completions(query: str, start_position: int) -> List[Completion]:
    """Pi-style ranked completions from the in-memory file index."""
    _ensure_index_for_cwd()
    snap = file_index.get_index()
    if not snap.paths:
        return []

    q_lower = query.lower()
    scored: List[Tuple[int, str, str]] = []  # (-score, path, basename)
    for path, path_lower, basename_lower in zip(
        snap.paths, snap.lowered, snap.basenames_lower
    ):
        s = _score(basename_lower, path_lower, q_lower)
        if s > 0:
            # Negate score so a normal ascending sort gives us best-first.
            scored.append((-s, path, os.path.basename(path)))

    if not scored:
        return []

    # Stable secondary sort on path keeps deterministic ordering for ties.
    scored.sort()
    top = scored[:MAX_FUZZY_RESULTS]

    return [
        Completion(
            path,
            start_position=start_position,
            display=basename,
            display_meta=path,  # show full relpath so users see disambiguation
        )
        for _neg_score, path, basename in top
    ]


# --------------------------------------------------------- glob (legacy path)


def _glob_completions(
    text_after_symbol: str, start_position: int
) -> Iterable[Completion]:
    """Original directory-navigation completion. Untouched semantics."""
    try:
        pattern = text_after_symbol + "*"
        if not pattern.strip("*") or pattern.strip("*").endswith("/"):
            base_path = pattern.strip("*")
            if not base_path:
                base_path = "."
            if base_path.startswith("~"):
                base_path = os.path.expanduser(base_path)
            if os.path.isdir(base_path):
                paths = [
                    os.path.join(base_path, f)
                    for f in os.listdir(base_path)
                    if not f.startswith(".") or text_after_symbol.endswith(".")
                ]
            else:
                paths = []
        else:
            paths = glob.glob(pattern)
            if not pattern.startswith(".") and not pattern.startswith("*/."):
                paths = [p for p in paths if not os.path.basename(p).startswith(".")]
        paths.sort()
        for path in paths:
            is_dir = os.path.isdir(path)
            display = os.path.basename(path)
            if os.path.isabs(path):
                display_path = path
            else:
                if text_after_symbol.startswith("/"):
                    display_path = os.path.abspath(path)
                elif text_after_symbol.startswith("~"):
                    home = os.path.expanduser("~")
                    if path.startswith(home):
                        display_path = "~" + path[len(home) :]
                    else:
                        display_path = path
                else:
                    display_path = path
            display_meta = "Directory" if is_dir else "File"
            yield Completion(
                display_path,
                start_position=start_position,
                display=display,
                display_meta=display_meta,
            )
    except (PermissionError, FileNotFoundError, OSError):
        return


# ------------------------------------------------------------------- completer


def _looks_like_path_navigation(query: str) -> bool:
    """Should we route to legacy glob instead of fuzzy?

    True for empty queries, trailing slashes, and absolute/tilde/explicit-relative
    prefixes — basically any time the user is clearly drilling a known path.
    """
    if not query:
        return True
    if query.endswith("/"):
        return True
    if query.startswith(("/", "~", "./", "../")):
        return True
    # Leading dot = "show me dotfiles in cwd" — glob handles this perfectly.
    if query.startswith("."):
        return True
    # `dir/partial` — they're inside a known directory, glob is better here.
    if "/" in query:
        return True
    return False


class FilePathCompleter(Completer):
    """Pi-style fuzzy @file completer with a glob fallback.

    Public API preserved from the original implementation: a single
    ``symbol`` kwarg (defaults to ``@``) and the standard prompt_toolkit
    ``get_completions`` contract.
    """

    def __init__(self, symbol: str = "@"):
        self.symbol = symbol

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text
        cursor_position = document.cursor_position
        text_before_cursor = text[:cursor_position]
        # ``/fork @...`` reserves its first argument for an agent name.
        # ``/fork @... @...`` reserves its second for a model name.
        # Let Fork's AgentCompleter/ModelNameCompleter own those slots
        # instead of mixing in project files.
        if text_before_cursor.lstrip().startswith("/fork @"):
            return
        if self.symbol not in text_before_cursor:
            return
        symbol_pos = text_before_cursor.rfind(self.symbol)
        query = text_before_cursor[symbol_pos + len(self.symbol) :]
        start_position = -len(query)

        if _looks_like_path_navigation(query):
            yield from _glob_completions(query, start_position)
            return

        fuzzy = _fuzzy_completions(query, start_position)
        if fuzzy:
            yield from fuzzy
            return

        # Index empty (cold start / no rg / outside a project) — fall back to
        # glob in cwd so the prompt always feels responsive.
        yield from _glob_completions(query, start_position)
