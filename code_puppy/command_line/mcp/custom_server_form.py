"""Interactive TUI form for adding custom MCP servers.

Provides a form-based interface for configuring custom MCP servers
with inline JSON editing and live validation.
"""

import json
import os
import sys
import time
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    Dimension,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame, TextArea

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
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
  },
  "timeout": 30
}""",
    "sse": """{
  "type": "sse",
  "url": "http://localhost:8080/sse",
  "headers": {
    "Authorization": "Bearer YOUR_API_KEY"
  }
}""",
}

SERVER_TYPES = ["stdio", "http", "sse"]

SERVER_TYPE_DESCRIPTIONS = {
    "stdio": "Local command (npx, python, uvx) via stdin/stdout",
    "http": "HTTP endpoint implementing MCP protocol",
    "sse": "Server-Sent Events for real-time streaming",
}


class CustomServerForm:
    """Interactive TUI form for adding custom MCP servers."""

    def __init__(self, manager):
        """Initialize the custom server form.

        Args:
            manager: MCP manager instance for server installation
        """
        self.manager = manager

        # Form state
        self.server_name = ""
        self.selected_type_idx = 0  # 0=stdio, 1=http, 2=sse
        self.json_config = CUSTOM_SERVER_EXAMPLES["stdio"]
        self.validation_error: Optional[str] = None

        # Focus state: 0=name, 1=type, 2=json
        self.focused_field = 0

        # Result
        self.result = None  # "installed", "cancelled", None

        # UI controls
        self.name_buffer = None
        self.json_area = None
        self.info_control = None
        self.status_control = None

    def _get_current_type(self) -> str:
        """Get the currently selected server type."""
        return SERVER_TYPES[self.selected_type_idx]

    def _render_form(self) -> List:
        """Render the form panel."""
        lines = []

        lines.append(("bold cyan", " ➕ ADD CUSTOM MCP SERVER"))
        lines.append(("", "\n\n"))

        # Server Name field - now in separate frame below
        name_style = "fg:ansibrightcyan bold" if self.focused_field == 0 else "bold"
        lines.append((name_style, "  1. Server Name:"))
        lines.append(("", "\n"))
        if self.focused_field == 0:
            lines.append(("fg:ansibrightgreen", "     ▶ Type in the box below"))
        else:
            name_display = self.server_name if self.server_name else "(not set)"
            lines.append(("fg:ansibrightblack", f"     {name_display}"))
        lines.append(("", "\n\n"))

        # Server Type field
        type_style = "fg:ansibrightcyan bold" if self.focused_field == 1 else "bold"
        lines.append((type_style, "  2. Server Type:"))
        lines.append(("", "\n"))

        type_icons = {
            "stdio": "📟",
            "http": "🌐",
            "sse": "📡",
        }

        for i, server_type in enumerate(SERVER_TYPES):
            is_selected = i == self.selected_type_idx
            icon = type_icons.get(server_type, "")

            if self.focused_field == 1 and is_selected:
                lines.append(("fg:ansibrightgreen", "  ▶ "))
            elif is_selected:
                lines.append(("fg:ansigreen", "  ✓ "))
            else:
                lines.append(("", "    "))

            if is_selected:
                lines.append(("fg:ansibrightcyan bold", f"{icon} {server_type}"))
            else:
                lines.append(("fg:ansibrightblack", f"{icon} {server_type}"))
            lines.append(("", "\n"))

        lines.append(("", "\n"))

        # JSON Configuration field
        json_style = "fg:ansibrightcyan bold" if self.focused_field == 2 else "bold"
        lines.append((json_style, "  3. JSON Configuration:"))
        lines.append(("", "\n"))

        if self.focused_field == 2:
            lines.append(("fg:ansibrightgreen", "     ▶ Editing in box below"))
        else:
            lines.append(("fg:ansibrightblack", "     (Tab to edit)"))
        lines.append(("", "\n\n"))

        # Validation status
        if self.validation_error:
            lines.append(("fg:ansired bold", f"  ❌ {self.validation_error}"))
        else:
            lines.append(("fg:ansigreen", "  ✓ Valid JSON"))
        lines.append(("", "\n\n"))

        # Navigation hints
        lines.append(("fg:ansibrightblack", "  Tab "))
        lines.append(("", "Next field  "))
        lines.append(("fg:ansibrightblack", "Shift+Tab "))
        lines.append(("", "Prev\n"))

        if self.focused_field == 1:
            lines.append(("fg:ansibrightblack", "  ↑/↓ "))
            lines.append(("", "Change type\n"))

        lines.append(("fg:green bold", "  Ctrl+S "))
        lines.append(("", "Save & Install\n"))
        lines.append(("fg:ansired", "  Ctrl+C/Esc "))
        lines.append(("", "Cancel"))

        return lines

    def _render_preview(self) -> List:
        """Render the preview/help panel."""
        lines = []

        current_type = self._get_current_type()

        lines.append(("bold cyan", " 📝 HELP & PREVIEW"))
        lines.append(("", "\n\n"))

        # Type description
        lines.append(("bold", f"  {current_type.upper()} Server"))
        lines.append(("", "\n"))
        desc = SERVER_TYPE_DESCRIPTIONS.get(current_type, "")
        lines.append(("fg:ansibrightblack", f"  {desc}"))
        lines.append(("", "\n\n"))

        # Required fields
        lines.append(("bold", "  Required Fields:"))
        lines.append(("", "\n"))

        if current_type == "stdio":
            lines.append(("fg:ansicyan", '    • "command"'))
            lines.append(("fg:ansibrightblack", " - executable to run"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", "  Optional:"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", '    • "args" - command arguments'))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", '    • "env" - environment variables'))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", '    • "timeout" - seconds'))
            lines.append(("", "\n"))
        else:  # http or sse
            lines.append(("fg:ansicyan", '    • "url"'))
            lines.append(("fg:ansibrightblack", " - server endpoint"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", "  Optional:"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", '    • "headers" - HTTP headers'))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", '    • "timeout" - seconds'))
            lines.append(("", "\n"))

        lines.append(("", "\n"))

        # Example
        lines.append(("bold", "  Example:"))
        lines.append(("", "\n"))

        example = CUSTOM_SERVER_EXAMPLES.get(current_type, "{}")
        for line in example.split("\n"):
            lines.append(("fg:ansibrightblack", f"  {line}"))
            lines.append(("", "\n"))

        lines.append(("", "\n"))

        # Tips
        lines.append(("bold", "  💡 Tips:"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  • Use $ENV_VAR for secrets"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  • Ctrl+E loads example"))
        lines.append(("", "\n"))

        return lines

    def _validate_json(self) -> bool:
        """Validate the current JSON configuration.

        Returns:
            True if valid, False otherwise
        """
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
        """Install the custom server.

        Returns:
            True if successful, False otherwise
        """
        from code_puppy.config import MCP_SERVERS_FILE
        from code_puppy.mcp_.managed_server import ServerConfig

        if not self.server_name.strip():
            self.validation_error = "Server name is required"
            return False

        if not self._validate_json():
            return False

        server_name = self.server_name.strip()
        server_type = self._get_current_type()
        config_dict = json.loads(self.json_config)

        try:
            server_config = ServerConfig(
                id=server_name,
                name=server_name,
                type=server_type,
                enabled=True,
                config=config_dict,
            )

            # Register with manager
            server_id = self.manager.register_server(server_config)

            if not server_id:
                self.validation_error = "Failed to register server"
                return False

            # Save to mcp_servers.json for persistence
            if os.path.exists(MCP_SERVERS_FILE):
                with open(MCP_SERVERS_FILE, "r") as f:
                    data = json.load(f)
                    servers = data.get("mcp_servers", {})
            else:
                servers = {}
                data = {"mcp_servers": servers}

            # Add new server with type
            save_config = config_dict.copy()
            save_config["type"] = server_type
            servers[server_name] = save_config

            # Save back
            os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
            with open(MCP_SERVERS_FILE, "w") as f:
                json.dump(data, f, indent=2)

            return True

        except Exception as e:
            self.validation_error = f"Error: {e}"
            return False

    def run(self) -> bool:
        """Run the custom server form.

        Returns:
            True if a server was installed, False otherwise
        """
        # Create form info control
        form_control = FormattedTextControl(text="")
        preview_control = FormattedTextControl(text="")

        # Create name input text area (single line)
        self.name_area = TextArea(
            text="",
            multiline=False,
            wrap_lines=False,
            focusable=True,
            height=1,
        )

        # Create JSON text area
        self.json_area = TextArea(
            text=self.json_config,
            multiline=True,
            wrap_lines=False,
            scrollbar=True,
            focusable=True,
            height=Dimension(min=8, max=15),
        )

        # Layout with form on left, preview on right
        form_window = Window(content=form_control, wrap_lines=True)
        preview_window = Window(content=preview_control, wrap_lines=True)

        # Right panel: help/preview (narrower - 25% width)
        right_panel = Frame(
            preview_window,
            title="Help",
            width=Dimension(weight=25),
        )

        # Left panel gets 75% width
        root_container = VSplit(
            [
                HSplit(
                    [
                        Frame(
                            form_window,
                            title="➕ Custom Server",
                            height=Dimension(min=18, weight=35),
                        ),
                        Frame(
                            self.name_area,
                            title="Server Name",
                            height=3,
                        ),
                        Frame(
                            self.json_area,
                            title="JSON Config (Ctrl+E for example)",
                            height=Dimension(min=10, weight=55),
                        ),
                    ],
                    width=Dimension(weight=75),
                ),
                right_panel,
            ]
        )

        # Key bindings
        kb = KeyBindings()

        # Track which element is focused: name_area, json_area, or form (type selector)
        focus_elements = [self.name_area, None, self.json_area]  # None = type selector

        def update_display():
            # Sync values from text areas
            self.server_name = self.name_area.text
            self.json_config = self.json_area.text
            self._validate_json()
            form_control.text = self._render_form()
            preview_control.text = self._render_preview()

        def focus_current():
            """Focus the appropriate element based on focused_field."""
            element = focus_elements[self.focused_field]
            if element is not None:
                app.layout.focus(element)

        @kb.add("tab")
        def _(event):
            self.focused_field = (self.focused_field + 1) % 3
            update_display()
            focus_current()

        @kb.add("s-tab")
        def _(event):
            self.focused_field = (self.focused_field - 1) % 3
            update_display()
            focus_current()

        # Only capture Up/Down when on the type selector field
        # Otherwise let the TextArea handle cursor movement
        is_type_selector_focused = Condition(lambda: self.focused_field == 1)

        @kb.add("up", filter=is_type_selector_focused)
        def handle_up(event):
            if self.selected_type_idx > 0:
                self.selected_type_idx -= 1
                # Update JSON example when type changes
                self.json_area.text = CUSTOM_SERVER_EXAMPLES[self._get_current_type()]
            update_display()

        @kb.add("down", filter=is_type_selector_focused)
        def handle_down(event):
            if self.selected_type_idx < len(SERVER_TYPES) - 1:
                self.selected_type_idx += 1
                # Update JSON example when type changes
                self.json_area.text = CUSTOM_SERVER_EXAMPLES[self._get_current_type()]
            update_display()

        @kb.add("c-e")
        def _(event):
            """Load example for current type."""
            self.json_area.text = CUSTOM_SERVER_EXAMPLES[self._get_current_type()]
            update_display()

        @kb.add("c-s")
        def _(event):
            """Save and install."""
            # Sync values before install
            self.server_name = self.name_area.text
            self.json_config = self.json_area.text
            if self._install_server():
                self.result = "installed"
                event.app.exit()
            else:
                update_display()

        @kb.add("escape")
        def _(event):
            self.result = "cancelled"
            event.app.exit()

        @kb.add("c-c")
        def _(event):
            self.result = "cancelled"
            event.app.exit()

        # Create application - start focused on name input
        layout = Layout(root_container, focused_element=self.name_area)
        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=True,
        )

        set_awaiting_user_input(True)

        # Enter alternate screen buffer
        sys.stdout.write("\033[?1049h")
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            # Initial display
            update_display()

            # Clear screen
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            # Run application
            app.run(in_thread=True)

        finally:
            # Exit alternate screen buffer
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
            set_awaiting_user_input(False)

        # Handle result
        if self.result == "installed":
            print(f"\n  ✅ Successfully added custom server '{self.server_name}'!")
            print(f"  Use '/mcp start {self.server_name}' to start the server.\n")
            return True

        return False


def run_custom_server_form(manager) -> bool:
    """Run the custom server form.

    Args:
        manager: MCP manager instance

    Returns:
        True if a server was installed, False otherwise
    """
    form = CustomServerForm(manager)
    return form.run()
