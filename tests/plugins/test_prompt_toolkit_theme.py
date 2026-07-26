"""Contract tests for the theme plugin's central prompt-toolkit adapter."""

from prompt_toolkit.styles import Style

from code_puppy.plugins.theme.bundled_palettes import CATPPUCCIN_MOCHA, SOLARIZED_LIGHT
from code_puppy.plugins.theme.prompt_toolkit_theme import (
    _contrast_ratio,
    get_style_rules,
    merge_with_active_style,
)


_SEMANTIC_ROLES = {
    "",
    "tui",
    "tui.header",
    "tui.title",
    "tui.body",
    "tui.label",
    "tui.muted",
    "tui.border",
    "tui.selected",
    "tui.help",
    "tui.help-key",
    "tui.success",
    "tui.warning",
    "tui.error",
    "tui.input",
    "tui.input.focused",
}

_COMPLETION_ADAPTER_ROLES = {
    "completion-menu",
    "completion-menu.completion",
    "completion-menu.completion.current",
    "completion-menu.meta.completion",
    "completion-menu.meta.completion.current",
    "completion-menu.multi-column-meta",
    "scrollbar.background",
    "scrollbar.button",
}


def test_active_adapter_exposes_shared_semantic_roles(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.plugins.theme.prompt_toolkit_theme._active_palette",
        lambda: SOLARIZED_LIGHT,
    )

    rules = get_style_rules()
    assert _SEMANTIC_ROLES <= rules.keys()
    assert _COMPLETION_ADAPTER_ROLES <= rules.keys()
    assert "#ffffff" not in repr(rules)
    assert "#000000" not in repr(rules)


def test_solarized_light_muted_text_does_not_use_its_background(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.plugins.theme.prompt_toolkit_theme._active_palette",
        lambda: SOLARIZED_LIGHT,
    )

    muted_rule = get_style_rules()["tui.muted"]

    assert muted_rule == f"fg:{SOLARIZED_LIGHT['ansi'][14]}"
    assert SOLARIZED_LIGHT["bg"] not in muted_rule


def test_dark_theme_muted_text_meets_wcag_contrast(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.plugins.theme.prompt_toolkit_theme._active_palette",
        lambda: CATPPUCCIN_MOCHA,
    )

    muted = get_style_rules()["tui.muted"].removeprefix("fg:")

    assert _contrast_ratio(muted, CATPPUCCIN_MOCHA["bg"]) >= 4.5
    assert muted != CATPPUCCIN_MOCHA["ansi"][8]


def test_menu_style_merges_over_semantic_base(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.plugins.theme.prompt_toolkit_theme._active_palette",
        lambda: SOLARIZED_LIGHT,
    )
    local_style = Style.from_dict(
        {
            "tui.header": "fg:#123456",
            "menu-only": "italic",
        }
    )

    merged = merge_with_active_style(local_style)

    header = merged.get_attrs_for_style_str("class:tui.header")
    body = merged.get_attrs_for_style_str("class:tui.body")
    menu_only = merged.get_attrs_for_style_str("class:menu-only")
    assert header.color == "123456"
    assert body.color == SOLARIZED_LIGHT["fg"].lstrip("#")
    assert menu_only.italic is True
