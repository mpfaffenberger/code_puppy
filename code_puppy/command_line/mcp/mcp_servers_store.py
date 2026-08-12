"""Shared read/write helpers for ``mcp_servers.json``.

Four separate call sites (the install wizard, the custom-server form, the
custom-server installer, and ``/mcp remove``) used to each hand-roll their
own ``open("r") -> json.load -> mutate -> open("w") -> json.dump`` against
this file with no atomicity and no lock -- two wizard flows in different
terminals (or a wizard racing ``/mcp remove``) could lose each other's
writes, and a large hand-edited file could balloon ``json.load`` the same
way ``configparser`` ballooned in the original PUP-605 crash. This module
collapses all four into one locked, bounded, atomically-written transaction.
"""

from __future__ import annotations

from typing import Any, Dict

from code_puppy import atomic_json
from code_puppy import config as cp_config


def _ensure_wrapper(data: Any) -> Dict[str, Any]:
    """Normalize whatever was loaded into the canonical ``{"mcp_servers": {}}``
    shape, tolerating a missing/empty file or an already-wrapped dict."""
    if not isinstance(data, dict):
        return {"mcp_servers": {}}
    if "mcp_servers" not in data or not isinstance(data.get("mcp_servers"), dict):
        data["mcp_servers"] = {}
    return data


def upsert_mcp_server(
    server_name: str,
    server_config: Dict[str, Any],
    replace_name: str | None = None,
) -> None:
    """Add or replace ``server_name`` in ``mcp_servers.json``.

    If ``replace_name`` is given (a server being renamed) and differs from
    ``server_name``, its old entry is removed in the *same* locked
    transaction -- matching the single-write semantics the rename+save flow
    always had, rather than splitting it into two separately-locked writes.
    """

    def _mutate(data: Any) -> Dict[str, Any]:
        data = _ensure_wrapper(data)
        if replace_name and replace_name != server_name:
            data["mcp_servers"].pop(replace_name, None)
        data["mcp_servers"][server_name] = server_config
        return data

    atomic_json.mutate_json(
        cp_config.MCP_SERVERS_FILE, _mutate, default={"mcp_servers": {}}
    )


def remove_mcp_server(server_name: str) -> bool:
    """Remove ``server_name`` from ``mcp_servers.json`` if present.

    Returns whether the server was actually present (and thus removed).
    """
    removed = False

    def _mutate(data: Any) -> Dict[str, Any]:
        nonlocal removed
        data = _ensure_wrapper(data)
        if server_name in data["mcp_servers"]:
            del data["mcp_servers"][server_name]
            removed = True
        return data

    atomic_json.mutate_json(
        cp_config.MCP_SERVERS_FILE, _mutate, default={"mcp_servers": {}}
    )
    return removed
