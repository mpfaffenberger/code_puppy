"""Phase 3 Wave B: the /mcp install flow as Textual screens.

The classic ``/mcp install`` launches a prompt_toolkit menu (browse) and uses
blocking ``emit_prompt`` calls (catalog config), both of which fight Textual.
Here it's a list browser + a form, built on the FilterableListScreen and
FormScreen kits.

Other ``/mcp`` subcommands (list/start/stop/status/logs/...) already work in
the TUI because they only emit messages through the bus.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import TYPE_CHECKING, List, Optional

from .screens.base import FilterableListScreen, ListChoice
from .screens.form import FormField, FormScreen

if TYPE_CHECKING:
    from .app import CooperApp

_CUSTOM_ID = "__custom__"
_SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def _is_secret(name: str) -> bool:
    upper = name.upper()
    return any(hint in upper for hint in _SECRET_HINTS)


def open_mcp_install(app: "CooperApp", server_id: Optional[str] = None) -> None:
    """Entry point for ``/mcp install [id]``."""
    from code_puppy.mcp_.server_registry_catalog import catalog
    from code_puppy.messaging import emit_error

    if server_id:
        server = catalog.get_by_id(server_id)
        if server is None:
            results = catalog.search(server_id)
            server = results[0] if len(results) == 1 else None
        if server is None:
            emit_error(
                f"No unique catalog server matching '{server_id}'. "
                "Run /mcp install to browse."
            )
            return
        _open_catalog_form(app, server)
        return

    choices: List[ListChoice] = [
        ListChoice(id=_CUSTOM_ID, label="+ Add a custom server...", search="custom add")
    ]
    for server in catalog.servers:
        marker = " (verified)" if getattr(server, "verified", False) else ""
        choices.append(
            ListChoice(
                id=server.id,
                label=f"{server.display_name}{marker}",
                search=f"{server.name} {server.display_name} "
                f"{getattr(server, 'description', '') or ''}",
            )
        )

    def _on_pick(picked) -> None:
        if not picked:
            return
        if picked == _CUSTOM_ID:
            _open_custom_form(app)
            return
        server = catalog.get_by_id(picked)
        if server is not None:
            _open_catalog_form(app, server)

    app.push_screen(FilterableListScreen("Install an MCP server", choices), _on_pick)


def _open_catalog_form(app: "CooperApp", server) -> None:
    """Form for a catalog server: custom name + env vars + cmd args."""
    fields: List[FormField] = [
        FormField("name", "Custom name", default=server.name, required=True)
    ]
    env_names = list(server.get_environment_vars() or [])
    for i, var in enumerate(env_names):
        fields.append(
            FormField(
                f"env_{i}",
                f"Env: {var}",
                default=os.environ.get(var, ""),
                kind="password" if _is_secret(var) else "text",
            )
        )
    arg_specs = list(server.get_command_line_args() or [])
    for i, spec in enumerate(arg_specs):
        fields.append(
            FormField(
                f"arg_{i}",
                spec.get("prompt", spec.get("name", f"arg {i}")),
                default=spec.get("default", "") or "",
                required=bool(spec.get("required", False)),
            )
        )

    def _on_submit(values) -> None:
        if values is None:
            return
        from code_puppy.command_line.mcp.wizard_utils import (
            install_server_from_catalog,
        )
        from code_puppy.mcp_.manager import get_mcp_manager
        from code_puppy.messaging import emit_error

        env_vars = {
            env_names[i]: values[f"env_{i}"]
            for i in range(len(env_names))
            if values.get(f"env_{i}")
        }
        cmd_args = {
            arg_specs[i].get("name", f"arg_{i}"): values[f"arg_{i}"]
            for i in range(len(arg_specs))
            if values.get(f"arg_{i}")
        }
        try:
            install_server_from_catalog(
                get_mcp_manager(),
                server,
                values["name"],
                env_vars,
                cmd_args,
                str(uuid.uuid4()),
            )
        except Exception as exc:
            emit_error(f"Install failed: {exc}")

    app.push_screen(
        FormScreen(f"Install {server.display_name}", fields, submit_label="Install"),
        _on_submit,
    )


def _open_custom_form(app: "CooperApp") -> None:
    """Form for a hand-rolled MCP server (stdio/http/sse)."""
    fields = [
        FormField("name", "Server name", required=True, placeholder="my-server"),
        FormField(
            "type",
            "Type",
            kind="select",
            options=["stdio", "http", "sse"],
            default="stdio",
        ),
        FormField("command", "Command (stdio)", placeholder="npx -y @scope/server"),
        FormField("args", "Extra args (space-separated, stdio)"),
        FormField("url", "URL (http/sse)", placeholder="http://localhost:8080/mcp"),
        FormField("auth", "Auth token (http/sse, optional)", kind="password"),
    ]

    def _on_submit(values) -> None:
        if values is None:
            return
        _save_custom_server(values)

    app.push_screen(
        FormScreen("Add a custom MCP server", fields, submit_label="Add"), _on_submit
    )


def _save_custom_server(values: dict) -> None:
    from code_puppy.config import MCP_SERVERS_FILE
    from code_puppy.mcp_.managed_server import ServerConfig
    from code_puppy.mcp_.manager import get_mcp_manager
    from code_puppy.messaging import emit_error, emit_success

    name = values["name"].strip()
    stype = values.get("type") or "stdio"

    if stype == "stdio":
        tokens = values.get("command", "").split()
        if not tokens:
            emit_error("stdio servers require a command.")
            return
        config = {
            "type": "stdio",
            "command": tokens[0],
            "args": tokens[1:] + values.get("args", "").split(),
        }
    else:
        url = values.get("url", "").strip()
        if not url:
            emit_error(f"{stype} servers require a URL.")
            return
        config = {"type": stype, "url": url}
        auth = values.get("auth", "").strip()
        if auth:
            config["headers"] = {"Authorization": f"Bearer {auth}"}

    try:
        manager = get_mcp_manager()
        server_config = ServerConfig(
            id=name, name=name, type=stype, enabled=True, config=config
        )
        if not manager.register_server(server_config):
            emit_error("Failed to register server.")
            return

        # Persist to mcp_servers.json (mirrors the classic installer).
        if os.path.exists(MCP_SERVERS_FILE):
            with open(MCP_SERVERS_FILE, "r") as f:
                data = json.load(f)
        else:
            data = {"mcp_servers": {}}
        servers = data.setdefault("mcp_servers", {})
        saved = dict(config)
        saved["type"] = stype
        servers[name] = saved
        os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
        with open(MCP_SERVERS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        emit_success(f"Added custom MCP server '{name}'. Use /mcp start {name}.")
    except Exception as exc:
        emit_error(f"Failed to add server: {exc}")
