"""Interactive picker for the ``/set`` command.

UX parity with ``/mcp`` and ``/agent``: split-panel TUI, arrow-key
navigation, ``/`` search, ``Enter`` to edit, ``r`` to reset, ``Esc`` to
exit. All saves are routed through
:func:`code_puppy.command_line.config_apply.apply_setting` so the
slash-command path and the menu share one source of validation truth.

The picker never emits messages directly while prompt_toolkit owns the
terminal -- success/warning/error strings are queued on
:class:`PickerResult` and drained by the dispatcher once the picker
returns. Same trick :mod:`agent_menu` uses for pending pin reloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line.config_apply import apply_setting
from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)
from code_puppy.command_line.set_menu_render import (
    render_left_panel,
    render_right_panel,
)
from code_puppy.command_line.set_menu_settings import (
    Setting,
    SettingsCategory,
    iter_curated_settings,
)
from code_puppy.command_line.set_menu_values import display_value, mask_value
from code_puppy.config import (
    get_config_keys,
    get_value,
    reset_value,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 12

_DYNAMIC_CATEGORY = SettingsCategory(name="Dynamic")
# Alphabet bound to the search buffer. ``r`` is excluded so the
# reset shortcut keeps working in nav mode.
_SEARCH_ALPHABET = "abcdefghijklmnopqstuvwxyz0123456789_ -"


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Entry:
    """One row in the flattened picker list."""

    category: SettingsCategory
    setting: Setting


@dataclass
class PickerResult:
    """Returned by :func:`interactive_set_picker`.

    ``pending_messages`` is a list of ``(level, text)`` pairs the
    dispatcher emits after the picker exits, where ``level`` is one of
    ``"info"``, ``"success"``, ``"warning"``, ``"error"``.
    """

    changed_settings: dict = field(default_factory=dict)
    pending_messages: List[Tuple[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Entry construction & type detection
# ---------------------------------------------------------------------------


def _detect_dynamic_type(key: str) -> str:
    """Best-effort type guess for un-curated keys in the Dynamic section."""
    if key.endswith("_enabled") or key.endswith("_mode"):
        return "bool"
    current = get_value(key)
    if current is None:
        return "string"
    lower = current.strip().lower()
    if lower in ("true", "false", "1", "0", "yes", "no", "on", "off"):
        return "bool"
    try:
        int(current)
        return "int"
    except (TypeError, ValueError):
        pass
    try:
        float(current)
        return "float"
    except (TypeError, ValueError):
        pass
    return "string"


def _build_entries() -> List[_Entry]:
    """Flatten curated settings + Dynamic catch-all into render order."""
    entries: List[_Entry] = []
    curated_keys: set = set()
    for category, setting in iter_curated_settings():
        entries.append(_Entry(category=category, setting=setting))
        curated_keys.add(setting.key)

    for key in get_config_keys():
        if key in curated_keys:
            continue
        entries.append(
            _Entry(
                category=_DYNAMIC_CATEGORY,
                setting=Setting(
                    key=key,
                    display_name=key.replace("_", " ").title(),
                    description="Auto-detected setting (no description available).",
                    type_hint=_detect_dynamic_type(key),
                ),
            )
        )
    return entries


def _entry_matches(entry: _Entry, needle: str) -> bool:
    haystack = (
        entry.setting.key,
        entry.setting.display_name,
        entry.setting.description,
        entry.category.name,
    )
    return any(needle in candidate.lower() for candidate in haystack)


# ---------------------------------------------------------------------------
# Sub-prompt for editing a single setting
# ---------------------------------------------------------------------------


async def _prompt_for_value(
    setting: Setting,
    current_val: Optional[str],
) -> Optional[str]:
    """Ask the user for a new value. Returns ``None`` if cancelled.

    For ``choice`` settings, presents an :func:`arrow_select_async`
    picker; a real choice returns immediately, ``Cancel`` returns
    ``None``, and ``Type custom value...`` falls through to a free-text
    prompt. For non-choice settings, goes straight to free-text.
    """
    from prompt_toolkit import PromptSession

    from code_puppy.tools.common import arrow_select_async

    set_awaiting_user_input(True)
    try:
        if setting.type_hint == "choice" and setting.valid_values:
            CANCEL_LABEL = "Cancel (keep current)"
            CUSTOM_LABEL = "Type custom value..."
            choices: List[str] = []
            for val in setting.valid_values:
                suffix = " (current)" if val == current_val else ""
                choices.append(f"  {val}{suffix}")
            choices.append("---")
            choices.append(CUSTOM_LABEL)
            choices.append(CANCEL_LABEL)

            try:
                selected = await arrow_select_async(
                    f"Select value for '{setting.key}':",
                    choices,
                )
            except KeyboardInterrupt:
                return None

            if selected == CANCEL_LABEL:
                return None
            if selected != CUSTOM_LABEL:
                cleaned = selected.replace(" (current)", "").strip()
                return cleaned or None
            # CUSTOM_LABEL falls through to the free-text PromptSession.

        prompt = (
            f"New value for '{setting.key}' (current: {current_val or '(not set)'}): "
        )
        session = PromptSession(prompt, is_password=setting.sensitive)
        try:
            new_val = await session.prompt_async()
        except KeyboardInterrupt:
            return None

        return _coerce_typed_input(setting.type_hint, new_val.strip())
    finally:
        set_awaiting_user_input(False)


def _coerce_typed_input(type_hint: str, value: str) -> Optional[str]:
    """Validate user input against ``type_hint``. ``None`` = invalid/cancel."""
    if type_hint == "bool":
        if value.lower() in (
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
            return value.lower()
        return None
    if type_hint == "int":
        if value == "":
            return ""
        try:
            int(value)
        except ValueError:
            return None
        return value
    if type_hint == "float":
        if value == "":
            return ""
        try:
            float(value)
        except ValueError:
            return None
        return value
    return value


# ---------------------------------------------------------------------------
# Picker state
# ---------------------------------------------------------------------------


@dataclass
class _PickerState:
    all_entries: List[_Entry]
    selected_idx: int = 0
    current_page: int = 0
    search_text: str = ""
    in_search_mode: bool = False
    search_buffer: str = ""
    exit_requested: bool = False
    enter_triggered: bool = False
    visible_entries: List[_Entry] = field(default_factory=list)
    result: PickerResult = field(default_factory=PickerResult)

    @property
    def current_entry(self) -> Optional[_Entry]:
        if 0 <= self.selected_idx < len(self.visible_entries):
            return self.visible_entries[self.selected_idx]
        return None

    def update_visible(self) -> None:
        needle = self.search_text.lower()
        if needle:
            self.visible_entries = [
                e for e in self.all_entries if _entry_matches(e, needle)
            ]
        else:
            self.visible_entries = list(self.all_entries)
        self.selected_idx = min(
            self.selected_idx, max(0, len(self.visible_entries) - 1)
        )
        self.current_page = get_page_for_index(self.selected_idx, PAGE_SIZE)


# ---------------------------------------------------------------------------
# Main picker entry point
# ---------------------------------------------------------------------------


async def interactive_set_picker() -> Optional[PickerResult]:
    """Run the interactive ``/set`` picker."""
    all_entries = _build_entries()
    if not all_entries:
        result = PickerResult()
        result.pending_messages.append(("info", "No settings found."))
        return result

    state = _PickerState(all_entries=all_entries)
    state.update_visible()

    left_control = FormattedTextControl(text="")
    right_control = FormattedTextControl(text="")

    def update_display() -> None:
        left_control.text = render_left_panel(
            state.visible_entries,
            state.current_page,
            state.selected_idx,
            state.search_text,
            state.in_search_mode,
            state.search_buffer,
            page_size=PAGE_SIZE,
            page_bounds=get_page_bounds,
            total_pages_fn=get_total_pages,
        )
        right_control.text = render_right_panel(state.current_entry)

    layout = Layout(
        VSplit(
            [
                Frame(
                    Window(
                        content=left_control,
                        wrap_lines=True,
                        width=Dimension(weight=50),
                    ),
                    title="Settings",
                ),
                Frame(
                    Window(
                        content=right_control,
                        wrap_lines=True,
                        width=Dimension(weight=50),
                    ),
                    title="Details",
                ),
            ]
        )
    )
    kb = _build_keybindings(state, update_display)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    set_awaiting_user_input(True)
    try:
        while True:
            update_display()
            try:
                await app.run_async()
            except KeyboardInterrupt:
                state.exit_requested = True
                break

            if state.enter_triggered:
                state.enter_triggered = False
                await _handle_edit(state)
                continue
            if state.exit_requested:
                break
    finally:
        set_awaiting_user_input(False)

    state.result.pending_messages.append(("info", "Exited config settings menu"))
    return state.result


async def _handle_edit(state: _PickerState) -> None:
    entry = state.current_entry
    if entry is None:
        return
    current_val = display_value(entry.setting)
    new_val = await _prompt_for_value(entry.setting, current_val)
    if new_val is None:
        return
    if new_val == "":
        _record_reset(state, entry.setting.key)
        return
    _apply_and_record(state, entry.setting, new_val)


def _record_reset(state: _PickerState, key: str) -> None:
    """Reset ``key`` to its default and queue a coalesced agent reload.

    Reset is a real config mutation just like a set: the dispatcher's
    end-of-picker reload is gated on ``changed_settings`` being non-empty,
    so an unrecorded reset would silently leave the running agent with
    the old value until next restart.
    """
    from code_puppy.command_line.config_apply import invalidate_post_write_caches

    reset_value(key)
    invalidate_post_write_caches(key)
    state.result.changed_settings[key] = None
    state.result.pending_messages.append(("success", f"Reset '{key}' to default"))


def _apply_and_record(state: _PickerState, setting: Setting, new_val: str) -> None:
    result = apply_setting(setting.key, new_val, reload_agent=False)
    if not result.ok:
        state.result.pending_messages.append(
            ("error", result.error or "Failed to apply setting.")
        )
        return
    state.result.changed_settings[setting.key] = result.value_after
    display = (
        mask_value(result.value_after or "")
        if setting.sensitive
        else result.value_after
    )
    state.result.pending_messages.append(
        ("success", f'Set {setting.key} = "{display}"')
    )
    if result.warning:
        state.result.pending_messages.append(("warning", result.warning))


# ---------------------------------------------------------------------------
# Keybindings
# ---------------------------------------------------------------------------


def _build_keybindings(state: _PickerState, update_display) -> KeyBindings:
    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        if state.in_search_mode or state.selected_idx <= 0:
            return
        state.selected_idx -= 1
        state.current_page = ensure_visible_page(
            state.selected_idx,
            state.current_page,
            len(state.visible_entries),
            PAGE_SIZE,
        )
        update_display()

    @kb.add("down")
    def _(event):
        if state.in_search_mode:
            return
        if state.selected_idx >= len(state.visible_entries) - 1:
            return
        state.selected_idx += 1
        state.current_page = ensure_visible_page(
            state.selected_idx,
            state.current_page,
            len(state.visible_entries),
            PAGE_SIZE,
        )
        update_display()

    @kb.add("left")
    def _(event):
        if state.in_search_mode or state.current_page <= 0:
            return
        state.current_page -= 1
        state.selected_idx = state.current_page * PAGE_SIZE
        update_display()

    @kb.add("right")
    def _(event):
        total_pages = get_total_pages(len(state.visible_entries), PAGE_SIZE)
        if state.in_search_mode or state.current_page >= total_pages - 1:
            return
        state.current_page += 1
        state.selected_idx = state.current_page * PAGE_SIZE
        update_display()

    @kb.add("enter")
    def _(event):
        if state.in_search_mode:
            state.search_text = state.search_buffer
            state.in_search_mode = False
            state.search_buffer = ""
            state.update_visible()
            update_display()
            return
        if state.current_entry is None:
            return
        state.enter_triggered = True
        event.app.exit()

    @kb.add("r")
    def _(event):
        if state.in_search_mode:
            state.search_buffer += "r"
            update_display()
            return
        entry = state.current_entry
        if entry is None:
            return
        _record_reset(state, entry.setting.key)
        update_display()

    @kb.add("/")
    def _(event):
        state.in_search_mode = True
        state.search_buffer = ""
        update_display()

    for char in _SEARCH_ALPHABET:

        @kb.add(char)
        def _c(event, c=char):
            if state.in_search_mode:
                state.search_buffer += c
                update_display()

    @kb.add("backspace")
    def _(event):
        if state.in_search_mode:
            state.search_buffer = state.search_buffer[:-1]
            update_display()

    @kb.add("c-c")
    def _(event):
        state.exit_requested = True
        event.app.exit()

    @kb.add("escape")
    def _(event):
        if state.in_search_mode:
            state.in_search_mode = False
            state.search_buffer = ""
            update_display()
            return
        state.exit_requested = True
        event.app.exit()

    return kb
