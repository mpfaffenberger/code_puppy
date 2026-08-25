"""Interactive picker for the ``/set`` command, on termflow.

A searchable Menu over curated + dynamic settings with a details
preview pane; ``Enter`` edits (choice settings get a picker, everything
else a typed TextInput), ``r`` resets, ``Esc`` exits. All saves are
routed through :func:`code_puppy.command_line.config_apply.apply_setting`
so the slash-command path and the menu share one source of validation
truth.

The picker never emits messages directly while the widgets own the
terminal -- success/warning/error strings are queued on
:class:`PickerResult` and drained by the dispatcher once the picker
returns. Same trick :mod:`agent_menu` uses for pending pin reloads.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from code_puppy.command_line.config_apply import (
    MODEL_SETTINGS_ONLY_KEYS,
    apply_setting,
)
from code_puppy.command_line.set_menu_settings import (
    Setting,
    SettingsCategory,
    iter_curated_settings,
)
from code_puppy.command_line.set_menu_values import (
    display_value,
    is_default_value,
    mask_value,
)
from code_puppy.config import (
    get_config_keys,
    get_value,
    reset_value,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

_DYNAMIC_CATEGORY = SettingsCategory(name="Dynamic")
_RESET = "__reset_setting__"
_CUSTOM = "__custom_value__"
_CANCEL = "__cancel_edit__"


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
        if key in curated_keys or key in MODEL_SETTINGS_ONLY_KEYS:
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
# Details preview
# ---------------------------------------------------------------------------


def _style():
    from termflow.render.style import RenderStyle

    from code_puppy.command_line.tui_style import menu_style

    return menu_style() or RenderStyle.default()


def _ansi(color: str, text: str) -> str:
    from termflow.ansi.codes import RESET
    from termflow.ansi.color import fg_color

    return f"{fg_color(color)}{text}{RESET}"


def value_for_display(setting: Setting) -> str:
    """Resolve a setting's effective value, falling back to ``(not set)``."""
    value = display_value(setting)
    return value if value is not None else "(not set)"


def entry_details(entry: _Entry) -> str:
    """Details pane for one setting."""
    import textwrap

    s = _style()
    setting = entry.setting
    value = value_for_display(setting)
    if setting.sensitive and value not in ("(not set)",):
        value = mask_value(value)
    default_marker = " (default)" if is_default_value(setting) else ""
    lines = [
        _ansi(s.bright, setting.display_name),
        _ansi(s.grey, f"{entry.category.name} - {setting.key}"),
        "",
        _ansi(s.head, f"Current: {value}{default_marker}"),
        _ansi(s.grey, f"Type: {setting.type_hint}"),
    ]
    if setting.valid_values:
        lines.append(_ansi(s.grey, f"Choices: {', '.join(setting.valid_values)}"))
    lines.append("")
    lines.extend(textwrap.wrap(setting.description, width=56))
    lines += ["", _ansi(s.grey, "Enter edit - r reset - Esc exit")]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Menus & editors
# ---------------------------------------------------------------------------


def build_settings_menu(entries: List[_Entry], initial_index: int = 0, **overrides):
    """Searchable settings list with a details preview.

    ``r`` resets via an on_key sentinel -- which means the search filter
    cannot contain the letter r, the same quirk the previous
    implementation had (its search alphabet excluded r too).
    """
    from termflow.tui import MenuBuilder, MenuItem
    from termflow.tui.menu import MenuResult

    from code_puppy.command_line.tui_style import themed

    items = [
        MenuItem(
            f"{e.setting.display_name}",
            value=e,
            description=f"{e.category.name} - {e.setting.key}",
        )
        for e in entries
    ]

    def reset_handler(_menu, item):
        return MenuResult(item=MenuItem("", value=(_RESET, item.value)))

    builder = themed(
        MenuBuilder("Settings - /set")
        .items(items)
        .searchable()
        .list_width(44)
        .alt_screen(False)
        .initial_index(min(initial_index, max(len(items) - 1, 0)))
        .preview(
            lambda item: entry_details(
                item.value if not isinstance(item.value, tuple) else item.value[1]
            )
        )
        .footer_hint("type filter - Enter edit - r reset - Esc exit")
        .on_key("r", reset_handler)
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def build_choice_menu(setting: Setting, current: Optional[str], **overrides):
    """Value picker for choice settings: values + custom + cancel."""
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    items = [
        MenuItem(
            f"{val}{' (current)' if val == current else ''}",
            value=val,
        )
        for val in setting.valid_values or []
    ]
    items.append(MenuItem("Type custom value...", value=_CUSTOM))
    items.append(MenuItem("Cancel (keep current)", value=_CANCEL))
    values = [item.value for item in items]
    initial = values.index(current) if current in values else 0
    builder = themed(
        MenuBuilder(f"Select value for '{setting.key}'")
        .items(items)
        .initial_index(initial)
        .alt_screen(False)
        .footer_hint("Enter select - Esc cancel")
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def run_text_editor(setting: Setting, current: Optional[str], **overrides):
    """Typed TextInput for a setting. Returns (edited, value).

    Empty commit returns ``(True, "")`` which callers treat as a reset,
    matching the previous prompt-based behavior.
    """
    from termflow.tui import TextInputBuilder

    from code_puppy.command_line.tui_style import menu_style

    def validate(text: str) -> Optional[str]:
        if _coerce_typed_input(setting.type_hint, text.strip()) is None:
            return f"expected a {setting.type_hint} value"
        return None

    builder = (
        TextInputBuilder(f"New value for '{setting.key}'")
        .prompt("Value: ")
        .placeholder(f"current: {current or '(not set)'} (empty resets)")
        .validator(validate)
        .footer_hint("Enter save (empty resets) - Esc cancel")
        .alt_screen(False)
    )
    if setting.sensitive:
        builder.mask("*")
    style = menu_style()
    if style is not None:
        builder.style(style)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    result = builder.build().run()
    if result.cancelled:
        return False, None
    return True, _coerce_typed_input(setting.type_hint, (result.value or "").strip())


# ---------------------------------------------------------------------------
# Mutation recording
# ---------------------------------------------------------------------------


def _record_reset(result: PickerResult, key: str) -> None:
    """Reset ``key`` to its default and queue a coalesced agent reload.

    Reset is a real config mutation just like a set: the dispatcher's
    end-of-picker reload is gated on ``changed_settings`` being non-empty,
    so an unrecorded reset would silently leave the running agent with
    the old value until next restart.
    """
    from code_puppy.command_line.config_apply import invalidate_post_write_caches

    reset_value(key)
    invalidate_post_write_caches(key)
    result.changed_settings[key] = None
    result.pending_messages.append(("success", f"Reset '{key}' to default"))


def _apply_and_record(result: PickerResult, setting: Setting, new_val: str) -> None:
    applied = apply_setting(setting.key, new_val, reload_agent=False)
    if not applied.ok:
        result.pending_messages.append(
            ("error", applied.error or "Failed to apply setting.")
        )
        return
    result.changed_settings[setting.key] = applied.value_after
    display = (
        mask_value(applied.value_after or "")
        if setting.sensitive
        else applied.value_after
    )
    result.pending_messages.append(("success", f'Set {setting.key} = "{display}"'))
    if applied.warning:
        result.pending_messages.append(("warning", applied.warning))


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


def _edit_setting(
    result: PickerResult,
    setting: Setting,
    choice_menu_factory: Callable = build_choice_menu,
    text_editor: Callable = run_text_editor,
) -> None:
    """Run the edit flow for one setting and record the outcome."""
    current = display_value(setting)
    if setting.type_hint == "choice" and setting.valid_values:
        pick = choice_menu_factory(setting, current).run()
        if pick.cancelled or pick.item is None or pick.item.value == _CANCEL:
            return
        if pick.item.value != _CUSTOM:
            _apply_and_record(result, setting, pick.item.value)
            return
        # _CUSTOM falls through to the free-text editor.
    edited, new_val = text_editor(setting, current)
    if not edited or new_val is None:
        return
    if new_val == "":
        _record_reset(result, setting.key)
        return
    _apply_and_record(result, setting, new_val)


def run_set_picker_flow(
    settings_menu_factory: Callable = build_settings_menu,
    choice_menu_factory: Callable = build_choice_menu,
    text_editor: Callable = run_text_editor,
) -> PickerResult:
    """The settings-list edit loop. Collaborators injectable for tests."""
    result = PickerResult()
    entries = _build_entries()
    if not entries:
        result.pending_messages.append(("info", "No settings found."))
        return result

    cursor = 0
    while True:
        menu_result = settings_menu_factory(entries, initial_index=cursor).run()
        if menu_result.cancelled or menu_result.item is None:
            break
        value = menu_result.item.value
        if isinstance(value, tuple) and value[0] == _RESET:
            _record_reset(result, value[1].setting.key)
            continue
        entry = value
        cursor = entries.index(entry) if entry in entries else 0
        _edit_setting(
            result,
            entry.setting,
            choice_menu_factory=choice_menu_factory,
            text_editor=text_editor,
        )

    result.pending_messages.append(("info", "Exited config settings menu"))
    return result


async def interactive_set_picker() -> Optional[PickerResult]:
    """Run the interactive ``/set`` picker."""
    from code_puppy.command_line.menu_session import menu_session

    set_awaiting_user_input(True)
    try:
        with menu_session():
            return await asyncio.to_thread(run_set_picker_flow)
    finally:
        set_awaiting_user_input(False)
