"""Ranked @file completion with bounded literal directory navigation.

Queries without slashes search a periodically refreshed ripgrep snapshot.
Explicit paths use scandir and literal prefix matching (not glob expansion).
Both paths return at most 20 candidates; quotes preserve filename spaces.
"""

from __future__ import annotations

import heapq
import os
from typing import Iterable, List

from code_puppy.file_completion_tokens import active_reference, quote_path

from termflow.tui.completion import Completer, Completion, Document

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
    file_index.reindex(os.path.abspath(os.getcwd()), blocking=False)


# -------------------------------------------------------------- fuzzy results


def _fuzzy_completions(query: str, start_position: int) -> List[Completion]:
    """Pi-style ranked completions from the in-memory file index."""
    _ensure_index_for_cwd()
    snap = file_index.get_index()
    if snap.root != os.path.abspath(os.getcwd()) or not snap.paths:
        return []

    q_lower = query.lower()
    candidates = (
        (-score, path)
        for path, lower, base in zip(snap.paths, snap.lowered, snap.basenames_lower)
        if (score := _score(base, lower, q_lower)) > 0
    )
    top = heapq.nsmallest(MAX_FUZZY_RESULTS, candidates)

    return [
        Completion(
            path,
            start_position=start_position,
            display=os.path.basename(path),
            display_meta=path,  # show full relpath so users see disambiguation
        )
        for _neg_score, path in top
    ]


# --------------------------------------------------------- glob (legacy path)


def _glob_completions(
    text_after_symbol: str, start_position: int
) -> Iterable[Completion]:
    """Literal prefix navigation with bounded selection, including ~/partial."""
    expanded = os.path.expanduser(text_after_symbol)
    directory, prefix = os.path.split(expanded)
    try:
        with os.scandir(directory or ".") as entries:
            paths = heapq.nsmallest(
                MAX_FUZZY_RESULTS,
                (
                    entry.name
                    for entry in entries
                    if entry.name.startswith(prefix)
                    and (not entry.name.startswith(".") or prefix.startswith("."))
                ),
            )
        original_directory = os.path.dirname(text_after_symbol)
        for name in paths:
            path = os.path.join(original_directory, name)
            actual = os.path.join(directory, name)
            yield Completion(
                path,
                start_position=start_position,
                display=name,
                display_meta="Directory" if os.path.isdir(actual) else "File",
            )
    except (OSError, ValueError):
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
        # ``/fork @...`` reserves arg 1 for an agent, arg 2 for a model — let
        # Fork's AgentCompleter/ModelNameCompleter own those slots instead of
        # mixing in project files.
        if text_before_cursor.lstrip().startswith("/fork @"):
            return
        reference = active_reference(text_before_cursor, self.symbol)
        if reference is None:
            return
        query, raw_length = reference
        start_position = -raw_length
        _ensure_index_for_cwd()
        if _looks_like_path_navigation(query):
            results = _glob_completions(query, start_position)
        else:
            results = _fuzzy_completions(query, start_position) or _glob_completions(
                query, start_position
            )
        for result in results:
            yield Completion(
                quote_path(result.text),
                start_position=start_position,
                display=result.display,
                display_meta=result.display_meta,
            )
