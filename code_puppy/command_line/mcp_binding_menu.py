"""Interactive sub-menu for binding MCP servers to a specific agent.

Launched from :mod:`code_puppy.command_line.agent_menu` (and reused by the
post-install flow in :mod:`code_puppy.command_line.mcp.install_command`).

Built on termflow's MenuBuilder:

* Rows show ``[x]`` / ``[ ]`` for bound/unbound plus an auto-start marker.
* Right panel shows server details for the highlighted row.
* Keys: up/down navigate, ``space`` toggle binding, ``a`` toggle
  auto-start, ``enter``/``q`` close, ``esc``/``ctrl-c`` cancel.

Toggles mutate the bindings file immediately (no save/cancel split), so
"close" and "cancel" are equivalent exits.
"""

from __future__ import annotations

import asyncio
from typing import List, Tuple

from termflow.ansi.codes import BOLD_ON, DIM_ON, RESET
from termflow.tui import MenuBuilder, MenuItem
from termflow.tui.menu import MenuResult

from code_puppy.command_line.menu_session import menu_session
from code_puppy.mcp_ import get_mcp_manager
from code_puppy.mcp_.agent_bindings import (
    get_bound_servers,
    is_bound,
    set_binding,
    toggle_auto_start,
    toggle_binding,
)
from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.command_runner import set_awaiting_user_input

_AUTO_MARKER = " \u26a1auto"


def _list_servers() -> List[Tuple[str, str, str]]:
    """Return ``[(name, type, state)]`` for every registered MCP server."""
    manager = get_mcp_manager()
    rows: List[Tuple[str, str, str]] = []
    try:
        infos = manager.list_servers()
    except Exception as exc:  # pragma: no cover - defensive
        emit_warning(f"Failed to list MCP servers: {exc}")
        return rows
    for info in infos:
        rows.append((info.name, info.type, info.state.value))
    rows.sort(key=lambda r: r[0].lower())
    return rows


def _binding_label(agent_name: str, server_name: str) -> str:
    """Checkbox + auto marker + server name for one row."""
    bindings = get_bound_servers(agent_name)
    bound = server_name in bindings
    auto = bool(bindings.get(server_name, {}).get("auto_start"))
    checkbox = "[x]" if bound else "[ ]"
    return f"{checkbox} {server_name}{_AUTO_MARKER if auto else ''}"


def _server_items(
    agent_name: str, servers: List[Tuple[str, str, str]]
) -> list[MenuItem]:
    return [
        MenuItem(_binding_label(agent_name, name), value=name)
        for name, _type, _state in servers
    ]


def _render_details(
    agent_name: str, servers: List[Tuple[str, str, str]], server_name: str
) -> str:
    """ANSI detail pane for the highlighted server."""
    row = next((r for r in servers if r[0] == server_name), None)
    if row is None:
        return f"{DIM_ON}Nothing to preview.{RESET}"
    name, type_, state = row
    bindings = get_bound_servers(agent_name)
    bound = name in bindings
    auto = bool(bindings.get(name, {}).get("auto_start"))
    yn = lambda flag: "yes" if flag else "no"  # noqa: E731 - tiny local formatter
    return "\n".join(
        [
            f"{BOLD_ON}SERVER DETAILS{RESET}",
            "",
            f"{DIM_ON}Name:{RESET}       {name}",
            f"{DIM_ON}Type:{RESET}       {type_}",
            f"{DIM_ON}State:{RESET}      {state}",
            f"{DIM_ON}Bound:{RESET}      {yn(bound)}",
            f"{DIM_ON}Auto-start:{RESET} {yn(auto)}",
        ]
    )


def build_binding_menu(
    agent_name: str, servers: List[Tuple[str, str, str]], **overrides
):
    """Build the termflow menu for per-agent MCP bindings (testable headless)."""

    def _toggle(menu, item: MenuItem) -> MenuResult | None:
        toggle_binding(agent_name, item.value)
        menu.replace_items(_server_items(agent_name, servers))
        return None

    def _toggle_auto(menu, item: MenuItem) -> MenuResult | None:
        if toggle_auto_start(agent_name, item.value) is None:
            # Not bound yet -- bind first, then turn auto_start on.
            set_binding(agent_name, item.value, auto_start=True)
        menu.replace_items(_server_items(agent_name, servers))
        return None

    def _done(_menu, item: MenuItem) -> MenuResult:
        return MenuResult(item=item)

    builder = (
        MenuBuilder(f"MCP bindings for agent: {agent_name}")
        .items(_server_items(agent_name, servers))
        .preview(lambda item: _render_details(agent_name, servers, item.value))
        .on_key(" ", _toggle)
        .on_key("a", _toggle_auto)
        .on_key("q", _done)
        .footer_hint(
            "Up/Down navigate - Space toggle bind - A auto-start - Enter/Q done - Esc cancel"
        )
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


async def interactive_mcp_binding_menu(agent_name: str) -> None:
    """Open the MCP-binding sub-menu for ``agent_name``.

    Returns when the user hits Enter / Q / Esc / Ctrl+C. Mutates the
    bindings file immediately on each toggle (no save/cancel split).
    """
    servers = _list_servers()
    if not servers:
        # Show the hint inside the TUI: an emit here would paint behind
        # the alternate screen and leave the user mashing B in confusion.
        empty_menu = (
            MenuBuilder(f"MCP bindings for agent: {agent_name}")
            .items(
                [
                    MenuItem(
                        "No MCP servers installed. Use /mcp install to add "
                        "some, then bind them to this agent.",
                        disabled=True,
                    )
                ]
            )
            .footer_hint("Esc to go back")
            .alt_screen(False)
            .build()
        )
        set_awaiting_user_input(True)
        try:
            with menu_session():
                await asyncio.to_thread(empty_menu.run)
        finally:
            set_awaiting_user_input(False)
        return

    set_awaiting_user_input(True)
    try:
        with menu_session():
            await asyncio.to_thread(
                build_binding_menu(agent_name, servers, alt_screen=False).run
            )
    finally:
        set_awaiting_user_input(False)

    bindings = get_bound_servers(agent_name)
    emit_info(
        f"Saved MCP bindings for '{agent_name}': {len(bindings)} server(s) bound."
    )


# ---------- post-install bind helper -----------------------------------------


def _agent_label(agent: str, server_name: str) -> str:
    from code_puppy.mcp_.agent_bindings import get_auto_start

    bound = is_bound(agent, server_name)
    auto = get_auto_start(agent, server_name) if bound else False
    checkbox = "[x]" if bound else "[ ]"
    return f"{checkbox} {agent}{_AUTO_MARKER if auto else ''}"


def build_post_install_menu(server_name: str, agents: List[str], **overrides):
    """Build the inverted menu (one server, many agents) after an install."""

    def _items() -> list[MenuItem]:
        return [MenuItem(_agent_label(a, server_name), value=a) for a in agents]

    def _toggle(menu, item: MenuItem) -> MenuResult | None:
        toggle_binding(item.value, server_name)
        menu.replace_items(_items())
        return None

    def _toggle_auto(menu, item: MenuItem) -> MenuResult | None:
        if toggle_auto_start(item.value, server_name) is None:
            set_binding(item.value, server_name, auto_start=True)
        menu.replace_items(_items())
        return None

    def _done(_menu, item: MenuItem) -> MenuResult:
        return MenuResult(item=item)

    builder = (
        MenuBuilder(f"Bind '{server_name}' to which agents?")
        .items(_items())
        .on_key(" ", _toggle)
        .on_key("a", _toggle_auto)
        .on_key("q", _done)
        .footer_hint("Space toggle bind - A auto-start - Enter/Q done - Esc skip")
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


async def prompt_bind_after_install(server_name: str) -> None:
    """After a fresh install, ask the user which agents to bind the server to.

    Walks every registered agent and lets the user toggle binding +
    auto-start for the *new* server. Same TUI shape as the per-agent menu
    but inverted (one server, many agents).
    """
    from code_puppy.agents import get_available_agents

    available = get_available_agents()
    if not available:
        return
    agents = sorted(available.keys(), key=str.lower)

    set_awaiting_user_input(True)
    try:
        with menu_session():
            await asyncio.to_thread(
                build_post_install_menu(server_name, agents, alt_screen=False).run
            )
    finally:
        set_awaiting_user_input(False)
