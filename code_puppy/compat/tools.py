"""Translate between 0.0.x tool vocabulary and the runtime's.

Three jobs, all about names:

* 0.0.x hooks match on 0.0.x tool names and argument names, so tool calls are
  described to them in those terms.
* Tools registered through the ``register_tools`` hook are collected into one
  toolset the model loads on demand.
* ``custom_command_help`` entries are free-form; they are reduced to a
  command name.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic_ai.capabilities import Toolset
from pydantic_ai.toolsets import FunctionToolset

from code_puppy import callbacks, messaging

SHELL_TOOLS = frozenset({"run_command", "start_command", "shell"})

LEGACY_TOOL_NAMES = {
    "run_command": "agent_run_shell_command",
    "start_command": "agent_run_shell_command",
    "shell": "agent_run_shell_command",
    "write_file": "create_file",
    "list_directory": "list_files",
    "find_files": "list_files",
    "search_files": "grep",
}
"""Runtime tool name to the 0.0.x name hooks were written against.

Tools absent here kept their name (``read_file``, ``edit_file``, ``grep``,
``list_files``) or have no 0.0.x counterpart, and are reported as they are.
"""

LEGACY_ARG_NAMES = {"path": "file_path"}
"""Runtime argument name to the 0.0.x one, added alongside the original."""

LEGACY_TOOLSET_ID = "code_puppy_legacy_tools"

_COMMAND_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def legacy_tool_name(name: str) -> str:
    return LEGACY_TOOL_NAMES.get(name, name)


def legacy_tool_args(name: str, args: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of ``args`` that also carries the 0.0.x argument names."""
    translated = dict(args)
    for new, old in LEGACY_ARG_NAMES.items():
        if new in translated and old not in translated:
            translated[old] = translated[new]
    return translated


def command_name(advertised: str) -> str | None:
    """``"/kennel <query>"`` as ``"kennel"``; ``None`` when no name can be read."""
    match = _COMMAND_NAME.match(advertised.strip().lstrip("/"))
    return match.group(0) if match else None


def legacy_toolset() -> Toolset[Any] | None:
    """Every tool 0.0.x plugins register, as one capability loaded on demand.

    A 0.0.x ``register_func(agent)`` decorates functions with ``@agent.tool``.
    ``FunctionToolset`` has the same decorators, so it stands in for the agent.
    The capability is deferred: its tools cost no prompt tokens until the
    model asks for them.
    """
    toolset: FunctionToolset[Any] = FunctionToolset(id=LEGACY_TOOLSET_ID)
    for result in callbacks.fire_sync("register_tools"):
        if isinstance(result, callbacks.CallbackError):
            messaging.emit_warning(
                f"{result.owner or 'A 0.0.x plugin'} failed to list its tools: {result.error}"
            )
            continue
        for entry in result or ():
            register = entry.get("register_func") if isinstance(entry, dict) else None
            if not callable(register):
                continue
            try:
                register(toolset)
            except Exception as exc:  # noqa: BLE001 - one bad tool must not drop the rest
                name = entry.get("name", "?")
                messaging.emit_warning(f"0.0.x tool {name} failed to register: {exc}")
    names = sorted(toolset.tools)
    if not names:
        return None
    return Toolset(
        toolset,
        id=LEGACY_TOOLSET_ID,
        description=f"Tools from Code Puppy 0.0.x plugins: {', '.join(names)}.",
        defer_loading=True,
    )
