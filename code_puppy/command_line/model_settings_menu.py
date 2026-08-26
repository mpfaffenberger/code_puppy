"""Interactive termflow UI for configuring per-model settings.

Model list -> settings list -> typed editors: choices cycle through a
small picker, numerics get a validated TextInput (empty clears the
override back to the model default), and custom params get their own
pair list with add/edit/delete. All persistence helpers live in
:mod:`code_puppy.command_line.model_settings_defs`.
"""

from typing import Dict, List, Optional

from code_puppy.command_line.model_settings_defs import (
    _RETRY_MENU_KEYS,
    SETTING_DEFINITIONS,
    _format_custom_pairs,
    _format_custom_value,
    _get_model_display_settings,
    _get_setting_choices,
    _get_setting_default,
    _load_all_model_names,
    _supports_setting,
    _write_per_model_retry,
)
from code_puppy.config import (
    CUSTOM_MODEL_SETTING,
    get_custom_model_settings,
    get_global_model_name,
    parse_config_scalar,
    set_custom_model_setting,
    set_model_setting,
)
from code_puppy.messaging import emit_info
from code_puppy.model_factory import ModelFactory
from code_puppy.tools.command_runner import set_awaiting_user_input

_RESET = "__reset_setting__"
_ADD_PAIR = "__add_custom_pair__"
_DELETE_PAIR = "__delete_custom_pair__"


def format_value(setting: str, value, model_name: Optional[str] = None) -> str:
    """Format a setting value for display."""
    setting_def = SETTING_DEFINITIONS.get(setting)
    if setting_def is None:
        return str(value) if value is not None else "(unknown)"
    if setting == CUSTOM_MODEL_SETTING:
        if isinstance(value, dict) and value:
            return _format_custom_pairs(value)
        return "(none)"
    if value is None:
        if setting in _RETRY_MENU_KEYS:
            return "(uses global)"
        default = _get_setting_default(setting, model_name)
        if default is not None:
            return f"(default: {default})"
        return "(model default)"
    if setting_def.get("type") == "choice":
        return str(value)
    if setting_def.get("type") == "boolean":
        return "Enabled" if value else "Disabled"
    return setting_def.get("format", "{:.2f}").format(value)


def supported_settings(model_name: str, models_config: Optional[dict]) -> List[str]:
    """Settings offered for a model (retry + custom always included)."""
    return [
        key
        for key in SETTING_DEFINITIONS
        if key == CUSTOM_MODEL_SETTING
        or key in _RETRY_MENU_KEYS
        or _supports_setting(model_name, key, models_config)
    ]


def save_setting(model_name: str, setting_key: str, value) -> None:
    """Persist a setting value (retry overrides use their own namespace)."""
    if setting_key in _RETRY_MENU_KEYS:
        _write_per_model_retry(model_name, setting_key, value)
    else:
        set_model_setting(model_name, setting_key, value)


def reset_setting(model_name: str, setting_key: str) -> None:
    """Reset a setting to its default (custom params: delete them all)."""
    if setting_key == CUSTOM_MODEL_SETTING:
        for key in list(get_custom_model_settings(model_name)):
            set_custom_model_setting(model_name, key, None)
    elif setting_key in _RETRY_MENU_KEYS:
        _write_per_model_retry(model_name, setting_key, None)
    else:
        set_model_setting(model_name, setting_key, None)


def parse_numeric(text: str, setting_def: dict) -> Optional[object]:
    """Parse and clamp-validate numeric input. None on failure."""
    try:
        value = float(text.strip())
    except ValueError:
        return None
    if not (setting_def["min"] <= value <= setting_def["max"]):
        return None
    if isinstance(setting_def.get("step"), int) and isinstance(
        setting_def.get("min"), int
    ):
        return int(round(value))
    return value


# -- previews ----------------------------------------------------------------


def _style():
    from termflow.render.style import RenderStyle

    from code_puppy.command_line.tui_style import menu_style

    return menu_style() or RenderStyle.default()


def _ansi(color: str, text: str) -> str:
    from termflow.ansi.codes import RESET
    from termflow.ansi.color import fg_color

    return f"{fg_color(color)}{text}{RESET}"


def model_summary(model_name: str, models_config: Optional[dict]) -> str:
    """Preview pane for the model list: configured settings at a glance."""
    s = _style()
    settings = _get_model_display_settings(model_name, models_config)
    lines = [_ansi(s.bright, model_name), ""]
    if not settings:
        lines.append(_ansi(s.grey, "No custom settings (model defaults)."))
        return "\n".join(lines)
    lines.append(_ansi(s.head, "Configured settings:"))
    for key, value in settings.items():
        name = SETTING_DEFINITIONS.get(key, {}).get("name", key)
        lines.append(_ansi(s.grey, f"  {name}: {format_value(key, value, model_name)}"))
    return "\n".join(lines)


def setting_details(
    setting_key: str, model_name: str, models_config: Optional[dict], current
) -> str:
    """Preview pane for the settings list: description + range/choices."""
    s = _style()
    setting_def = SETTING_DEFINITIONS.get(setting_key, {})
    lines = [
        _ansi(s.bright, setting_def.get("name", setting_key)),
        "",
        setting_def.get("description", ""),
        "",
        _ansi(s.head, f"Current: {format_value(setting_key, current, model_name)}"),
    ]
    if setting_def.get("type") == "numeric":
        lines.append(
            _ansi(
                s.grey,
                f"Range: {setting_def['min']} - {setting_def['max']} "
                f"(step {setting_def['step']})",
            )
        )
    elif setting_def.get("type") == "choice":
        choices = _get_setting_choices(setting_key, model_name, models_config)
        lines.append(_ansi(s.grey, f"Choices: {', '.join(choices)}"))
    lines += ["", _ansi(s.grey, "Enter edit - r reset to default - Esc back")]
    return "\n".join(lines)


# -- menu builders ------------------------------------------------------------


def _themed_menu(title: str):
    from termflow.tui import MenuBuilder

    from code_puppy.command_line.tui_style import themed

    return themed(MenuBuilder(title).alt_screen(False))


def _apply(builder, overrides):
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def build_models_menu(
    models: List[str], current: Optional[str], models_config=None, **overrides
):
    from termflow.tui import MenuItem

    items = [MenuItem(name, value=name) for name in models]
    initial = models.index(current) if current in models else 0
    builder = (
        _themed_menu("Model Settings - Select a Model")
        .items(items)
        .searchable()
        .list_width(40)
        .initial_index(initial)
        .preview(lambda item: model_summary(item.value, models_config))
        .footer_hint("type filter - Enter configure - Esc exit")
    )
    return _apply(builder, overrides)


def build_settings_menu(
    model_name: str,
    models_config: Optional[dict],
    initial_index: int = 0,
    **overrides,
):
    from termflow.tui import MenuItem
    from termflow.tui.menu import MenuResult

    settings = _get_model_display_settings(model_name, models_config)
    keys = supported_settings(model_name, models_config)
    items = [
        MenuItem(
            f"{SETTING_DEFINITIONS[key].get('name', key)}: "
            f"{format_value(key, settings.get(key), model_name)}",
            value=key,
        )
        for key in keys
    ]

    def reset_handler(_menu, item):
        return MenuResult(item=MenuItem("", value=(_RESET, item.value)))

    builder = (
        _themed_menu(f"Settings - {model_name}")
        .items(items)
        .list_width(46)
        .initial_index(min(initial_index, max(len(items) - 1, 0)))
        .preview(
            lambda item: setting_details(
                item.value if not isinstance(item.value, tuple) else item.value[1],
                model_name,
                models_config,
                settings.get(item.value),
            )
        )
        .footer_hint("Enter edit - r reset - Esc back")
        .on_key("r", reset_handler)
    )
    return _apply(builder, overrides)


def build_choice_editor(
    setting_key: str,
    model_name: str,
    models_config: Optional[dict],
    current,
    **overrides,
):
    from termflow.tui import MenuItem

    setting_def = SETTING_DEFINITIONS[setting_key]
    if setting_def.get("type") == "boolean":
        choices = [("Enabled", True), ("Disabled", False)]
    else:
        choices = [
            (choice, choice)
            for choice in _get_setting_choices(setting_key, model_name, models_config)
        ]
    values = [value for _, value in choices]
    initial = values.index(current) if current in values else 0
    builder = (
        _themed_menu(f"{setting_def.get('name', setting_key)} - {model_name}")
        .items([MenuItem(label, value=value) for label, value in choices])
        .initial_index(initial)
        .footer_hint("Enter save - Esc cancel")
    )
    return _apply(builder, overrides)


def run_numeric_editor(setting_key: str, model_name: str, current, **overrides):
    """TextInput for a numeric setting. Returns (changed, value)."""
    from termflow.tui import TextInputBuilder

    from code_puppy.command_line.tui_style import menu_style

    setting_def = SETTING_DEFINITIONS[setting_key]
    builder = (
        TextInputBuilder(f"{setting_def.get('name', setting_key)} - {model_name}")
        .prompt("Value: ")
        .initial("" if current is None else format_value(setting_key, current))
        .placeholder(
            f"{setting_def['min']} - {setting_def['max']} (empty = model default)"
        )
        .validator(
            lambda text: (
                None
                if not text.strip() or parse_numeric(text, setting_def) is not None
                else f"expected a number between {setting_def['min']} and {setting_def['max']}"
            )
        )
        .footer_hint("Enter save (empty clears override) - Esc cancel")
        .alt_screen(False)
    )
    style = menu_style()
    if style is not None:
        builder.style(style)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    result = builder.build().run()
    if result.cancelled:
        return False, None
    if not (result.value or "").strip():
        return True, None  # clear override
    return True, parse_numeric(result.value, setting_def)


# -- custom params ------------------------------------------------------------


def build_custom_menu(pairs: Dict, model_name: str, **overrides):
    from termflow.tui import MenuItem
    from termflow.tui.menu import MenuResult

    items = [
        MenuItem(f"{key} = {_format_custom_value(value)}", value=key)
        for key, value in pairs.items()
    ]
    items.append(MenuItem("+ Add param...", value=_ADD_PAIR))

    def delete_handler(_menu, item):
        if item.value == _ADD_PAIR:
            return None
        return MenuResult(item=MenuItem("", value=(_DELETE_PAIR, item.value)))

    builder = (
        _themed_menu(f"Custom Params - {model_name}")
        .items(items)
        .footer_hint("Enter add/edit - d delete - Esc back")
        .on_key("d", delete_handler)
    )
    return _apply(builder, overrides)


def run_pair_editor(model_name: str, initial: str = "", **overrides):
    """TextInput for one 'key = value' pair. Returns (key, value) or None."""
    from termflow.tui import TextInputBuilder

    from code_puppy.command_line.tui_style import menu_style

    def validate(text: str) -> Optional[str]:
        key, sep, value = (part.strip() for part in text.partition("="))
        if not sep or not key or not value:
            return "Expected format: key = value"
        return None

    builder = (
        TextInputBuilder(f"Custom param - {model_name}")
        .prompt("key = value: ")
        .initial(initial)
        .placeholder("chat_template_kwargs.thinking = medium")
        .validator(validate)
        .footer_hint("Enter save - Esc cancel")
        .alt_screen(False)
    )
    style = menu_style()
    if style is not None:
        builder.style(style)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    result = builder.build().run()
    if result.cancelled or not result.value:
        return None
    key, _, value = (part.strip() for part in result.value.partition("="))
    return key, parse_config_scalar(value)


def run_custom_params_flow(
    model_name: str,
    menu_factory=build_custom_menu,
    pair_editor=run_pair_editor,
) -> bool:
    """The custom-params add/edit/delete loop. Returns True on any change."""
    changed = False
    while True:
        pairs = get_custom_model_settings(model_name)
        result = menu_factory(pairs, model_name).run()
        if result.cancelled or result.item is None:
            return changed
        value = result.item.value
        if isinstance(value, tuple) and value[0] == _DELETE_PAIR:
            set_custom_model_setting(model_name, value[1], None)
            changed = True
            continue
        if value == _ADD_PAIR:
            saved = pair_editor(model_name)
        else:
            initial = f"{value} = {_format_custom_value(pairs[value])}"
            saved = pair_editor(model_name, initial=initial)
            if saved and saved[0] != value:
                set_custom_model_setting(model_name, value, None)  # renamed
        if saved:
            set_custom_model_setting(model_name, saved[0], saved[1])
            changed = True


# -- orchestration ------------------------------------------------------------


def run_settings_flow(
    model_name: str,
    models_config: Optional[dict],
    settings_menu_factory=build_settings_menu,
    choice_editor_factory=build_choice_editor,
    numeric_editor=run_numeric_editor,
    custom_flow=run_custom_params_flow,
) -> bool:
    """Edit loop for one model's settings. Returns True on any change."""
    changed = False
    cursor = 0
    while True:
        menu = settings_menu_factory(model_name, models_config, initial_index=cursor)
        result = menu.run()
        if result.cancelled or result.item is None:
            return changed
        value = result.item.value
        if isinstance(value, tuple) and value[0] == _RESET:
            reset_setting(model_name, value[1])
            changed = True
            continue
        setting_key = value
        keys = supported_settings(model_name, models_config)
        cursor = keys.index(setting_key) if setting_key in keys else 0
        setting_def = SETTING_DEFINITIONS[setting_key]
        current = _get_model_display_settings(model_name, models_config).get(
            setting_key
        )

        if setting_key == CUSTOM_MODEL_SETTING:
            changed = custom_flow(model_name) or changed
        elif setting_def.get("type") in ("choice", "boolean"):
            pick = choice_editor_factory(
                setting_key, model_name, models_config, current
            ).run()
            if not pick.cancelled and pick.item is not None:
                save_setting(model_name, setting_key, pick.item.value)
                changed = True
        else:
            did_edit, new_value = numeric_editor(setting_key, model_name, current)
            if did_edit:
                save_setting(model_name, setting_key, new_value)
                changed = True


def run_model_settings_flow(
    models_config: Optional[dict] = None,
    models_menu_factory=build_models_menu,
    settings_flow=run_settings_flow,
) -> bool:
    """Model list -> per-model settings loop. Returns True on any change."""
    if models_config is None:
        models_config = ModelFactory.load_config()
    models = _load_all_model_names(models_config)
    if not models:
        emit_info("No models configured.")
        return False
    changed = False
    current = get_global_model_name()
    while True:
        result = models_menu_factory(models, current, models_config).run()
        if result.cancelled or result.item is None:
            return changed
        current = result.item.value
        changed = settings_flow(current, models_config) or changed


def interactive_model_settings() -> bool:
    """Show the model-settings TUI. True when any setting changed."""
    from code_puppy.command_line.menu_session import menu_session

    set_awaiting_user_input(True)
    try:
        with menu_session():
            return run_model_settings_flow()
    finally:
        set_awaiting_user_input(False)


def show_model_settings_summary(model_name: Optional[str] = None) -> None:
    """Print a summary of current model settings to the console."""
    model = model_name or get_global_model_name()
    settings = _get_model_display_settings(model)

    if not settings:
        emit_info(f"No custom settings configured for {model} (using model defaults)")
        return

    emit_info(f"Settings for {model}:")
    for setting_key, value in settings.items():
        setting_def = SETTING_DEFINITIONS.get(setting_key, {})
        name = setting_def.get("name", setting_key)
        emit_info(f"  {name}: {format_value(setting_key, value, model)}")
