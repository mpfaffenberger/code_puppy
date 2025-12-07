"""Rich console renderer for structured messages.

This module implements the presentation layer for Code Puppy's messaging system.
It consumes structured messages from the MessageBus and renders them using Rich.

The renderer is responsible for ALL presentation decisions - the messages contain
only structured data with no formatting hints.
"""

from typing import Dict, Optional, Protocol, runtime_checkable

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

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
    ShellOutputMessage,
    SpinnerControl,
    StatusPanelMessage,
    TextMessage,
    UserInputRequest,
    VersionCheckMessage,
)

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
            # Call the sync version of render
            self._do_render(message)
        except Exception as e:
            # Don't let rendering errors crash the loop
            self._console.print(f"[dim red]Render error: {e}[/dim red])")

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
        elif isinstance(message, ShellOutputMessage):
            self._render_shell_output(message)
        elif isinstance(message, AgentReasoningMessage):
            self._render_agent_reasoning(message)
        elif isinstance(message, AgentResponseMessage):
            self._render_agent_response(message)
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
        """Render a text message with appropriate styling."""
        style = self._styles.get(msg.level, "white")
        prefix = self._get_level_prefix(msg.level)
        self._console.print(f"{prefix}{msg.text}", style=style)

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
        """Render a directory listing as a tree."""
        tree = Tree(f"📁 [bold cyan]{msg.directory}[/bold cyan]")

        # Build tree structure from flat list
        for entry in msg.files:
            indent = "  " * entry.depth
            if entry.type == "dir":
                icon = "📁"
                style = "bold blue"
            else:
                icon = "📄"
                style = "green"
            size_str = (
                f" [dim]({self._format_size(entry.size)})[/dim]"
                if entry.size > 0
                else ""
            )
            tree.add(f"{indent}{icon} [{style}]{entry.path}[/{style}]{size_str}")

        self._console.print(tree)
        self._console.print(
            f"[dim]{msg.dir_count} directories, {msg.file_count} files "
            f"({self._format_size(msg.total_size)} total)[/dim]"
        )

    def _render_file_content(self, msg: FileContentMessage) -> None:
        """Render file content with syntax highlighting."""
        # Determine language from file extension
        ext = msg.path.rsplit(".", 1)[-1] if "." in msg.path else ""
        lexer = self._get_lexer_for_extension(ext)

        # Create header
        header = f"📄 {msg.path}"
        if msg.start_line:
            header += (
                f" (lines {msg.start_line}-{msg.start_line + (msg.num_lines or 0) - 1})"
            )
        header += f" [{msg.total_lines} lines, ~{msg.num_tokens} tokens]"

        self._console.print(f"[bold cyan]{header}[/bold cyan]")

        # Render with syntax highlighting
        syntax = Syntax(
            msg.content,
            lexer,
            line_numbers=True,
            start_line=msg.start_line or 1,
            theme="monokai",
        )
        self._console.print(syntax)

    def _render_grep_result(self, msg: GrepResultMessage) -> None:
        """Render grep results grouped by file."""
        self._console.print(
            f"[bold]Found {msg.total_matches} matches for [cyan]'{msg.search_term}'[/cyan] "
            f"in {msg.files_searched} files[/bold]"
        )

        if not msg.matches:
            return

        # Group by file
        by_file: Dict[str, list] = {}
        for match in msg.matches:
            by_file.setdefault(match.file_path, []).append(match)

        for file_path, matches in by_file.items():
            self._console.print(f"\n[bold cyan]{file_path}[/bold cyan]")
            for match in matches:
                # Highlight the search term in the line
                line_text = Text(f"  {match.line_number}: ")
                line_text.append(match.line_content.strip())
                self._console.print(line_text)

    # =========================================================================
    # Diff
    # =========================================================================

    def _render_diff(self, msg: DiffMessage) -> None:
        """Render a diff with color coding."""
        # Header
        op_colors = {"create": "green", "modify": "yellow", "delete": "red"}
        op_color = op_colors.get(msg.operation, "white")
        self._console.print(
            f"[{op_color}]{msg.operation.upper()}[/{op_color}] [bold]{msg.path}[/bold]"
        )

        if not msg.diff_lines:
            return

        # Render diff lines
        for line in msg.diff_lines:
            style = DIFF_STYLES.get(line.type, "white")
            prefix = {"add": "+", "remove": "-", "context": " "}.get(line.type, " ")
            self._console.print(f"[{style}]{prefix} {line.content}[/{style}]")

    # =========================================================================
    # Shell Output
    # =========================================================================

    def _render_shell_output(self, msg: ShellOutputMessage) -> None:
        """Render shell command output."""
        # Command header
        exit_style = "green" if msg.exit_code == 0 else "red"
        self._console.print(
            f"[bold]❯[/bold] [cyan]{msg.command}[/cyan] "
            f"[{exit_style}](exit {msg.exit_code})[/{exit_style}] "
            f"[dim]{msg.duration_seconds:.2f}s[/dim]"
        )

        # stdout
        if msg.stdout:
            self._console.print(msg.stdout)

        # stderr (if any)
        if msg.stderr:
            self._console.print(f"[red]{msg.stderr}[/red]")

    # =========================================================================
    # Agent Messages
    # =========================================================================

    def _render_agent_reasoning(self, msg: AgentReasoningMessage) -> None:
        """Render agent reasoning in a panel."""
        content = Text()
        content.append("🧠 ", style="bold")
        content.append(msg.reasoning)

        if msg.next_steps:
            content.append("\n\n")
            content.append("📋 Next Steps:\n", style="bold cyan")
            content.append(msg.next_steps)

        panel = Panel(
            content,
            title="[bold]Agent Reasoning[/bold]",
            border_style="blue",
            padding=(0, 1),
        )
        self._console.print(panel)

    def _render_agent_response(self, msg: AgentResponseMessage) -> None:
        """Render agent response, optionally as markdown."""
        if msg.is_markdown:
            md = Markdown(msg.content)
            self._console.print(md)
        else:
            self._console.print(msg.content)

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
        # Show title and description
        self._console.print(f"\n[bold yellow]{msg.title}[/bold yellow]")
        self._console.print(msg.description)

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
        self._console.print(f"\n[bold]{msg.prompt_text}[/bold]")

        # Show numbered options
        for i, opt in enumerate(msg.options):
            self._console.print(f"  [cyan]{i + 1}[/cyan]. {opt}")

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
            self._console.print(
                f"[yellow]⬆ Update available: {msg.current_version} → {msg.latest_version}[/yellow]"
            )
        else:
            self._console.print(
                f"[green]✓ You're on the latest version ({msg.current_version})[/green]"
            )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _format_size(self, size: int) -> str:
        """Format byte size to human readable."""
        for unit in ["", "K", "M", "G", "T"]:
            if abs(size) < 1024:
                return f"{size:.1f}{unit}B" if unit else f"{size}B"
            size //= 1024
        return f"{size}PB"

    def _get_lexer_for_extension(self, ext: str) -> str:
        """Map file extension to Pygments lexer name."""
        mapping = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
            "jsx": "javascript",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "md": "markdown",
            "html": "html",
            "css": "css",
            "sh": "bash",
            "bash": "bash",
            "sql": "sql",
            "rs": "rust",
            "go": "go",
            "rb": "ruby",
            "c": "c",
            "cpp": "cpp",
            "h": "c",
            "hpp": "cpp",
            "java": "java",
            "kt": "kotlin",
            "swift": "swift",
            "toml": "toml",
            "ini": "ini",
            "xml": "xml",
            "dockerfile": "dockerfile",
        }
        return mapping.get(ext.lower(), "text")


# =============================================================================
# Export all public symbols
# =============================================================================

__all__ = [
    "RendererProtocol",
    "RichConsoleRenderer",
    "DEFAULT_STYLES",
    "DIFF_STYLES",
]
