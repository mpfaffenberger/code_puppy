"""SubAgentConsoleManager - Aggregated display for parallel sub-agents.

Provides a Rich Live dashboard that shows real-time status of multiple
running sub-agents, each in its own panel with spinner animations,
status badges, and performance metrics.

Usage:
    >>> manager = SubAgentConsoleManager.get_instance()
    >>> manager.register_agent("session-123", "code-puppy", "gpt-4o")
    >>> manager.update_agent("session-123", status="running", tool_call_count=5)
    >>> manager.unregister_agent("session-123")
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from code_puppy.messaging.messages import SubAgentStatusMessage


# =============================================================================
# Status Configuration
# =============================================================================

STATUS_STYLES = {
    "starting": {"color": "cyan", "spinner": "dots", "emoji": "🚀"},
    "running": {"color": "green", "spinner": "dots", "emoji": "🐕"},
    "thinking": {"color": "magenta", "spinner": "dots", "emoji": "🤔"},
    "tool_calling": {"color": "yellow", "spinner": "dots12", "emoji": "🔧"},
    "completed": {"color": "green", "spinner": None, "emoji": "✅"},
    "error": {"color": "red", "spinner": None, "emoji": "❌"},
}

DEFAULT_STYLE = {"color": "white", "spinner": "dots", "emoji": "⏳"}


# =============================================================================
# Agent State Tracking
# =============================================================================


@dataclass
class AgentState:
    """Internal state tracking for a single sub-agent.

    Tracks all metrics needed for rendering the agent's status panel,
    including timing, tool usage, and error information.
    """

    session_id: str
    agent_name: str
    model_name: str
    status: str = "starting"
    tool_call_count: int = 0
    token_count: int = 0
    current_tool: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    error_message: Optional[str] = None

    def elapsed_seconds(self) -> float:
        """Calculate elapsed time since agent started."""
        return time.time() - self.start_time

    def elapsed_formatted(self) -> str:
        """Format elapsed time as human-readable string."""
        elapsed = self.elapsed_seconds()
        if elapsed < 60:
            return f"{elapsed:.1f}s"
        minutes = int(elapsed // 60)
        seconds = elapsed % 60
        return f"{minutes}m {seconds:.1f}s"

    def to_status_message(self) -> SubAgentStatusMessage:
        """Convert to a SubAgentStatusMessage for bus emission."""
        return SubAgentStatusMessage(
            session_id=self.session_id,
            agent_name=self.agent_name,
            model_name=self.model_name,
            status=self.status,  # type: ignore[arg-type]
            tool_call_count=self.tool_call_count,
            token_count=self.token_count,
            current_tool=self.current_tool,
            elapsed_seconds=self.elapsed_seconds(),
            error_message=self.error_message,
        )


# =============================================================================
# SubAgent Console Manager
# =============================================================================


class SubAgentConsoleManager:
    """Manager for displaying multiple parallel sub-agents in Rich Live panels.

    This is a singleton that tracks all running sub-agents and renders them
    in a unified Rich Live display. Each agent gets its own panel with:
    - Agent name and session ID
    - Model being used
    - Status with spinner animation (for active states)
    - Tool call count and current tool
    - Token count
    - Elapsed time

    The display auto-starts when the first agent registers and auto-stops
    when the last agent unregisters.

    Thread-safe: All operations are protected by locks.
    """

    _instance: Optional["SubAgentConsoleManager"] = None
    _lock = threading.Lock()

    def __init__(self, console: Optional[Console] = None):
        """Initialize the manager.

        Args:
            console: Optional Rich Console instance. If not provided,
                    a new one will be created.
        """
        self.console = console or Console()
        self._agents: Dict[str, AgentState] = {}
        self._agents_lock = threading.RLock()  # Reentrant lock for agent operations
        self._live: Optional[Live] = None
        self._update_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @classmethod
    def get_instance(
        cls, console: Optional[Console] = None
    ) -> "SubAgentConsoleManager":
        """Get or create the singleton instance.

        Thread-safe singleton pattern using double-checked locking.

        Args:
            console: Optional Rich Console to use. Only used when creating
                    the initial instance.

        Returns:
            The singleton SubAgentConsoleManager instance.
        """
        if cls._instance is None:
            with cls._lock:
                # Double-check inside lock
                if cls._instance is None:
                    cls._instance = cls(console)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (primarily for testing).

        Stops any running display and clears the singleton.
        """
        with cls._lock:
            if cls._instance is not None:
                cls._instance._stop_display()
                cls._instance = None

    # =========================================================================
    # Agent Registration
    # =========================================================================

    def register_agent(self, session_id: str, agent_name: str, model_name: str) -> None:
        """Register a new sub-agent and start display if needed.

        Args:
            session_id: Unique identifier for this agent session.
            agent_name: Name of the agent (e.g., 'code-puppy', 'qa-kitten').
            model_name: Name of the model being used (e.g., 'gpt-4o').
        """
        with self._agents_lock:
            # Create new agent state
            self._agents[session_id] = AgentState(
                session_id=session_id,
                agent_name=agent_name,
                model_name=model_name,
            )

            # Start display if this is the first agent
            if len(self._agents) == 1:
                self._start_display()

    def update_agent(self, session_id: str, **kwargs) -> None:
        """Update status of an existing agent.

        Args:
            session_id: The session ID of the agent to update.
            **kwargs: Fields to update. Valid fields:
                - status: Current status string
                - tool_call_count: Number of tools called
                - token_count: Tokens in context
                - current_tool: Name of tool being called (or None)
                - error_message: Error message if status is 'error'
        """
        with self._agents_lock:
            if session_id not in self._agents:
                return  # Silently ignore updates for unknown agents

            agent = self._agents[session_id]

            # Update only provided fields
            if "status" in kwargs:
                agent.status = kwargs["status"]
            if "tool_call_count" in kwargs:
                agent.tool_call_count = kwargs["tool_call_count"]
            if "token_count" in kwargs:
                agent.token_count = kwargs["token_count"]
            if "current_tool" in kwargs:
                agent.current_tool = kwargs["current_tool"]
            if "error_message" in kwargs:
                agent.error_message = kwargs["error_message"]

    def unregister_agent(
        self, session_id: str, final_status: str = "completed"
    ) -> None:
        """Remove an agent from tracking.

        Args:
            session_id: The session ID of the agent to remove.
            final_status: Final status to set before removal (for display).
                         Defaults to 'completed'.
        """
        with self._agents_lock:
            if session_id in self._agents:
                # Set final status
                self._agents[session_id].status = final_status
                # Remove from tracking
                del self._agents[session_id]

                # Stop display if no agents remain
                if not self._agents:
                    self._stop_display()

    def get_agent_state(self, session_id: str) -> Optional[AgentState]:
        """Get the current state of an agent.

        Args:
            session_id: The session ID to look up.

        Returns:
            The AgentState if found, None otherwise.
        """
        with self._agents_lock:
            return self._agents.get(session_id)

    def get_all_agents(self) -> List[AgentState]:
        """Get a list of all currently tracked agents.

        Returns:
            List of AgentState objects (copies to prevent mutation).
        """
        with self._agents_lock:
            return list(self._agents.values())

    # =========================================================================
    # Display Management
    # =========================================================================

    def _start_display(self) -> None:
        """Start the Rich Live display.

        Creates the Live context and starts a background thread to
        continuously refresh the display.
        """
        if self._live is not None:
            return  # Already running

        self._stop_event.clear()

        # Create Live display
        self._live = Live(
            self._render_display(),
            console=self.console,
            refresh_per_second=10,
            transient=True,  # Clear when stopped
        )
        self._live.start()

        # Start background update thread
        self._update_thread = threading.Thread(
            target=self._update_loop, daemon=True, name="SubAgentDisplayUpdater"
        )
        self._update_thread.start()

    def _stop_display(self) -> None:
        """Stop the Rich Live display when no agents remain."""
        # Signal stop
        self._stop_event.set()

        # Stop update thread
        if self._update_thread is not None:
            self._update_thread.join(timeout=1.0)
            self._update_thread = None

        # Stop Live display
        if self._live is not None:
            try:
                self._live.stop()
            except Exception:
                pass  # Ignore errors during cleanup
            self._live = None

    def _update_loop(self) -> None:
        """Background thread that refreshes the display."""
        while not self._stop_event.is_set():
            try:
                if self._live is not None:
                    self._live.update(self._render_display())
            except Exception:
                pass  # Ignore rendering errors, keep trying

            # Sleep between updates (10 FPS)
            time.sleep(0.1)

    # =========================================================================
    # Rendering
    # =========================================================================

    def _render_display(self) -> Group:
        """Render all agent panels as a Rich Group.

        Returns:
            A Group containing all agent panels stacked vertically.
        """
        with self._agents_lock:
            if not self._agents:
                return Group(Text("No active sub-agents", style="dim"))

            panels = [
                self._render_agent_panel(agent) for agent in self._agents.values()
            ]
            return Group(*panels)

    def _render_agent_panel(self, agent: AgentState) -> Panel:
        """Render a single agent's status panel.

        Args:
            agent: The AgentState to render.

        Returns:
            A Rich Panel containing the agent's status information.
        """
        style_config = STATUS_STYLES.get(agent.status, DEFAULT_STYLE)
        color = style_config["color"]
        spinner_name = style_config["spinner"]
        emoji = style_config["emoji"]

        # Build the content table
        table = Table.grid(padding=(0, 2))
        table.add_column("label", style="dim")
        table.add_column("value")

        # Status row with spinner (if active)
        status_text = Text()
        status_text.append(f"{emoji} ", style=color)
        if spinner_name:
            # For active statuses, we add the status text
            # The spinner is visual only in Rich Live
            status_text.append(agent.status.upper(), style=f"bold {color}")
        else:
            status_text.append(agent.status.upper(), style=f"bold {color}")

        table.add_row("Status:", status_text)

        # Model
        table.add_row("Model:", Text(agent.model_name, style="cyan"))

        # Session ID (truncated for display)
        session_display = agent.session_id
        if len(session_display) > 24:
            session_display = session_display[:21] + "..."
        table.add_row("Session:", Text(session_display, style="dim"))

        # Tool calls
        tool_text = Text()
        tool_text.append(str(agent.tool_call_count), style="bold yellow")
        if agent.current_tool:
            tool_text.append(" (calling: ", style="dim")
            tool_text.append(agent.current_tool, style="yellow")
            tool_text.append(")", style="dim")
        table.add_row("Tools:", tool_text)

        # Token count
        token_display = f"{agent.token_count:,}" if agent.token_count else "0"
        table.add_row("Tokens:", Text(token_display, style="blue"))

        # Elapsed time
        table.add_row("Elapsed:", Text(agent.elapsed_formatted(), style="magenta"))

        # Error message (if any)
        if agent.error_message:
            error_text = Text(agent.error_message, style="red")
            table.add_row("Error:", error_text)

        # Build panel title with spinner for active states
        title = Text()
        title.append("🐕 ", style="bold")
        title.append(agent.agent_name, style=f"bold {color}")

        # Create panel
        return Panel(
            table,
            title=title,
            border_style=color,
            padding=(0, 1),
        )

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    def __enter__(self) -> "SubAgentConsoleManager":
        """Support use as context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up on context exit."""
        self._stop_display()


# =============================================================================
# Convenience Functions
# =============================================================================


def get_subagent_console_manager(
    console: Optional[Console] = None,
) -> SubAgentConsoleManager:
    """Get the singleton SubAgentConsoleManager instance.

    Convenience function for accessing the manager.

    Args:
        console: Optional Rich Console (only used on first call).

    Returns:
        The singleton SubAgentConsoleManager.
    """
    return SubAgentConsoleManager.get_instance(console)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "AgentState",
    "SubAgentConsoleManager",
    "get_subagent_console_manager",
    "STATUS_STYLES",
    "DEFAULT_STYLE",
]
