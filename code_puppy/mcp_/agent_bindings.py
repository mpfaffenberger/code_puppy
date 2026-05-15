"""Agent ↔ MCP server bindings.

Persists which MCP servers each agent should see, and whether those servers
should auto-start when the agent is invoked.

Storage: ``$XDG_CONFIG_HOME/code_puppy/mcp_agent_bindings.json``

Schema::

    {
      "bindings": {
        "<agent_name>": {
          "<mcp_server_name>": {"auto_start": true}
        }
      }
    }

Design notes:

* This module is **pure data**. No prompts, no TUI, no manager calls.
* Strict opt-in: an agent with no entry gets *zero* MCP servers from
  :py:meth:`code_puppy.mcp_.MCPManager.get_servers_for_agent`.
* Server identity is the user-chosen ``name`` (the key in
  ``mcp_servers.json``), matching how everything else in the MCP layer talks
  about servers.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Dict, List, Optional

from code_puppy.config import CONFIG_DIR

logger = logging.getLogger(__name__)

BINDINGS_FILE = os.path.join(CONFIG_DIR, "mcp_agent_bindings.json")

_EMPTY: Dict[str, Any] = {"bindings": {}}


# ---------- low-level I/O ----------------------------------------------------


def _read() -> Dict[str, Any]:
    """Load the bindings file, returning an empty skeleton if missing/broken."""
    path = pathlib.Path(BINDINGS_FILE)
    if not path.exists():
        return {"bindings": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # pragma: no cover - corrupted file
        logger.warning("Failed to read %s: %s — starting fresh", BINDINGS_FILE, exc)
        return {"bindings": {}}
    if not isinstance(data, dict) or "bindings" not in data:
        return {"bindings": {}}
    return data


def _write(data: Dict[str, Any]) -> None:
    """Atomically persist the bindings file."""
    path = pathlib.Path(BINDINGS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    tmp.replace(path)


# ---------- public API -------------------------------------------------------


def load_bindings() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Return the entire bindings map (agent → server → options)."""
    return _read().get("bindings", {})


def _load_json_declared_bindings(agent_name: str) -> Dict[str, Dict[str, Any]]:
    """Load MCP bindings declared inside a JSON sub-agent's config file.

    Lazy-imports the agent layer to avoid a circular dependency: this
    module is pure data, and the agents package depends transitively on
    it. We swallow every error here — a misbehaving agent loader must
    not be able to break MCP filtering for healthy agents.
    """
    try:
        from code_puppy.agents.agent_manager import load_agent
        from code_puppy.agents.json_agent import JSONAgent
    except Exception:  # pragma: no cover - defensive import
        return {}

    try:
        agent = load_agent(agent_name)
    except Exception:
        return {}

    if not isinstance(agent, JSONAgent):
        return {}

    try:
        return agent.get_declared_mcp_bindings()
    except Exception:  # pragma: no cover - defensive
        return {}


def get_bound_servers(agent_name: str) -> Dict[str, Dict[str, Any]]:
    """Return ``{server_name: {"auto_start": bool}}`` for one agent.

    Merges two sources, with the per-machine bindings file winning on
    conflict so users can always override declarations via the menu:

    1. **JSON-declared bindings** — the optional ``mcp_servers`` field on
       a :class:`JSONAgent`'s config file. Lets sub-agent authors ship a
       baseline set of MCP servers with their agent.
    2. **Bindings file** — ``mcp_agent_bindings.json``, edited by the
       ``/agents → B`` menu. Per-machine overrides; takes precedence.

    Returns an empty dict if neither source has anything (strict opt-in:
    unbound agents get *no* MCP servers).
    """
    declared = _load_json_declared_bindings(agent_name)
    file_bindings = load_bindings().get(agent_name, {})

    # Merge: start with declarations, layer file on top so file wins.
    merged: Dict[str, Dict[str, Any]] = {
        name: dict(opts) for name, opts in declared.items()
    }
    for name, opts in file_bindings.items():
        merged[name] = dict(opts)
    return merged


def is_bound(agent_name: str, server_name: str) -> bool:
    """Is ``server_name`` bound to ``agent_name``?"""
    return server_name in get_bound_servers(agent_name)


def get_auto_start(agent_name: str, server_name: str) -> bool:
    """Auto-start flag for one binding, or ``False`` if unbound."""
    return bool(get_bound_servers(agent_name).get(server_name, {}).get("auto_start"))


def set_binding(
    agent_name: str,
    server_name: str,
    auto_start: bool = True,
) -> None:
    """Bind ``server_name`` to ``agent_name`` (idempotent).

    ``auto_start`` defaults to ``True`` because the overwhelmingly common
    intent when binding an MCP server is "and yes, please spin it up when
    this agent is invoked." Callers who want a bound-but-dormant server
    must opt out explicitly.
    """
    data = _read()
    bindings = data.setdefault("bindings", {})
    agent_block = bindings.setdefault(agent_name, {})
    agent_block[server_name] = {"auto_start": bool(auto_start)}
    _write(data)


def remove_binding(agent_name: str, server_name: str) -> bool:
    """Unbind ``server_name`` from ``agent_name``. Returns True if removed."""
    data = _read()
    bindings = data.get("bindings", {})
    agent_block = bindings.get(agent_name)
    if not agent_block or server_name not in agent_block:
        return False
    del agent_block[server_name]
    if not agent_block:
        del bindings[agent_name]
    _write(data)
    return True


def toggle_binding(agent_name: str, server_name: str) -> bool:
    """Flip a binding on/off. Returns the new bound state (True=bound).

    When toggling ON we inherit ``set_binding``'s default of
    ``auto_start=True`` — see that function's docstring for rationale.
    """
    if is_bound(agent_name, server_name):
        remove_binding(agent_name, server_name)
        return False
    set_binding(agent_name, server_name)
    return True


def toggle_auto_start(agent_name: str, server_name: str) -> Optional[bool]:
    """Flip auto-start for an existing binding.

    Returns the new auto-start flag, or ``None`` if the server isn't bound
    (auto-start is meaningless without a binding).
    """
    if not is_bound(agent_name, server_name):
        return None
    new_value = not get_auto_start(agent_name, server_name)
    set_binding(agent_name, server_name, auto_start=new_value)
    return new_value


def get_agents_for_server(server_name: str) -> List[str]:
    """Reverse lookup: which agents are bound to this server?"""
    return [
        agent for agent, servers in load_bindings().items() if server_name in servers
    ]


def remove_server_from_all_agents(server_name: str) -> int:
    """Drop ``server_name`` from every agent's bindings. Returns count."""
    data = _read()
    bindings = data.get("bindings", {})
    removed = 0
    for agent, servers in list(bindings.items()):
        if server_name in servers:
            del servers[server_name]
            removed += 1
            if not servers:
                del bindings[agent]
    if removed:
        _write(data)
    return removed


def rename_server_in_bindings(old_name: str, new_name: str) -> int:
    """Rename a server everywhere it's bound. Returns count of agents affected."""
    if old_name == new_name:
        return 0
    data = _read()
    bindings = data.get("bindings", {})
    affected = 0
    for servers in bindings.values():
        if old_name in servers:
            servers[new_name] = servers.pop(old_name)
            affected += 1
    if affected:
        _write(data)
    return affected
