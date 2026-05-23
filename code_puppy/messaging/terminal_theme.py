"""Terminal-native theme resolution.

Code Puppy renders code blocks via Rich's ``Markdown`` and ``Syntax``. Both
accept a ``code_theme`` argument naming a Pygments style. Most Pygments styles
emit truecolor (``\\e[38;2;R;G;Bm``) escape sequences, which silently override
the user's terminal palette — exactly the contract we want to *respect*, not
ignore. Rich ships two ANSI-named Pygments styles for this very reason:

* ``ansi_dark``  — uses ANSI color names; reads well on dark terminals
* ``ansi_light`` — uses ANSI color names; reads well on light terminals

This module picks between them by sniffing the terminal's background. The
detection itself is best-effort:

1. ``COLORFGBG`` env var (set by many terminals, including rxvt/urxvt,
   konsole, and Terminal.app via the user's profile). Format is
   ``"<fg>;<bg>"`` with ANSI color indices; indices 0–6 and 8 mean dark
   background, the rest mean light.
2. (deliberately not implemented) OSC 11 query — would require writing to
   ``/dev/tty`` and reading back with a timeout. YAGNI for v1. If users on
   exotic terminals need it, they can set ``CODE_PUPPY_TERMINAL_BG=light``
   or override ``code_theme`` directly.

The resolver also honors two escape hatches:

* ``CODE_PUPPY_TERMINAL_BG`` env (``light`` / ``dark``) — forces detection.
* ``code_theme`` config key — bypasses detection entirely; pass any
  Pygments style name (``monokai``, ``github-dark``, etc.) for the old
  fixed-palette behavior.
"""

from __future__ import annotations

import os
from typing import Literal, Optional

__all__ = [
    "TerminalBackground",
    "detect_terminal_bg",
    "resolve_code_theme",
    "current_code_theme",
    "install_accessible_markdown_styles",
]

TerminalBackground = Literal["light", "dark"]

# ANSI palette indices that the COLORFGBG convention treats as "dark"
# backgrounds. Anything outside this set (typically 7 = white, 15 = bright
# white, 9–14 = brights) is treated as a light background.
_DARK_BG_INDICES = frozenset({"0", "1", "2", "3", "4", "5", "6", "8"})


def _bg_from_colorfgbg(raw: Optional[str]) -> Optional[TerminalBackground]:
    """Parse a ``COLORFGBG`` value into a background classification.

    Returns ``None`` if the value is missing or unparseable so callers can
    decide their own fallback.
    """
    if not raw:
        return None
    parts = raw.split(";")
    if not parts:
        return None
    # Last segment is the background index per the de-facto convention.
    bg_token = parts[-1].strip()
    if not bg_token:
        return None
    return "dark" if bg_token in _DARK_BG_INDICES else "light"


def _bg_from_env_override() -> Optional[TerminalBackground]:
    """Honor an explicit ``CODE_PUPPY_TERMINAL_BG`` env override."""
    forced = (os.environ.get("CODE_PUPPY_TERMINAL_BG") or "").strip().lower()
    if forced in ("light", "dark"):
        return forced  # type: ignore[return-value]
    return None


def detect_terminal_bg(default: TerminalBackground = "dark") -> TerminalBackground:
    """Best-effort terminal background detection.

    Priority:
      1. ``CODE_PUPPY_TERMINAL_BG`` env (``light`` / ``dark``).
      2. ``COLORFGBG`` env, parsed per the rxvt convention.
      3. ``default`` argument (defaults to ``"dark"`` — the safer assumption
         since dark themes dominate, and dim-on-dark is more readable than
         bright-on-light).

    Args:
        default: fallback when no signal is available.

    Returns:
        Either ``"light"`` or ``"dark"``.
    """
    forced = _bg_from_env_override()
    if forced is not None:
        return forced
    from_env = _bg_from_colorfgbg(os.environ.get("COLORFGBG"))
    if from_env is not None:
        return from_env
    return default


def resolve_code_theme(configured: Optional[str] = None) -> str:
    """Resolve the Pygments style name to hand to Rich.

    Args:
        configured: value from the ``code_theme`` config key (or ``None``).
            Special value ``"system"`` (the default) triggers terminal-bg
            detection. Anything else is passed through unchanged so users
            can opt back into fixed palettes like ``monokai``.

    Returns:
        A Pygments style name suitable for Rich's
        ``Markdown(code_theme=...)`` / ``Syntax(theme=...)`` arguments.
    """
    if configured and configured.strip().lower() != "system":
        return configured.strip()
    bg = detect_terminal_bg()
    return "ansi_light" if bg == "light" else "ansi_dark"


def install_accessible_markdown_styles() -> None:
    """Patch Rich's default ``markdown.code`` / ``markdown.kbd`` styles.

    Rich ships ``markdown.code`` as ``bold cyan on black`` and
    ``markdown.kbd`` as ``bold bright_yellow``. Both bake in specific ANSI
    slots that can collide with the user's theme. Concrete failure mode:
    Catppuccin Latte renders ANSI ``cyan`` as a greenish teal and ANSI
    ``black`` as a soft grey, which together produce an unreadable
    green-on-grey — catastrophic for users with red–green color vision
    deficiency (deuteranopia / protanopia, ~8% of men).

    The fix: replace both with ``Style(bold=True, reverse=True)``. Reverse
    swaps the terminal's *own* foreground/background pair, which is
    readable by construction (the user already chose a legible default).
    No color slot is selected, so no theme can mismatch it. Bold provides
    a redundant non-color signal that this region is code, satisfying
    WCAG 1.4.1 ("use of color").

    Idempotent. Mutates ``rich.themes.DEFAULT.styles`` directly so every
    subsequently-created ``Console`` inherits the patched values without
    each call site having to know.

    Must be called *before* any ``rich.console.Console`` is instantiated
    if you want existing-process consoles to pick up the new styles
    (Consoles snapshot a reference to ``themes.DEFAULT`` at construction
    time, but since they consult ``.styles`` lazily at render time,
    mutating the dict in place propagates anyway). Practically: call from
    package ``__init__.py``.
    """
    from rich import themes
    from rich.style import Style

    accessible = Style(bold=True, reverse=True)
    themes.DEFAULT.styles["markdown.code"] = accessible
    themes.DEFAULT.styles["markdown.kbd"] = accessible


def current_code_theme() -> str:
    """Convenience wrapper: read the ``code_theme`` config key and resolve.

    Imports ``code_puppy.config`` lazily to avoid circular imports (config
    already pulls in ``code_puppy.messaging``). Falls back to pure detection
    if config isn't importable for any reason.
    """
    try:
        from code_puppy.config import get_value

        configured = get_value("code_theme")
    except Exception:
        configured = None
    return resolve_code_theme(configured)
