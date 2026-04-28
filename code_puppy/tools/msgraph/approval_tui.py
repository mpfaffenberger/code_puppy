"""Approval TUI for MS Graph send operations.

Provides a polished full-screen approval experience for sensitive actions
like sending emails or Teams messages. Uses prompt_toolkit for rendering.

Layout:
  ┌─────────────────────────────┐
  │ 🔒 Approval Required        │
  │                             │
  │ Send Email                  │
  │ ─────────────────────────── │
  │ To: user@example.com        │
  │ Subject: Hello World        │
  │ Body:                       │  ← scrollable
  │   Full email content here   │
  │   that can be very long...  │
  │ ─────────────────────────── │
  ├─────────────────────────────┤
  │ ❯ ✓ Approve                 │  ← fixed
  │   ✗ Reject                  │
  │                             │
  │ ↑↓ Choice │ PgUp/Dn Scroll  │
  └─────────────────────────────┘

Navigation:
- Up/Down or j/k: Switch between Approve and Reject
- PgUp/PgDn or Ctrl+U/Ctrl+D: Scroll content
- Enter: Confirm selection
- y/Y: Quick approve
- n/N or Esc: Quick reject
- Ctrl+C: Cancel (reject)
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import sys
from dataclasses import dataclass

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.output import create_output
from prompt_toolkit.output.color_depth import ColorDepth
from prompt_toolkit.widgets import Frame
from rich.console import Console
from rich.markup import escape as rich_escape

# =============================================================================
# CONSTANTS
# =============================================================================

CURSOR_POINTER = "\u276f"
CHECK_APPROVE = "\u2713"
CROSS_REJECT = "\u2717"
LOCK_ICON = "\U0001f512"
SCROLL_INDICATOR = "\u2502"

COLOR_HEADER = "bold cyan"
COLOR_APPROVE = "bold green"
COLOR_REJECT = "bold red"
COLOR_CURSOR = "bold yellow"
COLOR_DIM = "dim"
COLOR_KEY = "bold white"
COLOR_LABEL = "bold white"
COLOR_VALUE = "white"
COLOR_BORDER = "cyan"
COLOR_SCROLL_HINT = "bold cyan"

PAD = "  "
MAX_PANEL_WIDTH = 100
SCROLL_PAGE_SIZE = 10
SCROLL_HALF_PAGE = 5

CI_ENV_VARS = ("CI", "GITHUB_ACTIONS", "JENKINS_URL", "GITLAB_CI", "TF_BUILD")


# =============================================================================
# STATE
# =============================================================================


@dataclass
class ApprovalState:
    """Holds the current approval UI state."""

    action: str
    details: dict[str, str]
    context: str = ""  # "mail" or "teams" for whitelist instructions; empty = none
    cursor: int = 0  # 0 = Approve, 1 = Reject
    content_scroll: int = 0  # scroll offset for the details panel
    result: str | None = None  # "approved", "rejected", or None

    @property
    def is_approve_selected(self) -> bool:
        return self.cursor == 0

    @property
    def is_reject_selected(self) -> bool:
        return self.cursor == 1

    def move_up(self) -> None:
        self.cursor = max(0, self.cursor - 1)

    def move_down(self) -> None:
        self.cursor = min(1, self.cursor + 1)

    def toggle(self) -> None:
        self.cursor = 1 - self.cursor

    def approve(self) -> None:
        self.result = "approved"

    def reject(self) -> None:
        self.result = "rejected"

    def confirm_selection(self) -> None:
        if self.cursor == 0:
            self.approve()
        else:
            self.reject()

    def scroll_up(self, lines: int = 1) -> None:
        self.content_scroll = max(0, self.content_scroll - lines)

    def scroll_down(self, lines: int = 1) -> None:
        self.content_scroll += lines

    def scroll_page_up(self) -> None:
        self.scroll_up(SCROLL_PAGE_SIZE)

    def scroll_page_down(self) -> None:
        self.scroll_down(SCROLL_PAGE_SIZE)

    def scroll_half_up(self) -> None:
        self.scroll_up(SCROLL_HALF_PAGE)

    def scroll_half_down(self) -> None:
        self.scroll_down(SCROLL_HALF_PAGE)


# =============================================================================
# RENDERING — CONTENT PANEL (scrollable)
# =============================================================================


def _get_whitelist_instructions(context: str) -> list[str]:
    """Get context-specific whitelist instructions.

    Args:
        context: "mail" or "teams"

    Returns:
        List of instruction lines to display.
    """
    if context == "mail":
        return [
            "",
            "💡 Tip: Skip this prompt for trusted recipients",
            "",
            "To whitelist email recipients, run:",
            '  /set msgraph_mail_whitelist = ["boss@walmart.com", "team@walmart.com"]',
            "",
            "Whitelisted recipients will auto-approve without prompting.",
        ]
    elif context == "teams":
        return [
            "",
            "💡 Tip: Skip this prompt for trusted recipients",
            "",
            "To whitelist Teams recipients, run:",
            '  /set msgraph_teams_whitelist = ["boss@walmart.com"]',
            "",
            "Supported formats:",
            "  • Email address for DMs: \"user@walmart.com\"",
            "  • Named group chat: \"chat:Daily Standup\"",
            "  • Channel: \"channel:Platform Team/General\"",
            "",
            "Whitelisted recipients will auto-approve without prompting.",
        ]
    return []


def _build_content_lines(state: ApprovalState, terminal_width: int) -> list[str]:
    """Build the full content as a list of rendered lines.

    Renders all details with Rich formatting, then splits into lines
    so we can apply scroll offset for the viewport.
    """
    buffer = io.StringIO()
    width = min(terminal_width, MAX_PANEL_WIDTH)
    console = Console(
        file=buffer,
        force_terminal=True,
        width=width,
        legacy_windows=False,
        color_system="truecolor",
        no_color=False,
        force_interactive=True,
    )

    # Header
    console.print()
    console.print(f"{PAD}[{COLOR_HEADER}]{LOCK_ICON} Approval Required[/{COLOR_HEADER}]")
    console.print()
    console.print(f"{PAD}[bold]{state.action}[/bold]")
    console.print()

    # Details
    border_width = min(60, width - 6)
    border = "\u2500" * border_width
    console.print(f"{PAD}[{COLOR_BORDER}]{border}[/{COLOR_BORDER}]")

    for key, value in state.details.items():
        escaped_value = rich_escape(value)

        # Short values on one line, long values get a labeled block
        if "\n" not in value and len(value) <= 80:
            console.print(
                f"{PAD}[{COLOR_LABEL}]{key}:[/{COLOR_LABEL}] "
                f"[{COLOR_VALUE}]{escaped_value}[/{COLOR_VALUE}]"
            )
        else:
            # Multi-line or long content: label on its own line, content indented
            console.print(f"{PAD}[{COLOR_LABEL}]{key}:[/{COLOR_LABEL}]")
            for line in escaped_value.splitlines():
                console.print(f"{PAD}  [{COLOR_VALUE}]{line}[/{COLOR_VALUE}]")

    console.print(f"{PAD}[{COLOR_BORDER}]{border}[/{COLOR_BORDER}]")

    # Add whitelist instructions
    whitelist_lines = _get_whitelist_instructions(state.context)
    for line in whitelist_lines:
        if line.startswith("  "):
            # Indented content (commands, bullet points)
            console.print(f"{PAD}[{COLOR_DIM}]{line}[/{COLOR_DIM}]")
        elif line.startswith("💡"):
            # Tip header - use a distinct color
            console.print(f"{PAD}[bold yellow]{line}[/bold yellow]")
        elif line:
            # Regular instruction text
            console.print(f"{PAD}[{COLOR_DIM}]{line}[/{COLOR_DIM}]")
        else:
            # Empty line for spacing
            console.print()

    return buffer.getvalue().splitlines()


def _render_content_panel(state: ApprovalState, viewport_height: int, terminal_width: int) -> ANSI:
    """Render the scrollable content area."""
    all_lines = _build_content_lines(state, terminal_width)
    total_lines = len(all_lines)

    # Clamp scroll offset
    max_scroll = max(0, total_lines - viewport_height)
    if state.content_scroll > max_scroll:
        state.content_scroll = max_scroll

    # Slice the viewport
    start = state.content_scroll
    end = start + viewport_height
    visible = all_lines[start:end]

    # Build output with scroll indicators
    output_lines = list(visible)

    # Add scroll hint if there's more content
    can_scroll_up = state.content_scroll > 0
    can_scroll_down = end < total_lines

    if can_scroll_up or can_scroll_down:
        hints = []
        if can_scroll_up:
            hints.append(f"\u2191 {state.content_scroll} lines above")
        if can_scroll_down:
            hints.append(f"\u2193 {total_lines - end} lines below")
        hint_text = " \u2502 ".join(hints)
        # Inject scroll hint as a Rich-styled line
        buf = io.StringIO()
        mini = Console(
            file=buf,
            force_terminal=True,
            width=min(terminal_width, MAX_PANEL_WIDTH),
            legacy_windows=False,
            color_system="truecolor",
        )
        mini.print(f"{PAD}[{COLOR_SCROLL_HINT}]{hint_text}[/{COLOR_SCROLL_HINT}]")
        output_lines.append(buf.getvalue().rstrip())

    return ANSI("\n".join(output_lines))


# =============================================================================
# RENDERING — ACTION PANEL (fixed)
# =============================================================================


def _render_action_panel(state: ApprovalState, terminal_width: int) -> ANSI:
    """Render the fixed approve/reject buttons and help text."""
    buffer = io.StringIO()
    width = min(terminal_width, MAX_PANEL_WIDTH)
    console = Console(
        file=buffer,
        force_terminal=True,
        width=width,
        legacy_windows=False,
        color_system="truecolor",
        no_color=False,
        force_interactive=True,
    )

    # Approve option
    if state.is_approve_selected:
        console.print(
            f"{PAD}[{COLOR_CURSOR}]{CURSOR_POINTER}[/{COLOR_CURSOR}] "
            f"[{COLOR_APPROVE}]{CHECK_APPROVE} Approve[/{COLOR_APPROVE}]"
        )
    else:
        console.print(f"{PAD}  [{COLOR_DIM}]{CHECK_APPROVE} Approve[/{COLOR_DIM}]")

    # Reject option
    if state.is_reject_selected:
        console.print(
            f"{PAD}[{COLOR_CURSOR}]{CURSOR_POINTER}[/{COLOR_CURSOR}] "
            f"[{COLOR_REJECT}]{CROSS_REJECT} Reject[/{COLOR_REJECT}]"
        )
    else:
        console.print(f"{PAD}  [{COLOR_DIM}]{CROSS_REJECT} Reject[/{COLOR_DIM}]")

    console.print()

    # Help bar
    console.print(
        f"{PAD}[{COLOR_DIM}]\u2191\u2193 Choice \u2502 Enter Confirm \u2502 "
        f"[{COLOR_KEY}]y[/{COLOR_KEY}] Approve \u2502 "
        f"[{COLOR_KEY}]n[/{COLOR_KEY}]/Esc Reject \u2502 "
        f"PgUp/Dn Scroll[/{COLOR_DIM}]"
    )

    return ANSI(buffer.getvalue())


# =============================================================================
# TUI LOOP
# =============================================================================

# Fixed height for the action panel (buttons + help)
_ACTION_PANEL_LINES = 5


async def _run_approval_tui(state: ApprovalState) -> bool:
    """Run the approval TUI and return True if approved."""
    kb = KeyBindings()

    # --- Choice navigation ---
    @kb.add("up")
    @kb.add("k")
    def move_up(event: KeyPressEvent) -> None:
        state.move_up()
        event.app.invalidate()

    @kb.add("down")
    @kb.add("j")
    def move_down(event: KeyPressEvent) -> None:
        state.move_down()
        event.app.invalidate()

    @kb.add("space")
    def toggle(event: KeyPressEvent) -> None:
        state.toggle()
        event.app.invalidate()

    @kb.add("enter")
    def confirm(event: KeyPressEvent) -> None:
        state.confirm_selection()
        event.app.exit()

    # --- Quick actions ---
    @kb.add("y")
    @kb.add("Y")
    def quick_approve(event: KeyPressEvent) -> None:
        state.approve()
        event.app.exit()

    @kb.add("n")
    @kb.add("N")
    @kb.add("escape")
    def quick_reject(event: KeyPressEvent) -> None:
        state.reject()
        event.app.exit()

    @kb.add("c-c")
    def ctrl_c(event: KeyPressEvent) -> None:
        state.reject()
        event.app.exit()

    # --- Content scrolling ---
    @kb.add("pageup")
    def page_up(event: KeyPressEvent) -> None:
        state.scroll_page_up()
        event.app.invalidate()

    @kb.add("pagedown")
    def page_down(event: KeyPressEvent) -> None:
        state.scroll_page_down()
        event.app.invalidate()

    @kb.add("c-u")
    def half_page_up(event: KeyPressEvent) -> None:
        state.scroll_half_up()
        event.app.invalidate()

    @kb.add("c-d")
    def half_page_down(event: KeyPressEvent) -> None:
        state.scroll_half_down()
        event.app.invalidate()

    # --- Layout ---
    def get_content_text() -> ANSI:
        term_size = shutil.get_terminal_size()
        term_w, term_h = term_size.columns, term_size.lines
        viewport_h = max(5, term_h - _ACTION_PANEL_LINES - 4)  # 4 for frame borders
        return _render_content_panel(state, viewport_h, term_w - 4)

    def get_action_text() -> ANSI:
        term_w = shutil.get_terminal_size().columns
        return _render_action_panel(state, term_w - 4)

    content_window = Window(
        content=FormattedTextControl(lambda: get_content_text()),
        wrap_lines=False,  # Rich already wraps at the right width
    )

    action_window = Window(
        content=FormattedTextControl(lambda: get_action_text()),
        height=Dimension(preferred=_ACTION_PANEL_LINES, max=_ACTION_PANEL_LINES),
        wrap_lines=False,  # Rich already wraps at the right width
    )

    root_container = Frame(
        HSplit([content_window, action_window]),
        title="",
    )

    layout = Layout(root_container)
    output = create_output(stdout=sys.__stdout__)

    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        mouse_support=False,
        color_depth=ColorDepth.DEPTH_24_BIT,
        output=output,
    )

    await app.run_async()
    return state.result == "approved"


# =============================================================================
# PUBLIC API
# =============================================================================


def is_interactive() -> bool:
    """Check if we're running in an interactive terminal."""
    try:
        if not sys.stdin.isatty():
            return False
    except (AttributeError, OSError):
        return False
    return not any(os.environ.get(var) for var in CI_ENV_VARS)


def request_approval(action: str, details: dict[str, str], context: str = "") -> bool:
    """Request user approval for a sensitive action via TUI.

    Shows a full-screen approval dialog with the action details.
    The details panel is scrollable for long content (PgUp/PgDn, Ctrl+U/D).
    Returns True if approved, False if rejected.

    Args:
        action: Short description of the action (e.g., "Send Email")
        details: Key/value pairs to display — full content, no truncation needed.
        context: "mail" or "teams" - determines which whitelist instructions to show.
            If empty, no whitelist instructions are displayed.

    Returns:
        True if user approved, False if rejected or non-interactive.

    Note:
        Unlike ask_user_question, this DOES work in sub-agent context.
        Sensitive actions (sending emails/messages) require explicit user
        approval regardless of which agent is executing them.
    """
    # Check for wiggum mode (autonomous loop)
    try:
        from code_puppy.command_line.wiggum_state import is_wiggum_active

        if is_wiggum_active():
            return False
    except ImportError:
        pass

    # Check for interactive terminal
    if not is_interactive():
        return False

    # Set awaiting user input flag if available
    set_awaiting_user_input = None
    try:
        from code_puppy.tools.command_runner import set_awaiting_user_input

        set_awaiting_user_input(True)
    except ImportError:
        pass

    try:
        state = ApprovalState(action=action, details=details, context=context)

        # Handle async context detection
        try:
            asyncio.get_running_loop()
            # Already in async context — fall back to simple prompt
            return _fallback_prompt(action, details, context=context)
        except RuntimeError:
            pass

        return asyncio.run(_run_approval_tui(state))
    finally:
        if set_awaiting_user_input is not None:
            set_awaiting_user_input(False)


def _fallback_prompt(action: str, details: dict[str, str], context: str = "") -> bool:
    """Fallback to simple y/N prompt when TUI can't be used."""
    from code_puppy.messaging.message_queue import emit_prompt

    lines = [f"\n{LOCK_ICON} Approval required \u2014 {action}"]
    for key, value in details.items():
        display_value = (value[:200] + "\u2026") if len(value) > 200 else value
        lines.append(f"   {key}: {display_value}")
    lines.append("")

    # Add whitelist tip
    if context == "mail":
        lines.append(
            '💡 Tip: /set msgraph_mail_whitelist = ["email@walmart.com"] to skip this prompt'
        )
    elif context == "teams":
        lines.append(
            '💡 Tip: /set msgraph_teams_whitelist = ["email@walmart.com"] to skip this prompt'
        )
    lines.append("")

    summary = "\n".join(lines)
    response = emit_prompt(f"{summary}\nDo you approve? [y/N]: ")

    return response.strip().lower() in ("y", "yes")
