"""Interactive sub-menu for binding MCP servers to a specific agent.

Launched from :mod:`code_puppy.command_line.agent_menu` (and reused by the
post-install flow in :mod:`code_puppy.command_line.mcp.install_command`).

UI:

* Left panel — every MCP server known to the manager. Each row shows
  ``[x]`` / ``[ ]`` for bound/unbound and ``⚡`` if auto-start is on.
* Right panel — server details (id, type, current state).
* Keys: ``↑↓`` navigate, ``space`` toggle binding, ``a`` toggle auto-start,
  ``enter``/``q`` close, ``Ctrl+C`` cancel.
"""

from __future__ import annotations

import asyncio
import sys
from typing import List, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

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


def _render_menu(
    agent_name: str,
    servers: List[Tuple[str, str, str]],
    selected_idx: int,
) -> List:
    """Format the left binding panel."""
    bindings = get_bound_servers(agent_name)
    lines: List = []
    lines.append(("bold", "MCP bindings for agent: "))
    lines.append(("fg:ansicyan bold", agent_name))
    lines.append(("", "\n\n"))

    if not servers:
        lines.append(("fg:yellow", "  No MCP servers installed yet.\n"))
        lines.append(("fg:ansibrightblack", "  Run /mcp install to add some.\n"))
    else:
        for i, (name, _type, _state) in enumerate(servers):
            bound = name in bindings
            auto = bool(bindings.get(name, {}).get("auto_start"))
            checkbox = "[x]" if bound else "[ ]"
            auto_marker = " ⚡auto" if auto else ""
            prefix = "▶ " if i == selected_idx else "  "
            style_prefix = "fg:ansigreen bold" if i == selected_idx else ""
            style_box = "fg:ansigreen" if bound else "fg:ansibrightblack"
            lines.append((style_prefix, prefix))
            lines.append((style_box, f"{checkbox} "))
            lines.append((style_prefix or "", name))
            if auto_marker:
                lines.append(("fg:ansiyellow", auto_marker))
            lines.append(("", "\n"))

    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  ↑↓ "))
    lines.append(("", "Navigate\n"))
    lines.append(("fg:green", "  Space "))
    lines.append(("", "Toggle bind\n"))
    lines.append(("fg:ansiyellow", "  A "))
    lines.append(("", "Toggle auto-start\n"))
    lines.append(("fg:ansicyan", "  Enter / Q "))
    lines.append(("", "Done\n"))
    lines.append(("fg:ansibrightred", "  Ctrl+C "))
    lines.append(("", "Cancel"))
    return lines


def _render_preview(
    agent_name: str,
    servers: List[Tuple[str, str, str]],
    selected_idx: int,
) -> List:
    """Format the right detail panel."""
    lines: List = []
    lines.append(("dim cyan", " SERVER DETAILS"))
    lines.append(("", "\n\n"))
    if not servers or not (0 <= selected_idx < len(servers)):
        lines.append(("fg:ansibrightblack", "  Nothing to preview.\n"))
        return lines

    name, type_, state = servers[selected_idx]
    bindings = get_bound_servers(agent_name)
    bound = name in bindings
    auto = bool(bindings.get(name, {}).get("auto_start"))

    lines.append(("bold", "Name: "))
    lines.append(("fg:ansicyan", name))
    lines.append(("", "\n\n"))
    lines.append(("bold", "Type: "))
    lines.append(("", type_))
    lines.append(("", "\n\n"))
    lines.append(("bold", "State: "))
    lines.append(
        ("fg:ansigreen" if state == "running" else "fg:ansibrightblack", state)
    )
    lines.append(("", "\n\n"))
    lines.append(("bold", "Bound: "))
    lines.append(
        ("fg:ansigreen" if bound else "fg:ansibrightblack", "yes" if bound else "no"),
    )
    lines.append(("", "\n\n"))
    lines.append(("bold", "Auto-start: "))
    lines.append(
        ("fg:ansiyellow" if auto else "fg:ansibrightblack", "yes" if auto else "no"),
    )
    lines.append(("", "\n"))
    return lines


async def interactive_mcp_binding_menu(agent_name: str) -> None:
    """Open the MCP-binding sub-menu for ``agent_name``.

    Returns when the user hits Enter / Q / Ctrl+C. Mutates the bindings file
    immediately on each toggle (no save/cancel split).
    """
    servers = _list_servers()
    if not servers:
        emit_info(
            "No MCP servers installed. Use /mcp install to add some, "
            "then bind them to this agent."
        )
        return

    selected_idx = [0]
    menu_control = FormattedTextControl(text="")
    preview_control = FormattedTextControl(text="")

    def refresh() -> None:
        menu_control.text = _render_menu(agent_name, servers, selected_idx[0])
        preview_control.text = _render_preview(agent_name, servers, selected_idx[0])

    refresh()

    menu_window = Window(content=menu_control, wrap_lines=False)
    preview_window = Window(content=preview_control, wrap_lines=False)
    menu_frame = Frame(menu_window, width=Dimension(weight=55), title="MCP Servers")
    preview_frame = Frame(preview_window, width=Dimension(weight=45), title="Details")
    root = VSplit([menu_frame, preview_frame])

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            refresh()

    @kb.add("down")
    def _(event):
        if selected_idx[0] < len(servers) - 1:
            selected_idx[0] += 1
            refresh()

    @kb.add("space")
    def _(event):
        name = servers[selected_idx[0]][0]
        toggle_binding(agent_name, name)
        refresh()

    @kb.add("a")
    def _(event):
        name = servers[selected_idx[0]][0]
        result = toggle_auto_start(agent_name, name)
        if result is None:
            # Not bound yet — bind first, then turn auto_start on.
            set_binding(agent_name, name, auto_start=True)
        refresh()

    @kb.add("enter")
    @kb.add("q")
    def _(event):
        event.app.exit()

    @kb.add("c-c")
    def _(event):
        event.app.exit()

    app = Application(
        layout=Layout(root),
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    set_awaiting_user_input(True)
    sys.stdout.write("\033[?1049h\033[2J\033[H")
    sys.stdout.flush()
    await asyncio.sleep(0.05)
    try:
        await app.run_async()
    finally:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        set_awaiting_user_input(False)

    bindings = get_bound_servers(agent_name)
    emit_info(
        f"✓ Saved MCP bindings for '{agent_name}': {len(bindings)} server(s) bound."
    )


# ---------- post-install bind helper -----------------------------------------


async def prompt_bind_after_install(server_name: str) -> None:
    """After a fresh install, ask the user which agents to bind the server to.

    Walks every registered agent and lets the user toggle binding + auto-start
    for the *new* server. Reuses the same TUI shape as the per-agent menu but
    inverted (one server, many agents).
    """
    from code_puppy.agents import get_available_agents
    from code_puppy.mcp_.agent_bindings import (
        get_auto_start,
        toggle_binding,
    )

    available = get_available_agents()
    if not available:
        return
    agents = sorted(available.keys(), key=str.lower)

    selected_idx = [0]
    menu_control = FormattedTextControl(text="")

    def render() -> List:
        lines: List = []
        lines.append(("bold", "Bind '"))
        lines.append(("fg:ansicyan bold", server_name))
        lines.append(("bold", "' to which agents?"))
        lines.append(("", "\n\n"))
        for i, agent in enumerate(agents):
            bound = is_bound(agent, server_name)
            auto = get_auto_start(agent, server_name) if bound else False
            checkbox = "[x]" if bound else "[ ]"
            prefix = "▶ " if i == selected_idx[0] else "  "
            style_prefix = "fg:ansigreen bold" if i == selected_idx[0] else ""
            style_box = "fg:ansigreen" if bound else "fg:ansibrightblack"
            lines.append((style_prefix, prefix))
            lines.append((style_box, f"{checkbox} "))
            lines.append((style_prefix or "", agent))
            if auto:
                lines.append(("fg:ansiyellow", " ⚡auto"))
            lines.append(("", "\n"))
        lines.append(("", "\n"))
        lines.append(("fg:green", "  Space "))
        lines.append(("", "Toggle bind   "))
        lines.append(("fg:ansiyellow", "A "))
        lines.append(("", "Toggle auto-start\n"))
        lines.append(("fg:ansicyan", "  Enter / Q "))
        lines.append(("", "Done   "))
        lines.append(("fg:ansibrightred", "Ctrl+C "))
        lines.append(("", "Skip"))
        return lines

    def refresh() -> None:
        menu_control.text = render()

    refresh()

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            refresh()

    @kb.add("down")
    def _(event):
        if selected_idx[0] < len(agents) - 1:
            selected_idx[0] += 1
            refresh()

    @kb.add("space")
    def _(event):
        toggle_binding(agents[selected_idx[0]], server_name)
        refresh()

    @kb.add("a")
    def _(event):
        agent = agents[selected_idx[0]]
        result = toggle_auto_start(agent, server_name)
        if result is None:
            set_binding(agent, server_name, auto_start=True)
        refresh()

    @kb.add("enter")
    @kb.add("q")
    @kb.add("c-c")
    def _(event):
        event.app.exit()

    window = Window(content=menu_control, wrap_lines=False)
    frame = Frame(window, title=f"Bind {server_name}")
    app = Application(
        layout=Layout(frame), key_bindings=kb, full_screen=False, mouse_support=False
    )

    set_awaiting_user_input(True)
    sys.stdout.write("\033[?1049h\033[2J\033[H")
    sys.stdout.flush()
    await asyncio.sleep(0.05)
    try:
        await app.run_async()
    finally:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        set_awaiting_user_input(False)

    bound_agents = [a for a in agents if is_bound(a, server_name)]
    if bound_agents:
        emit_info(f"✓ '{server_name}' is now bound to: {', '.join(bound_agents)}")
    else:
        emit_info(
            f"'{server_name}' was installed but isn't bound to any agent yet. "
            "Use /agents → B to bind it later."
        )


def prompt_bind_after_install_sync(server_name: str) -> None:
    """Sync entrypoint for the post-install bind flow.

    Asks the user (via a normal text prompt) whether to launch the binding
    TUI right now. If they decline, prints a hint about ``/agents → B`` and
    returns without opening any full-screen menu.

    Mirrors the threading pattern used by ``/agents`` in ``core_commands.py``
    so we don't fight the outer CLI event loop.
    """
    import concurrent.futures

    emit_info(
        "\nMCP servers are bound per-agent (strict opt-in). "
        f"Right now, '{server_name}' is installed but not visible to any agent."
    )
    emit_info(
        "You can bind it now via a quick menu, or skip and bind later from /agents → B."
    )

    # Use safe_input (not emit_prompt) so the answer appears inline after
    # the question, matching the rest of the install wizard's [y/N]: style.
    # emit_prompt would put the answer on its own ">>> " line below.
    from code_puppy.command_line.utils import safe_input

    try:
        answer = safe_input("Configure bindings for this server now? [Y/n]: ")
    except (KeyboardInterrupt, EOFError):
        emit_info("Skipped binding. Use /agents → B to bind later.")
        return

    if answer.strip().lower().startswith("n"):
        emit_info("Skipped binding. Use /agents → B to bind later.")
        return

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(prompt_bind_after_install(server_name))
            )
            future.result(timeout=300)
    except Exception as exc:
        emit_warning(f"Could not show bind prompt: {exc}")
