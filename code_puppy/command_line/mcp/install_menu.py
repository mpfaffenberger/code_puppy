"""Interactive terminal UI for browsing and installing MCP servers.

Provides a beautiful split-panel interface for browsing categories and servers
with live preview of server details and one-click installation.
"""

import logging
import os
import sys
import time
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.list_filtering import query_matches_text
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.command_runner import set_awaiting_user_input

from .catalog_server_installer import (
    install_catalog_server,
    prompt_for_server_config,
)
from .custom_server_form import run_custom_server_form

logger = logging.getLogger(__name__)

PAGE_SIZE = 12  # Items per page

# Special category for custom servers
CUSTOM_SERVER_CATEGORY = "➕ Custom Server"


class MCPInstallMenu:
    """Interactive TUI for browsing and installing MCP servers."""

    def __init__(self, manager):
        """Initialize the MCP server browser menu.

        Args:
            manager: MCP manager instance for server installation
        """
        self.manager = manager
        self.catalog = None
        self.categories: List[str] = []
        self.current_category: Optional[str] = None
        self.current_servers: List = []

        # State management
        self.view_mode = "categories"  # "categories" or "servers"
        self.selected_category_idx = 0
        self.selected_server_idx = 0
        self.current_page = 0
        self.result = None  # Track installation result

        # Live text filter (mirrors /model's ModelSelectionMenu UX). Applies
        # to whichever list is currently visible (categories or servers).
        self.filter_text = ""

        # Pending server for configuration
        self.pending_server = None

        # UI controls
        self.menu_control = None
        self.preview_control = None

        # Initialize catalog
        self._initialize_catalog()

    def _initialize_catalog(self):
        """Initialize the MCP server catalog with error handling."""
        try:
            from code_puppy.mcp_.server_registry_catalog import catalog

            self.catalog = catalog
            # Add custom server option as first category
            self.categories = [CUSTOM_SERVER_CATEGORY] + self.catalog.list_categories()
            if len(self.categories) <= 1:  # Only custom category
                emit_error("No categories found in server catalog")
        except ImportError as e:
            emit_error(f"Server catalog not available: {e}")
            # Still allow custom servers even if catalog fails
            self.categories = [CUSTOM_SERVER_CATEGORY]
        except Exception as e:
            emit_error(f"Error loading server catalog: {e}")
            self.categories = [CUSTOM_SERVER_CATEGORY]

    def _get_current_category(self) -> Optional[str]:
        """Get the currently selected category (filter-aware)."""
        visible = self._visible_categories()
        if 0 <= self.selected_category_idx < len(visible):
            return visible[self.selected_category_idx]
        return None

    def _get_current_server(self):
        """Get the currently selected server (filter-aware)."""
        if self.view_mode != "servers":
            return None
        visible = self._visible_servers()
        if 0 <= self.selected_server_idx < len(visible):
            return visible[self.selected_server_idx]
        return None

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def _visible_categories(self) -> List[str]:
        """Return categories matching the current filter text.

        The Custom Server entry is always shown so the user can fall back
        to a hand-rolled config even when the filter hides everything else.
        """
        if not self.filter_text:
            return list(self.categories)
        out = []
        for cat in self.categories:
            if cat == CUSTOM_SERVER_CATEGORY:
                out.append(cat)
                continue
            if query_matches_text(self.filter_text, cat):
                out.append(cat)
        return out

    def _visible_servers(self) -> List:
        """Return servers in the current category that match the filter.

        Filters across the rich text on a server template — display name,
        description, tags, and the underlying name — so users can search
        by anything they remember about a server.
        """
        if not self.filter_text:
            return list(self.current_servers)
        out = []
        for s in self.current_servers:
            tags_str = " ".join(s.tags or [])
            if query_matches_text(
                self.filter_text,
                s.display_name or "",
                s.name or "",
                s.description or "",
                tags_str,
            ):
                out.append(s)
        return out

    def _on_filter_changed(self) -> None:
        """Re-clamp selection + page after the filter text changes."""
        if self.view_mode == "categories":
            visible = self._visible_categories()
        else:
            visible = self._visible_servers()

        if not visible:
            self.selected_category_idx = 0
            self.selected_server_idx = 0
            self.current_page = 0
            return

        if self.view_mode == "categories":
            self.selected_category_idx = min(
                self.selected_category_idx, len(visible) - 1
            )
            self.current_page = self.selected_category_idx // PAGE_SIZE
        else:
            self.selected_server_idx = min(
                self.selected_server_idx, len(visible) - 1
            )
            self.current_page = self.selected_server_idx // PAGE_SIZE

    def _get_category_icon(self, category: str) -> str:
        """Get an icon for a category."""
        if category == CUSTOM_SERVER_CATEGORY:
            return "➕"
        icons = {
            "Code": "💻",
            "Storage": "💾",
            "Database": "🗄️",
            "Documentation": "📝",
            "DevOps": "🔧",
            "Monitoring": "📊",
            "Package Management": "📦",
            "Communication": "💬",
            "AI": "🤖",
            "Search": "🔍",
            "Development": "🛠️",
            "Cloud": "☁️",
        }
        return icons.get(category, "📁")

    def _is_custom_server_selected(self) -> bool:
        """Check if the custom server category is selected."""
        if self.view_mode != "categories":
            return False
        return self._get_current_category() == CUSTOM_SERVER_CATEGORY

    def _render_category_list(self) -> List:
        """Render the category list panel."""
        lines = []

        lines.append(("bold cyan", " 📂 CATEGORIES"))
        lines.append(("", "\n"))
        self._render_filter_line(lines)
        lines.append(("", "\n"))

        visible = self._visible_categories()

        if not visible:
            empty_msg = (
                "  No categories match the current filter."
                if self.filter_text
                else "  No categories available."
            )
            lines.append(("fg:yellow", empty_msg))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        # Show categories for current page
        total_pages = (len(visible) + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(visible))

        for i in range(start_idx, end_idx):
            category = visible[i]
            is_selected = i == self.selected_category_idx
            icon = self._get_category_icon(category)

            prefix = " > " if is_selected else "   "

            # Custom server category doesn't have a count
            if category == CUSTOM_SERVER_CATEGORY:
                label = f"{prefix}{icon} Custom Server (JSON)"
                if is_selected:
                    lines.append(("fg:ansibrightgreen bold", label))
                else:
                    lines.append(("fg:ansigreen", label))
            else:
                # Count servers in category
                server_count = (
                    len(self.catalog.get_by_category(category)) if self.catalog else 0
                )
                label = f"{prefix}{icon} {category} ({server_count})"
                if is_selected:
                    lines.append(("fg:ansibrightcyan bold", label))
                else:
                    lines.append(("fg:ansibrightblack", label))

            lines.append(("", "\n"))

        lines.append(("", "\n"))
        if total_pages > 1:
            lines.append(
                ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
            )
            lines.append(("", "\n"))

        self._render_navigation_hints(lines)
        return lines

    def _render_server_list(self) -> List:
        """Render the server list panel."""
        lines = []

        if not self.current_category:
            lines.append(("fg:yellow", "  No category selected."))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        icon = self._get_category_icon(self.current_category)
        lines.append(("bold cyan", f" {icon} {self.current_category.upper()}"))
        lines.append(("", "\n"))
        self._render_filter_line(lines)
        lines.append(("", "\n"))

        visible = self._visible_servers()

        if not visible:
            if self.filter_text:
                lines.append(("fg:yellow", "  No servers match the current filter."))
            elif not self.current_servers:
                lines.append(("fg:yellow", "  No servers in this category."))
            else:
                lines.append(("fg:yellow", "  No servers available."))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        # Show servers for current page
        total_pages = (len(visible) + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(visible))

        for i in range(start_idx, end_idx):
            server = visible[i]
            is_selected = i == self.selected_server_idx

            # Create indicator icons
            icons = []
            if server.verified:
                icons.append("✓")
            if server.popular:
                icons.append("⭐")

            icon_str = " ".join(icons) + " " if icons else ""

            prefix = " > " if is_selected else "   "
            label = f"{prefix}{icon_str}{server.display_name}"

            if is_selected:
                lines.append(("fg:ansibrightcyan bold", label))
            else:
                lines.append(("fg:ansibrightblack", label))

            lines.append(("", "\n"))

        lines.append(("", "\n"))
        if total_pages > 1:
            lines.append(
                ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
            )
            lines.append(("", "\n"))

        self._render_navigation_hints(lines)
        return lines

    def _render_filter_line(self, lines: List) -> None:
        """Render the filter status line. Always present so the keybinding
        is discoverable even before the user types."""
        if self.filter_text:
            lines.append(("fg:ansibrightblack", "  Filter: "))
            lines.append(("fg:ansibrightyellow", self.filter_text))
        else:
            lines.append(("fg:ansibrightblack", "  Filter: type to filter"))

    def _render_navigation_hints(self, lines: List):
        """Render navigation hints at the bottom of the list panel."""
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:ansibrightblack", "←/→ "))
        lines.append(("", "Page\n"))
        lines.append(("fg:ansibrightblack", "  Type  "))
        lines.append(("", "Filter  "))
        lines.append(("fg:ansibrightblack", "Ctrl+U  "))
        lines.append(("", "Clear filter\n"))
        if self.view_mode == "categories":
            lines.append(("fg:green", "  Enter  "))
            lines.append(("", "Browse Servers\n"))
        else:
            lines.append(("fg:green", "  Enter  "))
            lines.append(("", "Install Server\n"))
            lines.append(("fg:ansibrightblack", "  Esc/Back  "))
            lines.append(("", "Back\n"))
        lines.append(("fg:ansired", "  Ctrl+C "))
        lines.append(("", "Cancel"))

    def _render_details(self) -> List:
        """Render the details panel."""
        lines = []

        lines.append(("bold cyan", " 📋 DETAILS"))
        lines.append(("", "\n\n"))

        if self.view_mode == "categories":
            category = self._get_current_category()
            if not category:
                lines.append(("fg:yellow", "  No category selected."))
                return lines

            # Special handling for custom server category
            if category == CUSTOM_SERVER_CATEGORY:
                return self._render_custom_server_details()

            icon = self._get_category_icon(category)
            lines.append(("bold", f"  {icon} {category}"))
            lines.append(("", "\n\n"))

            # Show servers in this category
            servers = self.catalog.get_by_category(category) if self.catalog else []
            lines.append(("fg:ansibrightblack", f"  {len(servers)} servers available"))
            lines.append(("", "\n\n"))

            # Show popular servers in this category
            popular = [s for s in servers if s.popular]
            if popular:
                lines.append(("bold", "  ⭐ Popular:"))
                lines.append(("", "\n"))
                for server in popular[:5]:
                    lines.append(("fg:ansibrightblack", f"    • {server.display_name}"))
                    lines.append(("", "\n"))

        else:  # servers view
            server = self._get_current_server()
            if not server:
                lines.append(("fg:yellow", "  No server selected."))
                return lines

            # Server name with indicators
            indicators = []
            if server.verified:
                indicators.append("✓ Verified")
            if server.popular:
                indicators.append("⭐ Popular")

            lines.append(("bold", f"  {server.display_name}"))
            lines.append(("", "\n"))

            if indicators:
                lines.append(("fg:green", f"  {' | '.join(indicators)}"))
                lines.append(("", "\n"))

            lines.append(("", "\n"))

            # Description
            lines.append(("bold", "  Description:"))
            lines.append(("", "\n"))
            # Wrap description
            desc = server.description or "No description available"
            # Simple word wrap
            words = desc.split()
            line = "    "
            for word in words:
                if len(line) + len(word) > 50:
                    lines.append(("fg:ansibrightblack", line))
                    lines.append(("", "\n"))
                    line = "    " + word + " "
                else:
                    line += word + " "
            if line.strip():
                lines.append(("fg:ansibrightblack", line))
                lines.append(("", "\n"))

            lines.append(("", "\n"))

            # Type
            lines.append(("bold", "  Type:"))
            lines.append(("", "\n"))
            type_icons = {"stdio": "📟", "http": "🌐", "sse": "📡"}
            type_icon = type_icons.get(server.type, "❓")
            lines.append(("fg:ansibrightblack", f"    {type_icon} {server.type}"))
            lines.append(("", "\n\n"))

            # Tags
            if server.tags:
                lines.append(("bold", "  Tags:"))
                lines.append(("", "\n"))
                tag_line = "    " + ", ".join(server.tags[:6])
                lines.append(("fg:ansicyan", tag_line))
                lines.append(("", "\n\n"))

            # Requirements
            requirements = server.get_requirements()

            # Environment variables
            env_vars = server.get_environment_vars()
            if env_vars:
                lines.append(("bold", "  🔑 Environment Variables:"))
                lines.append(("", "\n"))
                for var in env_vars:
                    # Check if already set
                    is_set = os.environ.get(var)
                    if is_set:
                        lines.append(("fg:green", f"    ✓ {var}"))
                    else:
                        lines.append(("fg:yellow", f"    ○ {var}"))
                    lines.append(("", "\n"))
                lines.append(("", "\n"))

            # Command line args
            cmd_args = server.get_command_line_args()
            if cmd_args:
                lines.append(("bold", "  ⚙️ Configuration:"))
                lines.append(("", "\n"))
                for arg in cmd_args:
                    name = arg.get("name", "unknown")
                    required = arg.get("required", True)
                    default = arg.get("default", "")
                    marker = "*" if required else "?"
                    default_str = f" [{default}]" if default else ""
                    lines.append(
                        ("fg:ansibrightblack", f"    {marker} {name}{default_str}")
                    )
                    lines.append(("", "\n"))
                lines.append(("", "\n"))

            # Required tools
            required_tools = requirements.required_tools
            if required_tools:
                lines.append(("bold", "  🛠️ Required Tools:"))
                lines.append(("", "\n"))
                lines.append(("fg:ansibrightblack", f"    {', '.join(required_tools)}"))
                lines.append(("", "\n\n"))

            # Example usage
            if server.example_usage:
                lines.append(("bold", "  💡 Example:"))
                lines.append(("", "\n"))
                lines.append(("fg:ansibrightblack", f"    {server.example_usage}"))
                lines.append(("", "\n"))

        return lines

    def _render_custom_server_details(self) -> List:
        """Render details for the custom server option."""
        lines = []

        lines.append(("bold cyan", " 📋 DETAILS"))
        lines.append(("", "\n\n"))

        lines.append(("bold green", "  ➕ Add Custom MCP Server"))
        lines.append(("", "\n\n"))

        lines.append(("fg:ansibrightblack", "  Add your own MCP server by providing"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  a JSON configuration."))
        lines.append(("", "\n\n"))

        lines.append(("bold", "  📟 Supported Types:"))
        lines.append(("", "\n\n"))

        lines.append(("fg:ansicyan bold", "  1. stdio"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "     Runs a local command (npx, python,"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "     uvx, etc.) and communicates via"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "     stdin/stdout."))
        lines.append(("", "\n\n"))

        lines.append(("fg:ansicyan bold", "  2. http"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "     Connects to an HTTP endpoint that"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "     implements the MCP protocol."))
        lines.append(("", "\n\n"))

        lines.append(("fg:ansicyan bold", "  3. sse"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "     Connects via Server-Sent Events"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "     for real-time streaming."))
        lines.append(("", "\n\n"))

        lines.append(("bold", "  💡 Press Enter to configure"))
        lines.append(("", "\n"))

        return lines

    def update_display(self):
        """Update the display based on current state."""
        if self.view_mode == "categories":
            self.menu_control.text = self._render_category_list()
        else:
            self.menu_control.text = self._render_server_list()

        self.preview_control.text = self._render_details()

    def _enter_category(self):
        """Enter the selected category to view its servers."""
        category = self._get_current_category()
        if not category:
            return

        # Handle custom server selection
        if category == CUSTOM_SERVER_CATEGORY:
            self.result = "pending_custom"
            return  # Signal to exit and prompt for custom config

        if not self.catalog:
            return

        self.current_category = category
        self.current_servers = self.catalog.get_by_category(category)
        self.view_mode = "servers"
        self.selected_server_idx = 0
        self.current_page = 0
        # Filter is intentionally preserved across view changes — if you
        # typed "jira" to find the category, that same filter is likely
        # useful for narrowing servers within it. Press Ctrl+U to clear.
        self._on_filter_changed()
        self.update_display()

    def _go_back_to_categories(self):
        """Go back to categories view."""
        self.view_mode = "categories"
        self.current_category = None
        self.current_servers = []
        self.selected_server_idx = 0
        self.current_page = 0
        self._on_filter_changed()
        self.update_display()

    def _select_current_server(self):
        """Select the current server for installation."""
        server = self._get_current_server()
        if server:
            self.pending_server = server
            self.result = "pending_install"

    def _handle_up(self):
        """Handle up arrow key."""
        if self.view_mode == "categories":
            if self.selected_category_idx > 0:
                self.selected_category_idx -= 1
                self.current_page = self.selected_category_idx // PAGE_SIZE
        else:
            if self.selected_server_idx > 0:
                self.selected_server_idx -= 1
                self.current_page = self.selected_server_idx // PAGE_SIZE
        self.update_display()

    def _handle_down(self):
        """Handle down arrow key."""
        if self.view_mode == "categories":
            limit = len(self._visible_categories())
            if self.selected_category_idx < limit - 1:
                self.selected_category_idx += 1
                self.current_page = self.selected_category_idx // PAGE_SIZE
        else:
            limit = len(self._visible_servers())
            if self.selected_server_idx < limit - 1:
                self.selected_server_idx += 1
                self.current_page = self.selected_server_idx // PAGE_SIZE
        self.update_display()

    def _handle_left(self):
        """Handle left arrow key (previous page)."""
        if self.current_page > 0:
            self.current_page -= 1
            if self.view_mode == "categories":
                self.selected_category_idx = self.current_page * PAGE_SIZE
            else:
                self.selected_server_idx = self.current_page * PAGE_SIZE
            self.update_display()

    def _handle_right(self):
        """Handle right arrow key (next page)."""
        if self.view_mode == "categories":
            total_items = len(self._visible_categories())
        else:
            total_items = len(self._visible_servers())

        total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
        if self.current_page < total_pages - 1:
            self.current_page += 1
            if self.view_mode == "categories":
                self.selected_category_idx = self.current_page * PAGE_SIZE
            else:
                self.selected_server_idx = self.current_page * PAGE_SIZE
            self.update_display()

    def _handle_enter(self):
        """Handle enter key. Returns True if app should exit."""
        if self.view_mode == "categories":
            self._enter_category()
            if self.result == "pending_custom":
                return True
        elif self.view_mode == "servers":
            self._select_current_server()
            return True
        return False

    def _handle_back(self):
        """Handle escape/backspace key (when filter is empty)."""
        if self.view_mode == "servers":
            self._go_back_to_categories()

    # ------------------------------------------------------------------
    # Filter input handlers
    # ------------------------------------------------------------------
    def _append_filter_char(self, ch: str) -> None:
        if not ch or not ch.isprintable():
            return
        self.filter_text += ch
        self._on_filter_changed()
        self.update_display()

    def _delete_filter_char(self) -> None:
        if not self.filter_text:
            return
        self.filter_text = self.filter_text[:-1]
        self._on_filter_changed()
        self.update_display()

    def _clear_filter(self) -> None:
        if not self.filter_text:
            return
        self.filter_text = ""
        self._on_filter_changed()
        self.update_display()

    def _reload_mcp_servers(self):
        """Attempt to reload MCP servers after installation."""
        try:
            from code_puppy.agent import reload_mcp_servers

            reload_mcp_servers()
        except ImportError:
            pass

    def run(self) -> bool:
        """Run the interactive MCP server browser (synchronous).

        Returns:
            True if a server was installed, False otherwise
        """
        if not self.categories:
            emit_warning("No MCP server catalog available.")
            return False

        # Build UI
        self.menu_control = FormattedTextControl(text="")
        self.preview_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=35)
        )
        preview_window = Window(
            content=self.preview_control, wrap_lines=True, width=Dimension(weight=65)
        )

        menu_frame = Frame(menu_window, width=Dimension(weight=35), title="Browse")
        preview_frame = Frame(
            preview_window, width=Dimension(weight=65), title="Details"
        )

        root_container = VSplit([menu_frame, preview_frame])

        # Key bindings
        kb = KeyBindings()

        @kb.add("up")
        def _(event):  # pragma: no cover
            self._handle_up()

        @kb.add("down")
        def _(event):  # pragma: no cover
            self._handle_down()

        @kb.add("left")
        def _(event):  # pragma: no cover
            self._handle_left()

        @kb.add("right")
        def _(event):  # pragma: no cover
            self._handle_right()

        @kb.add("enter")
        def _(event):  # pragma: no cover
            if self._handle_enter():
                event.app.exit()

        @kb.add("escape")
        def _(event):  # pragma: no cover
            self._handle_back()

        @kb.add("backspace")
        def _(event):  # pragma: no cover
            # Delete filter char if there is one; otherwise act as "back".
            if self.filter_text:
                self._delete_filter_char()
            else:
                self._handle_back()
                self.update_display()

        @kb.add("c-u")
        def _(event):  # pragma: no cover
            self._clear_filter()

        @kb.add("<any>")
        def _(event):  # pragma: no cover
            data = getattr(event, "data", "") or ""
            # Single printable character only — ignore control sequences.
            if len(data) == 1 and data.isprintable():
                self._append_filter_char(data)

        @kb.add("c-c")
        def _(event):  # pragma: no cover
            event.app.exit()

        layout = Layout(root_container)
        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
        )

        set_awaiting_user_input(True)

        # Enter alternate screen buffer
        sys.stdout.write("\033[?1049h")  # Enter alternate buffer
        sys.stdout.write("\033[2J\033[H")  # Clear and home
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            # Initial display
            self.update_display()

            # Clear the current buffer
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            # Run application
            app.run(in_thread=True)

        finally:
            # Exit alternate screen buffer
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
            set_awaiting_user_input(False)

        # Clear exit message (unless we're about to prompt for more input)
        if self.result not in ("pending_custom", "pending_install"):
            emit_info("✓ Exited MCP server browser")

        # Handle custom server after TUI exits
        if self.result == "pending_custom":
            success = run_custom_server_form(self.manager)
            if success:
                self._reload_mcp_servers()
            return success

        # Handle catalog server installation after TUI exits
        if self.result == "pending_install" and self.pending_server:
            config = prompt_for_server_config(self.manager, self.pending_server)
            if config:
                success = install_catalog_server(
                    self.manager, self.pending_server, config
                )
                if success:
                    self._reload_mcp_servers()
                return success
            return False

        return False


def run_mcp_install_menu(manager) -> bool:
    """Run the MCP install menu.

    Args:
        manager: MCP manager instance

    Returns:
        True if a server was installed, False otherwise
    """
    menu = MCPInstallMenu(manager)
    return menu.run()
