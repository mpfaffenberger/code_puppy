"""
Main TUI application class.
"""

from datetime import datetime, timezone
from typing import Dict, List

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import Resize
from textual.reactive import reactive
from textual.widgets import Footer, Label, ListItem, ListView

from code_puppy.agent import (
    get_code_generation_agent,
    get_custom_usage_limits,
    session_memory,
)
from code_puppy.command_line.meta_command_handler import handle_meta_command
from code_puppy.config import get_model_name, get_puppy_name

# Import our message queue system
from code_puppy.messaging import TUIRenderer, get_global_queue

from ..message_history_processor import message_history_processor
from .components import ChatView, CustomTextArea, InputArea, Sidebar, StatusBar

# Import shared message classes
from .messages import HistoryEntrySelected
from .models import ChatMessage, MessageType
from .screens import HelpScreen, SettingsScreen, ToolsScreen


class CodePuppyTUI(App):
    """Main Code Puppy TUI application."""

    TITLE = "Code Puppy - AI Code Assistant"
    SUB_TITLE = "Walmart Global Tech Edition"

    CSS = """
    Screen {
        layout: horizontal;
    }

    #main-area {
        layout: vertical;
        width: 1fr;
        min-width: 40;
    }

    #chat-container {
        height: 1fr;
        min-height: 10;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
        Binding("ctrl+1", "show_help", "Help"),
        Binding("ctrl+2", "toggle_sidebar", "History"),
        Binding("ctrl+3", "open_settings", "Settings"),
        Binding("ctrl+4", "show_tools", "Tools"),
        Binding("ctrl+5", "focus_input", "Focus Prompt"),
        Binding("ctrl+6", "focus_chat", "Focus Response"),
    ]

    # Reactive variables for app state
    current_model = reactive("")
    puppy_name = reactive("")
    message_history: List[Dict] = []
    agent_busy = reactive(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent = None
        self.session_memory = None

        # Initialize message queue renderer
        self.message_queue = get_global_queue()
        self.message_renderer = TUIRenderer(self.message_queue, self)
        self._renderer_started = False

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield StatusBar()
        yield Sidebar()
        with Container(id="main-area"):
            with Container(id="chat-container"):
                yield ChatView(id="chat-view")
            yield InputArea()
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the application when mounted."""
        # Load configuration
        self.current_model = get_model_name()
        self.puppy_name = get_puppy_name()

        # Initialize agent and session memory
        self.agent = get_code_generation_agent()
        self.session_memory = session_memory()

        # Update status bar
        status_bar = self.query_one(StatusBar)
        status_bar.current_model = self.current_model
        status_bar.puppy_name = self.puppy_name
        status_bar.agent_status = "Ready"

        # Add welcome message with YOLO mode notification
        self.add_system_message(
            "Welcome to Code Puppy 🐶!\n💨 YOLO mode is enabled in TUI: commands will execute without confirmation."
        )

        # Start the message renderer EARLY to catch startup messages
        # Using call_after_refresh to start it as soon as possible after mount
        self.call_after_refresh(self.start_message_renderer_sync)

        # Load session history
        self.load_history_list()

        # Apply responsive design adjustments
        self.apply_responsive_layout()

        # Auto-focus the input field so user can start typing immediately
        self.call_after_refresh(self.focus_input_field)

    def add_system_message(
        self, content: str, message_group: str = None, group_id: str = None
    ) -> None:
        """Add a system message to the chat."""
        # Support both parameter names for backward compatibility
        final_group_id = message_group or group_id
        message = ChatMessage(
            id=f"sys_{datetime.now(timezone.utc).timestamp()}",
            type=MessageType.SYSTEM,
            content=content,
            timestamp=datetime.now(timezone.utc),
            group_id=final_group_id,
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def add_system_message_rich(
        self, rich_content, message_group: str = None, group_id: str = None
    ) -> None:
        """Add a system message with Rich content (like Markdown) to the chat."""
        # Support both parameter names for backward compatibility
        final_group_id = message_group or group_id
        message = ChatMessage(
            id=f"sys_rich_{datetime.now(timezone.utc).timestamp()}",
            type=MessageType.SYSTEM,
            content=rich_content,  # Store the Rich object directly
            timestamp=datetime.now(timezone.utc),
            group_id=final_group_id,
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def add_user_message(self, content: str, message_group: str = None) -> None:
        """Add a user message to the chat."""
        message = ChatMessage(
            id=f"user_{datetime.now(timezone.utc).timestamp()}",
            type=MessageType.USER,
            content=content,
            timestamp=datetime.now(timezone.utc),
            group_id=message_group,
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def add_agent_message(self, content: str, message_group: str = None) -> None:
        """Add an agent message to the chat."""
        message = ChatMessage(
            id=f"agent_{datetime.now(timezone.utc).timestamp()}",
            type=MessageType.AGENT_RESPONSE,
            content=content,
            timestamp=datetime.now(timezone.utc),
            group_id=message_group,
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def add_error_message(self, content: str, message_group: str = None) -> None:
        """Add an error message to the chat."""
        message = ChatMessage(
            id=f"error_{datetime.now(timezone.utc).timestamp()}",
            type=MessageType.ERROR,
            content=content,
            timestamp=datetime.now(timezone.utc),
            group_id=message_group,
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def add_agent_reasoning_message(
        self, content: str, message_group: str = None
    ) -> None:
        """Add an agent reasoning message to the chat."""
        message = ChatMessage(
            id=f"agent_reasoning_{datetime.now(timezone.utc).timestamp()}",
            type=MessageType.AGENT_REASONING,
            content=content,
            timestamp=datetime.now(timezone.utc),
            group_id=message_group,
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def add_planned_next_steps_message(
        self, content: str, message_group: str = None
    ) -> None:
        """Add an planned next steps to the chat."""
        message = ChatMessage(
            id=f"planned_next_steps_{datetime.now(timezone.utc).timestamp()}",
            type=MessageType.PLANNED_NEXT_STEPS,
            content=content,
            timestamp=datetime.now(timezone.utc),
            group_id=message_group,
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def on_custom_text_area_message_sent(
        self, event: CustomTextArea.MessageSent
    ) -> None:
        """Handle message sent from custom text area."""
        self.action_send_message()

    async def on_key(self, event) -> None:
        """Handle app-level key events."""
        input_field = self.query_one("#input-field", CustomTextArea)

        # Only handle keys when input field is focused
        if input_field.has_focus:
            # Handle Ctrl+Enter for new lines (more reliable than Shift+Enter)
            if event.key == "ctrl+enter":
                input_field.insert("\\n")
                event.prevent_default()
                return

        # Handle arrow keys for sidebar navigation when sidebar is visible
        if not input_field.has_focus:
            try:
                sidebar = self.query_one(Sidebar)
                if sidebar.display:
                    # Handle navigation for the currently active tab
                    tabs = self.query_one("#sidebar-tabs")
                    active_tab = tabs.active

                    if active_tab == "history-tab":
                        history_list = self.query_one("#history-list", ListView)
                        if event.key == "up":
                            current_index = history_list.index
                            if current_index > 0:
                                history_list.index = current_index - 1
                            event.prevent_default()
                            return
                        elif event.key == "down":
                            current_index = history_list.index
                            if current_index < len(history_list.children) - 1:
                                history_list.index = current_index + 1
                            event.prevent_default()
                            return
                        elif event.key == "enter":
                            if history_list.highlighted_child and hasattr(
                                history_list.highlighted_child, "history_entry"
                            ):
                                history_entry = (
                                    history_list.highlighted_child.history_entry
                                )
                                self.show_history_details(history_entry)
                            event.prevent_default()
                            return
            except Exception:
                pass

    def refresh_history_display(self) -> None:
        """Refresh the history display with current session memory."""
        try:
            history_list = self.query_one("#history-list", ListView)
            # Remove all children manually to ensure proper clearing
            for child in list(history_list.children):
                child.remove()
            self.load_history_list()
        except Exception:
            pass  # Silently fail if history list not available

    def action_send_message(self) -> None:
        """Send the current message."""
        input_field = self.query_one("#input-field", CustomTextArea)
        message = input_field.text.strip()

        if message:
            # Clear input
            input_field.text = ""

            # Add user message to chat
            self.add_user_message(message)

            # Process the message asynchronously using Textual's worker system
            # Using exclusive=False to avoid TaskGroup conflicts with MCP servers
            self.run_worker(self.process_message(message), exclusive=False)

    async def process_message(self, message: str) -> None:
        """Process a user message asynchronously."""
        try:
            self.agent_busy = True
            self.start_agent_progress("Thinking")

            # Handle meta commands
            if message.strip().startswith("~"):
                if message.strip().lower() in ("clear", "~clear"):
                    self.action_clear_chat()
                    return

                # Use the existing meta command handler
                try:
                    import sys
                    from io import StringIO

                    from code_puppy.tools.common import console as rich_console

                    # Capture the output from the meta command handler
                    old_stdout = sys.stdout
                    captured_output = StringIO()
                    sys.stdout = captured_output

                    # Also capture Rich console output
                    rich_console.file = captured_output

                    try:
                        # Call the existing meta command handler
                        result = handle_meta_command(message.strip())
                        if result:  # Command was handled
                            output = captured_output.getvalue()
                            if output.strip():
                                self.add_system_message(output.strip())
                            else:
                                self.add_system_message(
                                    f"Meta command '{message}' executed"
                                )
                        else:
                            self.add_system_message(f"Unknown meta command: {message}")
                    finally:
                        # Restore stdout and console
                        sys.stdout = old_stdout
                        rich_console.file = sys.__stdout__

                except Exception as e:
                    self.add_error_message(f"Error executing meta command: {str(e)}")
                return

            # Process with agent
            if self.agent:
                try:
                    self.update_agent_progress("Processing", 25)

                    # Handle MCP servers with specific TaskGroup exception handling
                    try:
                        try:
                            async with self.agent.run_mcp_servers():
                                self.update_agent_progress("Processing", 50)
                                result = await self.agent.run(
                                    message,
                                    message_history=self.message_history,
                                    usage_limits=get_custom_usage_limits(),
                                )
                        except Exception as mcp_error:
                            # Log MCP error and fall back to running without MCP servers
                            self.log(f"MCP server error: {str(mcp_error)}")
                            self.add_system_message(
                                "⚠️ MCP server error, running without MCP servers"
                            )
                            result = await self.agent.run(
                                message,
                                message_history=self.message_history,
                                usage_limits=get_custom_usage_limits(),
                            )

                        if not result or not hasattr(result, "output"):
                            self.add_error_message("Invalid response format from agent")
                            return

                        self.update_agent_progress("Processing", 75)
                        agent_response = result.output
                        self.add_agent_message(agent_response.output_message)

                        # Update message history
                        new_msgs = result.all_messages()
                        self.message_history = await message_history_processor(new_msgs)

                        # Refresh history display to show new interaction
                        self.refresh_history_display()

                        # Log to session memory
                        if self.session_memory:
                            self.session_memory.log_task(
                                f"TUI interaction: {message}",
                                extras={
                                    "output": agent_response.output_message,
                                    "awaiting_user_input": agent_response.awaiting_user_input,
                                },
                            )
                    except Exception as eg:
                        # Handle TaskGroup and other exceptions
                        # BaseExceptionGroup is only available in Python 3.11+
                        if hasattr(eg, "exceptions"):
                            # Handle TaskGroup exceptions specifically (Python 3.11+)
                            for e in eg.exceptions:
                                self.add_error_message(f"MCP/Agent error: {str(e)}")
                        else:
                            # Handle regular exceptions
                            self.add_error_message(f"MCP/Agent error: {str(eg)}")
                except Exception as agent_error:
                    # Handle any other errors in agent processing
                    self.add_error_message(
                        f"Agent processing failed: {str(agent_error)}"
                    )
            else:
                self.add_error_message("Agent not initialized")

        except Exception as e:
            self.add_error_message(f"Error processing message: {str(e)}")
        finally:
            self.agent_busy = False
            self.stop_agent_progress()

    # Action methods
    def action_clear_chat(self) -> None:
        """Clear the chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.clear_messages()
        self.message_history.clear()
        self.add_system_message("Chat history cleared")

    def action_show_help(self) -> None:
        """Show help information in a modal."""
        self.push_screen(HelpScreen())

    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility."""
        sidebar = self.query_one(Sidebar)
        sidebar.display = not sidebar.display

        # If sidebar is now visible, focus the history list to enable immediate keyboard navigation
        if sidebar.display:
            try:
                # Ensure history tab is active
                tabs = self.query_one("#sidebar-tabs")
                tabs.active = "history-tab"

                # Focus the history list
                history_list = self.query_one("#history-list", ListView)
                history_list.focus()

                # If the list has items, ensure the first item is highlighted
                if len(history_list.children) > 0:
                    history_list.index = 0
            except Exception:
                # Silently fail if there's an issue with focusing
                pass
        else:
            # If sidebar is now hidden, focus the input field for a smooth workflow
            try:
                self.action_focus_input()
            except Exception:
                # Silently fail if there's an issue with focusing
                pass

    def action_focus_input(self) -> None:
        """Focus the input field."""
        input_field = self.query_one("#input-field", CustomTextArea)
        input_field.focus()

    def focus_input_field(self) -> None:
        """Focus the input field (used for auto-focus on startup)."""
        try:
            input_field = self.query_one("#input-field", CustomTextArea)
            input_field.focus()
        except Exception:
            pass  # Silently handle if widget not ready yet

    def action_focus_chat(self) -> None:
        """Focus the chat area."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.focus()

    def action_show_tools(self) -> None:
        """Show the tools modal with TOOLS.md content."""
        self.push_screen(ToolsScreen())

    def action_open_settings(self) -> None:
        """Open the settings configuration screen."""

        def handle_settings_result(result):
            if result and result.get("success"):
                # Update reactive variables
                from code_puppy.config import get_model_name, get_puppy_name

                self.puppy_name = get_puppy_name()

                # Handle model change if needed
                if result.get("model_changed"):
                    new_model = get_model_name()
                    self.current_model = new_model
                    # Reinitialize agent with new model
                    self.agent = get_code_generation_agent()

                # Update status bar
                status_bar = self.query_one(StatusBar)
                status_bar.puppy_name = self.puppy_name
                status_bar.current_model = self.current_model

                # Show success message
                self.add_system_message(result.get("message", "Settings updated"))
            elif (
                result
                and not result.get("success")
                and "cancelled" not in result.get("message", "").lower()
            ):
                # Show error message (but not for cancellation)
                self.add_error_message(result.get("message", "Settings update failed"))

        self.push_screen(SettingsScreen(), handle_settings_result)

    # History management methods
    def load_history_list(self) -> None:
        """Load session history into the history tab."""
        try:
            from datetime import datetime, timezone

            history_list = self.query_one("#history-list", ListView)

            # Get history from session memory
            if self.session_memory:
                # Get recent history (last 24 hours by default)
                recent_history = self.session_memory.get_history(within_minutes=24 * 60)

                if not recent_history:
                    # No history available
                    history_list.append(
                        ListItem(Label("No recent history", classes="history-empty"))
                    )
                    return

                # Filter out model loading entries and group history by type, display most recent first
                filtered_history = [
                    entry
                    for entry in recent_history
                    if not entry.get("description", "").startswith("Agent loaded")
                ]

                # Get sidebar width for responsive text truncation
                try:
                    sidebar_width = (
                        self.query_one("Sidebar").size.width
                        if hasattr(self.query_one("Sidebar"), "size")
                        else 30
                    )
                except Exception:
                    sidebar_width = 30

                # Adjust text length based on sidebar width
                if sidebar_width >= 35:
                    max_text_length = 45
                    time_format = "%H:%M:%S"
                elif sidebar_width >= 25:
                    max_text_length = 30
                    time_format = "%H:%M"
                else:
                    max_text_length = 20
                    time_format = "%H:%M"

                for entry in reversed(filtered_history[-20:]):  # Show last 20 entries
                    timestamp_str = entry.get("timestamp", "")
                    description = entry.get("description", "Unknown task")

                    # Parse timestamp for display with safe parsing
                    def parse_timestamp_safely_for_display(timestamp_str: str) -> str:
                        """Parse timestamp string safely for display purposes."""
                        try:
                            # Handle 'Z' suffix (common UTC format)
                            cleaned_timestamp = timestamp_str.replace("Z", "+00:00")
                            parsed_dt = datetime.fromisoformat(cleaned_timestamp)

                            # If the datetime is naive (no timezone), assume UTC
                            if parsed_dt.tzinfo is None:
                                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)

                            return parsed_dt.strftime(time_format)
                        except (ValueError, AttributeError, TypeError):
                            # Handle invalid timestamp formats gracefully
                            fallback = (
                                timestamp_str[:5]
                                if sidebar_width < 25
                                else timestamp_str[:8]
                            )
                            return "??:??" if len(fallback) < 5 else fallback

                    time_display = parse_timestamp_safely_for_display(timestamp_str)

                    # Format description for display with responsive truncation
                    if description.startswith("Interactive task:"):
                        task_text = description[
                            17:
                        ].strip()  # Remove "Interactive task: "
                        truncated = task_text[:max_text_length] + (
                            "..." if len(task_text) > max_text_length else ""
                        )
                        display_text = f"[{time_display}] 💬 {truncated}"
                        css_class = "history-interactive"
                    elif description.startswith("TUI interaction:"):
                        task_text = description[
                            16:
                        ].strip()  # Remove "TUI interaction: "
                        truncated = task_text[:max_text_length] + (
                            "..." if len(task_text) > max_text_length else ""
                        )
                        display_text = f"[{time_display}] 🖥️ {truncated}"
                        css_class = "history-tui"
                    elif description.startswith("Command executed"):
                        cmd_text = description[
                            18:
                        ].strip()  # Remove "Command executed: "
                        truncated = cmd_text[: max_text_length - 5] + (
                            "..." if len(cmd_text) > max_text_length - 5 else ""
                        )
                        display_text = f"[{time_display}] ⚡ {truncated}"
                        css_class = "history-command"
                    else:
                        # Generic entry
                        truncated = description[:max_text_length] + (
                            "..." if len(description) > max_text_length else ""
                        )
                        display_text = f"[{time_display}] 📝 {truncated}"
                        css_class = "history-generic"

                    label = Label(display_text, classes=css_class)
                    history_item = ListItem(label)
                    history_item.history_entry = (
                        entry  # Store full entry for detail view
                    )
                    history_list.append(history_item)
            else:
                history_list.append(
                    ListItem(
                        Label("Session memory not available", classes="history-error")
                    )
                )

        except Exception as e:
            self.add_error_message(f"Failed to load history: {e}")

    def show_history_details(self, history_entry: dict) -> None:
        """Show detailed information about a selected history entry."""
        try:
            timestamp = history_entry.get("timestamp", "Unknown time")
            description = history_entry.get("description", "No description")
            output = history_entry.get("output", "")
            awaiting_input = history_entry.get("awaiting_user_input", False)

            # Parse timestamp for better display with safe parsing
            def parse_timestamp_safely_for_details(timestamp_str: str) -> str:
                """Parse timestamp string safely for detailed display."""
                try:
                    # Handle 'Z' suffix (common UTC format)
                    cleaned_timestamp = timestamp_str.replace("Z", "+00:00")
                    parsed_dt = datetime.fromisoformat(cleaned_timestamp)

                    # If the datetime is naive (no timezone), assume UTC
                    if parsed_dt.tzinfo is None:
                        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)

                    return parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, AttributeError, TypeError):
                    # Handle invalid timestamp formats gracefully
                    return timestamp_str

            formatted_time = parse_timestamp_safely_for_details(timestamp)

            # Create detailed view content
            details = [
                f"Timestamp: {formatted_time}",
                f"Description: {description}",
                "",
            ]

            if output:
                details.extend(
                    [
                        "Output:",
                        "─" * 40,
                        output,
                        "",
                    ]
                )

            if awaiting_input:
                details.append("⚠️  Was awaiting user input")

            # Display details as a system message in the chat
            detail_text = "\\n".join(details)
            self.add_system_message(f"History Details:\\n{detail_text}")

        except Exception as e:
            self.add_error_message(f"Failed to show history details: {e}")

    # Progress and status methods
    def set_agent_status(self, status: str, show_progress: bool = False) -> None:
        """Update agent status and optionally show/hide progress bar."""
        try:
            # Update status bar
            status_bar = self.query_one(StatusBar)
            status_bar.agent_status = status

            # Update spinner visibility
            from .components.input_area import SimpleSpinnerWidget

            spinner = self.query_one("#spinner", SimpleSpinnerWidget)
            if show_progress:
                spinner.add_class("visible")
                spinner.display = True
                spinner.start_spinning()
            else:
                spinner.remove_class("visible")
                spinner.display = False
                spinner.stop_spinning()

        except Exception:
            pass  # Silently fail if widgets not available

    def start_agent_progress(self, initial_status: str = "Thinking") -> None:
        """Start showing agent progress indicators."""
        self.set_agent_status(initial_status, show_progress=True)

    def update_agent_progress(self, status: str, progress: int = None) -> None:
        """Update agent progress during processing."""
        try:
            status_bar = self.query_one(StatusBar)
            status_bar.agent_status = status
            # Note: LoadingIndicator doesn't use progress values, it just spins
        except Exception:
            pass

    def stop_agent_progress(self) -> None:
        """Stop showing agent progress indicators."""
        self.set_agent_status("Ready", show_progress=False)

    def on_resize(self, event: Resize) -> None:
        """Handle terminal resize events to update responsive elements."""
        try:
            # Apply responsive layout adjustments
            self.apply_responsive_layout()

            # Update status bar to reflect new width
            status_bar = self.query_one(StatusBar)
            status_bar.update_status()

            # Refresh history display with new responsive truncation
            self.refresh_history_display()

        except Exception:
            pass  # Silently handle resize errors

    def apply_responsive_layout(self) -> None:
        """Apply responsive layout adjustments based on terminal size."""
        try:
            terminal_width = self.size.width if hasattr(self, "size") else 80
            terminal_height = self.size.height if hasattr(self, "size") else 24
            sidebar = self.query_one(Sidebar)

            # Responsive sidebar width based on terminal width
            if terminal_width >= 120:
                sidebar.styles.width = 35
            elif terminal_width >= 100:
                sidebar.styles.width = 30
            elif terminal_width >= 80:
                sidebar.styles.width = 25
            elif terminal_width >= 60:
                sidebar.styles.width = 20
            else:
                sidebar.styles.width = 15

            # Auto-hide sidebar on very narrow terminals
            if terminal_width < 50:
                if sidebar.display:
                    sidebar.display = False
                    self.add_system_message(
                        "💡 Sidebar auto-hidden for narrow terminal. Press Ctrl+2 to toggle."
                    )

            # Adjust input area height for very short terminals
            if terminal_height < 20:
                input_area = self.query_one(InputArea)
                input_area.styles.height = 7
            else:
                input_area = self.query_one(InputArea)
                input_area.styles.height = 9

        except Exception:
            pass

    def start_message_renderer_sync(self):
        """Synchronous wrapper to start message renderer via run_worker."""
        self.run_worker(self.start_message_renderer(), exclusive=False)

    async def start_message_renderer(self):
        """Start the message renderer to consume messages from the queue."""
        if not self._renderer_started:
            self._renderer_started = True

            # Process any buffered startup messages first
            from io import StringIO

            from rich.console import Console

            from code_puppy.messaging import get_buffered_startup_messages

            buffered_messages = get_buffered_startup_messages()

            if buffered_messages:
                # Group startup messages into a single display
                startup_content_lines = []

                for message in buffered_messages:
                    try:
                        # Convert message content to string for grouping
                        if hasattr(message.content, "__rich_console__"):
                            # For Rich objects, render to plain text
                            string_io = StringIO()
                            # Use markup=False to prevent interpretation of square brackets as markup
                            temp_console = Console(
                                file=string_io,
                                width=80,
                                legacy_windows=False,
                                markup=False,
                            )
                            temp_console.print(message.content)
                            content_str = string_io.getvalue().rstrip("\n")
                        else:
                            content_str = str(message.content)

                        startup_content_lines.append(content_str)
                    except Exception as e:
                        startup_content_lines.append(
                            f"Error processing startup message: {e}"
                        )

                # Create a single grouped startup message
                grouped_content = "\n".join(startup_content_lines)
                self.add_system_message(grouped_content)

                # Clear the startup buffer after processing
                self.message_queue.clear_startup_buffer()

            # Now start the regular message renderer
            await self.message_renderer.start()

    async def stop_message_renderer(self):
        """Stop the message renderer."""
        if self._renderer_started:
            self._renderer_started = False
            try:
                await self.message_renderer.stop()
            except Exception as e:
                # Log renderer stop errors but don't crash
                self.add_system_message(f"Renderer stop error: {e}")

    @on(HistoryEntrySelected)
    def on_history_entry_selected(self, event: HistoryEntrySelected) -> None:
        """Handle selection of a history entry from the sidebar."""
        # Display the history entry details
        self.show_history_details(event.history_entry)

    async def on_unmount(self):
        """Clean up when the app is unmounted."""
        try:
            await self.stop_message_renderer()
        except Exception as e:
            # Log unmount errors but don't crash during cleanup
            try:
                self.add_system_message(f"Unmount cleanup error: {e}")
            except Exception:
                # If we can't even add a message, just ignore
                pass


async def run_textual_ui():
    """Run the Textual UI interface."""
    # Always enable YOLO mode in TUI mode for a smoother experience
    from code_puppy.config import set_config_value

    set_config_value("yolo_mode", "true")

    app = CodePuppyTUI()
    await app.run_async()
