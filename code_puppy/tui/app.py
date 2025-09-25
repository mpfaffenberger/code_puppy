"""
Main TUI application class.
"""

from datetime import datetime, timezone

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.events import Resize
from textual.reactive import reactive
from textual.widgets import Footer, ListView

from code_puppy.agent import get_code_generation_agent, get_custom_usage_limits
from code_puppy.agents.runtime_manager import get_runtime_agent_manager
from code_puppy.command_line.command_handler import handle_command
from code_puppy.config import (
    get_model_name,
    get_puppy_name,
    initialize_command_history_file,
    save_command_to_history,
)
from code_puppy.message_history_processor import (
    message_history_accumulator,
    prune_interrupted_tool_calls,
)

# Import our message queue system
from code_puppy.messaging import TUIRenderer, get_global_queue
from code_puppy.state_management import (
    clear_message_history,
    get_message_history,
    set_message_history,
)
from code_puppy.tui.components import (
    ChatView,
    CustomTextArea,
    InputArea,
    Sidebar,
    StatusBar,
)

from .. import state_management

# Import shared message classes
from .messages import CommandSelected, HistoryEntrySelected
from .models import ChatMessage, MessageType
from .screens import HelpScreen, MCPInstallWizardScreen, SettingsScreen, ToolsScreen


class CodePuppyTUI(App):
    """Main Code Puppy TUI application."""

    TITLE = "Code Puppy - AI Code Assistant"
    SUB_TITLE = "TUI Mode"

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
        Binding("ctrl+t", "open_mcp_wizard", "MCP Install Wizard"),
    ]

    # Reactive variables for app state
    current_model = reactive("")
    puppy_name = reactive("")
    current_agent = reactive("")
    agent_busy = reactive(False)

    def watch_agent_busy(self) -> None:
        """Watch for changes to agent_busy state."""
        # Update the submit/cancel button state when agent_busy changes
        self._update_submit_cancel_button(self.agent_busy)

    def watch_current_agent(self) -> None:
        """Watch for changes to current_agent and update title."""
        self._update_title()

    def _update_title(self) -> None:
        """Update the application title to include current agent."""
        if self.current_agent:
            self.title = f"Code Puppy - {self.current_agent}"
            self.sub_title = "TUI Mode"
        else:
            self.title = "Code Puppy - AI Code Assistant"
            self.sub_title = "TUI Mode"

    def _on_agent_reload(self, agent_id: str, agent_name: str) -> None:
        """Callback for when agent is reloaded/changed."""
        # Get the updated agent configuration
        from code_puppy.agents.agent_manager import get_current_agent_config

        current_agent_config = get_current_agent_config()
        new_agent_display = (
            current_agent_config.display_name if current_agent_config else "code-puppy"
        )

        # Update the reactive variable (this will trigger watch_current_agent)
        self.current_agent = new_agent_display

        # Add a system message to notify the user
        self.add_system_message(f"🔄 Switched to agent: {new_agent_display}")

    def __init__(self, initial_command: str = None, **kwargs):
        super().__init__(**kwargs)
        self.agent_manager = None
        self._current_worker = None
        self.initial_command = initial_command

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
        # Register this app instance for global access
        from code_puppy.state_management import set_tui_app_instance

        set_tui_app_instance(self)

        # Register callback for agent reload events
        from code_puppy.callbacks import register_callback

        register_callback("agent_reload", self._on_agent_reload)

        # Load configuration
        self.current_model = get_model_name()
        self.puppy_name = get_puppy_name()

        # Get current agent information
        from code_puppy.agents.agent_manager import get_current_agent_config

        current_agent_config = get_current_agent_config()
        self.current_agent = (
            current_agent_config.display_name if current_agent_config else "code-puppy"
        )

        # Initial title update
        self._update_title()

        # Use runtime manager to ensure we always have the current agent
        self.agent_manager = get_runtime_agent_manager()

        # Update status bar
        status_bar = self.query_one(StatusBar)
        status_bar.current_model = self.current_model
        status_bar.puppy_name = self.puppy_name
        status_bar.agent_status = "Ready"

        # Add welcome message with YOLO mode notification
        self.add_system_message(
            "Welcome to Code Puppy 🐶!\n💨 YOLO mode is enabled in TUI: commands will execute without confirmation."
        )

        # Get current agent and display info
        get_code_generation_agent()
        self.add_system_message(
            f"🐕 Loaded agent '{self.puppy_name}' with model '{self.current_model}'"
        )

        # Start the message renderer EARLY to catch startup messages
        # Using call_after_refresh to start it as soon as possible after mount
        self.call_after_refresh(self.start_message_renderer_sync)

        # Apply responsive design adjustments
        self.apply_responsive_layout()

        # Auto-focus the input field so user can start typing immediately
        self.call_after_refresh(self.focus_input_field)

        # Process initial command if provided
        if self.initial_command:
            self.call_after_refresh(self.process_initial_command)

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

    def on_input_area_submit_requested(self, event) -> None:
        """Handle submit button clicked."""
        self.action_send_message()

    def on_input_area_cancel_requested(self, event) -> None:
        """Handle cancel button clicked."""
        self.action_cancel_processing()

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

        # Check if a modal is currently active - if so, let the modal handle keys
        if hasattr(self, "_active_screen") and self._active_screen:
            # Don't handle keys at the app level when a modal is active
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
                        if event.key == "enter":
                            if history_list.highlighted_child and hasattr(
                                history_list.highlighted_child, "command_entry"
                            ):
                                # Show command history modal
                                from .components.command_history_modal import (
                                    CommandHistoryModal,
                                )

                                # Make sure sidebar's current_history_index is synced with the ListView
                                sidebar.current_history_index = history_list.index

                                # Push the modal screen
                                # The modal will get the command entries from the sidebar
                                self.push_screen(CommandHistoryModal())
                            event.prevent_default()
                            return
            except Exception:
                pass

    def refresh_history_display(self) -> None:
        """Refresh the history display with the command history file."""
        try:
            sidebar = self.query_one(Sidebar)
            sidebar.load_command_history()
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

            # Save command to history file with timestamp
            try:
                save_command_to_history(message)
            except Exception as e:
                self.add_error_message(f"Failed to save command history: {str(e)}")

            # Update button state
            self._update_submit_cancel_button(True)

            # Process the message asynchronously using Textual's worker system
            # Using exclusive=False to avoid TaskGroup conflicts with MCP servers
            self._current_worker = self.run_worker(
                self.process_message(message), exclusive=False
            )

    def _update_submit_cancel_button(self, is_cancel_mode: bool) -> None:
        """Update the submit/cancel button state."""
        try:
            from .components.input_area import SubmitCancelButton

            button = self.query_one(SubmitCancelButton)
            button.is_cancel_mode = is_cancel_mode
        except Exception:
            pass  # Silently fail if button not found

    def action_cancel_processing(self) -> None:
        """Cancel the current message processing."""
        if hasattr(self, "_current_worker") and self._current_worker is not None:
            try:
                # First, kill any running shell processes (same as interactive mode Ctrl+C)
                from code_puppy.tools.command_runner import (
                    kill_all_running_shell_processes,
                )

                killed = kill_all_running_shell_processes()
                if killed:
                    self.add_system_message(
                        f"🔥 Cancelled {killed} running shell process(es)"
                    )
                    # Don't stop spinner/agent - let the agent continue processing
                    # Shell processes killed, but agent worker continues running

                else:
                    # Only cancel the agent task if NO processes were killed
                    self._current_worker.cancel()
                    state_management.set_message_history(
                        prune_interrupted_tool_calls(
                            state_management.get_message_history()
                        )
                    )
                    self.add_system_message("⚠️  Processing cancelled by user")
                    # Stop spinner and clear state only when agent is actually cancelled
                    self._current_worker = None
                    self.agent_busy = False
                    self.stop_agent_progress()
            except Exception as e:
                self.add_error_message(f"Failed to cancel processing: {str(e)}")
                # Only clear state on exception if we haven't already done so
                if (
                    hasattr(self, "_current_worker")
                    and self._current_worker is not None
                ):
                    self._current_worker = None
                    self.agent_busy = False
                    self.stop_agent_progress()

    async def process_message(self, message: str) -> None:
        """Process a user message asynchronously."""
        try:
            self.agent_busy = True
            self._update_submit_cancel_button(True)
            self.start_agent_progress("Thinking")

            # Handle commands
            if message.strip().startswith("/"):
                # Handle special commands directly
                if message.strip().lower() in ("clear", "/clear"):
                    self.action_clear_chat()
                    return

                # Let the command handler process all /agent commands
                # result will be handled by the command handler directly through messaging system
                if message.strip().startswith("/agent"):
                    # The command handler will emit messages directly to our messaging system
                    handle_command(message.strip())
                    # Agent manager will automatically use the latest agent
                    return

                # Handle exit commands
                if message.strip().lower() in ("/exit", "/quit"):
                    self.add_system_message("Goodbye!")
                    # Exit the application
                    self.app.exit()
                    return

                # Use the existing command handler
                # The command handler directly uses the messaging system, so we don't need to capture stdout
                try:
                    result = handle_command(message.strip())
                    if not result:
                        self.add_system_message(f"Unknown command: {message}")
                except Exception as e:
                    self.add_error_message(f"Error executing command: {str(e)}")
                return

            # Process with agent
            if self.agent_manager:
                try:
                    self.update_agent_progress("Processing", 25)

                    # Use agent_manager's run_with_mcp to handle MCP servers properly
                    try:
                        self.update_agent_progress("Processing", 50)
                        result = await self.agent_manager.run_with_mcp(
                            message,
                            message_history=get_message_history(),
                            usage_limits=get_custom_usage_limits(),
                        )

                        if not result or not hasattr(result, "output"):
                            self.add_error_message("Invalid response format from agent")
                            return

                        self.update_agent_progress("Processing", 75)
                        agent_response = result.output
                        self.add_agent_message(agent_response)

                        # Update message history
                        new_msgs = result.new_messages()
                        message_history_accumulator(new_msgs)

                        # Refresh history display to show new interaction
                        self.refresh_history_display()

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
                    finally:
                        set_message_history(
                            prune_interrupted_tool_calls(get_message_history())
                        )
                except Exception as agent_error:
                    # Handle any other errors in agent processing
                    self.add_error_message(
                        f"Agent processing failed: {str(agent_error)}"
                    )
            else:
                self.add_error_message("Agent manager not initialized")

        except Exception as e:
            self.add_error_message(f"Error processing message: {str(e)}")
        finally:
            self.agent_busy = False
            self._update_submit_cancel_button(False)
            self.stop_agent_progress()

    # Action methods
    def action_clear_chat(self) -> None:
        """Clear the chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.clear_messages()
        clear_message_history()
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

                # Refresh the command history
                sidebar.load_command_history()

                # Focus the history list
                history_list = self.query_one("#history-list", ListView)
                history_list.focus()

                # If the list has items, get the first item for the modal
                if len(history_list.children) > 0:
                    # Reset sidebar's internal index tracker to 0
                    sidebar.current_history_index = 0

                    # Set ListView index to match
                    history_list.index = 0

                    # Get the first item and show the command history modal
                    first_item = history_list.children[0]
                    if hasattr(first_item, "command_entry"):
                        # command_entry = first_item.command_entry

                        # Use call_after_refresh to allow UI to update first
                        def show_modal():
                            from .components.command_history_modal import (
                                CommandHistoryModal,
                            )

                            # Get all command entries from the history list
                            command_entries = []
                            for i, child in enumerate(history_list.children):
                                if hasattr(child, "command_entry"):
                                    command_entries.append(child.command_entry)

                            # Push the modal screen
                            # The modal will get the command entries from the sidebar
                            self.push_screen(CommandHistoryModal())

                        # Schedule modal to appear after UI refresh
                        self.call_after_refresh(show_modal)
            except Exception as e:
                # Log the exception in debug mode but silently fail for end users
                import logging

                logging.debug(f"Error focusing history item: {str(e)}")
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
        """Show the tools modal."""
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
                    self.agent_manager.reload_agent()

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

    def action_open_mcp_wizard(self) -> None:
        """Open the MCP Install Wizard."""

        def handle_wizard_result(result):
            if result and result.get("success"):
                # Show success message
                self.add_system_message(
                    result.get("message", "MCP server installed successfully")
                )

                # If a server was installed, suggest starting it
                if result.get("server_name"):
                    server_name = result["server_name"]
                    self.add_system_message(
                        f"💡 Use '/mcp start {server_name}' to start the server"
                    )
            elif (
                result
                and not result.get("success")
                and "cancelled" not in result.get("message", "").lower()
            ):
                # Show error message (but not for cancellation)
                self.add_error_message(result.get("message", "MCP installation failed"))

        self.push_screen(MCPInstallWizardScreen(), handle_wizard_result)

    def process_initial_command(self) -> None:
        """Process the initial command provided when starting the TUI."""
        if self.initial_command:
            # Add the initial command to the input field
            input_field = self.query_one("#input-field", CustomTextArea)
            input_field.text = self.initial_command

            # Show that we're auto-executing the initial command
            self.add_system_message(
                f"🚀 Auto-executing initial command: {self.initial_command}"
            )

            # Automatically submit the message
            self.action_send_message()

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

    @on(CommandSelected)
    def on_command_selected(self, event: CommandSelected) -> None:
        """Handle selection of a command from the history modal."""
        # Set the command in the input field
        input_field = self.query_one("#input-field", CustomTextArea)
        input_field.text = event.command

        # Focus the input field for immediate editing
        input_field.focus()

        # Close the sidebar automatically for a smoother workflow
        sidebar = self.query_one(Sidebar)
        sidebar.display = False

    async def on_unmount(self):
        """Clean up when the app is unmounted."""
        try:
            # Unregister the agent reload callback
            from code_puppy.callbacks import unregister_callback

            unregister_callback("agent_reload", self._on_agent_reload)

            await self.stop_message_renderer()
        except Exception as e:
            # Log unmount errors but don't crash during cleanup
            try:
                self.add_system_message(f"Unmount cleanup error: {e}")
            except Exception:
                # If we can't even add a message, just ignore
                pass


async def run_textual_ui(initial_command: str = None):
    """Run the Textual UI interface."""
    # Always enable YOLO mode in TUI mode for a smoother experience
    from code_puppy.config import set_config_value

    # Initialize the command history file
    initialize_command_history_file()

    set_config_value("yolo_mode", "true")

    app = CodePuppyTUI(initial_command=initial_command)
    await app.run_async()
