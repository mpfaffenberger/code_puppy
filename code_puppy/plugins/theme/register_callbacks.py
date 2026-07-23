"""/theme — pick a curated banner+content color theme, interactively or by name.

UX:
  /theme               → interactive split-panel picker with live preview
  /theme <N>           → apply theme number N (1-16)
  /theme <name>        → apply by name (ocean, forest, sunset, vaporwave,
                         bubblegum-pink, purple-puppy, mocha, latte,
                         tokyo-night, green-screen, deep-black, solarized-light,
                         github-light, rose-pine-dawn, surprise, default)
  /theme reset         → restore Code Puppy defaults (alias of /theme default)
  /theme show          → show current banner → color mapping

The 15th option (Surprise Me) re-rolls a random palette every time.
The 16th option (Restore Defaults) puts everything back to factory.

Plays nice with /colors — same color pool, same config keys.
"""

from __future__ import annotations

import asyncio
import concurrent.futures

from code_puppy.callbacks import register_callback

# NOTE: Sibling module imports (.themes, .picker, .content_styles, .osc_palette,
# .rich_themes, .prompt_toolkit_theme) and heavier code_puppy imports
# (colors_menu, config, messaging) live inside the functions that use them
# rather than at module scope. This keeps plugin discovery cheap and — more
# importantly — avoids transitively requiring prompt_toolkit just to load
# the theme package. Callbacks like _apply_default_theme_on_first_run
# short-circuit on already-configured installs, so the deferred modules
# never get loaded on the common launch path.

_INTERACTIVE_TIMEOUT_SECONDS = 300  # 5 min — generous; user is browsing
_ACTIVE_THEME_CONFIG_KEY = "theme_active_theme"
_DEFAULT_THEME_NAME = "tokyo-night"
_LEGACY_THEME_NAME = "legacy-custom"


def _custom_help():
    return [
        ("theme", "Pick a curated banner+content color theme (interactive: /theme)"),
    ]


# --- Rendering helpers ------------------------------------------------------
# Note: emit_info escapes Rich markup for safety, so these helpers emit
# plain text only. Pretty visual previews live in the picker (which uses
# Rich directly).
def _format_banner_mapping(mapping: dict[str, str]) -> str:
    from code_puppy.command_line.colors_menu import BANNER_DISPLAY_INFO

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
    from code_puppy.messaging import emit_info

    from .themes import MENU_BY_NAME

    theme = MENU_BY_NAME[theme_name]
    emit_info(
        f"{theme['icon']} {theme['label']} theme applied. "
        f"(/theme show to inspect, /theme default to undo)"
    )


# --- Interactive flow -------------------------------------------------------
def _run_interactive_picker() -> str | None:
    """Run the async TUI from a sync command handler."""
    from .picker import interactive_theme_picker

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(lambda: asyncio.run(interactive_theme_picker()))
        return future.result(timeout=_INTERACTIVE_TIMEOUT_SECONDS)


def _apply_theme(theme_name: str, *, announce: bool = True) -> None:
    """Apply banner colors + content styles + inline remap + terminal palette.

    `default` is special: resets banner config, content styles, Rich color
    remap, AND the terminal-level OSC palette.
    """
    from code_puppy.config import reset_all_banner_colors, set_config_value

    from . import content_styles as cs
    from . import osc_palette as osc
    from . import rich_themes as rt
    from .themes import (
        apply,
        color_remap_for,
        colors_for,
        content_styles_for,
        terminal_palette_for,
    )

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

    set_config_value(_ACTIVE_THEME_CONFIG_KEY, theme_name)
    if announce:
        _announce_applied(theme_name)


def _active_terminal_palette() -> tuple[str, dict] | None:
    """Return the active curated theme and its complete persisted palette."""
    from code_puppy.config import get_value

    from . import osc_palette as osc

    active_theme = get_value(_ACTIVE_THEME_CONFIG_KEY)
    if not active_theme or active_theme in {"default", _LEGACY_THEME_NAME}:
        return None
    palette = osc.get_saved_palette()
    if not palette or len(palette.get("ansi") or []) < 16:
        return None
    return active_theme, palette


def _termflow_style(default_style):
    """Derive Termflow's truecolor Markdown chrome from the active theme."""
    active = _active_terminal_palette()
    if active is None:
        return default_style
    _, palette = active
    ansi = palette["ansi"]

    from termflow.render.style import RenderStyle

    return RenderStyle(
        bright=ansi[14],
        head=ansi[10],
        symbol=ansi[13],
        grey=ansi[8],
        dark=palette.get("bg", ansi[0]),
        mid=ansi[8],
        light=ansi[7],
        link=ansi[12],
        error=ansi[9],
    )


def _termflow_highlighter(default_highlighter):
    """Build syntax colors from the active theme instead of Monokai."""
    active = _active_terminal_palette()
    if active is None:
        return default_highlighter
    active_theme, palette = active
    ansi = palette["ansi"]

    from pygments.formatters.terminal256 import TerminalTrueColorFormatter
    from pygments.style import Style
    from pygments.token import (
        Comment,
        Error,
        Keyword,
        Name,
        Number,
        Operator,
        String,
        Token,
    )
    from termflow.syntax import Highlighter

    if active_theme in {"green-screen", "green", "crt"}:
        # Preserve monochrome phosphor while giving token classes enough
        # separation to remain useful on both addition and deletion lines.
        token_styles = {
            Token: "#72a85b",
            Comment: "#456b4f",
            Error: "#7dff68",
            Keyword: "#39e75f",
            Name.Function: "#75ff87",
            Number: "#8acb72",
            Operator: "#63b96a",
            String: "#9bdc79",
        }
    elif active_theme in {"solarized-light", "solarized"}:
        token_styles = {
            Token: "#657b83",
            Comment: "#586e75",
            Error: "#dc322f",
            Keyword: "#859900",
            Name.Function: "#268bd2",
            Number: "#2aa198",
            Operator: "#657b83",
            String: "#2aa198",
        }
    else:
        token_styles = {
            Token: ansi[7],
            Comment: ansi[8],
            Error: ansi[9],
            Keyword: ansi[13],
            Name.Function: ansi[14],
            Number: ansi[11],
            Operator: ansi[6],
            String: ansi[10],
        }

    theme_style = type(
        "CodePuppyThemeStyle",
        (Style,),
        {"background_color": palette.get("bg"), "styles": token_styles},
    )
    highlighter = Highlighter()
    highlighter._formatter = TerminalTrueColorFormatter(style=theme_style)
    if active_theme in {"green-screen", "green", "crt"}:
        # Added lines lean brighter/yellower; removed lines become cooler and
        # more muted. Small shifts retain the token palette's internal contrast.
        highlighter.diff_line_tints = {
            "added": (10, 14, -8),
            "removed": (-18, -4, 10),
        }
    return highlighter


def _prompt_text_color(default_color):
    """Use the active terminal foreground for the persistent prompt buffer."""
    active = _active_terminal_palette()
    return active[1].get("fg", default_color) if active else default_color


def _prompt_toolkit_style(*args, **kwargs):
    """Lazy shim for prompt_toolkit_theme.merge_with_active_style.

    The real implementation lives in .prompt_toolkit_theme which pulls in
    prompt_toolkit.styles at import time. Deferring the import until the
    prompt_toolkit_style callback actually fires (during REPL init, well
    after startup) keeps that cost off the launch-time critical path.
    """
    from .prompt_toolkit_theme import merge_with_active_style

    return merge_with_active_style(*args, **kwargs)


def _apply_default_theme_on_first_run() -> None:
    """Apply Tokyo Night once, preserving explicit and legacy theme choices."""
    from code_puppy.config import get_value, set_config_value

    from . import osc_palette as osc

    if get_value(_ACTIVE_THEME_CONFIG_KEY):
        return

    if osc.get_saved_palette():
        # Theme persistence predates the active-theme marker. Treat an existing
        # palette as an intentional choice and migrate without changing it.
        set_config_value(_ACTIVE_THEME_CONFIG_KEY, _LEGACY_THEME_NAME)
        return

    _apply_theme(_DEFAULT_THEME_NAME, announce=False)


# --- Command handler --------------------------------------------------------
def _handle_theme(command: str, name: str):
    if name != "theme":
        return None

    from code_puppy.config import get_all_banner_colors
    from code_puppy.messaging import emit_error, emit_info, emit_warning

    from . import content_styles as cs
    from .themes import MENU_BY_NAME, resolve_theme_arg

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


register_callback("startup", _apply_default_theme_on_first_run)
register_callback("termflow_style", _termflow_style)
register_callback("termflow_highlighter", _termflow_highlighter)
register_callback("prompt_text_color", _prompt_text_color)
register_callback("prompt_toolkit_style", _prompt_toolkit_style)
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_theme)
