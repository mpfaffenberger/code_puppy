"""/theme — pick a curated banner+content color theme, interactively or by name.

UX:
  /theme               → interactive split-panel picker with live preview
  /theme <N>           → apply theme number N (1-14)
  /theme <name>        → apply by name (ocean, forest, sunset, vaporwave,
                         bubblegum-pink, mocha, latte, tokyo-night,
                         deep-black, solarized-light, github-light,
                         rose-pine-dawn, surprise, default)
  /theme reset         → restore Code Puppy defaults (alias of /theme default)
  /theme show          → show current banner → color mapping

The 13th option (🎲 Surprise Me) re-rolls a random palette every time.
The 14th option (🔄 Restore Defaults) puts everything back to factory.

Plays nice with /colors — same color pool, same config keys.
"""

from __future__ import annotations

import asyncio
import concurrent.futures

from code_puppy.callbacks import register_callback
from code_puppy.command_line.colors_menu import BANNER_DISPLAY_INFO
from code_puppy.config import (
    get_all_banner_colors,
    reset_all_banner_colors,
)
from code_puppy.messaging import emit_error, emit_info, emit_warning

from . import content_styles as cs
from . import osc_palette as osc
from . import rich_themes as rt
from .picker import interactive_theme_picker
from .themes import (
    MENU_BY_NAME,
    apply,
    color_remap_for,
    colors_for,
    content_styles_for,
    resolve_theme_arg,
    terminal_palette_for,
)

_INTERACTIVE_TIMEOUT_SECONDS = 300  # 5 min — generous; user is browsing


def _custom_help():
    return [
        ("theme", "Pick a curated banner+content color theme (interactive: /theme)"),
    ]


# --- Rendering helpers ------------------------------------------------------
# Note: emit_info escapes Rich markup for safety, so these helpers emit
# plain text only. Pretty visual previews live in the picker (which uses
# Rich directly).
def _format_banner_mapping(mapping: dict[str, str]) -> str:
    lines = []
    for banner, color in mapping.items():
        display, icon = BANNER_DISPLAY_INFO.get(banner, (banner, ""))
        prefix = f"{icon} " if icon else "  "
        lines.append(f"  {prefix}{display:<24} -> {color}")
    return "\n".join(lines)


def _format_content_mapping(mapping: dict[str, str]) -> str:
    lines = []
    for key, style in mapping.items():
        lines.append(f"  {key:<14} -> {style}")
    return "\n".join(lines)


def _announce_applied(theme_name: str) -> None:
    """Quietly confirm the theme is applied. Mappings available via /theme show."""
    theme = MENU_BY_NAME[theme_name]
    emit_info(
        f"{theme['icon']} {theme['label']} theme applied. "
        f"(/theme show to inspect, /theme default to undo)"
    )


# --- Interactive flow -------------------------------------------------------
def _run_interactive_picker() -> str | None:
    """Run the async TUI from a sync command handler."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(lambda: asyncio.run(interactive_theme_picker()))
        return future.result(timeout=_INTERACTIVE_TIMEOUT_SECONDS)


def _apply_theme(theme_name: str) -> None:
    """Apply banner colors + content styles + inline remap + terminal palette.

    `default` is special: resets banner config, content styles, Rich color
    remap, AND the terminal-level OSC palette.
    """
    if theme_name == "default":
        reset_all_banner_colors()
        cs.restore_defaults()
        rt.restore()
        osc.reset_palette()
    else:
        banner_mapping = colors_for(theme_name)
        content_mapping = content_styles_for(theme_name)
        remap = color_remap_for(theme_name)
        terminal_palette = terminal_palette_for(theme_name)
        apply(banner_mapping)
        cs.apply_content_styles(content_mapping)
        rt.apply_remap(remap)
        if terminal_palette:
            osc.apply_palette(terminal_palette)

    _announce_applied(theme_name)


# --- Command handler --------------------------------------------------------
def _handle_theme(command: str, name: str):
    if name != "theme":
        return None

    parts = command.split()
    sub = parts[1].lower() if len(parts) > 1 else ""

    if sub == "":
        try:
            chosen = _run_interactive_picker()
        except Exception as e:  # pragma: no cover — defensive UX
            emit_error(f"Theme picker failed: {e}")
            return True
        if chosen is None:
            emit_info("🎨 Theme unchanged.")
            return True
        _apply_theme(chosen)
        return True

    if sub == "show":
        emit_info(
            "🎨 Current theme:\n"
            "Banners:\n"
            + _format_banner_mapping(get_all_banner_colors())
            + "\nContent text:\n"
            + _format_content_mapping(cs.get_all_content_styles())
        )
        return True

    theme_name = resolve_theme_arg(sub)
    if theme_name is None:
        valid = ", ".join(
            k for k in MENU_BY_NAME if k not in ("random", "reset", "defaults")
        )
        emit_warning(
            f"Unknown theme '{sub}'. Try /theme for the picker, "
            f"or pick one of: {valid}."
        )
        return True

    _apply_theme(theme_name)
    return True


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_theme)
