"""Content-text style theming (level 1).

The banner plugin already paints the banner headers. This module paints the
body text underneath by mutating the `RichConsoleRenderer`'s style maps.

Two upstream knobs:
    code_puppy.messaging.rich_renderer.DEFAULT_STYLES  (MessageLevel -> style)
    code_puppy.messaging.rich_renderer.DIFF_STYLES     ({add,remove,context} -> style)

These dicts are **copied** by `RichConsoleRenderer.__init__`. Mutating them
after construction won't affect already-running renderers, so we also reach
into live renderer instances (via gc) and update their `_styles` dict in place.

Pure logic + a small amount of surgical monkey patching. Config-persisted so
preferences survive restarts.

Zen: namespaces are one honking great idea; we keep everything in one place.
"""

from __future__ import annotations

import gc
from typing import Callable

from code_puppy.config import get_value, set_config_value
from code_puppy.messaging import rich_renderer
from code_puppy.messaging.messages import MessageLevel

# --- The 8 themable content keys -------------------------------------------
# We expose a flat string-keyed namespace so config persistence is trivial.
CONTENT_KEYS: tuple[str, ...] = (
    "info",
    "warning",
    "success",
    "error",
    "debug",
    "diff_add",
    "diff_remove",
    "diff_context",
)

_LEVEL_KEYS: dict[str, MessageLevel] = {
    "info": MessageLevel.INFO,
    "warning": MessageLevel.WARNING,
    "success": MessageLevel.SUCCESS,
    "error": MessageLevel.ERROR,
    "debug": MessageLevel.DEBUG,
}
_DIFF_KEYS: dict[str, str] = {
    "diff_add": "add",
    "diff_remove": "remove",
    "diff_context": "context",
}

# Snapshot taken at import time (before any mutation). This becomes our
# "factory default" for restore.
DEFAULT_CONTENT_STYLES: dict[str, str] = {
    **{k: rich_renderer.DEFAULT_STYLES[lvl] for k, lvl in _LEVEL_KEYS.items()},
    **{k: rich_renderer.DIFF_STYLES[v] for k, v in _DIFF_KEYS.items()},
}

_CONFIG_PREFIX = "content_style_"


# --- Persistence helpers ----------------------------------------------------
def _config_key(name: str) -> str:
    return f"{_CONFIG_PREFIX}{name}"


def get_content_style(name: str) -> str:
    """Return current style for `name`, falling back to the factory default."""
    if name not in DEFAULT_CONTENT_STYLES:
        raise KeyError(f"Unknown content style: {name!r}")
    return get_value(_config_key(name)) or DEFAULT_CONTENT_STYLES[name]


def get_all_content_styles() -> dict[str, str]:
    """Return the current effective mapping for every content key."""
    return {name: get_content_style(name) for name in CONTENT_KEYS}


def _persist(mapping: dict[str, str]) -> None:
    for name, style in mapping.items():
        set_config_value(_config_key(name), style)


# --- Mutation -------------------------------------------------------------
def _push_to_renderers(mapping: dict[str, str]) -> None:
    """Push a {content_key: style} mapping into module dicts AND live renderers.

    Live renderers copy `DEFAULT_STYLES` at __init__, so mutating the module
    dict isn't enough — we walk live instances and patch them too.
    """
    # 1. Module-level dicts (in case fresh renderers spawn later)
    for k, lvl in _LEVEL_KEYS.items():
        rich_renderer.DEFAULT_STYLES[lvl] = mapping[k]
    for k, diff_key in _DIFF_KEYS.items():
        rich_renderer.DIFF_STYLES[diff_key] = mapping[k]

    # 2. Live renderer instances (the ones actually painting your terminal)
    try:
        for obj in gc.get_objects():
            if isinstance(obj, rich_renderer.RichConsoleRenderer):
                styles = getattr(obj, "_styles", None)
                if isinstance(styles, dict):
                    for k, lvl in _LEVEL_KEYS.items():
                        styles[lvl] = mapping[k]
    except Exception:
        # gc walks can be flaky in odd interpreters; never let that nuke UX
        pass


def apply_content_styles(
    mapping: dict[str, str],
    persist: bool = True,
    setter: Callable[[dict[str, str]], None] | None = None,
) -> None:
    """Apply a content style mapping live + (optionally) persist it.

    Args:
        mapping: dict with every key in CONTENT_KEYS.
        persist: if True, write to config so it survives restarts.
        setter: injectable for tests; defaults to the real persister.
    """
    missing = set(CONTENT_KEYS) - mapping.keys()
    if missing:
        raise ValueError(f"Content style mapping missing keys: {sorted(missing)}")

    _push_to_renderers(mapping)
    if persist:
        (setter or _persist)(mapping)


def restore_defaults(persist: bool = True) -> dict[str, str]:
    """Restore factory-default content styles. Returns the mapping applied."""
    apply_content_styles(DEFAULT_CONTENT_STYLES, persist=persist)
    return dict(DEFAULT_CONTENT_STYLES)


def reapply_from_config() -> None:
    """On plugin load, push any persisted overrides into the live renderer.

    Safe to call multiple times; no-op if config has no overrides
    (since get_content_style falls back to defaults).
    """
    _push_to_renderers(get_all_content_styles())
