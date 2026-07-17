"""Level 2 theming: live remap of inline Rich color names.

The renderer is full of hardcoded inline markup like `[bold cyan]`,
`[dim cyan]`, `[dim white]`, etc. Rich's stock `Theme` class can intercept
top-level *named styles* (`[my_style]`) but it does NOT remap base color
names embedded inside complex styles (`[bold cyan]` → still cyan).

So we go one level deeper: monkey-patch `Console.get_style()` on live console
instances. Every parsed style flows through it; we inspect the resolved
`Style.color` (and `bgcolor`) and swap it out if it's in our remap dict.

What we DO remap by default: "decorative" colors (cyan, blue, magenta,
bright_*). What we DON'T touch:
    - red    (errors must look angry)
    - yellow (warnings)
    - green  (success / diff add)
    - white  (high-contrast text)

That keeps semantic meaning intact across all themes.

Persisted via config so the patch survives Mist restarts.
"""

from __future__ import annotations

import gc
import json
import weakref
from typing import Callable, Optional

from rich.color import Color
from rich.console import Console
from rich.style import Style

from code_puppy.config import get_value, set_config_value
from code_puppy.messaging import rich_renderer

# --- Remap registry ---------------------------------------------------------
# Per-console bookkeeping: original get_style + current remap dict.
# WeakKeyDictionary so we don't keep dead consoles alive.
_PATCHED: "weakref.WeakKeyDictionary[Console, Callable]" = weakref.WeakKeyDictionary()

_CONFIG_KEY = "rich_color_remap_json"


# --- Color-swap mechanics ---------------------------------------------------
def _safe_parse(name: str) -> Optional[Color]:
    """Parse a color name, returning None if Rich can't handle it.

    Rich's named-color set is a strict subset of what some palettes use
    (e.g. ``cyan4`` and ``dark_orchid`` exist as banner backgrounds but
    aren't parseable as standalone Colors). Never let one bad name take
    down rendering.
    """
    try:
        return Color.parse(name)
    except Exception:
        return None


def _swap_color(style: Style, remap: dict[str, str]) -> Style:
    """Return a new Style with color/bgcolor remapped if names match."""
    changes = {}
    if style.color is not None and style.color.name in remap:
        new = _safe_parse(remap[style.color.name])
        if new is not None:
            changes["color"] = new
    if style.bgcolor is not None and style.bgcolor.name in remap:
        new = _safe_parse(remap[style.bgcolor.name])
        if new is not None:
            changes["bgcolor"] = new
    if not changes:
        return style
    return style + Style(**changes)


def _install_patch(console: Console, remap: dict[str, str]) -> None:
    """Patch a console's get_style to apply the remap. Idempotent."""
    if not remap:
        _uninstall_patch(console)
        return

    if console in _PATCHED:
        # Already patched — just swap the remap (closure captures it).
        # Re-install to refresh the captured remap dict.
        _uninstall_patch(console)

    original = console.get_style

    def patched(name, *, default=None):
        style = original(name, default=default)
        return _swap_color(style, remap)

    console.get_style = patched  # type: ignore[method-assign]
    _PATCHED[console] = original


def _uninstall_patch(console: Console) -> None:
    """Restore a console's original get_style. Safe if not patched."""
    original = _PATCHED.pop(console, None)
    if original is not None:
        try:
            console.get_style = original  # type: ignore[method-assign]
        except Exception:
            pass


# --- Live-console discovery -------------------------------------------------
def _live_consoles() -> list[Console]:
    """Find every live rich.console.Console instance via gc.

    Cheap heuristic but reliable. We patch them all so subagent renderers
    and the interactive renderer get themed alongside the bus renderer.
    """
    consoles: list[Console] = []
    try:
        for obj in gc.get_objects():
            if isinstance(obj, Console):
                consoles.append(obj)
        # Also grab any Console hanging off a live RichConsoleRenderer
        # (belt-and-suspenders; usually already covered by the above).
        for obj in gc.get_objects():
            if isinstance(obj, rich_renderer.RichConsoleRenderer):
                c = getattr(obj, "_console", None)
                if isinstance(c, Console) and c not in consoles:
                    consoles.append(c)
    except Exception:
        pass
    return consoles


# --- Public API -------------------------------------------------------------
def apply_remap(remap: dict[str, str], persist: bool = True) -> int:
    """Apply a color remap to every live Console. Returns how many got patched.

    Empty remap = restore (un-patch everything).
    """
    consoles = _live_consoles()
    if remap:
        for c in consoles:
            _install_patch(c, remap)
    else:
        for c in consoles:
            _uninstall_patch(c)

    if persist:
        try:
            set_config_value(_CONFIG_KEY, json.dumps(remap))
        except Exception:
            pass
    return len(consoles)


def restore() -> int:
    """Remove the color remap from every live console."""
    return apply_remap({}, persist=True)


def get_saved_remap() -> dict[str, str]:
    """Read the persisted remap from config (or {} if none)."""
    raw = get_value(_CONFIG_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def reapply_from_config() -> None:
    """Push any persisted remap back into live consoles. Safe to call repeatedly."""
    remap = get_saved_remap()
    if remap:
        apply_remap(remap, persist=False)


# --- Reasonable default palette presets -------------------------------------
# Used by themes.py. Keep semantic colors (red/yellow/green) untouched.
def make_remap(
    cyan: Optional[str] = None,
    blue: Optional[str] = None,
    magenta: Optional[str] = None,
    bright_cyan: Optional[str] = None,
    bright_blue: Optional[str] = None,
    bright_magenta: Optional[str] = None,
    white: Optional[str] = None,
) -> dict[str, str]:
    """Build a clean remap dict from optional kwargs (None = skip)."""
    mapping = {
        "cyan": cyan,
        "blue": blue,
        "magenta": magenta,
        "bright_cyan": bright_cyan,
        "bright_blue": bright_blue,
        "bright_magenta": bright_magenta,
        "white": white,
    }
    # Drop entries Rich can't parse so a typo in a theme never crashes the UI.
    return {k: v for k, v in mapping.items() if v and _safe_parse(v) is not None}
