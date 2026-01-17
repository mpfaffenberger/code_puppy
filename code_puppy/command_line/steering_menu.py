"""Interactive steering TUI for Pause & Steer functionality.

Provides a split-panel interface for viewing active agents and sending
steering messages to them during a global pause. This enables real-time
control over agent execution.

Usage:
    >>> await run_steering_menu()  # Pauses all agents, shows TUI
    # User navigates agents, sends steering messages
    # On exit (Esc), resumes all agents
"""

import sys
import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    Dimension,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.steering import get_steering_manager
from code_puppy.tools.command_runner import set_awaiting_user_input

# Conditional import for SubAgentConsoleManager
try:
    from code_puppy.messaging.subagent_console import (
        MAIN_AGENT_SESSION_ID,
        SubAgentConsoleManager,
    )

    _SUBAGENT_CONSOLE_AVAILABLE = True
except ImportError:
    _SUBAGENT_CONSOLE_AVAILABLE = False
    SubAgentConsoleManager = None  # type: ignore[misc, assignment]
    MAIN_AGENT_SESSION_ID = "main-agent"


# =============================================================================
# Helper Functions
# =============================================================================


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
            "Lu", "Ll", "Lt", "Lm", "Lo",  # Letters
            "Nd", "Nl", "No",  # Numbers
            "Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po",  # Punctuation
            "Zs",  # Space
            "Sm", "Sc", "Sk",  # Safe symbols
        )
        if cat in safe_categories:
            result.append(char)

    cleaned = " ".join("".join(result).split())
    return cleaned


def _get_agent_entries() -> List[Dict[str, Any]]:
    """Get all active agents from both SteeringManager and SubAgentConsoleManager.

    Returns:
        List of agent info dictionaries with session_id, agent_name, status, etc.
    """
    entries = []

    # Get agents from SteeringManager
    manager = get_steering_manager()
    steering_agents = manager.get_active_agents()

    # Get agents from SubAgentConsoleManager for richer status info
    subagent_states = {}
    if _SUBAGENT_CONSOLE_AVAILABLE and SubAgentConsoleManager is not None:
        try:
            console_manager = SubAgentConsoleManager.get_instance()
            for agent_state in console_manager.get_all_agents():
                subagent_states[agent_state.session_id] = {
                    "status": agent_state.status,
                    "tool_call_count": agent_state.tool_call_count,
                    "token_count": agent_state.token_count,
                    "current_tool": agent_state.current_tool,
                    "elapsed_seconds": agent_state.elapsed_seconds(),
                }
        except Exception:
            pass  # Gracefully handle failures

    # Merge information from both sources
    seen_sessions = set()

    for agent in steering_agents:
        session_id = agent["session_id"]
        seen_sessions.add(session_id)

        # Merge with SubAgentConsoleManager data if available
        extra = subagent_states.get(session_id, {})

        entries.append({
            "session_id": session_id,
            "agent_name": agent.get("agent_name", "Unknown"),
            "model_name": agent.get("model_name", "Unknown"),
            "status": extra.get("status", "registered"),
            "tool_call_count": extra.get("tool_call_count", 0),
            "token_count": extra.get("token_count", 0),
            "current_tool": extra.get("current_tool"),
            "elapsed_seconds": extra.get("elapsed_seconds", 0),
            "is_main": session_id == MAIN_AGENT_SESSION_ID,
        })

    # Add any agents only in SubAgentConsoleManager
    for session_id, state_data in subagent_states.items():
        if session_id not in seen_sessions:
            if _SUBAGENT_CONSOLE_AVAILABLE and SubAgentConsoleManager is not None:
                try:
                    console_manager = SubAgentConsoleManager.get_instance()
                    agent_state = console_manager.get_agent_state(session_id)
                    if agent_state:
                        entries.append({
                            "session_id": session_id,
                            "agent_name": agent_state.agent_name,
                            "model_name": agent_state.model_name,
                            "status": agent_state.status,
                            "tool_call_count": agent_state.tool_call_count,
                            "token_count": agent_state.token_count,
                            "current_tool": agent_state.current_tool,
                            "elapsed_seconds": agent_state.elapsed_seconds(),
                            "is_main": session_id == MAIN_AGENT_SESSION_ID,
                        })
                except Exception:
                    pass

    # Sort: main agent first, then by agent name
    entries.sort(key=lambda x: (not x.get("is_main", False), x.get("agent_name", "").lower()))

    return entries


def _get_pending_count(session_id: str) -> int:
    """Get the number of pending steering messages for an agent.

    Args:
        session_id: The agent's session ID.

    Returns:
        Number of pending messages (without consuming them).
    """
    manager = get_steering_manager()
    # Note: We can't peek without consuming, so we return 0
    # The SteeringManager doesn't have a peek method - messages are consumed on get
    # This is a limitation we'll document
    with manager._state_lock:
        queue = manager._message_queues.get(session_id, [])
        return len(queue)


# =============================================================================
# Panel Rendering Functions
# =============================================================================


def _render_agent_list_panel(
    entries: List[Dict[str, Any]],
    selected_idx: int,
) -> List[Tuple[str, str]]:
    """Render the left panel with list of agents.

    Args:
        entries: List of agent info dictionaries.
        selected_idx: Currently selected agent index.

    Returns:
        List of (style, text) tuples for FormattedTextControl.
    """
    lines: List[Tuple[str, str]] = []

    # Header with PAUSED indicator
    lines.append(("bold fg:yellow", "⏸️  PAUSED - Steering Mode"))
    lines.append(("", "\n"))
    lines.append(("fg:ansiyellow", "─" * 32))
    lines.append(("", "\n\n"))

    if not entries:
        lines.append(("fg:ansiyellow", "  No active agents found.\n"))
        lines.append(("fg:ansibrightblack", "\n  Agents will appear here when\n"))
        lines.append(("fg:ansibrightblack", "  they register with the\n"))
        lines.append(("fg:ansibrightblack", "  SteeringManager.\n"))
    else:
        for i, agent in enumerate(entries):
            is_selected = i == selected_idx
            is_main = agent.get("is_main", False)

            # Agent name (sanitized)
            agent_name = _sanitize_display_text(agent.get("agent_name", "Unknown"))
            status = agent.get("status", "unknown")

            # Build line with selection indicator
            if is_selected:
                lines.append(("fg:ansigreen bold", "▶ "))
            else:
                lines.append(("", "  "))

            # Main agent indicator
            if is_main:
                lines.append(("fg:ansicyan bold", "[MAIN] "))

            # Agent name
            if is_selected:
                lines.append(("fg:ansigreen bold", agent_name))
            else:
                lines.append(("", agent_name))

            # Current selection marker
            if is_selected:
                lines.append(("fg:ansigreen", " ← current"))

            lines.append(("", "\n"))

            # Status line (indented)
            status_color = _get_status_color(status)
            lines.append(("fg:ansibrightblack", "    "))
            lines.append((f"fg:{status_color}", f"[{status}]"))

            # Pending messages indicator
            pending = _get_pending_count(agent.get("session_id", ""))
            if pending > 0:
                lines.append(("fg:ansiyellow bold", f" ({pending} pending)"))

            lines.append(("", "\n"))

    # Navigation hints
    lines.append(("", "\n"))
    lines.append(("fg:ansiyellow", "─" * 32))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  ↑↓  "))
    lines.append(("", "Navigate\n"))
    lines.append(("fg:ansigreen", "  Enter "))
    lines.append(("", "Send steering\n"))
    lines.append(("fg:ansired", "  Esc   "))
    lines.append(("", "Resume & Exit\n"))

    return lines


def _get_status_color(status: str) -> str:
    """Get the display color for a status.

    Args:
        status: The status string.

    Returns:
        Color name for the status.
    """
    status_colors = {
        "starting": "ansicyan",
        "running": "ansigreen",
        "thinking": "ansimagenta",
        "tool_calling": "ansiyellow",
        "completed": "ansigreen",
        "error": "ansired",
        "paused": "ansiyellow",
        "registered": "ansiblue",
    }
    return status_colors.get(status, "ansiwhite")


def _render_agent_details_panel(
    agent: Optional[Dict[str, Any]],
) -> List[Tuple[str, str]]:
    """Render the right panel with agent details.

    Args:
        agent: The selected agent's info dict, or None.

    Returns:
        List of (style, text) tuples for FormattedTextControl.
    """
    lines: List[Tuple[str, str]] = []

    # Header
    lines.append(("bold fg:ansicyan", "📋 AGENT DETAILS"))
    lines.append(("", "\n"))
    lines.append(("fg:ansiyellow", "─" * 44))
    lines.append(("", "\n\n"))

    if not agent:
        lines.append(("fg:ansiyellow", "  No agent selected.\n\n"))
        lines.append(("fg:ansibrightblack", "  Select an agent from the left panel\n"))
        lines.append(("fg:ansibrightblack", "  to view details and send steering\n"))
        lines.append(("fg:ansibrightblack", "  messages.\n"))
        return lines

    # Agent name
    agent_name = _sanitize_display_text(agent.get("agent_name", "Unknown"))
    is_main = agent.get("is_main", False)

    lines.append(("bold", "Agent: "))
    if is_main:
        lines.append(("fg:ansicyan bold", f"{agent_name} [MAIN]"))
    else:
        lines.append(("fg:ansicyan", agent_name))
    lines.append(("", "\n\n"))

    # Model
    model_name = agent.get("model_name", "Unknown")
    lines.append(("bold", "Model: "))
    lines.append(("", model_name))
    lines.append(("", "\n\n"))

    # Session ID (truncated)
    session_id = agent.get("session_id", "Unknown")
    session_display = session_id
    if len(session_display) > 30:
        session_display = session_display[:27] + "..."
    lines.append(("bold", "Session: "))
    lines.append(("fg:ansibrightblack", session_display))
    lines.append(("", "\n\n"))

    # Status
    status = agent.get("status", "unknown")
    status_color = _get_status_color(status)
    lines.append(("bold", "Status: "))
    lines.append((f"fg:{status_color} bold", status.upper()))
    lines.append(("", "\n\n"))

    # Metrics
    lines.append(("fg:ansiyellow", "─" * 44))
    lines.append(("", "\n"))
    lines.append(("bold fg:ansibrightblack", "METRICS\n"))

    # Tool calls
    tool_count = agent.get("tool_call_count", 0)
    lines.append(("bold", "  Tool Calls: "))
    lines.append(("fg:ansiyellow", str(tool_count)))
    current_tool = agent.get("current_tool")
    if current_tool:
        lines.append(("fg:ansibrightblack", f" (calling: {current_tool})"))
    lines.append(("", "\n"))

    # Tokens
    token_count = agent.get("token_count", 0)
    lines.append(("bold", "  Tokens: "))
    lines.append(("fg:ansiblue", f"{token_count:,}"))
    lines.append(("", "\n"))

    # Elapsed time
    elapsed = agent.get("elapsed_seconds", 0)
    if elapsed < 60:
        elapsed_str = f"{elapsed:.1f}s"
    else:
        minutes = int(elapsed // 60)
        seconds = elapsed % 60
        elapsed_str = f"{minutes}m {seconds:.1f}s"
    lines.append(("bold", "  Elapsed: "))
    lines.append(("fg:ansimagenta", elapsed_str))
    lines.append(("", "\n\n"))

    # Pending steering messages
    pending = _get_pending_count(agent.get("session_id", ""))
    lines.append(("fg:ansiyellow", "─" * 44))
    lines.append(("", "\n"))
    lines.append(("bold fg:ansibrightblack", "STEERING\n"))
    lines.append(("bold", "  Pending Messages: "))
    if pending > 0:
        lines.append(("fg:ansiyellow bold", str(pending)))
    else:
        lines.append(("fg:ansibrightblack", "0"))
    lines.append(("", "\n\n"))

    # Instructions
    lines.append(("fg:ansibrightblack", "  Type a message below and press Enter\n"))
    lines.append(("fg:ansibrightblack", "  to send steering to this agent.\n"))

    return lines


def _render_input_prompt() -> List[Tuple[str, str]]:
    """Render the input area prompt text.

    Returns:
        List of (style, text) tuples.
    """
    return [
        ("fg:ansiyellow bold", "STEERING MESSAGE > "),
    ]


def _render_status_bar(message: str = "") -> List[Tuple[str, str]]:
    """Render a status bar message.

    Args:
        message: The status message to display.

    Returns:
        List of (style, text) tuples.
    """
    if message:
        return [("fg:ansigreen", f"  ✓ {message}")]
    return [("fg:ansibrightblack", "  Ready to send steering messages...")]


# =============================================================================
# Main TUI Function
# =============================================================================


async def run_steering_menu() -> None:
    """Show the steering TUI and pause all agents.

    On launch:
        1. Call set_awaiting_user_input(True)
        2. Pause all agents via SteeringManager
        3. Show TUI

    On exit:
        1. Resume all agents via SteeringManager
        2. Call set_awaiting_user_input(False)
    """
    # Get steering manager
    steering_manager = get_steering_manager()

    # State for the TUI
    selected_idx = [0]
    entries = [_get_agent_entries()]
    status_message = [""]
    last_sent_to = [""]  # Track last agent we sent to for confirmation

    # Create input buffer for steering messages
    input_buffer = Buffer()

    def get_current_agent() -> Optional[Dict[str, Any]]:
        """Get the currently selected agent."""
        current_entries = entries[0]
        if 0 <= selected_idx[0] < len(current_entries):
            return current_entries[selected_idx[0]]
        return None

    def refresh_entries() -> None:
        """Refresh the agent entries list."""
        entries[0] = _get_agent_entries()
        # Clamp selected index
        if entries[0]:
            selected_idx[0] = min(selected_idx[0], len(entries[0]) - 1)
        else:
            selected_idx[0] = 0

    # Build UI controls
    agent_list_control = FormattedTextControl(text="")
    details_control = FormattedTextControl(text="")
    status_control = FormattedTextControl(text="")
    input_prompt_control = FormattedTextControl(text=_render_input_prompt)

    def update_display() -> None:
        """Update all display panels."""
        refresh_entries()
        current_entries = entries[0]
        agent_list_control.text = _render_agent_list_panel(current_entries, selected_idx[0])
        details_control.text = _render_agent_details_panel(get_current_agent())
        status_control.text = _render_status_bar(status_message[0])

    # Create windows
    agent_list_window = Window(
        content=agent_list_control,
        wrap_lines=False,
        width=Dimension(weight=35),
    )
    details_window = Window(
        content=details_control,
        wrap_lines=False,
        width=Dimension(weight=65),
    )

    # Input area
    input_window = Window(
        content=BufferControl(buffer=input_buffer),
        height=1,
        wrap_lines=False,
    )

    input_prompt_window = Window(
        content=input_prompt_control,
        height=1,
        width=Dimension.exact(20),
        wrap_lines=False,
    )

    status_window = Window(
        content=status_control,
        height=1,
        wrap_lines=False,
    )

    # Create frames
    agent_list_frame = Frame(
        agent_list_window,
        width=Dimension(weight=35),
        title="Active Agents",
        style="fg:ansiyellow",
    )
    details_frame = Frame(
        details_window,
        width=Dimension(weight=65),
        title="Details",
        style="fg:ansicyan",
    )

    # Input row
    input_row = HSplit([
        Window(height=1, char="─", style="fg:ansiyellow"),
        HSplit([
            VSplit([input_prompt_window, input_window]),
            status_window,
        ]),
    ])

    # Main layout: VSplit for left/right, HSplit to add input at bottom
    root_container = HSplit([
        VSplit([agent_list_frame, details_frame]),
        input_row,
    ])

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    def _move_up(event) -> None:
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            status_message[0] = ""
            update_display()

    @kb.add("down")
    def _move_down(event) -> None:
        current_entries = entries[0]
        if selected_idx[0] < len(current_entries) - 1:
            selected_idx[0] += 1
            status_message[0] = ""
            update_display()

    @kb.add("enter")
    def _send_steering(event) -> None:
        """Send steering message to selected agent."""
        agent = get_current_agent()
        message = input_buffer.text.strip()

        if not agent:
            status_message[0] = "No agent selected!"
            update_display()
            return

        if not message:
            status_message[0] = "Please type a message first!"
            update_display()
            return

        session_id = agent.get("session_id", "")
        agent_name = agent.get("agent_name", "Unknown")

        # Queue the steering message
        steering_manager.queue_message(session_id, message)

        # Update status and clear input
        status_message[0] = f"Sent to {agent_name}!"
        last_sent_to[0] = agent_name
        input_buffer.reset()

        update_display()

    @kb.add("escape")
    def _exit(event) -> None:
        """Exit and resume all agents."""
        event.app.exit()

    @kb.add("c-c")
    def _cancel(event) -> None:
        """Also allow Ctrl+C to exit."""
        event.app.exit()

    # Create application
    layout = Layout(root_container, focused_element=input_window)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    # === LAUNCH SEQUENCE ===
    set_awaiting_user_input(True)
    steering_manager.pause_all()

    # Enter alternate screen buffer
    sys.stdout.write("\033[?1049h")  # Enter alternate buffer
    sys.stdout.write("\033[2J\033[H")  # Clear and home
    sys.stdout.flush()
    time.sleep(0.05)

    try:
        # Initial display update
        update_display()

        # Clear the buffer
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

        # Run the application
        await app.run_async()

    finally:
        # === EXIT SEQUENCE ===
        # Exit alternate screen buffer
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()

        # Resume all agents
        steering_manager.resume_all()

        # Reset input flag
        set_awaiting_user_input(False)

        # Emit info message
        try:
            from code_puppy.messaging import emit_info
            emit_info("✓ Steering menu closed - agents resumed")
        except ImportError:
            pass  # Gracefully handle if messaging not available


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "run_steering_menu",
]
