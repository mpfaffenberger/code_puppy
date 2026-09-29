"""Shared interactive-startup presentation (logo + help lines).

Both the classic interactive loop (``cli_runner.interactive_mode``) and the
Textual TUI (``tui.app.CooperApp.on_mount``) greet the user with the same
``CODE PUPPY`` logo and a short block of help text. Keeping that here means
one source of truth (DRY) instead of two copies drifting apart.

The help text is *mode-aware*: the classic hints (Tab help overlay, the
Ctrl+X Ctrl+S speculation chord) don't exist in the Textual UI, which
cancels with Esc, steers with Ctrl+T, and opens a palette with Ctrl+P. We
emit the correct variant for each.
"""

from __future__ import annotations

from rich.text import Text

from code_puppy.i18n import t
from code_puppy.messaging import emit_info, emit_system_message
from code_puppy.platform_utils import startup_banner_text

# Top-to-bottom blue -> cyan -> green gradient for the figlet logo.
_GRADIENT_COLORS = ["bright_blue", "bright_cyan", "bright_green"]


def build_logo_renderable(columns: int | None = None) -> Text | None:
    """Return the gradient figlet logo as a Rich renderable.

    Width-aware via :func:`startup_banner_text`: the full ``CODE PUPPY`` when
    it fits in ``columns``, ``PUP`` on narrow terminals. Returns ``None``
    when ``pyfiglet`` isn't installed so callers can fall back to a plain
    greeting.
    """
    try:
        import pyfiglet
    except ImportError:
        return None

    intro_lines = pyfiglet.figlet_format(
        startup_banner_text(columns), font="ansi_shadow"
    ).split("\n")
    logo = Text()
    for line_num, line in enumerate(intro_lines):
        if line.strip():
            color_idx = min(line_num // 2, len(_GRADIENT_COLORS) - 1)
            logo.append(line + "\n", style=_GRADIENT_COLORS[color_idx])
        else:
            logo.append("\n")
    return logo


def emit_logo_fallback() -> None:
    """Emit a plain greeting when the figlet logo can't be built."""
    emit_system_message(t("cli.loading"))


def emit_interactive_help(textual: bool = False) -> None:
    """Emit the interactive-mode help lines through the message bus.

    Both UIs consume the legacy queue, so this works in either mode; it just
    has to actually be *called* from each startup path. The truecolor
    warning is intentionally excluded (it's classic-only).
    """
    from code_puppy.config import get_agency_level, get_speculative_code_mode_enabled

    if textual:
        emit_system_message(t("tui.help.keys"))
    else:
        # A Text object (not a plain str): the SYSTEM renderer escapes Rich
        # markup in plain strings, so this is the way to render it bold.
        emit_system_message(Text(t("cli.help.press_tab"), style="bold"))
    # Tell the user how relentless the puppy is configured to be.
    emit_info(t("cli.agency.status", level=get_agency_level().upper()))
    if textual:
        # The speculation toggle is a classic line-editor chord; the TUI
        # binds Ctrl+X natively, so advertising it here would be a lie.
        return
    speculation_key = (
        "cli.speculation.on"
        if get_speculative_code_mode_enabled()
        else "cli.speculation.off"
    )
    emit_info(t(speculation_key))
