"""Interactive terminal UI for configuring puppy settings."""

import asyncio
import sys
from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)
from code_puppy.command_line.set_menu_settings import SETTINGS_CATEGORIES
from code_puppy.config import (
    get_value,
    set_config_value,
)
from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 12


def _current_value(key: str) -> Optional[str]:
    return get_value(key)


def _build_flat_settings() -> List[Tuple[str, str, str, str, str, str]]:
    flat: List[Tuple[str, str, str, str, str, str]] = []
    curated_keys: set = set()
    # Add curated settings with proper descriptions
    for category, settings in SETTINGS_CATEGORIES:
        for key, display_name, description, type_hint, valid_values in settings:
            values_str = ", ".join(valid_values) if valid_values else ""
            flat.append(
                (category, key, display_name, description, type_hint, values_str)
            )
            curated_keys.add(key)
    # Add all other available keys from get_config_keys() to a Dynamic section
    from code_puppy.config import get_config_keys

    for key in get_config_keys():
        if key not in curated_keys:
            flat.append(
                (
                    " Dynamic",
                    key,
                    key.replace("_", " ").title(),
                    "Auto-detected setting (no description available)",
                    _detect_type(key),
                    "",
                )
            )
    return flat


def _detect_type(key: str) -> str:
    """Auto-detect the type of a setting from its current value or key name."""
    current = _current_value(key)
    # Check key name patterns first
    if "_enabled" in key or "_mode" in key:
        return "bool"
    # Try to parse current value
    if current is None:
        return "string"
    lower = current.strip().lower()
    if lower in ("true", "false", "1", "0", "yes", "no", "on", "off"):
        return "bool"
    try:
        int(current)
        return "int"
    except (ValueError, TypeError):
        pass
    try:
        float(current)
        return "float"
    except (ValueError, TypeError):
        pass
    return "string"


def _render_left_panel(
    entries: List,
    page: int,
    selected_idx: int,
    search_text: str,
) -> List:
    lines: List[Tuple[str, str]] = []
    total_pages = get_total_pages(len(entries), PAGE_SIZE)
    start_idx, end_idx = get_page_bounds(page, len(entries), PAGE_SIZE)
    lines.append(("bold cyan", " Puppy Config Settings"))
    lines.append(("fg:ansibrightblack", f" (Page {page + 1}/{total_pages})"))
    if search_text:
        lines.append(("fg:ansiyellow", f"   '{search_text}'"))
    lines.append(("", "\n\n"))
    current_category = ""
    for i in range(start_idx, end_idx):
        category, key, display_name, _, type_hint, _ = entries[i]
        if category != current_category:
            if current_category:
                lines.append(("", "\n"))
            lines.append(("bold fg:ansiblue", f"  {category}"))
            current_category = category
        is_selected = i == selected_idx
        current_val = _current_value(key)
        val_display = current_val if current_val else "(not set)"
        if len(val_display) > 30:
            val_display = val_display[:27] + "..."
        if is_selected:
            lines.append(("fg:ansigreen bold", f"> {display_name}"))
            lines.append(("fg:ansigreen", f"  = {val_display}"))
        else:
            lines.append(("", f"  {display_name}"))
            lines.append(("fg:ansibrightblack", f"    = {val_display}"))
        lines.append(("", "\n"))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  up/down   Navigate"))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  left/right   Page"))
    lines.append(("", "\n"))
    lines.append(("fg:green", "  Enter Edit value"))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  /    Search"))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  R    Reset to default"))
    lines.append(("", "\n"))
    lines.append(("fg:ansicyan", "  Esc  Save & Exit"))
    lines.append(("", "\n"))
    lines.append(("fg:ansired", "  Ctrl+C Cancel (discard)"))
    return lines


def _render_right_panel(
    entry: Optional[Tuple],
) -> List:
    lines: List[Tuple[str, str]] = []
    lines.append(("bold cyan", " Setting Details"))
    lines.append(("", "\n\n"))
    if not entry:
        lines.append(("fg:ansiyellow", "  No setting selected."))
        lines.append(("", "\n"))
        return lines
    category, key, display_name, description, type_hint, valid_values_str = entry
    lines.append(("bold", "Key: "))
    lines.append(("fg:ansicyan", key))
    lines.append(("", "\n\n"))
    lines.append(("bold", "Name: "))
    lines.append(("fg:ansigreen", display_name))
    lines.append(("", "\n\n"))
    lines.append(("bold", "Category: "))
    lines.append(("fg:ansiblue", category))
    lines.append(("", "\n\n"))
    type_display = {
        "bool": "true / false",
        "int": "integer",
        "float": "float (0.0 - X.X)",
        "string": "free text",
        "choice": f"one of: {valid_values_str}",
    }.get(type_hint, type_hint)
    lines.append(("bold", "Type: "))
    lines.append(("fg:ansiyellow", type_display))
    lines.append(("", "\n\n"))
    current_val = _current_value(key)
    lines.append(("bold", "Current Value: "))
    if current_val:
        lines.append(("fg:ansigreen", current_val))
    else:
        lines.append(("fg:ansibrightblack", "(not set - using default)"))
    lines.append(("", "\n\n"))
    lines.append(("bold", "Description:"))
    lines.append(("", "\n"))
    words = description.split()
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 > 55:
            lines.append(("fg:ansibrightblack", "  " + current_line))
            lines.append(("", "\n"))
            current_line = word
        else:
            if current_line == "":
                current_line = word
            else:
                current_line += " " + word
    if current_line.strip():
        lines.append(("fg:ansibrightblack", "  " + current_line))
        lines.append(("", "\n"))
    lines.append(("", "\n"))
    if type_hint == "choice" and valid_values_str:
        lines.append(("bold", "Valid Values:"))
        lines.append(("", "\n"))
        for val in valid_values_str.split(", "):
            marker = " <- current" if val == current_val else ""
            if val == current_val:
                lines.append(("fg:ansigreen", f"   {val}{marker}"))
            else:
                lines.append(("fg:ansibrightblack", f"    {val}"))
            lines.append(("", "\n"))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", " Tip: Press Enter to edit this setting."))
    return lines


async def _prompt_for_value(
    key: str,
    type_hint: str,
    valid_values: Optional[List[str]],
    current_val: Optional[str],
) -> Optional[str]:
    from prompt_toolkit import PromptSession

    set_awaiting_user_input(True)
    try:
        if type_hint == "choice" and valid_values:
            choices = []
            for val in valid_values:
                if val == current_val:
                    choices.append(f" {val} (current)")
                else:
                    choices.append(f"  {val}")
            choices.append("---")
            choices.append("Type custom value...")
            choices.append("Cancel (keep current)")
            from code_puppy.tools.common import arrow_select_async

            try:
                selected = await arrow_select_async(
                    f"Select value for '{key}':",
                    choices,
                )
            except KeyboardInterrupt:
                return None
            if "Cancel" in selected or "custom" in selected.lower():
                pass
            elif "Type custom" in selected:
                pass
            else:
                cleaned = selected.strip().lstrip("").strip()
                cleaned = cleaned.replace(" (current)", "")
                return cleaned if cleaned else None
        prompt = f"New value for '{key}' (current: {current_val or '(not set)'}): "
        session = PromptSession(prompt)
        try:
            new_val = await session.prompt_async()
        except KeyboardInterrupt:
            return None
        new_val = new_val.strip()
        if type_hint == "bool":
            if new_val.lower() in (
                "true",
                "false",
                "1",
                "0",
                "yes",
                "no",
                "on",
                "off",
                "",
            ):
                return new_val.lower()
            else:
                emit_warning("Enter 'true'/'false' or press Enter to cancel.")
                return None
        elif type_hint == "int":
            if new_val == "":
                return ""
            try:
                int(new_val)
                return new_val
            except ValueError:
                emit_warning("Please enter a valid integer.")
                return None
        elif type_hint == "float":
            if new_val == "":
                return ""
            try:
                float(new_val)
                return new_val
            except ValueError:
                emit_warning("Please enter a valid number.")
                return None
        else:
            return new_val if new_val is not None else None
    finally:
        set_awaiting_user_input(False)


def _reset_setting(key: str) -> None:
    import configparser
    from code_puppy.config import CONFIG_FILE, DEFAULT_SECTION

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if DEFAULT_SECTION in config and key in config[DEFAULT_SECTION]:
        del config[DEFAULT_SECTION][key]
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            config.write(f)
        emit_success(f"Reset '{key}' to default")


async def interactive_set_picker() -> Optional[dict]:
    all_entries = _build_flat_settings()
    if not all_entries:
        emit_info("No settings found.")
        return None
    selected_idx = [0]
    current_page = [0]
    changed_settings: dict = {}
    search_text = [""]
    in_search_mode = [False]
    search_buffer = [""]
    exit_requested = [False]  # Set by Escape/Ctrl+C to stop the loop
    enter_triggered = [False]  # Set by Enter to run sub-prompt
    total_pages = [get_total_pages(len(all_entries), PAGE_SIZE)]

    def get_current_entry() -> Optional[Tuple]:
        if 0 <= selected_idx[0] < len(all_entries):
            return all_entries[selected_idx[0]]
        return None

    def filter_entries(search: str) -> List:
        if not search:
            return all_entries
        lower = search.lower()
        return [
            e
            for e in all_entries
            if lower in e[1].lower()
            or lower in e[2].lower()
            or lower in e[3].lower()
            or lower in e[0].lower()
        ]

    visible_entries = [all_entries]

    def update_visible():
        nonlocal visible_entries
        visible_entries[0] = filter_entries(search_text[0])
        total_pages[0] = get_total_pages(len(visible_entries[0]), PAGE_SIZE)
        selected_idx[0] = min(selected_idx[0], max(0, len(visible_entries[0]) - 1))
        current_page[0] = get_page_for_index(selected_idx[0], PAGE_SIZE)

    left_control = FormattedTextControl(text="")
    right_control = FormattedTextControl(text="")

    def update_display():
        left_control.text = _render_left_panel(
            visible_entries[0],
            current_page[0],
            selected_idx[0],
            search_text[0],
        )
        right_control.text = _render_right_panel(get_current_entry())

    left_window = Window(
        content=left_control,
        wrap_lines=True,
        width=Dimension(weight=50),
    )
    right_window = Window(
        content=right_control,
        wrap_lines=True,
        width=Dimension(weight=50),
    )
    left_frame = Frame(left_window, title="Settings")
    right_frame = Frame(right_window, title="Details")
    root_container = VSplit([left_frame, right_frame])

    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        if in_search_mode[0]:
            return
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            current_page[0] = ensure_visible_page(
                selected_idx[0], current_page[0], len(visible_entries[0]), PAGE_SIZE
            )
            update_display()

    @kb.add("down")
    def _(event):
        if in_search_mode[0]:
            return
        if selected_idx[0] < len(visible_entries[0]) - 1:
            selected_idx[0] += 1
            current_page[0] = ensure_visible_page(
                selected_idx[0], current_page[0], len(visible_entries[0]), PAGE_SIZE
            )
            update_display()

    @kb.add("left")
    def _(event):
        if in_search_mode[0]:
            return
        if current_page[0] > 0:
            current_page[0] -= 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("right")
    def _(event):
        if in_search_mode[0]:
            return
        if current_page[0] < total_pages[0] - 1:
            current_page[0] += 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("enter")
    async def _(event):
        if in_search_mode[0]:
            search_text[0] = search_buffer[0]
            in_search_mode[0] = False
            search_buffer[0] = ""
            update_visible()
            update_display()
            return
        entry = get_current_entry()
        if not entry:
            return
        # Exit app so sub-prompts render in clean main terminal
        enter_triggered[0] = True
        event.app.exit()
        return  # Important: don't run sub-prompt here, main loop handles it

    @kb.add("r")
    def _(event):
        if in_search_mode[0]:
            return
        entry = get_current_entry()
        if entry:
            _reset_setting(entry[1])
            update_display()

    @kb.add("/")
    def _(event):
        in_search_mode[0] = True
        search_buffer[0] = ""
        update_display()

    for char in "abcdefghijklmnopqrstuvwxyz0123456789_ -":

        @kb.add(char)
        def _c(event, c=char):
            if in_search_mode[0]:
                search_buffer[0] += c
                update_display()

    @kb.add("backspace")
    def _(event):
        if in_search_mode[0]:
            search_buffer[0] = search_buffer[0][:-1]
            update_display()

    @kb.add("c-c")
    def _(event):
        exit_requested[0] = True
        event.app.exit()

    @kb.add("escape")
    def _(event):
        if in_search_mode[0]:
            in_search_mode[0] = False
            search_buffer[0] = ""
            update_display()
        else:
            exit_requested[0] = True
            event.app.exit()

    layout = Layout(root_container)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )
    set_awaiting_user_input(True)
    import code_puppy.messaging as messaging_module

    original_emit_success = messaging_module.emit_success
    original_emit_info = messaging_module.emit_info
    original_emit_warning = messaging_module.emit_warning

    def _no_op(msg):
        pass

    messaging_module.emit_success = _no_op
    messaging_module.emit_info = _no_op
    messaging_module.emit_warning = _no_op
    sys.stdout.write("\033[?1049h")
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    await asyncio.sleep(0.05)
    try:
        while True:
            update_display()
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            try:
                await app.run_async()
            except KeyboardInterrupt:
                exit_requested[0] = True
                break
            # Check if Enter was pressed (sub-prompt triggered)
            if enter_triggered[0]:
                enter_triggered[0] = False
                entry = get_current_entry()
                if entry:
                    category, key, _, _, type_hint, valid_values_str = entry
                    current_val = _current_value(key)
                    valid_values = (
                        valid_values_str.split(", ") if valid_values_str else None
                    )
                    new_val = await _prompt_for_value(
                        key, type_hint, valid_values, current_val
                    )
                    if new_val is None:
                        continue  # Cancelled, restart app
                    if new_val == "":
                        _reset_setting(key)
                    else:
                        set_config_value(key, new_val)
                        changed_settings[key] = new_val
                    continue  # Restart app with updated display
            # Exit requested (Escape/Ctrl+C)
            if exit_requested[0]:
                break
    finally:
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        set_awaiting_user_input(False)
        messaging_module.emit_success = original_emit_success
        messaging_module.emit_info = original_emit_info
        messaging_module.emit_warning = original_emit_warning
    emit_info(" Exited config settings menu")
    if changed_settings:
        return changed_settings
    return None
