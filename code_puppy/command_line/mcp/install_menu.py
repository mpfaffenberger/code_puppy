"""Interactive browser for installing MCP servers, on termflow.

Two chained menus (categories -> servers, details preview on both) with
the custom-server form as the first category. Menu selection happens
inside a ``menu_session``; the follow-up config prompts and the install
itself run afterwards on the normal terminal (they use ``safe_input``).
"""

import logging
import os
import textwrap
from typing import Callable, List

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.command_runner import set_awaiting_user_input

from .catalog_server_installer import (
    install_catalog_server,
    prompt_for_server_config,
)
from .custom_server_form import run_custom_server_form

logger = logging.getLogger(__name__)

# Special category for custom servers (first entry in the category list).
CUSTOM_SERVER_CATEGORY = "+ Custom Server"

_CATEGORY_ICONS = {
    "Code": "[C]",
    "Storage": "[S]",
    "Database": "[D]",
    "Documentation": "[D]",
    "DevOps": "[O]",
    "Monitoring": "[M]",
    "Package Management": "[P]",
    "Communication": "[C]",
    "AI": "[A]",
    "Search": "[S]",
    "Development": "[D]",
    "Cloud": "[C]",
}


def get_category_icon(category: str) -> str:
    if category == CUSTOM_SERVER_CATEGORY:
        return "[+]"
    return _CATEGORY_ICONS.get(category, "[ ]")


def load_catalog():
    """Load the server catalog. Returns (catalog_or_None, categories)."""
    try:
        from code_puppy.mcp_.server_registry_catalog import catalog

        categories = [CUSTOM_SERVER_CATEGORY] + catalog.list_categories()
        if len(categories) <= 1:  # Only custom category
            emit_error("No categories found in server catalog")
        return catalog, categories
    except ImportError as e:
        emit_error(f"Server catalog not available: {e}")
        return None, [CUSTOM_SERVER_CATEGORY]
    except Exception as e:
        emit_error(f"Error loading server catalog: {e}")
        return None, [CUSTOM_SERVER_CATEGORY]


# ---------------------------------------------------------------------------
# Details previews
# ---------------------------------------------------------------------------


def _style():
    from termflow.render.style import RenderStyle

    from code_puppy.command_line.tui_style import menu_style

    return menu_style() or RenderStyle.default()


def _ansi(color: str, text: str) -> str:
    from termflow.ansi.codes import RESET
    from termflow.ansi.color import fg_color

    return f"{fg_color(color)}{text}{RESET}"


def custom_server_details() -> str:
    s = _style()
    return "\n".join(
        [
            _ansi(s.bright, "DETAILS"),
            "",
            _ansi(s.head, "Add Custom MCP Server"),
            "",
            "Add your own MCP server by providing",
            "a JSON configuration.",
            "",
            _ansi(s.head, "Supported Types:"),
            "",
            _ansi(s.bright, "1. stdio"),
            _ansi(s.grey, "   Runs a local command (npx, python, uvx)"),
            _ansi(s.grey, "   and communicates via stdin/stdout."),
            "",
            _ansi(s.bright, "2. http"),
            _ansi(s.grey, "   Connects to an HTTP endpoint that"),
            _ansi(s.grey, "   implements the MCP protocol."),
            "",
            _ansi(s.bright, "3. sse"),
            _ansi(s.grey, "   Connects via Server-Sent Events"),
            _ansi(s.grey, "   for real-time streaming."),
            "",
            _ansi(s.grey, "Press Enter to configure"),
        ]
    )


def category_details(catalog, category: str) -> str:
    if category == CUSTOM_SERVER_CATEGORY:
        return custom_server_details()
    s = _style()
    lines = [
        _ansi(s.bright, "DETAILS"),
        "",
        _ansi(s.head, f"{get_category_icon(category)} {category}"),
        "",
    ]
    servers = catalog.get_by_category(category) if catalog else []
    lines.append(_ansi(s.grey, f"{len(servers)} servers available"))
    popular = [server for server in servers if server.popular]
    if popular:
        lines += ["", _ansi(s.head, "Popular:")]
        lines += [_ansi(s.grey, f"  - {server.display_name}") for server in popular[:5]]
    return "\n".join(lines)


def server_details(server) -> str:
    s = _style()
    lines = [_ansi(s.bright, "DETAILS"), "", _ansi(s.head, server.display_name)]
    indicators = []
    if server.verified:
        indicators.append("Verified")
    if server.popular:
        indicators.append("Popular")
    if indicators:
        lines.append(_ansi(s.head, " | ".join(indicators)))
    lines += ["", _ansi(s.head, "Description:")]
    desc = server.description or "No description available"
    lines += [f"  {line}" for line in textwrap.wrap(desc, 50)]
    lines += ["", _ansi(s.head, "Type:"), _ansi(s.grey, f"  [{server.type}]")]
    if server.tags:
        lines += ["", _ansi(s.head, "Tags:"), f"  {', '.join(server.tags[:6])}"]

    env_vars = server.get_environment_vars()
    if env_vars:
        lines += ["", _ansi(s.head, "Environment Variables:")]
        for var in env_vars:
            if os.environ.get(var):
                lines.append(_ansi(s.head, f"  + {var}"))
            else:
                lines.append(_ansi(s.error, f"  o {var}"))

    cmd_args = server.get_command_line_args()
    if cmd_args:
        lines += ["", _ansi(s.head, "Configuration:")]
        for arg in cmd_args:
            name = arg.get("name", "unknown")
            required = arg.get("required", True)
            default = arg.get("default", "")
            marker = "*" if required else "?"
            default_str = f" [{default}]" if default else ""
            lines.append(_ansi(s.grey, f"  {marker} {name}{default_str}"))

    required_tools = server.get_requirements().required_tools
    if required_tools:
        lines += [
            "",
            _ansi(s.head, "Required Tools:"),
            _ansi(s.grey, f"  {', '.join(required_tools)}"),
        ]
    if server.example_usage:
        lines += [
            "",
            _ansi(s.head, "Example:"),
            _ansi(s.grey, f"  {server.example_usage}"),
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Menus
# ---------------------------------------------------------------------------


def build_categories_menu(catalog, categories: List[str], **overrides):
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    items = [MenuItem(f"{get_category_icon(c)} {c}", value=c) for c in categories]
    builder = themed(
        MenuBuilder("Install MCP Server - Categories")
        .items(items)
        .searchable()
        .list_width(36)
        .alt_screen(False)
        .preview(lambda item: category_details(catalog, item.value))
        .footer_hint("type filter - Enter open - Esc exit")
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def build_servers_menu(category: str, servers: List, **overrides):
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    def label(server):
        markers = ""
        if server.verified:
            markers += " +"
        if server.popular:
            markers += " *"
        return f"{server.display_name}{markers}"

    items = [
        MenuItem(label(server), value=server, description=server.type)
        for server in servers
    ]
    builder = themed(
        MenuBuilder(f"Install MCP Server - {category}")
        .items(items)
        .searchable()
        .list_width(36)
        .alt_screen(False)
        .preview(lambda item: server_details(item.value))
        .footer_hint("type filter - Enter install - Esc back")
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


def run_browse_flow(
    catalog,
    categories: List[str],
    categories_menu_factory: Callable = build_categories_menu,
    servers_menu_factory: Callable = build_servers_menu,
):
    """Browse loop inside the menu session.

    Returns ``"custom"``, a selected catalog server, or ``None``.
    """
    while True:
        result = categories_menu_factory(catalog, categories).run()
        if result.cancelled or result.item is None:
            return None
        category = result.item.value
        if category == CUSTOM_SERVER_CATEGORY:
            return "custom"
        if catalog is None:
            continue
        servers = catalog.get_by_category(category)
        server_result = servers_menu_factory(category, servers).run()
        if server_result.cancelled or server_result.item is None:
            continue  # back to categories
        return server_result.item.value


def _reload_mcp_servers() -> None:
    """Attempt to reload MCP servers after installation."""
    try:
        from code_puppy.agent import reload_mcp_servers

        reload_mcp_servers()
    except ImportError:
        pass


def run_mcp_install_menu(manager) -> bool:
    """Run the MCP install menu. True if a server was installed."""
    from code_puppy.command_line.menu_session import menu_session

    catalog, categories = load_catalog()
    if not categories:
        emit_warning("No MCP server catalog available.")
        return False

    set_awaiting_user_input(True)
    try:
        with menu_session():
            selection = run_browse_flow(catalog, categories)
    finally:
        set_awaiting_user_input(False)

    if selection is None:
        emit_info("Exited MCP server browser")
        return False

    # Custom server: hand off to the form (it owns its own session).
    if selection == "custom":
        success = run_custom_server_form(manager)
        if success:
            _reload_mcp_servers()
        return success

    # Catalog server: config prompts + install on the normal terminal.
    config = prompt_for_server_config(manager, selection)
    if not config:
        return False
    success = install_catalog_server(manager, selection, config)
    if success:
        _reload_mcp_servers()
    return success
