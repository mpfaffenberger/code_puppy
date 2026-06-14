"""Phase 2e: completion engine for the Textual prompt.

Pure, testable logic that maps "the current line + cursor column" to a set of
completion candidates. Two contexts are supported (the two most-used in the
classic UI):

* ``/command``  -> slash-command names from the command registry
* ``@path``     -> fuzzy/glob file paths (reusing the classic completer's
  internals so behavior matches exactly)

The widget + key handling live in app.py; this module stays UI-free so it can
be unit-tested without a running app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CompletionItem:
    """A single candidate: what to insert, what to show, and a meta hint."""

    insert: str
    display: str
    meta: str = ""


@dataclass
class CompletionResult:
    """Candidates plus the column span on the current line they replace."""

    start_col: int
    end_col: int
    items: List[CompletionItem]


def _command_items(partial: str) -> List[CompletionItem]:
    from code_puppy.command_line.command_registry import get_unique_commands

    items: List[CompletionItem] = []
    for info in sorted(get_unique_commands(), key=lambda c: c.name):
        if info.name.startswith(partial):
            items.append(
                CompletionItem(
                    insert=f"/{info.name} ",
                    display=f"/{info.name}",
                    meta=info.description or "",
                )
            )
    return items


def _path_items(query: str) -> List[CompletionItem]:
    # Reuse the classic completer's internals so @-completion matches exactly.
    from code_puppy.command_line import file_path_completion as fpc

    start_position = -len(query)
    if fpc._looks_like_path_navigation(query):
        comps = list(fpc._glob_completions(query, start_position))
    else:
        comps = fpc._fuzzy_completions(query, start_position)
        if not comps:
            comps = list(fpc._glob_completions(query, start_position))

    items: List[CompletionItem] = []
    for c in comps:
        text = c.text
        display = c.display if isinstance(c.display, str) else text
        meta = c.display_meta if isinstance(c.display_meta, str) else ""
        items.append(CompletionItem(insert=f"@{text}", display=display, meta=meta))
    return items


def compute_completions(line: str, col: int) -> Optional[CompletionResult]:
    """Compute completions for ``line`` with the cursor at column ``col``.

    Returns None when there's nothing to complete in the current context.
    """
    before = line[:col]

    # Slash command: the whole first token, only before the first space.
    if before.startswith("/") and " " not in before:
        items = _command_items(before[1:])
        if not items:
            return None
        return CompletionResult(start_col=0, end_col=col, items=items)

    # @path: the whitespace-delimited token ending at the cursor.
    token_start = col
    while token_start > 0 and not before[token_start - 1].isspace():
        token_start -= 1
    token = before[token_start:col]
    if token.startswith("@"):
        items = _path_items(token[1:])
        if not items:
            return None
        return CompletionResult(start_col=token_start, end_col=col, items=items)

    return None
