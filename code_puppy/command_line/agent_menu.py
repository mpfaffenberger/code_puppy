"""Interactive terminal UI for selecting agents.

Provides a split-panel interface (termflow MenuBuilder) for browsing and
selecting agents with live preview of agent details.

Keys: up/down navigate, left/right page, Enter select, P pin model,
B bind MCP servers, C clone, D delete clone, Esc/Ctrl+C cancel.
"""

import asyncio
import unicodedata
from typing import List, Optional, Tuple

from termflow.ansi.codes import BOLD_ON, DIM_ON, RESET
from termflow.tui import MenuBuilder, MenuItem
from termflow.tui.menu import MenuResult

from code_puppy.agents import (
    clone_agent,
    delete_clone_agent,
    get_agent_descriptions,
    get_available_agents,
    get_current_agent,
    is_clone_agent_name,
)
from code_puppy.command_line.mcp_binding_menu import interactive_mcp_binding_menu
from code_puppy.mcp_.agent_bindings import get_bound_servers
from code_puppy.command_line.model_picker_completion import (
    ModelSelectionMenu,
    load_model_names,
)
from code_puppy.config import (
    clear_agent_pinned_model,
    get_agent_pinned_model,
    set_agent_pinned_model,
)
from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 10  # Agents per page

# ---------------------------------------------------------------------------
# Deferred-reload queue
# ---------------------------------------------------------------------------
# ``interactive_agent_picker`` runs in a worker thread + transient
# asyncio.run loop (see handle_agent_command / switch_agent_resume) that dies
# when the picker returns. Reloading inside would schedule MCP autostart tasks
# on that loop; its cleanup deadlocks on anyio teardown and the main thread
# hangs in future.result(timeout=300) — Enter after pinning a model freezes
# the app. Solution: queue the reload; the caller drains it on the main loop
# afterwards, where the MCP tasks belong.
_PENDING_PIN_RELOADS: List[Tuple[str, Optional[str]]] = []


def consume_pending_pin_reloads() -> List[Tuple[str, Optional[str]]]:
    """Drain and return queued (agent_name, pinned_model) reload requests.

    Callers MUST invoke this from the main event loop after the picker
    worker future has completed, then call
    :func:`apply_pending_pin_reload` for each tuple.
    """
    global _PENDING_PIN_RELOADS
    pending = _PENDING_PIN_RELOADS
    _PENDING_PIN_RELOADS = []
    return pending


def apply_pending_pin_reload(agent_name: str, pinned_model: Optional[str]) -> None:
    """Reload the active agent if its pinned model changed during the picker.

    Safe to call from the main event loop only. No-ops if the named agent
    is not currently active.
    """
    _reload_agent_if_current(agent_name, pinned_model)


def _sanitize_display_text(text: str) -> str:
    """Remove or replace characters that cause terminal rendering issues.

    Args:
        text: Text that may contain emojis or wide characters

    Returns:
        Sanitized text safe for terminal rendering
    """
    # Keep only characters that render cleanly in terminals
    # Be aggressive about stripping anything that could cause width issues
    result = []
    for char in text:
        # Get unicode category
        cat = unicodedata.category(char)
        # Categories to KEEP: L* (letters), N* (numbers), P* (punctuation),
        # Zs (space), Sm (math), Sc (currency), Sk (modifier).
        # Categories to SKIP (cause rendering issues): So (emojis), Cf (ZWJ),
        # Mn/Mc/Me (marks), Cn (unassigned), Co (private use), Cs (surrogate).
        safe_categories = (
            "Lu",
            "Ll",
            "Lt",
            "Lm",
            "Lo",  # Letters
            "Nd",
            "Nl",
            "No",  # Numbers
            "Pc",
            "Pd",
            "Ps",
            "Pe",
            "Pi",
            "Pf",
            "Po",  # Punctuation
            "Zs",  # Space
            "Sm",
            "Sc",
            "Sk",  # Safe symbols (math, currency, modifier)
        )
        if cat in safe_categories:
            result.append(char)

    # Clean up any double spaces left behind and strip
    cleaned = " ".join("".join(result).split())
    return cleaned


def _get_pinned_model(agent_name: str) -> Optional[str]:
    """Return the pinned model for an agent, if any.

    Checks both built-in agent config and JSON agent files.
    """
    import json

    # First check built-in agent config
    try:
        pinned = get_agent_pinned_model(agent_name)
        if pinned:
            return pinned
    except Exception:
        pass  # Continue to check JSON agents

    # Check if it's a JSON agent
    try:
        from code_puppy.agents.json_agent import discover_json_agents

        json_agents = discover_json_agents()
        if agent_name in json_agents:
            agent_file_path = json_agents[agent_name]
            with open(agent_file_path, "r", encoding="utf-8") as f:
                agent_config = json.load(f)
            model = agent_config.get("model")
            return model if model else None
    except Exception:
        pass  # Return None if we can't read the JSON file

    return None


async def _select_pinned_model(agent_name: str) -> Optional[str]:
    """Prompt for a model to pin to the agent, reusing the /model picker."""
    try:
        model_names = load_model_names() or []
    except Exception as exc:
        emit_warning(f"Failed to load models: {exc}")
        return None

    # Prepend the "(unpin)" sentinel that _apply_pinned_model already understands.
    return await ModelSelectionMenu(model_names=["(unpin)"] + model_names).run_async()


def _reload_agent_if_current(
    agent_name: str,
    pinned_model: Optional[str],
) -> None:
    """Reload the current agent when its pinned model changes."""
    current_agent = get_current_agent()
    if not current_agent or current_agent.name != agent_name:
        return

    try:
        if hasattr(current_agent, "refresh_config"):
            current_agent.refresh_config()
        current_agent.reload_code_generation_agent()
        if pinned_model:
            emit_info(f"Active agent reloaded with pinned model '{pinned_model}'")
        else:
            emit_info("Active agent reloaded with default model")
    except Exception as exc:
        emit_warning(f"Pinned model applied but reload failed: {exc}")


def _apply_pinned_model(agent_name: str, model_choice: str) -> None:
    """Persist a pinned model selection for an agent.

    Handles both built-in agents (via config) and JSON agents (via JSON file).
    """
    import json

    # Check if this is a JSON agent or a built-in agent
    try:
        from code_puppy.agents.json_agent import discover_json_agents

        json_agents = discover_json_agents()
        is_json_agent = agent_name in json_agents
    except Exception:
        is_json_agent = False

    try:
        if is_json_agent:
            # Handle JSON agent - modify the JSON file
            agent_file_path = json_agents[agent_name]

            with open(agent_file_path, "r", encoding="utf-8") as f:
                agent_config = json.load(f)

            if model_choice == "(unpin)":
                # Remove the model key if it exists
                if "model" in agent_config:
                    del agent_config["model"]
                emit_success(f"Model pin cleared for '{agent_name}'")
                pinned_model = None
            else:
                # Set the model
                agent_config["model"] = model_choice
                emit_success(f"Pinned '{model_choice}' to '{agent_name}'")
                pinned_model = model_choice

            # Save the updated configuration
            with open(agent_file_path, "w", encoding="utf-8") as f:
                json.dump(agent_config, f, indent=2, ensure_ascii=False)
        else:
            # Handle built-in Python agent - use config functions
            if model_choice == "(unpin)":
                clear_agent_pinned_model(agent_name)
                emit_success(f"Model pin cleared for '{agent_name}'")
                pinned_model = None
            else:
                set_agent_pinned_model(agent_name, model_choice)
                emit_success(f"Pinned '{model_choice}' to '{agent_name}'")
                pinned_model = model_choice

        # Defer the reload to the main loop — doing it here would schedule MCP
        # autostart on the picker's transient loop and deadlock on shutdown
        # (see ``_PENDING_PIN_RELOADS``).
        _PENDING_PIN_RELOADS.append((agent_name, pinned_model))
    except Exception as exc:
        emit_warning(f"Failed to apply pinned model: {exc}")


def _get_agent_entries() -> List[Tuple[str, str, str]]:
    """Get all agents with their display names and descriptions.

    Returns:
        List of tuples (agent_name, display_name, description) sorted by name.
    """
    available = get_available_agents()
    descriptions = get_agent_descriptions()

    entries = []
    for name, display_name in available.items():
        description = descriptions.get(name, "No description available")
        entries.append((name, display_name, description))

    # Sort alphabetically by agent name
    entries.sort(key=lambda x: x[0].lower())
    return entries


def _wrap(text: str, width: int) -> List[str]:
    """Simple word wrap for the preview description."""
    out: List[str] = []
    for raw_line in text.split("\n"):
        line = ""
        for word in raw_line.split():
            if len(line) + len(word) + 1 > width and line:
                out.append(line)
                line = word
            else:
                line = word if not line else f"{line} {word}"
        if line.strip():
            out.append(line)
    return out


def _render_agent_details(entry: Tuple[str, str, str], current_agent_name: str) -> str:
    """ANSI preview pane for the highlighted agent."""
    name, display_name, description = entry
    is_current = name == current_agent_name
    pinned_model = _get_pinned_model(name)

    lines = [f"{BOLD_ON}AGENT DETAILS{RESET}", ""]
    lines.append(f"{DIM_ON}Name:{RESET}          {name}")
    lines.append(
        f"{DIM_ON}Display Name:{RESET}  {_sanitize_display_text(display_name)}"
    )
    pinned = _sanitize_display_text(pinned_model) if pinned_model else "default"
    lines.append(f"{DIM_ON}Pinned Model:{RESET}  {pinned}")

    try:
        bound = get_bound_servers(name)
    except Exception:
        bound = {}
    if bound:
        auto_count = sum(1 for opts in bound.values() if opts.get("auto_start"))
        summary = f"{len(bound)} bound"
        if auto_count:
            summary += f" ({auto_count} auto-start)"
    else:
        summary = "none bound (strict opt-in)"
    lines.append(f"{DIM_ON}MCP Servers:{RESET}   {summary}")
    lines.append("")
    lines.append(f"{DIM_ON}Description:{RESET}")
    lines.extend(_wrap(_sanitize_display_text(description), 55))
    lines.append("")
    status = "Currently Active" if is_current else "Not active"
    lines.append(f"{DIM_ON}Status:{RESET} {status}")
    return "\n".join(lines)


def _agent_items(
    entries: List[Tuple[str, str, str]], current_agent_name: str
) -> List[MenuItem]:
    items = []
    for name, display_name, _description in entries:
        pinned = _get_pinned_model(name)
        marks = []
        if pinned:
            marks.append(f"-> {_sanitize_display_text(pinned)}")
        if name == current_agent_name:
            marks.append("(current)")
        items.append(
            MenuItem(
                _sanitize_display_text(display_name),
                value=name,
                description="  ".join(marks),
            )
        )
    return items


def build_agent_menu(
    entries: List[Tuple[str, str, str]],
    current_agent_name: str,
    pending_action: dict,
    initial_index: int = 0,
    **overrides,
):
    """Build the agent picker menu (overrides allow headless test driving)."""
    entry_by_name = {name: entry for entry in entries for name in [entry[0]]}

    def _action(action: str):
        def handler(_menu, item: MenuItem) -> MenuResult:
            pending_action["action"] = action
            return MenuResult(item=item)

        return handler

    def _page_left(menu, _item: MenuItem) -> None:
        menu.page_up()
        return None

    def _page_right(menu, _item: MenuItem) -> None:
        menu.page_down()
        return None

    builder = (
        MenuBuilder("Agents")
        .items(_agent_items(entries, current_agent_name))
        .page_size(PAGE_SIZE)
        .list_width(45)
        .initial_index(initial_index)
        .preview(
            lambda item: _render_agent_details(
                entry_by_name[item.value], current_agent_name
            )
        )
        .on_key("p", _action("pin"))
        .on_key("b", _action("bind"))
        .on_key("c", _action("clone"))
        .on_key("d", _action("delete"))
        .on_key("left", _page_left)
        .on_key("right", _page_right)
        .footer_hint(
            "Up/Down navigate - Left/Right page - Enter select - P pin model - "
            "B bind MCP - C clone - D delete clone - Esc cancel"
        )
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


async def interactive_agent_picker() -> Optional[str]:
    """Show interactive terminal UI to select an agent.

    Returns:
        Agent name to switch to, or None if cancelled.
    """
    entries = _get_agent_entries()
    current_agent = get_current_agent()
    current_agent_name = current_agent.name if current_agent else ""

    if not entries:
        emit_info("No agents found.")
        return None

    selected_index = 0
    result: Optional[str] = None

    def _index_of(agent_name: Optional[str]) -> int:
        for idx, (name, _, _) in enumerate(entries):
            if name == agent_name:
                return idx
        return min(selected_index, max(len(entries) - 1, 0))

    set_awaiting_user_input(True)
    try:
        while True:
            pending_action: dict = {"action": None}
            menu = build_agent_menu(
                entries, current_agent_name, pending_action, selected_index
            )
            menu_result = await asyncio.to_thread(menu.run)

            highlighted = menu_result.item.value if menu_result.item else None
            selected_index = _index_of(highlighted)
            action = pending_action["action"]

            if action == "pin" and highlighted:
                selected_model = await _select_pinned_model(highlighted)
                if selected_model:
                    _apply_pinned_model(highlighted, selected_model)
                continue

            if action == "bind" and highlighted:
                await interactive_mcp_binding_menu(highlighted)
                continue

            if action == "clone" and highlighted:
                cloned_name = clone_agent(highlighted)
                entries = _get_agent_entries()
                selected_index = _index_of(cloned_name or highlighted)
                continue

            if action == "delete" and highlighted:
                if not is_clone_agent_name(highlighted):
                    emit_warning("Only cloned agents can be deleted.")
                elif highlighted == current_agent_name:
                    emit_warning("Cannot delete the active agent. Switch first.")
                elif delete_clone_agent(highlighted):
                    selected_index = 0
                entries = _get_agent_entries()
                if not entries:
                    break
                selected_index = min(selected_index, len(entries) - 1)
                continue

            if not menu_result.cancelled and highlighted:
                result = highlighted
            break
    finally:
        set_awaiting_user_input(False)

    emit_info("Exited agent picker")
    return result
