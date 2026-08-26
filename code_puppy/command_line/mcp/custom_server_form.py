"""Interactive form for adding/editing custom MCP servers, on termflow.

A menu-of-fields loop: pick a field, edit it with the right widget
(TextInput for the name, a choice menu for the type, ``$EDITOR`` for
the JSON config with a single-line TextInput fallback), with a live
preview pane showing the highlighted JSON and validation status.
Ctrl-free: Save and Cancel are ordinary menu entries.
"""

import json
import os
import subprocess
import sys
import tempfile
from typing import Callable, List, Optional

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.command_runner import set_awaiting_user_input

# Example configurations for each server type
CUSTOM_SERVER_EXAMPLES = {
    "stdio": """{
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
  "env": {
    "NODE_ENV": "production"
  },
  "timeout": 30
}""",
    "http": """{
  "type": "http",
  "url": "http://localhost:8080/mcp",
  "headers": {
    "Authorization": "Bearer $MY_API_KEY",
    "Content-Type": "application/json"
  },
  "timeout": 30
}""",
    "sse": """{
  "type": "sse",
  "url": "http://localhost:8080/sse",
  "headers": {
    "Authorization": "Bearer $MY_API_KEY"
  }
}""",
}

SERVER_TYPES = ["stdio", "http", "sse"]

SERVER_TYPE_DESCRIPTIONS = {
    "stdio": "Local command (npx, python, uvx) via stdin/stdout",
    "http": "HTTP endpoint implementing MCP protocol",
    "sse": "Server-Sent Events for real-time streaming",
}

_FIELD_NAME = "name"
_FIELD_TYPE = "type"
_FIELD_JSON = "json"
_ACTION_EXAMPLE = "example"
_ACTION_SAVE = "save"
_ACTION_CANCEL = "cancel"


class CustomServerForm:
    """Form state + persistence for adding/editing custom MCP servers."""

    def __init__(
        self,
        manager,
        edit_mode: bool = False,
        existing_name: str = "",
        existing_type: str = "stdio",
        existing_config: Optional[dict] = None,
    ):
        self.manager = manager
        self.edit_mode = edit_mode
        self.original_name = existing_name  # Track original name for updates

        self.server_name = existing_name
        self.selected_type_idx = (
            SERVER_TYPES.index(existing_type) if existing_type in SERVER_TYPES else 0
        )

        if existing_config:
            self.json_config = json.dumps(existing_config, indent=2)
        else:
            self.json_config = CUSTOM_SERVER_EXAMPLES["stdio"]

        self.validation_error: Optional[str] = None
        self.status_message: Optional[str] = None
        self.status_is_error: bool = False
        self.result = None  # "installed", "cancelled", None

    def _get_current_type(self) -> str:
        return SERVER_TYPES[self.selected_type_idx]

    def _validate_server_name(self, name: str) -> Optional[str]:
        """Validate server name format. Error message or None."""
        if not name or not name.strip():
            return "Server name is required"

        name = name.strip()

        if not name.replace("-", "").replace("_", "").isalnum():
            return "Name must be alphanumeric (hyphens/underscores OK)"

        if len(name) > 64:
            return "Name too long (max 64 characters)"

        return None

    def _validate_json(self) -> bool:
        """Validate the current JSON configuration."""
        try:
            config = json.loads(self.json_config)
            current_type = self._get_current_type()

            if current_type == "stdio":
                if "command" not in config:
                    self.validation_error = "Missing 'command' field"
                    return False
            elif current_type in ("http", "sse"):
                if "url" not in config:
                    self.validation_error = "Missing 'url' field"
                    return False

            self.validation_error = None
            return True

        except json.JSONDecodeError as e:
            self.validation_error = f"Invalid JSON: {e.msg}"
            return False

    def _install_server(self) -> bool:
        """Persist the server (register or update). True on success."""
        from code_puppy.command_line.mcp.mcp_servers_store import upsert_mcp_server
        from code_puppy.mcp_.managed_server import ServerConfig

        name_error = self._validate_server_name(self.server_name)
        if name_error:
            self.validation_error = name_error
            self.status_message = f"Save failed: {name_error}"
            self.status_is_error = True
            return False

        if not self._validate_json():
            self.status_message = f"Save failed: {self.validation_error}"
            self.status_is_error = True
            return False

        server_name = self.server_name.strip()
        server_type = self._get_current_type()
        config_dict = json.loads(self.json_config)

        try:
            if self.edit_mode and self.original_name:
                existing_config = self.manager.get_server_by_name(self.original_name)
                if existing_config:
                    server_config = ServerConfig(
                        id=existing_config.id,
                        name=server_name,
                        type=server_type,
                        enabled=True,
                        config=config_dict,
                    )
                    success = self.manager.update_server(
                        existing_config.id, server_config
                    )
                    if not success:
                        self.validation_error = "Failed to update server"
                        self.status_message = "Save failed: Could not update server"
                        self.status_is_error = True
                        return False
                else:
                    # Original server not found, treat as new registration
                    server_config = ServerConfig(
                        id=server_name,
                        name=server_name,
                        type=server_type,
                        enabled=True,
                        config=config_dict,
                    )
                    self.manager.register_server(server_config)
            else:
                server_config = ServerConfig(
                    id=server_name,
                    name=server_name,
                    type=server_type,
                    enabled=True,
                    config=config_dict,
                )
                server_id = self.manager.register_server(server_config)
                if not server_id:
                    self.validation_error = "Failed to register server"
                    self.status_message = (
                        "Save failed: Could not register server "
                        "(name may already exist)"
                    )
                    self.status_is_error = True
                    return False

            # Save to mcp_servers.json for persistence
            save_config = config_dict.copy()
            save_config["type"] = server_type
            replace_name = None
            if (
                self.edit_mode
                and self.original_name
                and self.original_name != server_name
            ):
                replace_name = self.original_name
            upsert_mcp_server(server_name, save_config, replace_name=replace_name)

            return True

        except Exception as e:
            self.validation_error = f"Error: {e}"
            self.status_message = f"Save failed: {e}"
            self.status_is_error = True
            return False


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _style():
    from termflow.render.style import RenderStyle

    from code_puppy.command_line.tui_style import menu_style

    return menu_style() or RenderStyle.default()


def _ansi(color: str, text: str) -> str:
    from termflow.ansi.codes import RESET
    from termflow.ansi.color import fg_color

    return f"{fg_color(color)}{text}{RESET}"


def form_preview(form: CustomServerForm) -> str:
    """Preview pane: current values, validation status, highlighted JSON."""
    s = _style()
    form._validate_json()
    server_type = form._get_current_type()
    lines = [
        _ansi(
            s.bright,
            "EDIT MCP SERVER" if form.edit_mode else "ADD CUSTOM MCP SERVER",
        ),
        "",
        f"Name: {form.server_name or _ansi(s.grey, '(not set)')}",
        f"Type: {server_type} - {SERVER_TYPE_DESCRIPTIONS[server_type]}",
    ]
    name_error = form._validate_server_name(form.server_name)
    if name_error and form.server_name:
        lines.append(_ansi(s.error, f"  {name_error}"))
    if form.validation_error:
        lines.append(_ansi(s.error, f"JSON: {form.validation_error}"))
    else:
        lines.append(_ansi(s.head, "JSON: valid"))
    if form.status_message:
        color = s.error if form.status_is_error else s.head
        lines.append(_ansi(color, form.status_message))
    lines.append("")
    lines.extend(_highlight_json(form.json_config.splitlines()))
    return "\n".join(lines)


def _highlight_json(lines: List[str]) -> List[str]:
    from termflow.syntax import Highlighter

    from code_puppy.callbacks import on_termflow_highlighter

    try:
        highlighter = on_termflow_highlighter(Highlighter())
        return [highlighter.highlight_line(line, "json") for line in lines]
    except Exception:
        return list(lines)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


def build_form_menu(form: CustomServerForm, initial_index: int = 0, **overrides):
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    json_status = "valid" if form._validate_json() else "INVALID"
    items = [
        MenuItem(f"Server Name: {form.server_name or '(not set)'}", value=_FIELD_NAME),
        MenuItem(f"Server Type: {form._get_current_type()}", value=_FIELD_TYPE),
        MenuItem(f"JSON Configuration ({json_status})", value=_FIELD_JSON),
        MenuItem(f"Load example for {form._get_current_type()}", value=_ACTION_EXAMPLE),
        MenuItem("Save & Install", value=_ACTION_SAVE),
        MenuItem("Cancel", value=_ACTION_CANCEL),
    ]
    builder = themed(
        MenuBuilder("Edit MCP Server" if form.edit_mode else "Add Custom MCP Server")
        .items(items)
        .list_width(38)
        .alt_screen(False)
        .initial_index(initial_index)
        .preview(lambda _item: form_preview(form))
        .footer_hint("Enter edit field - Esc cancel")
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def run_name_editor(form: CustomServerForm, **overrides) -> None:
    from termflow.tui import TextInputBuilder

    from code_puppy.command_line.tui_style import menu_style

    builder = (
        TextInputBuilder("Server Name")
        .prompt("Name: ")
        .initial(form.server_name)
        .placeholder("alphanumeric, hyphens/underscores OK")
        .validator(form._validate_server_name)
        .footer_hint("Enter save - Esc cancel")
        .alt_screen(False)
    )
    style = menu_style()
    if style is not None:
        builder.style(style)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    result = builder.build().run()
    if not result.cancelled and result.value is not None:
        form.server_name = result.value.strip()


def run_type_menu(form: CustomServerForm, **overrides) -> None:
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    builder = themed(
        MenuBuilder("Server Type")
        .items(
            [
                MenuItem(t, value=t, description=SERVER_TYPE_DESCRIPTIONS[t])
                for t in SERVER_TYPES
            ]
        )
        .initial_index(form.selected_type_idx)
        .alt_screen(False)
        .footer_hint("Enter select - Esc keep current")
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    result = builder.build().run()
    if result.cancelled or result.item is None:
        return
    new_type = result.item.value
    old_type = form._get_current_type()
    form.selected_type_idx = SERVER_TYPES.index(new_type)
    # Swap in the new type's example only when the config is still the old
    # type's untouched example -- never clobber user (or existing) config.
    if form.json_config.strip() == CUSTOM_SERVER_EXAMPLES[old_type].strip():
        form.json_config = CUSTOM_SERVER_EXAMPLES[new_type]


def edit_json_in_editor(initial: str) -> Optional[str]:
    """Open ``$EDITOR`` on the JSON config. None when unavailable/failed.

    vim/nano configure and restore the terminal themselves, so spawning
    them from inside the raw-mode menu session round-trips cleanly.
    """
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    fd, path = tempfile.mkstemp(suffix=".json", prefix="mcp_server_")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(initial)
        sys.__stdout__.write("\x1b[2J\x1b[H")
        sys.__stdout__.flush()
        completed = subprocess.call([*editor.split(), path])
        if completed != 0:
            return None
        with open(path) as handle:
            return handle.read()
    except Exception:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def run_json_fallback_editor(form: CustomServerForm, **overrides) -> None:
    """Single-line TextInput fallback when ``$EDITOR`` is unavailable."""
    from termflow.tui import TextInputBuilder

    from code_puppy.command_line.tui_style import menu_style

    def validate(text: str) -> Optional[str]:
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e.msg}"
        return None

    compact = (
        json.dumps(json.loads(form.json_config))
        if _parses(form.json_config)
        else form.json_config
    )
    builder = (
        TextInputBuilder("JSON Configuration (single line)")
        .prompt("JSON: ")
        .initial(compact)
        .validator(validate)
        .footer_hint("Enter save - Esc cancel")
        .alt_screen(False)
    )
    style = menu_style()
    if style is not None:
        builder.style(style)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    result = builder.build().run()
    if not result.cancelled and result.value:
        form.json_config = json.dumps(json.loads(result.value), indent=2)


def _parses(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


def run_form_flow(
    form: CustomServerForm,
    menu_factory: Callable = build_form_menu,
    name_editor: Callable = run_name_editor,
    type_menu: Callable = run_type_menu,
    json_editor: Callable = edit_json_in_editor,
    json_fallback: Callable = run_json_fallback_editor,
) -> bool:
    """The field-edit loop. True when a server was installed."""
    cursor = 0
    field_order = [
        _FIELD_NAME,
        _FIELD_TYPE,
        _FIELD_JSON,
        _ACTION_EXAMPLE,
        _ACTION_SAVE,
        _ACTION_CANCEL,
    ]
    while True:
        result = menu_factory(form, initial_index=cursor).run()
        if result.cancelled or result.item is None:
            form.result = "cancelled"
            return False
        value = result.item.value
        cursor = field_order.index(value) if value in field_order else 0
        if value == _ACTION_CANCEL:
            form.result = "cancelled"
            return False
        if value == _FIELD_NAME:
            name_editor(form)
        elif value == _FIELD_TYPE:
            type_menu(form)
        elif value == _FIELD_JSON:
            edited = json_editor(form.json_config)
            if edited is not None:
                form.json_config = edited
            else:
                json_fallback(form)
        elif value == _ACTION_EXAMPLE:
            form.json_config = CUSTOM_SERVER_EXAMPLES[form._get_current_type()]
            form.status_message = None
        elif value == _ACTION_SAVE:
            if form._install_server():
                form.result = "installed"
                return True
            # Failure: loop; status_message shows in the preview.


def run_custom_server_form(
    manager,
    edit_mode: bool = False,
    existing_name: str = "",
    existing_type: str = "stdio",
    existing_config: Optional[dict] = None,
) -> bool:
    """Run the custom server form. True if a server was installed/updated."""
    from code_puppy.command_line.menu_session import menu_session

    form = CustomServerForm(
        manager,
        edit_mode=edit_mode,
        existing_name=existing_name,
        existing_type=existing_type,
        existing_config=existing_config,
    )

    set_awaiting_user_input(True)
    try:
        with menu_session():
            installed = run_form_flow(form)
    finally:
        set_awaiting_user_input(False)

    if not installed:
        emit_info("Exited custom server form")
        return False

    if form.edit_mode:
        emit_success(f"\n  Successfully updated server '{form.server_name}'!")
    else:
        emit_success(f"\n  Successfully added custom server '{form.server_name}'!")
    emit_info(f"  Use '/mcp start {form.server_name}' to start the server.\n")

    # Strict opt-in: prompt the user to bind this server to agents
    # (skip on edits -- bindings should already exist).
    if not form.edit_mode:
        try:
            from code_puppy.command_line.mcp_binding_menu import (
                prompt_bind_after_install_sync,
            )

            prompt_bind_after_install_sync(form.server_name)
        except Exception:
            pass

    return True
