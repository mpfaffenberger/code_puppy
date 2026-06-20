"""Pure rendering helpers for the ``/set`` interactive menu.

Kept in its own module so :mod:`set_menu` stays focused on state +
keybindings, and so the rendering functions can be unit-tested in
isolation without spinning up a prompt_toolkit app.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from code_puppy.command_line.set_menu_settings import Setting
from code_puppy.command_line.set_menu_values import display_value, is_default_value

KeyValueLine = Tuple[str, str]

_DEFAULT_PREFIX = "(Default) "
_DEFAULT_STYLE = "fg:ansibrightblack italic"


def truncate(text: str, max_len: int = 30) -> str:
    """Truncate ``text`` to ``max_len`` chars, appending ``...`` when cut."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def value_for_display(setting: Setting) -> str:
    """Resolve a setting's effective value, falling back to ``(not set)``."""
    value = display_value(setting)
    return value if value is not None else "(not set)"


def wrap(text: str, width: int = 55) -> List[str]:
    """Ad-hoc word wrap (avoids pulling in :mod:`textwrap` for one call)."""
    out: List[str] = []
    current = ""
    for word in text.split():
        if not current:
            current = word
            continue
        if len(current) + 1 + len(word) > width:
            out.append(current)
            current = word
        else:
            current += " " + word
    if current:
        out.append(current)
    return out


_KEY_HELP = (
    ("up/down", "Navigate", "fg:ansibrightblack"),
    ("left/right", "Page", "fg:ansibrightblack"),
    ("Enter", "Edit value", "fg:green"),
    ("/", "Search", "fg:ansibrightblack"),
    ("r", "Reset to default", "fg:ansibrightblack"),
    ("Esc", "Save & Exit", "fg:ansicyan"),
    ("Ctrl+C", "Cancel (discard)", "fg:ansired"),
)


def render_left_panel(
    entries: list,
    page: int,
    selected_idx: int,
    search_text: str,
    in_search_mode: bool,
    search_buffer: str,
    *,
    page_size: int,
    page_bounds,
    total_pages_fn,
) -> List[KeyValueLine]:
    """Render the left settings panel as a list of (style, text) pairs."""
    lines: List[KeyValueLine] = []
    total_pages = total_pages_fn(len(entries), page_size)
    start_idx, end_idx = page_bounds(page, len(entries), page_size)

    lines.append(("bold cyan", " Mist Config Settings"))
    lines.append(("fg:ansibrightblack", f"  (Page {page + 1}/{max(total_pages, 1)})"))
    if in_search_mode:
        lines.append(("fg:ansiyellow", f"  Searching: '{search_buffer}'"))
    elif search_text:
        lines.append(("fg:ansiyellow", f"  Filter: '{search_text}'"))
    lines.append(("", "\n\n"))

    current_category = ""
    for i in range(start_idx, end_idx):
        entry = entries[i]
        if entry.category.name != current_category:
            if current_category:
                lines.append(("", "\n"))
            lines.append(("bold fg:ansiblue", f"  {entry.category.name}"))
            lines.append(("", "\n"))
            current_category = entry.category.name

        is_selected = i == selected_idx
        val_display = truncate(value_for_display(entry.setting))
        from_default = is_default_value(entry.setting)
        if is_selected:
            lines.append(("fg:ansigreen bold", f"> {entry.setting.display_name}"))
            lines.append(("fg:ansigreen", "  = "))
            if from_default:
                lines.append((_DEFAULT_STYLE, _DEFAULT_PREFIX))
            lines.append(("fg:ansigreen", val_display))
        else:
            lines.append(("", f"  {entry.setting.display_name}"))
            lines.append(("fg:ansibrightblack", "    = "))
            if from_default:
                lines.append((_DEFAULT_STYLE, _DEFAULT_PREFIX))
            lines.append(("fg:ansibrightblack", val_display))
        lines.append(("", "\n"))

    lines.append(("", "\n"))
    for key_combo, label, style in _KEY_HELP:
        lines.append((style, f"  {key_combo:<10} {label}"))
        lines.append(("", "\n"))
    return lines


_TYPE_DISPLAY = {
    "bool": "true / false",
    "int": "integer",
    "float": "float",
    "string": "free text",
}


def _type_display(setting: Setting, valid_values_str: str) -> str:
    if setting.type_hint == "choice":
        return f"one of: {valid_values_str}"
    return _TYPE_DISPLAY.get(setting.type_hint, setting.type_hint)


def render_right_panel(entry: Optional[object]) -> List[KeyValueLine]:
    """Render the right details panel for the currently-selected entry."""
    lines: List[KeyValueLine] = [
        ("bold cyan", " Setting Details"),
        ("", "\n\n"),
    ]
    if entry is None:
        lines.append(("fg:ansiyellow", "  No setting selected."))
        lines.append(("", "\n"))
        return lines

    setting = entry.setting
    valid_values_str = ", ".join(setting.valid_values)

    for label, value, style in (
        ("Key: ", setting.key, "fg:ansicyan"),
        ("Name: ", setting.display_name, "fg:ansigreen"),
        ("Category: ", entry.category.name, "fg:ansiblue"),
    ):
        lines.append(("bold", label))
        lines.append((style, value))
        lines.append(("", "\n\n"))

    lines.append(("bold", "Type: "))
    lines.append(("fg:ansiyellow", _type_display(setting, valid_values_str)))
    lines.append(("", "\n\n"))

    lines.append(("bold", "Current Value: "))
    current = display_value(setting)
    from_default = is_default_value(setting)
    if current:
        if from_default:
            lines.append((_DEFAULT_STYLE, _DEFAULT_PREFIX))
        lines.append(("fg:ansigreen", current))
    else:
        lines.append(("fg:ansibrightblack", "(not set)"))
    if setting.requires_restart:
        lines.append(("fg:ansiyellow", "  (restart required)"))
    lines.append(("", "\n\n"))

    lines.append(("bold", "Description:"))
    lines.append(("", "\n"))
    for wrapped in wrap(setting.description):
        lines.append(("fg:ansibrightblack", "  " + wrapped))
        lines.append(("", "\n"))
    lines.append(("", "\n"))

    if setting.type_hint == "choice" and setting.valid_values:
        lines.append(("bold", "Valid Values:"))
        lines.append(("", "\n"))
        for val in setting.valid_values:
            if val == current:
                lines.append(("fg:ansigreen", f"   {val}  (current)"))
            else:
                lines.append(("fg:ansibrightblack", f"    {val}"))
            lines.append(("", "\n"))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", " Tip: Press Enter to edit this setting."))
    return lines
