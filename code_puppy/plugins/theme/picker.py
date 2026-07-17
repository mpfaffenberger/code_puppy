"""Interactive theme picker TUI.

Reuses prompt_toolkit's full-screen pattern (cribbed from
``code_puppy.command_line.colors_menu``) but pared down to the curated
theme choices, with a live preview that shows banners AND content text
in the theme's body styles.
"""

from __future__ import annotations

import asyncio
import io
import random
import sys
from typing import Optional

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame
from rich.console import Console

from code_puppy.command_line.colors_menu import (
    BANNER_DISPLAY_INFO,
    BANNER_SAMPLE_CONTENT,
)

from .themes import (
    MENU,
    color_remap_for,
    colors_for,
    content_styles_for,
    terminal_palette_for,
)

# A few representative banners to show in the preview pane (keeps it readable).
PREVIEW_BANNERS = [
    "thinking",
    "agent_response",
    "shell_command",
    "read_file",
    "edit_file",
    "grep",
    "invoke_agent",
    "subagent_response",
]

# Sample lines to demonstrate body content styling.
CONTENT_SAMPLES = [
    ("info", "i  Heads up, this is an info message."),
    ("success", "v Success - task finished cleanly."),
    ("warning", "! Warning - proceeding with caution."),
    ("error", "x Error - something went wrong."),
    ("debug", ". debug trace (only shown if you ask)"),
]

# Inline-markup samples to demonstrate the Level 2 color remap.
# These mirror the kind of hardcoded tags scattered through the renderer.
INLINE_MARKUP_SAMPLES = [
    "[bold cyan]bold cyan headline[/bold cyan]",
    "[dim cyan]dim cyan detail[/dim cyan]",
    "[bold blue]bold blue label[/bold blue]",
    "[magenta]magenta accent[/magenta]",
]


def _render_preview(theme_name: str, surprise_seed: int) -> ANSI:
    """Render a full-color preview of the theme using Rich -> ANSI.

    ``surprise_seed`` makes the "Surprise Me" preview stable while highlighted
    (otherwise it would re-roll on every redraw - dizzying).
    """
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=True,
        width=70,
        legacy_windows=False,
        color_system="truecolor",
        no_color=False,
        force_interactive=True,
    )

    rng = random.Random(surprise_seed) if theme_name == "surprise" else None
    banner_mapping = colors_for(theme_name, rng=rng)
    content_mapping = content_styles_for(theme_name, rng=rng)
    color_remap = color_remap_for(theme_name, rng=rng)
    theme = dict(MENU)[theme_name]

    # Apply the Level 2 remap to *this preview console only* so users see
    # exactly what the inline markup will look like.
    from . import rich_themes as rt

    if color_remap:
        rt._install_patch(console, color_remap)

    console.print("[bold]" + "=" * 60 + "[/bold]")
    console.print(
        f"[bold cyan] {theme['icon']} {theme['label']}[/bold cyan]  "
        f"[dim]- {theme['blurb']}[/dim]"
    )
    console.print("[bold]" + "=" * 60 + "[/bold]")
    console.print()

    # Banner samples
    for banner in PREVIEW_BANNERS:
        if banner not in banner_mapping:
            continue
        display, icon = BANNER_DISPLAY_INFO[banner]
        color = banner_mapping[banner]
        icon_str = f" {icon}" if icon else ""
        console.print(
            f"[bold white on {color}] {display} [/bold white on {color}]{icon_str}"
        )
        sample = BANNER_SAMPLE_CONTENT.get(banner, "")
        first_line = sample.split("\n", 1)[0]
        if first_line:
            console.print(f"    [dim]{first_line}[/dim]")
        console.print()

    # Content text samples (the new bit - Level 1 theming)
    console.print("[bold]" + "-" * 60 + "[/bold]")
    console.print("[bold dim]content text styles:[/bold dim]")
    for key, text in CONTENT_SAMPLES:
        style = content_mapping[key]
        console.print(f"  [{style}]{text}[/]")

    # Inline markup samples (Level 2 - remapped colors)
    console.print("[bold dim]inline markup remap:[/bold dim]")
    for sample in INLINE_MARKUP_SAMPLES:
        console.print("  " + sample)
    console.print("[bold]" + "=" * 60 + "[/bold]")

    if theme_name == "surprise":
        console.print(
            "[dim italic]Every apply re-rolls a fresh random palette.[/dim italic]"
        )
    elif theme_name == "default":
        console.print(
            "[dim italic]Resets banners + content to Mist defaults.[/dim italic]"
        )

    # Terminal-palette note (Level 3 - OSC sequences recolor the whole window)
    tp = terminal_palette_for(theme_name)
    if tp:
        bg = tp.get("bg", "?")
        fg = tp.get("fg", "?")
        ansi = tp.get("ansi") or []
        ansi_note = f" + {len(ansi)}-color ANSI palette" if ansi else ""

        # Big swatch block: shows the actual bg/fg combo so the user can
        # judge readability BEFORE applying. The OSC isn't fired live
        # (would flicker the whole terminal on every arrow keypress).
        console.print("[bold dim]terminal palette preview:[/bold dim]")
        sample_bg = bg if bg.startswith("#") else "#000000"
        sample_fg = fg if fg.startswith("#") else "#ffffff"
        # Two rows of the bg/fg combo with real text on top for readability check.
        console.print(
            f"  [{sample_fg} on {sample_bg}]"
            f"  Mist keeps the interface clear and readable   [/]"
        )
        console.print(
            f"  [{sample_fg} on {sample_bg}]"
            f"  bg={bg}  fg={fg}{' ' * max(0, 18 - len(bg) - len(fg))}  [/]"
        )

        # ANSI palette: 16 swatches in 2 rows of 8 so users see the rainbow.
        if ansi:
            console.print("[bold dim]ANSI palette (slots 0-15):[/bold dim]")
            for row_start in (0, 8):
                line = "  "
                for slot in range(row_start, min(row_start + 8, len(ansi))):
                    swatch_color = (
                        ansi[slot] if ansi[slot].startswith("#") else "#888888"
                    )
                    line += f"[on {swatch_color}]      [/]"
                console.print(line)

        console.print(
            f"[bold yellow]\u26a1[/bold yellow] [dim]Enter applies these to the whole terminal"
            f"{ansi_note}.[/dim]"
        )
    elif theme_name == "default":
        console.print(
            "[bold yellow]\u26a1[/bold yellow] [dim]Resets terminal bg/fg/ANSI palette too.[/dim]"
        )
    return ANSI(buffer.getvalue())


def _format_menu(selected_index: int) -> FormattedText:
    """Build the left-hand menu text with a highlighted selection."""
    lines: list[tuple[str, str]] = [
        ("bold cyan", "Pick a Theme"),
        ("", "\n\n"),
    ]
    for i, (name, theme) in enumerate(MENU):
        prefix = "> " if i == selected_index else "  "
        style = "fg:ansigreen bold" if i == selected_index else ""
        line = f"{prefix}{i + 1}. {theme['icon']} {theme['label']}"
        lines.append((style, line))
        lines.append(("", "\n"))
        lines.append(("fg:ansigray", f"     {theme['blurb']}"))
        lines.append(("", "\n\n"))

    lines.append(("", "\n"))
    lines.append(
        (
            "fg:ansicyan",
            "Up/Down Navigate  |  Enter Apply  |  Esc / Ctrl-C Cancel",
        )
    )
    return FormattedText(lines)


async def interactive_theme_picker() -> Optional[str]:
    """Show the full-screen theme picker.

    Returns:
        The selected theme key (e.g. ``"ocean"``) or ``None`` if cancelled.
    """
    from code_puppy.tools.command_runner import set_awaiting_user_input

    selected = [0]
    result: list[Optional[str]] = [None]
    # Stable seed for "Surprise Me" preview per highlight; bumps on each focus.
    surprise_seed = [random.randint(0, 1_000_000)]

    set_awaiting_user_input(True)
    sys.stdout.write("\033[?1049h\033[2J\033[H")
    sys.stdout.flush()
    await asyncio.sleep(0.05)

    kb = KeyBindings()

    def _refresh_surprise_seed_if_focused() -> None:
        name, _ = MENU[selected[0]]
        if name == "surprise":
            surprise_seed[0] = random.randint(0, 1_000_000)

    @kb.add("up")
    @kb.add("c-p")
    def _(event):
        selected[0] = (selected[0] - 1) % len(MENU)
        _refresh_surprise_seed_if_focused()
        event.app.invalidate()

    @kb.add("down")
    @kb.add("c-n")
    def _(event):
        selected[0] = (selected[0] + 1) % len(MENU)
        _refresh_surprise_seed_if_focused()
        event.app.invalidate()

    @kb.add("enter")
    def _(event):
        result[0] = MENU[selected[0]][0]
        event.app.exit()

    @kb.add("escape")
    @kb.add("c-c")
    def _(event):
        result[0] = None
        event.app.exit()

    def _current_preview_style() -> str:
        """Dynamic prompt_toolkit style for the preview pane.

        Paints the WHOLE right pane background with the selected theme's bg,
        and picks a readable fg, so the user instantly sees the new color.
        Updates every render via prompt_toolkit's dynamic-style support.
        """
        name, _ = MENU[selected[0]]
        try:
            tp = terminal_palette_for(name)
        except Exception:
            tp = None
        if not tp:
            return ""
        bg = tp.get("bg")
        fg = tp.get("fg", "")
        parts = []
        if bg:
            parts.append(f"bg:{bg}")
        if fg:
            parts.append(f"fg:{fg}")
        return " ".join(parts)

    left = Window(
        content=FormattedTextControl(lambda: _format_menu(selected[0])),
        width=40,
    )
    right = Window(
        content=FormattedTextControl(
            lambda: _render_preview(MENU[selected[0]][0], surprise_seed[0])
        ),
        style=_current_preview_style,
    )

    layout = Layout(
        VSplit([Frame(left, title="Themes"), Frame(right, title="Live Preview")])
    )
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
        color_depth="DEPTH_24_BIT",
    )

    try:
        await app.run_async()
    finally:
        set_awaiting_user_input(False)
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()

    return result[0]
