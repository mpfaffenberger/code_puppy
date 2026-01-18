"""Interactive terminal UI for pause+steer functionality.

Provides a split-panel interface for viewing agents, selecting which to steer,
entering steering prompts, and resuming paused agents.
"""

import sys
import time
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.pause_manager import AgentStatus, get_pause_manager
from code_puppy.tools.command_runner import set_awaiting_user_input
from code_puppy.tools.common import arrow_select_async

PAGE_SIZE = 10  # Agents per page


@dataclass
class SteeringResult:
    """Result from the pause menu interaction."""

    queued_prompts: List[Tuple[str, str]]  # List of (agent_id, prompt)
    resumed_agents: List[str]  # List of agent_ids that were resumed
    cancelled: bool = False


def _sanitize_display_text(text: str) -> str:
    """Remove or replace characters that cause terminal rendering issues.

    Args:
        text: Text that may contain emojis or wide characters

    Returns:
        Sanitized text safe for prompt_toolkit rendering
    """
    result = []
    for char in text:
        cat = unicodedata.category(char)
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
            "Sk",  # Safe symbols
        )
        if cat in safe_categories:
            result.append(char)
    cleaned = " ".join("".join(result).split())
    return cleaned


def _get_status_display(status: AgentStatus) -> Tuple[str, str]:
    """Get display text and style for an agent status.

    Args:
        status: The AgentStatus enum value

    Returns:
        Tuple of (display_text, style)
    """
    if status == AgentStatus.RUNNING:
        return ("RUNNING", "fg:ansigreen")
    elif status == AgentStatus.PAUSED:
        return ("PAUSED", "fg:ansiyellow")
    elif status == AgentStatus.PAUSE_REQUESTED:
        return ("PAUSING...", "fg:ansicyan")
    return (str(status), "")


def _render_menu_panel(
    agents: List,
    page: int,
    selected_idx: int,
    selected_agent_ids: set,
) -> List:
    """Render the left menu panel with agent list and checkboxes.

    Args:
        agents: List of AgentEntry objects
        page: Current page number (0-indexed)
        selected_idx: Currently highlighted index (global)
        selected_agent_ids: Set of agent IDs that are checked

    Returns:
        List of (style, text) tuples for FormattedTextControl
    """
    lines = []
    total_pages = (len(agents) + PAGE_SIZE - 1) // PAGE_SIZE if agents else 1
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, len(agents))

    lines.append(("bold", "Agents"))
    lines.append(("fg:ansibrightblack", f" (Page {page + 1}/{total_pages})"))
    lines.append(("", "\n\n"))

    if not agents:
        lines.append(("fg:yellow", "  No agents registered."))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  Agents must register with"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  PauseManager to appear here."))
        lines.append(("", "\n\n"))
    else:
        # Show agents for current page
        for i in range(start_idx, end_idx):
            agent = agents[i]
            is_highlighted = i == selected_idx
            is_checked = agent.agent_id in selected_agent_ids

            # Sanitize name for display
            safe_name = _sanitize_display_text(agent.name)

            # Checkbox
            checkbox = "[x]" if is_checked else "[ ]"

            # Build the line
            if is_highlighted:
                lines.append(("fg:ansigreen", f"▶ {checkbox} "))
                lines.append(("fg:ansigreen bold", safe_name))
            else:
                lines.append(("", f"  {checkbox} "))
                lines.append(("", safe_name))

            # Status badge
            status_text, status_style = _get_status_display(agent.status)
            lines.append((" ", " "))
            lines.append((status_style, f"[{status_text}]"))

            lines.append(("", "\n"))

    # Navigation hints
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  ↑↓ "))
    lines.append(("", "Navigate\n"))
    lines.append(("fg:ansibrightblack", "  ←→ "))
    lines.append(("", "Page\n"))
    lines.append(("fg:ansicyan", "  Space "))
    lines.append(("", "Toggle select\n"))
    lines.append(("fg:ansigreen", "  A "))
    lines.append(("", "Select all\n"))
    lines.append(("fg:ansiyellow", "  N "))
    lines.append(("", "Select none\n"))
    lines.append(("fg:ansiblue", "  S "))
    lines.append(("", "Steer selected\n"))
    lines.append(("fg:ansigreen", "  R "))
    lines.append(("", "Resume selected\n"))
    lines.append(("fg:ansired", "  Ctrl+C "))
    lines.append(("", "Cancel"))

    return lines


def _render_preview_panel(
    agent,
    is_selected: bool,
    selected_count: int,
    total_count: int,
) -> List:
    """Render the right preview panel with agent details.

    Args:
        agent: AgentEntry object or None
        is_selected: Whether this agent is in the selected set
        selected_count: Total number of selected agents
        total_count: Total number of agents

    Returns:
        List of (style, text) tuples for FormattedTextControl
    """
    lines = []

    lines.append(("dim cyan", " AGENT DETAILS"))
    lines.append(("", "\n\n"))

    # Selection summary
    lines.append(("bold", "Selection: "))
    if selected_count == 0:
        lines.append(("fg:ansibrightblack", "None selected"))
    elif selected_count == total_count:
        lines.append(("fg:ansigreen", f"All {total_count} selected"))
    else:
        lines.append(("fg:ansicyan", f"{selected_count} of {total_count} selected"))
    lines.append(("", "\n\n"))

    if not agent:
        lines.append(("fg:yellow", "  No agent highlighted."))
        lines.append(("", "\n"))
        return lines

    safe_name = _sanitize_display_text(agent.name)

    # Agent ID
    lines.append(("bold", "Agent ID: "))
    lines.append(("", agent.agent_id[:32]))
    if len(agent.agent_id) > 32:
        lines.append(("fg:ansibrightblack", "..."))
    lines.append(("", "\n\n"))

    # Display name
    lines.append(("bold", "Name: "))
    lines.append(("fg:ansicyan", safe_name))
    lines.append(("", "\n\n"))

    # Status
    lines.append(("bold", "Status: "))
    status_text, status_style = _get_status_display(agent.status)
    lines.append((status_style, status_text))
    lines.append(("", "\n\n"))

    # Selection status
    lines.append(("bold", "Selected: "))
    if is_selected:
        lines.append(("fg:ansigreen bold", "✓ Yes"))
    else:
        lines.append(("fg:ansibrightblack", "No"))
    lines.append(("", "\n\n"))

    # Registration time
    lines.append(("bold", "Registered: "))
    import datetime

    reg_time = datetime.datetime.fromtimestamp(agent.registered_at)
    lines.append(("fg:ansibrightblack", reg_time.strftime("%H:%M:%S")))
    lines.append(("", "\n\n"))

    # Steering queue info
    lines.append(("bold", "Pending Steers: "))
    try:
        queue_size = agent.steering_queue.qsize()
        if queue_size > 0:
            lines.append(("fg:ansiyellow", str(queue_size)))
        else:
            lines.append(("fg:ansibrightblack", "0"))
    except Exception:
        lines.append(("fg:ansibrightblack", "unknown"))
    lines.append(("", "\n"))

    return lines


async def _prompt_for_steering_text(agent_names: List[str]) -> Optional[str]:
    """Prompt user for steering text to send to selected agents.

    Args:
        agent_names: List of agent names that will receive the steering

    Returns:
        The steering text, or None if cancelled
    """
    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML

    if len(agent_names) == 1:
        prompt_text = f"Steering prompt for '{agent_names[0]}': "
    else:
        prompt_text = f"Steering prompt for {len(agent_names)} agents: "

    session = PromptSession()

    try:
        result = await session.prompt_async(
            HTML(f"<ansigreen>{prompt_text}</ansigreen>"),
            multiline=False,
        )
        return result.strip() if result else None
    except (KeyboardInterrupt, EOFError):
        return None


async def _confirm_action(action: str, count: int) -> bool:
    """Confirm an action with the user.

    Args:
        action: The action being confirmed (e.g., 'resume')
        count: Number of agents affected

    Returns:
        True if confirmed, False if cancelled
    """
    try:
        choices = ["Yes", "No"]
        prompt = f"{action} {count} agent(s)?"
        choice = await arrow_select_async(prompt, choices)
        return choice == "Yes"
    except KeyboardInterrupt:
        return False


async def interactive_pause_menu() -> SteeringResult:
    """Show interactive terminal UI for pause+steer functionality.

    Displays all registered agents with their status, allows multi-selection,
    and provides options to steer (send prompts to) or resume selected agents.

    Returns:
        SteeringResult containing queued prompts and resumed agents
    """
    pm = get_pause_manager()

    # Check DBOS guard
    if pm.is_dbos_enabled():
        emit_warning(
            "Pause+steer is disabled when DBOS is enabled. "
            "DBOS durability requires deterministic execution."
        )
        return SteeringResult(queued_prompts=[], resumed_agents=[], cancelled=True)

    # Get agents
    agents = pm.list_agents()

    if not agents:
        emit_info("No agents registered with PauseManager.")
        return SteeringResult(queued_prompts=[], resumed_agents=[], cancelled=False)

    # State
    selected_idx = [0]  # Currently highlighted
    current_page = [0]
    selected_agent_ids = set()  # Multi-select set
    result = [SteeringResult(queued_prompts=[], resumed_agents=[], cancelled=False)]
    pending_action = [None]  # 'steer', 'resume', or None

    total_pages = [max(1, (len(agents) + PAGE_SIZE - 1) // PAGE_SIZE)]

    def get_current_agent():
        if 0 <= selected_idx[0] < len(agents):
            return agents[selected_idx[0]]
        return None

    def refresh_agents():
        nonlocal agents
        agents = pm.list_agents()
        total_pages[0] = max(1, (len(agents) + PAGE_SIZE - 1) // PAGE_SIZE)
        if agents:
            selected_idx[0] = min(selected_idx[0], len(agents) - 1)
            current_page[0] = min(current_page[0], total_pages[0] - 1)
        else:
            selected_idx[0] = 0
            current_page[0] = 0
        # Remove any selected agents that no longer exist
        current_ids = {a.agent_id for a in agents}
        selected_agent_ids.intersection_update(current_ids)

    # Build UI
    menu_control = FormattedTextControl(text="")
    preview_control = FormattedTextControl(text="")

    def update_display():
        """Update both panels."""
        current_agent = get_current_agent()
        is_selected = (
            current_agent.agent_id in selected_agent_ids if current_agent else False
        )
        menu_control.text = _render_menu_panel(
            agents, current_page[0], selected_idx[0], selected_agent_ids
        )
        preview_control.text = _render_preview_panel(
            current_agent, is_selected, len(selected_agent_ids), len(agents)
        )

    menu_window = Window(
        content=menu_control, wrap_lines=False, width=Dimension(weight=40)
    )
    preview_window = Window(
        content=preview_control, wrap_lines=False, width=Dimension(weight=60)
    )

    menu_frame = Frame(menu_window, width=Dimension(weight=40), title="Pause Manager")
    preview_frame = Frame(preview_window, width=Dimension(weight=60), title="Details")

    root_container = VSplit([menu_frame, preview_frame])

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            current_page[0] = selected_idx[0] // PAGE_SIZE
            update_display()

    @kb.add("down")
    def _(event):
        if selected_idx[0] < len(agents) - 1:
            selected_idx[0] += 1
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

    @kb.add("space")
    def _(event):
        agent = get_current_agent()
        if agent:
            if agent.agent_id in selected_agent_ids:
                selected_agent_ids.discard(agent.agent_id)
            else:
                selected_agent_ids.add(agent.agent_id)
            update_display()

    @kb.add("a")  # Select all
    def _(event):
        for agent in agents:
            selected_agent_ids.add(agent.agent_id)
        update_display()

    @kb.add("n")  # Select none
    def _(event):
        selected_agent_ids.clear()
        update_display()

    @kb.add("s")  # Steer selected
    def _(event):
        if selected_agent_ids:
            pending_action[0] = "steer"
            event.app.exit()

    @kb.add("r")  # Resume selected
    def _(event):
        if selected_agent_ids:
            pending_action[0] = "resume"
            event.app.exit()

    @kb.add("enter")  # Same as steer
    def _(event):
        if selected_agent_ids:
            pending_action[0] = "steer"
            event.app.exit()

    @kb.add("c-c")
    def _(event):
        result[0] = SteeringResult(queued_prompts=[], resumed_agents=[], cancelled=True)
        event.app.exit()

    @kb.add("q")
    def _(event):
        # Exit without cancelling (keeping any accumulated results)
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
        while True:
            pending_action[0] = None
            refresh_agents()
            update_display()

            # Clear the current buffer
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            # Run application
            await app.run_async()

            # Check if cancelled
            if result[0].cancelled:
                break

            if pending_action[0] == "steer":
                # Get the selected agent names for prompt
                selected_agents = [
                    a for a in agents if a.agent_id in selected_agent_ids
                ]
                agent_names = [a.name for a in selected_agents]

                # Exit alternate buffer temporarily for text input
                sys.stdout.write("\033[?1049l")
                sys.stdout.flush()

                steering_text = await _prompt_for_steering_text(agent_names)

                # Re-enter alternate buffer
                sys.stdout.write("\033[?1049h")
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()

                if steering_text:
                    # Queue the steering input for each selected agent
                    for agent in selected_agents:
                        pm.send_steering_input(agent.agent_id, steering_text)
                        result[0].queued_prompts.append((agent.agent_id, steering_text))

                    emit_success(
                        f"Queued steering prompt for {len(selected_agents)} agent(s)"
                    )
                    # Clear selection after steering
                    selected_agent_ids.clear()
                continue

            if pending_action[0] == "resume":
                # Resume selected agents
                selected_agents = [
                    a for a in agents if a.agent_id in selected_agent_ids
                ]

                # Exit alternate buffer temporarily for confirmation
                sys.stdout.write("\033[?1049l")
                sys.stdout.flush()

                confirmed = await _confirm_action("Resume", len(selected_agents))

                # Re-enter alternate buffer
                sys.stdout.write("\033[?1049h")
                sys.stdout.write("\033[2J\033[H")
                sys.stdout.flush()

                if confirmed:
                    for agent in selected_agents:
                        pm.request_resume(agent.agent_id)
                        result[0].resumed_agents.append(agent.agent_id)

                    emit_success(f"Resumed {len(selected_agents)} agent(s)")
                    # Clear selection after resuming
                    selected_agent_ids.clear()
                continue

            # No pending action and not cancelled = 'q' was pressed
            break

    finally:
        # Exit alternate screen buffer
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        set_awaiting_user_input(False)

    # Summary message
    if result[0].cancelled:
        emit_info("Pause menu cancelled")
    else:
        queued = len(result[0].queued_prompts)
        resumed = len(result[0].resumed_agents)
        if queued > 0 or resumed > 0:
            parts = []
            if queued > 0:
                parts.append(f"{queued} steering prompt(s) queued")
            if resumed > 0:
                parts.append(f"{resumed} agent(s) resumed")
            emit_info(f"✓ Exited pause menu: {', '.join(parts)}")
        else:
            emit_info("✓ Exited pause menu")

    return result[0]


# Convenience function for simpler use cases
async def quick_steer(agent_id: str, prompt: str) -> bool:
    """Quickly send a steering prompt to a specific agent.

    Args:
        agent_id: The agent to steer
        prompt: The steering prompt text

    Returns:
        True if steering was queued, False otherwise
    """
    pm = get_pause_manager()

    if pm.is_dbos_enabled():
        emit_warning("Cannot steer: DBOS is enabled")
        return False

    return pm.send_steering_input(agent_id, prompt)


async def quick_resume(agent_id: Optional[str] = None) -> bool:
    """Quickly resume an agent or all agents.

    Args:
        agent_id: Specific agent to resume, or None for all agents

    Returns:
        True if resume was requested
    """
    pm = get_pause_manager()
    return pm.request_resume(agent_id)
