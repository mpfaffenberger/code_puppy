"""Rich console renderer for structured messages.

This module implements the presentation layer for Code Puppy's messaging system.
It consumes structured messages from the MessageBus and renders them using Rich.

The renderer is responsible for ALL presentation decisions - the messages contain
only structured data with no formatting hints.
"""

from typing import Dict, Optional, Protocol, runtime_checkable

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape as escape_rich_markup
from rich.panel import Panel
from rich.rule import Rule

# Note: Syntax import removed - file content not displayed, only header
from rich.table import Table

from code_puppy.tools.common import format_diff_with_colors

from .bus import MessageBus
from .commands import (
    ConfirmationResponse,
    SelectionResponse,
    UserInputResponse,
)
from .messages import (
    AgentReasoningMessage,
    AgentResponseMessage,
    AnyMessage,
    ConfirmationRequest,
    DiffMessage,
    DividerMessage,
    FileContentMessage,
    FileListingMessage,
    GrepResultMessage,
    MessageLevel,
    SelectionRequest,
    ShellLineMessage,
    ShellOutputMessage,
    ShellStartMessage,
    SpinnerControl,
    StatusPanelMessage,
    SubAgentInvocationMessage,
    SubAgentResponseMessage,
    TextMessage,
    UserInputRequest,
    VersionCheckMessage,
)

# Note: Text and Tree were removed - no longer used in this implementation


# =============================================================================
# Renderer Protocol
# =============================================================================


@runtime_checkable
class RendererProtocol(Protocol):
    """Protocol defining the interface for message renderers."""

    async def render(self, message: AnyMessage) -> None:
        """Render a single message."""
        ...

    async def start(self) -> None:
        """Start the renderer (begin consuming messages)."""
        ...

    async def stop(self) -> None:
        """Stop the renderer."""
        ...


# =============================================================================
# Default Styles
# =============================================================================

DEFAULT_STYLES: Dict[MessageLevel, str] = {
    MessageLevel.ERROR: "bold red",
    MessageLevel.WARNING: "yellow",
    MessageLevel.SUCCESS: "green",
    MessageLevel.INFO: "white",
    MessageLevel.DEBUG: "dim",
}

DIFF_STYLES = {
    "add": "green",
    "remove": "red",
    "context": "dim",
}


# =============================================================================
# Rich Console Renderer
# =============================================================================


class RichConsoleRenderer:
    """Rich console implementation of the renderer protocol.

    This renderer consumes messages from a MessageBus and renders them using Rich.
    It uses a background thread for synchronous compatibility with the main loop.
    """

    def __init__(
        self,
        bus: MessageBus,
        console: Optional[Console] = None,
        styles: Optional[Dict[MessageLevel, str]] = None,
    ) -> None:
        """Initialize the renderer.

        Args:
            bus: The MessageBus to consume messages from.
            console: Rich Console instance (creates default if None).
            styles: Custom style mappings (uses DEFAULT_STYLES if None).
        """
        import threading

        self._bus = bus
        self._console = console or Console()
        self._styles = styles or DEFAULT_STYLES.copy()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._spinners: Dict[str, object] = {}  # spinner_id -> status context

    @property
    def console(self) -> Console:
        """Get the Rich console."""
        return self._console

    def _get_banner_color(self, banner_name: str) -> str:
        """Get the configured color for a banner.

        Args:
            banner_name: The banner identifier (e.g., 'thinking', 'shell_command')

        Returns:
            Rich color name for the banner background
        """
        from code_puppy.config import get_banner_color

        return get_banner_color(banner_name)

    def _format_banner(self, banner_name: str, text: str) -> str:
        """Format a banner with its configured color.

        Args:
            banner_name: The banner identifier
            text: The banner text

        Returns:
            Rich markup string for the banner
        """
        color = self._get_banner_color(banner_name)
        return f"[bold white on {color}] {text} [/bold white on {color}]"

    # =========================================================================
    # Lifecycle (Synchronous - for compatibility with main.py)
    # =========================================================================

    def start(self) -> None:
        """Start the renderer in a background thread.

        This is synchronous to match the old SynchronousInteractiveRenderer API.
        """
        import threading

        if self._running:
            return

        self._running = True
        self._bus.mark_renderer_active()

        # Start background thread for message consumption
        self._thread = threading.Thread(target=self._consume_loop_sync, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the renderer.

        This is synchronous to match the old SynchronousInteractiveRenderer API.
        """
        self._running = False
        self._bus.mark_renderer_inactive()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _consume_loop_sync(self) -> None:
        """Synchronous message consumption loop running in background thread."""
        import time

        # First, process any buffered messages
        for msg in self._bus.get_buffered_messages():
            self._render_sync(msg)
        self._bus.clear_buffer()

        # Then consume new messages
        while self._running:
            message = self._bus.get_message_nowait()
            if message:
                self._render_sync(message)
            else:
                time.sleep(0.01)

    def _render_sync(self, message: AnyMessage) -> None:
        """Render a message synchronously with error handling."""
        try:
            self._do_render(message)
        except Exception as e:
            # Don't let rendering errors crash the loop
            # Escape the error message to prevent nested markup errors
            safe_error = escape_rich_markup(str(e))
            self._console.print(f"[dim red]Render error: {safe_error}[/dim red]")

    # =========================================================================
    # Async Lifecycle (for future async-first usage)
    # =========================================================================

    async def start_async(self) -> None:
        """Start the renderer asynchronously."""
        if self._running:
            return

        self._running = True
        self._bus.mark_renderer_active()

        # Process any buffered messages first
        for msg in self._bus.get_buffered_messages():
            self._render_sync(msg)
        self._bus.clear_buffer()

    async def stop_async(self) -> None:
        """Stop the renderer asynchronously."""
        self._running = False
        self._bus.mark_renderer_inactive()

    # =========================================================================
    # Main Dispatch
    # =========================================================================

    def _do_render(self, message: AnyMessage) -> None:
        """Synchronously render a message by dispatching to the appropriate handler.

        Note: User input requests are skipped in sync mode as they require async.
        """
        # Dispatch based on message type
        if isinstance(message, TextMessage):
            self._render_text(message)
        elif isinstance(message, FileListingMessage):
            self._render_file_listing(message)
        elif isinstance(message, FileContentMessage):
            self._render_file_content(message)
        elif isinstance(message, GrepResultMessage):
            self._render_grep_result(message)
        elif isinstance(message, DiffMessage):
            self._render_diff(message)
        elif isinstance(message, ShellStartMessage):
            self._render_shell_start(message)
        elif isinstance(message, ShellLineMessage):
            self._render_shell_line(message)
        elif isinstance(message, ShellOutputMessage):
            self._render_shell_output(message)
        elif isinstance(message, AgentReasoningMessage):
            self._render_agent_reasoning(message)
        elif isinstance(message, AgentResponseMessage):
            # Skip rendering - we now stream agent responses via event_stream_handler
            pass
        elif isinstance(message, SubAgentInvocationMessage):
            self._render_subagent_invocation(message)
        elif isinstance(message, SubAgentResponseMessage):
            self._render_subagent_response(message)
        elif isinstance(message, UserInputRequest):
            # Can't handle async user input in sync context - skip
            self._console.print("[dim]User input requested (requires async)[/dim]")
        elif isinstance(message, ConfirmationRequest):
            # Can't handle async confirmation in sync context - skip
            self._console.print("[dim]Confirmation requested (requires async)[/dim]")
        elif isinstance(message, SelectionRequest):
            # Can't handle async selection in sync context - skip
            self._console.print("[dim]Selection requested (requires async)[/dim]")
        elif isinstance(message, SpinnerControl):
            self._render_spinner_control(message)
        elif isinstance(message, DividerMessage):
            self._render_divider(message)
        elif isinstance(message, StatusPanelMessage):
            self._render_status_panel(message)
        elif isinstance(message, VersionCheckMessage):
            self._render_version_check(message)
        else:
            # Unknown message type - render as debug
            self._console.print(f"[dim]Unknown message: {type(message).__name__}[/dim]")

    async def render(self, message: AnyMessage) -> None:
        """Render a message asynchronously (supports user input requests)."""
        # Handle async-only message types
        if isinstance(message, UserInputRequest):
            await self._render_user_input_request(message)
        elif isinstance(message, ConfirmationRequest):
            await self._render_confirmation_request(message)
        elif isinstance(message, SelectionRequest):
            await self._render_selection_request(message)
        else:
            # Use sync render for everything else
            self._do_render(message)

    # =========================================================================
    # Text Messages
    # =========================================================================

    def _render_text(self, msg: TextMessage) -> None:
        """Render a text message with appropriate styling.

        Text is escaped to prevent Rich markup injection which could crash
        the renderer if malformed tags are present in shell output or other
        user-provided content.
        """
        style = self._styles.get(msg.level, "white")

        # Make version messages dim
        if "Current version:" in msg.text or "Latest version:" in msg.text:
            style = "dim"

        prefix = self._get_level_prefix(msg.level)
        # Escape Rich markup to prevent crashes from malformed tags
        safe_text = escape_rich_markup(msg.text)
        self._console.print(f"{prefix}{safe_text}", style=style)

    def _get_level_prefix(self, level: MessageLevel) -> str:
        """Get a prefix icon for the message level."""
        prefixes = {
            MessageLevel.ERROR: "✗ ",
            MessageLevel.WARNING: "⚠ ",
            MessageLevel.SUCCESS: "✓ ",
            MessageLevel.INFO: "ℹ ",
            MessageLevel.DEBUG: "• ",
        }
        return prefixes.get(level, "")

    # =========================================================================
    # File Operations
    # =========================================================================

    def _render_file_listing(self, msg: FileListingMessage) -> None:
        """Render a directory listing matching the old Rich-formatted output."""
        # Header on single line
        rec_flag = f"(recursive={msg.recursive})"
        banner = self._format_banner("directory_listing", "DIRECTORY LISTING")
        self._console.print(
            f"\n{banner} "
            f"📂 [bold cyan]{msg.directory}[/bold cyan] [dim]{rec_flag}[/dim]\n"
        )

        # Directory header
        dir_name = msg.directory.rstrip("/").split("/")[-1] or msg.directory
        self._console.print(f"📁 [bold blue]{dir_name}[/bold blue]")

        # Build tree structure from flat list
        for entry in msg.files:
            # Calculate indentation based on depth
            prefix = ""
            for d in range(entry.depth + 1):
                if d == entry.depth:
                    prefix += "└── "
                else:
                    prefix += "    "

            if entry.type == "dir":
                self._console.print(f"{prefix}📁 [bold blue]{entry.path}/[/bold blue]")
            else:
                icon = self._get_file_icon(entry.path)
                if entry.size > 0:
                    size_str = f" [dim]({self._format_size(entry.size)})[/dim]"
                else:
                    size_str = ""
                self._console.print(
                    f"{prefix}{icon} [green]{entry.path}[/green]{size_str}"
                )

        # Summary
        self._console.print("\n[bold cyan]Summary:[/bold cyan]")
        self._console.print(
            f"📁 [blue]{msg.dir_count} directories[/blue], "
            f"📄 [green]{msg.file_count} files[/green] "
            f"[dim]({self._format_size(msg.total_size)} total)[/dim]"
        )

    def _render_file_content(self, msg: FileContentMessage) -> None:
        """Render a file read - just show the header, not the content.

        The file content is for the LLM only, not for display in the UI.
        """
        # Build line info
        line_info = ""
        if msg.start_line is not None and msg.num_lines is not None:
            end_line = msg.start_line + msg.num_lines - 1
            line_info = f" [dim](lines {msg.start_line}-{end_line})[/dim]"

        # Just print the header - content is for LLM only
        banner = self._format_banner("read_file", "READ FILE")
        self._console.print(
            f"\n{banner} 📂 [bold cyan]{msg.path}[/bold cyan]{line_info}"
        )

    def _render_grep_result(self, msg: GrepResultMessage) -> None:
        """Render grep results grouped by file matching old format."""
        import re

        # Header
        banner = self._format_banner("grep", "GREP")
        self._console.print(
            f"\n{banner} 📂 [dim]{msg.directory} for '{msg.search_term}'[/dim]"
        )

        if not msg.matches:
            self._console.print(
                f"[dim]No matches found for '{msg.search_term}' "
                f"in {msg.directory}[/dim]"
            )
            return

        # Group by file
        by_file: Dict[str, list] = {}
        for match in msg.matches:
            by_file.setdefault(match.file_path, []).append(match)

        # Show verbose or concise based on message flag
        if msg.verbose:
            # Verbose mode: Show full output with line numbers and content
            for file_path in sorted(by_file.keys()):
                file_matches = by_file[file_path]
                match_word = "match" if len(file_matches) == 1 else "matches"
                self._console.print(
                    f"\n[dim]📄 {file_path} ({len(file_matches)} {match_word})[/dim]"
                )

                # Show each match with line number and content
                for match in file_matches:
                    line = match.line_content
                    # Extract the actual search term (not ripgrep flags)
                    search_term = msg.search_term.split()[-1]
                    if search_term.startswith("-"):
                        parts = msg.search_term.split()
                        search_term = parts[0] if parts else msg.search_term

                    # Case-insensitive highlighting
                    if search_term and not search_term.startswith("-"):
                        highlighted_line = re.sub(
                            f"({re.escape(search_term)})",
                            r"[bold yellow]\1[/bold yellow]",
                            line,
                            flags=re.IGNORECASE,
                        )
                    else:
                        highlighted_line = line

                    ln = match.line_number
                    self._console.print(f"  [dim]{ln:4d}[/dim] │ {highlighted_line}")
        else:
            # Concise mode (default): Show only file summaries
            self._console.print("")
            for file_path in sorted(by_file.keys()):
                file_matches = by_file[file_path]
                match_word = "match" if len(file_matches) == 1 else "matches"
                self._console.print(
                    f"[dim]📄 {file_path} ({len(file_matches)} {match_word})[/dim]"
                )

        # Summary - subtle
        match_word = "match" if msg.total_matches == 1 else "matches"
        file_word = "file" if len(by_file) == 1 else "files"
        num_files = len(by_file)
        self._console.print(
            f"[dim]Found {msg.total_matches} {match_word} "
            f"across {num_files} {file_word}[/dim]"
        )

        # Trailing newline for spinner separation
        self._console.print()

    # =========================================================================
    # Diff
    # =========================================================================

    def _render_diff(self, msg: DiffMessage) -> None:
        """Render a diff with beautiful syntax highlighting."""
        # Operation-specific styling
        op_icons = {"create": "✨", "modify": "✏️", "delete": "🗑️"}
        op_colors = {"create": "green", "modify": "yellow", "delete": "red"}
        icon = op_icons.get(msg.operation, "📄")
        op_color = op_colors.get(msg.operation, "white")

        # Header on single line
        banner = self._format_banner("edit_file", "EDIT FILE")
        self._console.print(
            f"\n{banner} "
            f"{icon} [{op_color}]{msg.operation.upper()}[/{op_color}] "
            f"[bold cyan]{msg.path}[/bold cyan]"
        )

        if not msg.diff_lines:
            return

        # Reconstruct unified diff text from diff_lines for format_diff_with_colors
        diff_text_lines = []
        for line in msg.diff_lines:
            if line.type == "add":
                diff_text_lines.append(f"+{line.content}")
            elif line.type == "remove":
                diff_text_lines.append(f"-{line.content}")
            else:  # context
                # Don't add space prefix to diff headers - they need to be preserved
                # exactly for syntax highlighting to detect the file extension
                if line.content.startswith(("---", "+++", "@@", "diff ", "index ")):
                    diff_text_lines.append(line.content)
                else:
                    diff_text_lines.append(f" {line.content}")

        diff_text = "\n".join(diff_text_lines)

        # Use the beautiful syntax-highlighted diff formatter
        formatted_diff = format_diff_with_colors(diff_text)
        self._console.print(formatted_diff)

    # =========================================================================
    # Shell Output
    # =========================================================================

    def _render_shell_start(self, msg: ShellStartMessage) -> None:
        """Render shell command start notification."""
        # Escape command to prevent Rich markup injection
        safe_command = escape_rich_markup(msg.command)
        # Header showing command is starting
        banner = self._format_banner("shell_command", "SHELL COMMAND")
        self._console.print(f"\n{banner} 🚀 [dim]$ {safe_command}[/dim]")

        # Show working directory if specified
        if msg.cwd:
            safe_cwd = escape_rich_markup(msg.cwd)
            self._console.print(f"[dim]📂 Working directory: {safe_cwd}[/dim]")

        # Show timeout
        self._console.print(f"[dim]⏱ Timeout: {msg.timeout}s[/dim]")

    def _render_shell_line(self, msg: ShellLineMessage) -> None:
        """Render shell output line preserving ANSI codes."""
        from rich.text import Text

        # Use Text.from_ansi() to parse ANSI codes into Rich styling
        # This preserves colors while still being safe
        text = Text.from_ansi(msg.line)

        # Make all shell output dim to reduce visual noise
        self._console.print(text, style="dim")

    def _render_shell_output(self, msg: ShellOutputMessage) -> None:
        """Render shell command output - just a trailing newline for spinner separation.

        Shell command results are already returned to the LLM via tool responses,
        so we don't need to clutter the UI with redundant output.
        """
        # Just print trailing newline for spinner separation
        self._console.print()

    # =========================================================================
    # Agent Messages
    # =========================================================================

    def _render_agent_reasoning(self, msg: AgentReasoningMessage) -> None:
        """Render agent reasoning matching old format."""
        # Header matching old format
        banner = self._format_banner("agent_reasoning", "AGENT REASONING")
        self._console.print(f"\n{banner}")

        # Current reasoning
        self._console.print("[bold cyan]Current reasoning:[/bold cyan]")
        # Render reasoning as markdown
        md = Markdown(msg.reasoning)
        self._console.print(md)

        # Next steps (if any)
        if msg.next_steps and msg.next_steps.strip():
            self._console.print("\n[bold cyan]Planned next steps:[/bold cyan]")
            md_steps = Markdown(msg.next_steps)
            self._console.print(md_steps)

        # Trailing newline for spinner separation
        self._console.print()

    def _render_agent_response(self, msg: AgentResponseMessage) -> None:
        """Render agent response with header and markdown formatting."""
        # Header
        banner = self._format_banner("agent_response", "AGENT RESPONSE")
        self._console.print(f"\n{banner}\n")

        # Content (markdown or plain)
        if msg.is_markdown:
            md = Markdown(msg.content)
            self._console.print(md)
        else:
            self._console.print(msg.content)

    def _render_subagent_invocation(self, msg: SubAgentInvocationMessage) -> None:
        """Render sub-agent invocation header with nice formatting."""
        # Header with agent name and session
        session_type = (
            "New session"
            if msg.is_new_session
            else f"Continuing ({msg.message_count} messages)"
        )
        banner = self._format_banner("invoke_agent", "🤖 INVOKE AGENT")
        self._console.print(
            f"\n{banner} "
            f"[bold cyan]{msg.agent_name}[/bold cyan] "
            f"[dim]({session_type})[/dim]"
        )

        # Session ID
        self._console.print(f"[dim]Session:[/dim] [bold]{msg.session_id}[/bold]")

        # Prompt (truncated if too long, rendered as markdown)
        prompt_display = (
            msg.prompt[:200] + "..." if len(msg.prompt) > 200 else msg.prompt
        )
        self._console.print("[dim]Prompt:[/dim]")
        md_prompt = Markdown(prompt_display)
        self._console.print(md_prompt)

    def _render_subagent_response(self, msg: SubAgentResponseMessage) -> None:
        """Render sub-agent response with markdown formatting."""
        # Response header
        banner = self._format_banner("subagent_response", "✓ AGENT RESPONSE")
        self._console.print(f"\n{banner} [bold cyan]{msg.agent_name}[/bold cyan]")

        # Render response as markdown
        md = Markdown(msg.response)
        self._console.print(md)

        # Footer with session info
        self._console.print(
            f"\n[dim]Session [bold]{msg.session_id}[/bold] saved "
            f"({msg.message_count} messages)[/dim]"
        )

    # =========================================================================
    # User Interaction
    # =========================================================================

    async def _render_user_input_request(self, msg: UserInputRequest) -> None:
        """Render input prompt and send response back to bus."""
        prompt = msg.prompt_text
        if msg.default_value:
            prompt += f" [{msg.default_value}]"
        prompt += ": "

        # Get input (password hides input)
        if msg.input_type == "password":
            value = self._console.input(prompt, password=True)
        else:
            value = self._console.input(f"[cyan]{prompt}[/cyan]")

        # Use default if empty
        if not value and msg.default_value:
            value = msg.default_value

        # Send response back
        response = UserInputResponse(prompt_id=msg.prompt_id, value=value)
        self._bus.provide_response(response)

    async def _render_confirmation_request(self, msg: ConfirmationRequest) -> None:
        """Render confirmation dialog and send response back."""
        # Show title and description - escape to prevent markup injection
        safe_title = escape_rich_markup(msg.title)
        safe_description = escape_rich_markup(msg.description)
        self._console.print(f"\n[bold yellow]{safe_title}[/bold yellow]")
        self._console.print(safe_description)

        # Show options
        options_str = "/".join(msg.options)
        prompt = f"[{options_str}]"

        while True:
            choice = self._console.input(f"[cyan]{prompt}[/cyan] ").strip().lower()

            # Check for match
            for i, opt in enumerate(msg.options):
                if choice == opt.lower() or choice == opt[0].lower():
                    confirmed = i == 0  # First option is "confirm"

                    # Get feedback if allowed
                    feedback = None
                    if msg.allow_feedback:
                        feedback = self._console.input(
                            "[dim]Feedback (optional): [/dim]"
                        )
                        feedback = feedback if feedback else None

                    response = ConfirmationResponse(
                        prompt_id=msg.prompt_id,
                        confirmed=confirmed,
                        feedback=feedback,
                    )
                    self._bus.provide_response(response)
                    return

            self._console.print(f"[red]Please enter one of: {options_str}[/red]")

    async def _render_selection_request(self, msg: SelectionRequest) -> None:
        """Render selection menu and send response back."""
        safe_prompt = escape_rich_markup(msg.prompt_text)
        self._console.print(f"\n[bold]{safe_prompt}[/bold]")

        # Show numbered options - escape to prevent markup injection
        for i, opt in enumerate(msg.options):
            safe_opt = escape_rich_markup(opt)
            self._console.print(f"  [cyan]{i + 1}[/cyan]. {safe_opt}")

        if msg.allow_cancel:
            self._console.print("  [dim]0. Cancel[/dim]")

        while True:
            choice = self._console.input("[cyan]Enter number: [/cyan]").strip()

            try:
                idx = int(choice)
                if msg.allow_cancel and idx == 0:
                    response = SelectionResponse(
                        prompt_id=msg.prompt_id,
                        selected_index=-1,
                        selected_value="",
                    )
                    self._bus.provide_response(response)
                    return

                if 1 <= idx <= len(msg.options):
                    response = SelectionResponse(
                        prompt_id=msg.prompt_id,
                        selected_index=idx - 1,
                        selected_value=msg.options[idx - 1],
                    )
                    self._bus.provide_response(response)
                    return
            except ValueError:
                pass

            self._console.print(f"[red]Please enter 1-{len(msg.options)}[/red]")

    # =========================================================================
    # Control Messages
    # =========================================================================

    def _render_spinner_control(self, msg: SpinnerControl) -> None:
        """Handle spinner control messages."""
        # Note: Rich's spinner/status is typically used as a context manager.
        # For full spinner support, we'd need a more complex implementation.
        # For now, we just print the status text.
        if msg.action == "start" and msg.text:
            self._console.print(f"[dim]⠋ {msg.text}[/dim]")
        elif msg.action == "update" and msg.text:
            self._console.print(f"[dim]⠋ {msg.text}[/dim]")
        elif msg.action == "stop":
            pass  # Spinner stopped

    def _render_divider(self, msg: DividerMessage) -> None:
        """Render a horizontal divider."""
        chars = {"light": "─", "heavy": "━", "double": "═"}
        char = chars.get(msg.style, "─")
        rule = Rule(style="dim", characters=char)
        self._console.print(rule)

    # =========================================================================
    # Status Messages
    # =========================================================================

    def _render_status_panel(self, msg: StatusPanelMessage) -> None:
        """Render a status panel with key-value fields."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="bold cyan")
        table.add_column("Value")

        for key, value in msg.fields.items():
            table.add_row(key, value)

        panel = Panel(table, title=f"[bold]{msg.title}[/bold]", border_style="blue")
        self._console.print(panel)

    def _render_version_check(self, msg: VersionCheckMessage) -> None:
        """Render version check information."""
        if msg.update_available:
            cur = msg.current_version
            latest = msg.latest_version
            self._console.print(f"[dim]⬆ Update available: {cur} → {latest}[/dim]")
        else:
            self._console.print(
                f"[dim]✓ You're on the latest version ({msg.current_version})[/dim]"
            )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _format_size(self, size_bytes: int) -> str:
        """Format byte size to human readable matching old format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def _get_file_icon(self, file_path: str) -> str:
        """Get an emoji icon for a file based on its extension."""
        import os

        ext = os.path.splitext(file_path)[1].lower()
        icons = {
            # Python
            ".py": "🐍",
            ".pyw": "🐍",
            # JavaScript/TypeScript
            ".js": "📜",
            ".jsx": "📜",
            ".ts": "📜",
            ".tsx": "📜",
            # Web
            ".html": "🌐",
            ".htm": "🌐",
            ".xml": "🌐",
            ".css": "🎨",
            ".scss": "🎨",
            ".sass": "🎨",
            # Documentation
            ".md": "📝",
            ".markdown": "📝",
            ".rst": "📝",
            ".txt": "📝",
            # Config
            ".json": "⚙️",
            ".yaml": "⚙️",
            ".yml": "⚙️",
            ".toml": "⚙️",
            ".ini": "⚙️",
            # Images
            ".jpg": "🖼️",
            ".jpeg": "🖼️",
            ".png": "🖼️",
            ".gif": "🖼️",
            ".svg": "🖼️",
            ".webp": "🖼️",
            # Audio
            ".mp3": "🎵",
            ".wav": "🎵",
            ".ogg": "🎵",
            ".flac": "🎵",
            # Video
            ".mp4": "🎬",
            ".avi": "🎬",
            ".mov": "🎬",
            ".webm": "🎬",
            # Documents
            ".pdf": "📄",
            ".doc": "📄",
            ".docx": "📄",
            ".xls": "📄",
            ".xlsx": "📄",
            ".ppt": "📄",
            ".pptx": "📄",
            # Archives
            ".zip": "📦",
            ".tar": "📦",
            ".gz": "📦",
            ".rar": "📦",
            ".7z": "📦",
            # Executables
            ".exe": "⚡",
            ".dll": "⚡",
            ".so": "⚡",
            ".dylib": "⚡",
        }
        return icons.get(ext, "📄")


# =============================================================================
# Export all public symbols
# =============================================================================

__all__ = [
    "RendererProtocol",
    "RichConsoleRenderer",
    "DEFAULT_STYLES",
    "DIFF_STYLES",
]
