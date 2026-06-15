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


# Commands that exist only in the Textual UI (no classic registry entry), so
# they must be advertised for completion explicitly.
_TUI_ONLY_COMMANDS = {
    "history": "Search & reuse a previous prompt",
}


def _command_items(partial: str) -> List[CompletionItem]:
    # Importing command_handler registers all built-in slash commands (it's a
    # cheap no-op after the first import), so completion works regardless of
    # import order.
    import code_puppy.command_line.command_handler  # noqa: F401
    from code_puppy.command_line.command_registry import get_unique_commands

    items: List[CompletionItem] = []
    seen = set()
    for info in sorted(get_unique_commands(), key=lambda c: c.name):
        if info.name.startswith(partial):
            seen.add(info.name)
            items.append(
                CompletionItem(
                    insert=f"/{info.name} ",
                    display=f"/{info.name}",
                    meta=info.description or "",
                )
            )
    for name, desc in sorted(_TUI_ONLY_COMMANDS.items()):
        if name.startswith(partial) and name not in seen:
            items.append(
                CompletionItem(insert=f"/{name} ", display=f"/{name}", meta=desc)
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


_MCP_SERVER_SUBCOMMANDS = {
    "start": "Start a server",
    "stop": "Stop a server",
    "restart": "Restart a server",
    "status": "Show server status",
    "logs": "Show server logs",
    "edit": "Edit a server config",
    "remove": "Remove a server",
}
_MCP_GENERAL_SUBCOMMANDS = {
    "install": "Install MCP servers",
    "start-all": "Start all servers",
    "stop-all": "Stop all servers",
    "search": "Search available servers",
    "silence-warning": "Silence the bind warning",
    "unsilence-warning": "Restore the bind warning",
    "help": "MCP help",
}
_MCP_ALL_SUBCOMMANDS = {**_MCP_SERVER_SUBCOMMANDS, **_MCP_GENERAL_SUBCOMMANDS}


def _model_names() -> List[str]:
    from code_puppy.command_line.model_picker_completion import load_model_names

    return sorted(load_model_names())


def _agent_names() -> List[str]:
    from code_puppy.agents.agent_manager import get_available_agents

    return sorted(get_available_agents().keys())


def _server_names() -> List[str]:
    try:
        from code_puppy.mcp_.manager import get_mcp_manager

        return [s.name for s in get_mcp_manager().list_servers()]
    except Exception:
        return []


def _filter(candidates: List[str], token: str) -> List[CompletionItem]:
    low = token.lower()
    return [
        CompletionItem(insert=c, display=c)
        for c in candidates
        if not low or low in c.lower()
    ]


def _arg_items(before: str, token: str) -> List[CompletionItem]:
    """Argument completions for /model, /agent, and /mcp."""
    head, _, _ = before.partition(" ")
    cmd = head[1:].lower()

    if cmd == "model":
        return _filter(_model_names(), token)
    if cmd in ("agent", "a", "agents"):
        return _filter(_agent_names(), token)
    if cmd == "mcp":
        # Tokens already completed (before the one under the cursor).
        seg = before[len(head) + 1 :]
        prior = seg[: len(seg) - len(token)].split()
        if not prior:
            return [
                CompletionItem(insert=name, display=name, meta=desc)
                for name, desc in sorted(_MCP_ALL_SUBCOMMANDS.items())
                if not token or token.lower() in name.lower()
            ]
        if len(prior) == 1 and prior[0] in _MCP_SERVER_SUBCOMMANDS:
            return _filter(_server_names(), token)
    return []


def compute_completions(line: str, col: int) -> Optional[CompletionResult]:
    """Compute completions for ``line`` with the cursor at column ``col``.

    Returns None when there's nothing to complete in the current context.
    """
    before = line[:col]

    # 1. Slash command name: the whole first token, only before the first space.
    if before.startswith("/") and " " not in before:
        items = _command_items(before[1:])
        if not items:
            return None
        return CompletionResult(start_col=0, end_col=col, items=items)

    # Current whitespace-delimited token ending at the cursor.
    token_start = col
    while token_start > 0 and not before[token_start - 1].isspace():
        token_start -= 1
    token = before[token_start:col]

    # 2. @path works anywhere (incl. inside command args).
    if token.startswith("@"):
        items = _path_items(token[1:])
        if not items:
            return None
        return CompletionResult(start_col=token_start, end_col=col, items=items)

    # 3. Slash-command argument completion (/model, /agent, /mcp ...).
    if before.startswith("/"):
        items = _arg_items(before, token)
        if not items:
            return None
        return CompletionResult(start_col=token_start, end_col=col, items=items)

    return None
