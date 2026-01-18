"""Interactive terminal UI for selecting agents.

Provides a split-panel interface for browsing and selecting agents
with live preview of agent details.
"""

import sys
import time
import unicodedata
from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.agents import (
    clone_agent,
    delete_clone_agent,
    get_agent_descriptions,
    get_available_agents,
    get_current_agent,
    is_clone_agent_name,
)
from code_puppy.command_line.model_picker_completion import load_model_names
from code_puppy.config import (
    clear_agent_pinned_model,
    get_agent_pinned_model,
    set_agent_pinned_model,
)
from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.command_runner import set_awaiting_user_input
from code_puppy.tools.common import arrow_select_async

PAGE_SIZE = 10  # Agents per page


def _sanitize_display_text(text: str) -> str:
    """Remove or replace characters that cause terminal rendering issues.

    Args:
        text: Text that may contain emojis or wide characters

    Returns:
        Sanitized text safe for prompt_toolkit rendering
    """
    # Keep only characters that render cleanly in terminals
    # Be aggressive about stripping anything that could cause width issues
    result = []
    for char in text:
        # Get unicode category
        cat = unicodedata.category(char)
        # Categories to KEEP:
        # - L* (Letters): Lu, Ll, Lt, Lm, Lo
        # - N* (Numbers): Nd, Nl, No
        # - P* (Punctuation): Pc, Pd, Ps, Pe, Pi, Pf, Po
        # - Zs (Space separator)
        # - Sm (Math symbols like +, -, =)
        # - Sc (Currency symbols like $, €)
        # - Sk (Modifier symbols)
        #
        # Categories to SKIP (cause rendering issues):
        # - So (Symbol, other) - emojis
        # - Cf (Format) - ZWJ, etc.
        # - Mn (Mark, nonspacing) - combining characters
        # - Mc (Mark, spacing combining)
        # - Me (Mark, enclosing)
        # - Cn (Not assigned)
        # - Co (Private use)
        # - Cs (Surrogate)
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


def _build_model_picker_choices(
    pinned_model: Optional[str],
    model_names: List[str],
) -> List[str]:
    """Build model picker choices with pinned/unpin indicators."""
    choices = ["✓ (unpin)" if not pinned_model else "  (unpin)"]

    for model_name in model_names:
        if model_name == pinned_model:
            choices.append(f"✓ {model_name} (pinned)")
        else:
            choices.append(f"  {model_name}")

    return choices


def _normalize_model_choice(choice: str) -> str:
    """Normalize a picker choice into a model name or '(unpin)' string."""
    cleaned = choice.strip()
    if cleaned.startswith("✓"):
        cleaned = cleaned.lstrip("✓").strip()
    if cleaned.endswith(" (pinned)"):
        cleaned = cleaned[: -len(" (pinned)")].strip()
    return cleaned


async def _select_pinned_model(agent_name: str) -> Optional[str]:
    """Prompt for a model to pin to the agent."""
    try:
        model_names = load_model_names() or []
    except Exception as exc:
        emit_warning(f"Failed to load models: {exc}")
        return None

    pinned_model = _get_pinned_model(agent_name)
    choices = _build_model_picker_choices(pinned_model, model_names)
    if not choices:
        emit_warning("No models available to pin.")
        return None

    try:
        choice = await arrow_select_async(
            f"Select a model to pin for '{agent_name}'",
            choices,
        )
    except KeyboardInterrupt:
        emit_info("Model pinning cancelled")
        return None

    return _normalize_model_choice(choice)


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

        _reload_agent_if_current(agent_name, pinned_model)
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


def _render_menu_panel(
    entries: List[Tuple[str, str, str]],
    page: int,
    selected_idx: int,
    current_agent_name: str,
) -> List:
    """Render the left menu panel with pagination.

    Args:
        entries: List of (name, display_name, description) tuples
        page: Current page number (0-indexed)
        selected_idx: Currently selected index (global)
        current_agent_name: Name of the current active agent

    Returns:
        List of (style, text) tuples for FormattedTextControl
    """
    lines = []
    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE if entries else 1
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, len(entries))

    lines.append(("bold", "Agents"))
    lines.append(("fg:ansibrightblack", f" (Page {page + 1}/{total_pages})"))
    lines.append(("", "\n\n"))

    if not entries:
        lines.append(("fg:yellow", "  No agents found."))
        lines.append(("", "\n\n"))
    else:
        # Show agents for current page
        for i in range(start_idx, end_idx):
            name, display_name, _ = entries[i]
            is_selected = i == selected_idx
            is_current = name == current_agent_name
            pinned_model = _get_pinned_model(name)

            # Sanitize display name to avoid emoji rendering issues
            safe_display_name = _sanitize_display_text(display_name)

            # Build the line
            if is_selected:
                lines.append(("fg:ansigreen", "▶ "))
                lines.append(("fg:ansigreen bold", safe_display_name))
            else:
                lines.append(("", "  "))
                lines.append(("", safe_display_name))

            if pinned_model:
                safe_pinned_model = _sanitize_display_text(pinned_model)
                lines.append(("fg:ansiyellow", f" → {safe_pinned_model}"))

            # Add current marker
            if is_current:
                lines.append(("fg:ansicyan", " ← current"))

            lines.append(("", "\n"))

    # Navigation hints
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  ↑↓ "))
    lines.append(("", "Navigate\n"))
    lines.append(("fg:ansibrightblack", "  ←→ "))
    lines.append(("", "Page\n"))
    lines.append(("fg:green", "  Enter  "))
    lines.append(("", "Select\n"))
    lines.append(("fg:ansibrightblack", "  P "))
    lines.append(("", "Pin model\n"))
    lines.append(("fg:ansibrightblack", "  C "))
    lines.append(("", "Clone\n"))
    lines.append(("fg:ansibrightblack", "  D "))
    lines.append(("", "Delete clone\n"))
    lines.append(("fg:ansibrightred", "  Ctrl+C "))
    lines.append(("", "Cancel"))

    return lines


def _render_preview_panel(
    entry: Optional[Tuple[str, str, str]],
    current_agent_name: str,
) -> List:
    """Render the right preview panel with agent details.

    Args:
        entry: Tuple of (name, display_name, description) or None
        current_agent_name: Name of the current active agent

    Returns:
        List of (style, text) tuples for FormattedTextControl
    """
    lines = []

    lines.append(("dim cyan", " AGENT DETAILS"))
    lines.append(("", "\n\n"))

    if not entry:
        lines.append(("fg:yellow", "  No agent selected."))
        lines.append(("", "\n"))
        return lines

    name, display_name, description = entry
    is_current = name == current_agent_name
    pinned_model = _get_pinned_model(name)

    # Sanitize text to avoid emoji rendering issues
    safe_display_name = _sanitize_display_text(display_name)
    safe_description = _sanitize_display_text(description)

    # Agent name (identifier)
    lines.append(("bold", "Name: "))
    lines.append(("", name))
    lines.append(("", "\n\n"))

    # Display name
    lines.append(("bold", "Display Name: "))
    lines.append(("fg:ansicyan", safe_display_name))
    lines.append(("", "\n\n"))

    # Pinned model
    lines.append(("bold", "Pinned Model: "))
    if pinned_model:
        safe_pinned_model = _sanitize_display_text(pinned_model)
        lines.append(("fg:ansiyellow", safe_pinned_model))
    else:
        lines.append(("fg:ansibrightblack", "default"))
    lines.append(("", "\n\n"))

    # Description
    lines.append(("bold", "Description:"))
    lines.append(("", "\n"))

    # Wrap description to fit panel
    desc_lines = safe_description.split("\n")
    for desc_line in desc_lines:
        # Word wrap long lines
        words = desc_line.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 > 55:
                lines.append(("fg:ansibrightblack", current_line))
                lines.append(("", "\n"))
                current_line = word
            else:
                if current_line == "":
                    current_line = word
                else:
                    current_line += " " + word
        if current_line.strip():
            lines.append(("fg:ansibrightblack", current_line))
            lines.append(("", "\n"))

    lines.append(("", "\n"))

    # Current status
    lines.append(("bold", "  Status: "))
    if is_current:
        lines.append(("fg:ansigreen bold", "✓ Currently Active"))
    else:
        lines.append(("fg:ansibrightblack", "Not active"))
    lines.append(("", "\n"))

    return lines


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

    # State
    selected_idx = [0]  # Current selection (global index)
    current_page = [0]  # Current page
    result = [None]  # Selected agent name
    pending_action = [None]  # 'pin', 'clone', 'delete', or None

    total_pages = [max(1, (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE)]

    def get_current_entry() -> Optional[Tuple[str, str, str]]:
        if 0 <= selected_idx[0] < len(entries):
            return entries[selected_idx[0]]
        return None

    def refresh_entries(selected_name: Optional[str] = None) -> None:
        nonlocal entries

        entries = _get_agent_entries()
        total_pages[0] = max(1, (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE)

        if not entries:
            selected_idx[0] = 0
            current_page[0] = 0
            return

        if selected_name:
            for idx, (name, _, _) in enumerate(entries):
                if name == selected_name:
                    selected_idx[0] = idx
                    break
            else:
                selected_idx[0] = min(selected_idx[0], len(entries) - 1)
        else:
            selected_idx[0] = min(selected_idx[0], len(entries) - 1)

        current_page[0] = selected_idx[0] // PAGE_SIZE

    # Build UI
    menu_control = FormattedTextControl(text="")
    preview_control = FormattedTextControl(text="")

    def update_display():
        """Update both panels."""
        menu_control.text = _render_menu_panel(
            entries, current_page[0], selected_idx[0], current_agent_name
        )
        preview_control.text = _render_preview_panel(
            get_current_entry(), current_agent_name
        )

    menu_window = Window(
        content=menu_control, wrap_lines=False, width=Dimension(weight=35)
    )
    preview_window = Window(
        content=preview_control, wrap_lines=False, width=Dimension(weight=65)
    )

    menu_frame = Frame(menu_window, width=Dimension(weight=35), title="Agents")
    preview_frame = Frame(preview_window, width=Dimension(weight=65), title="Preview")

    root_container = VSplit(
        [
            menu_frame,
            preview_frame,
        ]
    )

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            # Update page if needed
            current_page[0] = selected_idx[0] // PAGE_SIZE
            update_display()

    @kb.add("down")
    def _(event):
        if selected_idx[0] < len(entries) - 1:
            selected_idx[0] += 1
            # Update page if needed
            current_page[0] = selected_idx[0] // PAGE_SIZE
            update_display()

    @kb.add("left")
    def _(event):
        if current_page[0] > 0:
            current_page[0] -= 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("right")
    def _(event):
        if current_page[0] < total_pages[0] - 1:
            current_page[0] += 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("p")
    def _(event):
        if get_current_entry():
            pending_action[0] = "pin"
            event.app.exit()

    @kb.add("c")
    def _(event):
        if get_current_entry():
            pending_action[0] = "clone"
            event.app.exit()

    @kb.add("d")
    def _(event):
        if get_current_entry():
            pending_action[0] = "delete"
            event.app.exit()

    @kb.add("enter")
    def _(event):
        entry = get_current_entry()
        if entry:
            result[0] = entry[0]  # Store agent name
        event.app.exit()

    @kb.add("c-c")
    def _(event):
        result[0] = None
        event.app.exit()

    layout = Layout(root_container)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    set_awaiting_user_input(True)

    # Enter alternate screen buffer once for entire session
    sys.stdout.write("\033[?1049h")  # Enter alternate buffer
    sys.stdout.write("\033[2J\033[H")  # Clear and home
    sys.stdout.flush()
    time.sleep(0.05)

    try:
        while True:
            pending_action[0] = None
            result[0] = None
            update_display()

            # Clear the current buffer
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            # Run application
            await app.run_async()

            if pending_action[0] == "pin":
                entry = get_current_entry()
                if entry:
                    selected_model = await _select_pinned_model(entry[0])
                    if selected_model:
                        _apply_pinned_model(entry[0], selected_model)
                continue

            if pending_action[0] == "clone":
                entry = get_current_entry()
                selected_name = None
                if entry:
                    cloned_name = clone_agent(entry[0])
                    selected_name = cloned_name or entry[0]
                refresh_entries(selected_name=selected_name)
                continue

            if pending_action[0] == "delete":
                entry = get_current_entry()
                selected_name = None
                if entry:
                    agent_name = entry[0]
                    selected_name = agent_name
                    if not is_clone_agent_name(agent_name):
                        emit_warning("Only cloned agents can be deleted.")
                    elif agent_name == current_agent_name:
                        emit_warning("Cannot delete the active agent. Switch first.")
                    else:
                        if delete_clone_agent(agent_name):
                            selected_name = None
                refresh_entries(selected_name=selected_name)
                continue

            break

    finally:
        # Exit alternate screen buffer once at end
        sys.stdout.write("\033[?1049l")  # Exit alternate buffer
        sys.stdout.flush()
        # Reset awaiting input flag
        set_awaiting_user_input(False)

    # Clear exit message
    emit_info("✓ Exited agent picker")

    return result[0]
