"""Tests for the /theme custom-command plugin."""

from __future__ import annotations

import random
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.theme.themes import (
    CURATED_THEMES,
    DEFAULT,
    MENU,
    MENU_BY_INDEX,
    MENU_BY_NAME,
    SURPRISE,
    apply,
    color_remap_for,
    colors_for,
    content_styles_for,
    resolve_theme_arg,
    terminal_palette_for,
)
from code_puppy.plugins.theme.bundled_palettes import (
    BUBBLEGUM_PINK,
    CATPPUCCIN_LATTE,
    CATPPUCCIN_MOCHA,
    DEEP_BLACK,
    FOREST,
    GITHUB_LIGHT,
    GREEN_SCREEN,
    OCEAN,
    PURPLE_PUPPY,
    ROSE_PINE_DAWN,
    SOLARIZED_LIGHT,
    SUNSET,
    TOKYO_NIGHT,
    VAPORWAVE,
)
from code_puppy.plugins.theme.picker import (
    THEMES_PER_PAGE,
    _format_menu,
    _move_page,
    _page_for_index,
    _total_pages,
)
from code_puppy.plugins.theme.rich_themes import make_remap, _swap_color, _safe_parse
from code_puppy.plugins.theme.content_styles import (
    CONTENT_KEYS,
    DEFAULT_CONTENT_STYLES,
    get_all_content_styles,
    get_content_style,
    apply_content_styles,
    restore_defaults,
)
from code_puppy.plugins.theme.osc_palette import (
    _osc,
    BEL,
    ESC,
    get_saved_palette,
    apply_palette,
    reset_palette,
)


# ---------------------------------------------------------------------------
# themes.py
# ---------------------------------------------------------------------------
class TestThemeCatalog:
    def test_curated_themes_count(self):
        assert len(CURATED_THEMES) == 14

    def test_menu_has_expected_entries(self):
        names = [name for name, _ in MENU]
        assert len(names) == 16
        assert "ocean" in names
        assert "forest" in names
        assert "sunset" in names
        assert "vaporwave" in names
        assert "bubblegum-pink" in names
        assert "purple-puppy" in names
        assert "catppuccin-mocha" in names
        assert "tokyo-night" in names
        assert "green-screen" in names
        assert "deep-black" in names
        assert "solarized-light" in names
        assert "github-light" in names
        assert "rose-pine-dawn" in names
        assert "surprise" in names
        assert "default" in names

    def test_menu_by_index_maps_strings(self):
        assert MENU_BY_INDEX["1"] == "ocean"
        assert MENU_BY_INDEX["5"] == "bubblegum-pink"
        assert MENU_BY_INDEX["6"] == "purple-puppy"
        assert MENU_BY_INDEX["7"] == "catppuccin-mocha"
        assert MENU_BY_INDEX["10"] == "green-screen"
        assert MENU_BY_INDEX["12"] == "solarized-light"
        assert MENU_BY_INDEX[str(len(MENU))] == "default"

    def test_aliases_resolve(self):
        assert MENU_BY_NAME["mocha"] is CURATED_THEMES["catppuccin-mocha"]
        assert MENU_BY_NAME["bubblegum"] is CURATED_THEMES["bubblegum-pink"]
        assert MENU_BY_NAME["pink"] is CURATED_THEMES["bubblegum-pink"]
        assert MENU_BY_NAME["puppy"] is CURATED_THEMES["purple-puppy"]
        assert MENU_BY_NAME["purple"] is CURATED_THEMES["purple-puppy"]
        assert MENU_BY_NAME["tokyo"] is CURATED_THEMES["tokyo-night"]
        assert MENU_BY_NAME["green"] is CURATED_THEMES["green-screen"]
        assert MENU_BY_NAME["crt"] is CURATED_THEMES["green-screen"]
        assert MENU_BY_NAME["solarized"] is CURATED_THEMES["solarized-light"]
        assert MENU_BY_NAME["github"] is CURATED_THEMES["github-light"]
        assert MENU_BY_NAME["rose-pine"] is CURATED_THEMES["rose-pine-dawn"]
        assert MENU_BY_NAME["random"] is SURPRISE
        assert MENU_BY_NAME["reset"] is DEFAULT

    def test_every_curated_theme_has_required_keys(self):
        for name, theme in CURATED_THEMES.items():
            assert "icon" in theme, f"{name} missing icon"
            assert "label" in theme, f"{name} missing label"
            assert "colors" in theme, f"{name} missing colors"
            assert "content_styles" in theme, f"{name} missing content_styles"
            assert "color_remap" in theme, f"{name} missing color_remap"
            assert "terminal_palette" in theme, f"{name} missing terminal_palette"


class TestColorsFor:
    def test_curated_theme_returns_mapping(self):
        m = colors_for("ocean")
        assert isinstance(m, dict)
        assert len(m) > 0

    def test_all_menu_themes_produce_mappings(self):
        # "reset"/"defaults" are aliases for "default"; colors_for only
        # handles them via the literal "default" check, so use
        # resolve_theme_arg first (as the real command handler does).
        for name in MENU_BY_NAME:
            resolved = resolve_theme_arg(name) or name
            m = colors_for(resolved)
            assert isinstance(m, dict) and len(m) > 0, name

    def test_surprise_with_seed_is_deterministic(self):
        a = colors_for("surprise", rng=random.Random(42))
        b = colors_for("surprise", rng=random.Random(42))
        assert a == b

    def test_surprise_different_seeds_differ(self):
        a = colors_for("surprise", rng=random.Random(1))
        b = colors_for("surprise", rng=random.Random(999))
        assert a != b

    def test_default_returns_factory_colors(self):
        from code_puppy.config import DEFAULT_BANNER_COLORS

        m = colors_for("default")
        assert m == dict(DEFAULT_BANNER_COLORS)

    def test_unknown_theme_raises(self):
        with pytest.raises(KeyError):
            colors_for("nonexistent")


class TestContentStylesFor:
    def test_ocean_has_all_content_keys(self):
        s = content_styles_for("ocean")
        for key in CONTENT_KEYS:
            assert key in s

    def test_surprise_error_stays_red(self):
        s = content_styles_for("surprise", rng=random.Random(42))
        assert s["error"] == "bold red"

    def test_default_matches_factory(self):
        s = content_styles_for("default")
        assert s == dict(DEFAULT_CONTENT_STYLES)

    def test_unknown_theme_raises(self):
        with pytest.raises(KeyError):
            content_styles_for("nonexistent")


class TestColorRemapFor:
    def test_ocean_has_remap_entries(self):
        r = color_remap_for("ocean")
        assert isinstance(r, dict)
        assert len(r) > 0

    def test_default_returns_empty(self):
        assert color_remap_for("default") == {}

    def test_palette_first_themes_have_empty_remap(self):
        for name in (
            "mocha",
            "tokyo",
            "solarized",
            "github",
            "rose-pine",
        ):
            assert color_remap_for(name) == {}, name

    def test_latte_has_remap_entries(self):
        r = color_remap_for("latte")
        assert isinstance(r, dict)
        assert len(r) > 0

    def test_green_screen_remaps_both_white_slots(self):
        r = color_remap_for("green-screen")
        assert r["white"] == "#6a9955"
        assert r["bright_white"] == "#00ff00"

    def test_unknown_theme_raises(self):
        with pytest.raises(KeyError):
            color_remap_for("nonexistent")


class TestTerminalPaletteFor:
    def test_ocean_has_bg_fg_ansi(self):
        p = terminal_palette_for("ocean")
        assert p is not None
        assert "bg" in p and "fg" in p and "ansi" in p
        assert len(p["ansi"]) == 16

    def test_default_returns_none(self):
        assert terminal_palette_for("default") is None

    def test_surprise_returns_bg_fg(self):
        p = terminal_palette_for("surprise", rng=random.Random(42))
        assert p is not None
        assert "bg" in p and "fg" in p

    def test_unknown_theme_raises(self):
        with pytest.raises(KeyError):
            terminal_palette_for("nonexistent")


class TestApply:
    def test_calls_setter_for_each_banner(self):
        setter = MagicMock()
        mapping = {"a": "red", "b": "blue"}
        apply(mapping, setter=setter)
        assert setter.call_count == 2
        setter.assert_any_call("a", "red")
        setter.assert_any_call("b", "blue")


class TestResolveThemeArg:
    @pytest.mark.parametrize(
        "arg,expected",
        [
            ("1", "ocean"),
            ("ocean", "ocean"),
            ("forest", "forest"),
            ("random", "surprise"),
            ("reset", "default"),
            ("defaults", "default"),
        ],
    )
    def test_valid_args(self, arg, expected):
        assert resolve_theme_arg(arg) == expected

    def test_unknown_returns_none(self):
        assert resolve_theme_arg("nope") is None
        assert resolve_theme_arg("") is None

    def test_alias_keys_are_accepted(self):
        assert resolve_theme_arg("mocha") is not None
        assert resolve_theme_arg("bubblegum") is not None
        assert resolve_theme_arg("pink") is not None
        assert resolve_theme_arg("tokyo") is not None
        assert resolve_theme_arg("green") is not None
        assert resolve_theme_arg("crt") is not None
        assert resolve_theme_arg("gruvbox") is None


# ---------------------------------------------------------------------------
# picker.py
# ---------------------------------------------------------------------------
class TestThemePickerPagination:
    def test_catalog_is_split_into_pages(self):
        assert THEMES_PER_PAGE == 5
        assert _total_pages() == 4
        assert _page_for_index(0) == 0
        assert _page_for_index(5) == 1
        assert _page_for_index(len(MENU) - 1) == 3

    def test_menu_only_renders_the_selected_page(self):
        rendered = "".join(text for _, text in _format_menu(5))

        assert "Page 2/4" in rendered
        assert "6. " in rendered
        assert "10. " in rendered
        assert "Purple Puppy" in rendered
        assert "Green Screen" in rendered
        assert "Ocean" not in rendered
        assert "Deep Black" not in rendered

    def test_menu_uses_semantic_roles_for_chrome(self):
        fragments = list(_format_menu(0))
        styles = {style for style, _ in fragments}

        assert {
            "class:tui.header",
            "class:tui.muted",
            "class:tui.selected",
            "class:tui.body",
            "class:tui.help",
            "class:tui.help-key",
        } <= styles
        assert not any("ansi" in style for style in styles)

    def test_page_navigation_clamps_at_catalog_edges(self):
        assert _move_page(2, 1) == 7
        assert _move_page(7, -1) == 2
        assert _move_page(0, -1) == 0
        assert _move_page(len(MENU) - 2, 1) == len(MENU) - 1


# ---------------------------------------------------------------------------
# bundled_palettes.py
# ---------------------------------------------------------------------------
def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


class TestBundledPalettes:
    @pytest.mark.parametrize(
        "palette",
        [
            OCEAN,
            FOREST,
            SUNSET,
            VAPORWAVE,
            BUBBLEGUM_PINK,
            GREEN_SCREEN,
            PURPLE_PUPPY,
            CATPPUCCIN_MOCHA,
            CATPPUCCIN_LATTE,
            TOKYO_NIGHT,
            DEEP_BLACK,
            SOLARIZED_LIGHT,
            GITHUB_LIGHT,
            ROSE_PINE_DAWN,
        ],
    )
    def test_palette_structure(self, palette):
        assert "bg" in palette
        assert "fg" in palette
        assert "ansi" in palette
        assert len(palette["ansi"]) == 16

    @pytest.mark.parametrize(
        "palette",
        [
            OCEAN,
            FOREST,
            SUNSET,
            VAPORWAVE,
            BUBBLEGUM_PINK,
            GREEN_SCREEN,
            PURPLE_PUPPY,
            CATPPUCCIN_MOCHA,
            CATPPUCCIN_LATTE,
            TOKYO_NIGHT,
            DEEP_BLACK,
            SOLARIZED_LIGHT,
            GITHUB_LIGHT,
            ROSE_PINE_DAWN,
        ],
    )
    def test_palette_hex_format(self, palette):
        assert palette["bg"].startswith("#")
        assert palette["fg"].startswith("#")
        for color in palette["ansi"]:
            assert color.startswith("#"), f"Bad ANSI color: {color}"

    def test_green_screen_uses_llxprt_phosphor_colors(self):
        assert GREEN_SCREEN["bg"] == "#000000"
        assert GREEN_SCREEN["fg"] == "#6a9955"
        assert "#00ff00" in GREEN_SCREEN["ansi"]
        assert terminal_palette_for("green-screen") is GREEN_SCREEN

    def test_green_screen_banner_labels_have_accessible_contrast(self):
        banner_colors = set(colors_for("green-screen").values())

        assert banner_colors.isdisjoint({GREEN_SCREEN["bg"], GREEN_SCREEN["fg"]})
        assert all(
            _contrast_ratio(color, GREEN_SCREEN["fg"]) >= 4.5 for color in banner_colors
        )

    def test_purple_puppy_muted_text_has_accessible_contrast(self):
        """ANSI bright black is muted TUI text and must remain readable."""
        assert _contrast_ratio(PURPLE_PUPPY["bg"], PURPLE_PUPPY["ansi"][8]) >= 4.5


# ---------------------------------------------------------------------------
# rich_themes.py
# ---------------------------------------------------------------------------
class TestRichThemes:
    def test_make_remap_filters_none(self):
        r = make_remap(cyan="blue", magenta=None, blue="green")
        assert "cyan" in r and "blue" in r
        assert "magenta" not in r

    def test_make_remap_filters_unparseable(self):
        r = make_remap(cyan="totally_not_a_color_xyz")
        assert r == {}

    def test_safe_parse_valid(self):
        assert _safe_parse("red") is not None
        assert _safe_parse("blue") is not None

    def test_safe_parse_invalid_returns_none(self):
        assert _safe_parse("not_a_real_color_999") is None

    def test_swap_color_noop_when_no_match(self):
        from rich.style import Style

        style = Style(color="red")
        result = _swap_color(style, {"blue": "green"})
        assert result.color.name == "red"

    def test_swap_color_replaces_match(self):
        from rich.style import Style

        style = Style(color="cyan")
        result = _swap_color(style, {"cyan": "blue"})
        assert result.color.name == "blue"


# ---------------------------------------------------------------------------
# content_styles.py
# ---------------------------------------------------------------------------
class TestContentStyles:
    def test_content_keys_count(self):
        assert len(CONTENT_KEYS) == 8

    def test_default_styles_has_all_keys(self):
        for key in CONTENT_KEYS:
            assert key in DEFAULT_CONTENT_STYLES

    def test_get_content_style_returns_default(self):
        style = get_content_style("error")
        assert isinstance(style, str)
        assert len(style) > 0

    def test_get_content_style_unknown_raises(self):
        with pytest.raises(KeyError):
            get_content_style("not_a_key")

    def test_get_all_returns_full_mapping(self):
        styles = get_all_content_styles()
        assert len(styles) == 8
        for key in CONTENT_KEYS:
            assert key in styles

    def test_apply_missing_key_raises(self):
        with pytest.raises(ValueError, match="missing keys"):
            apply_content_styles({"info": "cyan"}, persist=False)

    def test_apply_and_restore_roundtrip(self):
        original = get_all_content_styles()
        custom = {k: "magenta" for k in CONTENT_KEYS}
        custom["error"] = "bold red"
        apply_content_styles(custom, persist=False)
        restore_defaults(persist=False)
        restored = get_all_content_styles()
        assert restored == original


# ---------------------------------------------------------------------------
# osc_palette.py
# ---------------------------------------------------------------------------
class TestOscPalette:
    def test_osc_bg_sequence(self):
        seq = _osc("11", "#0a1929")
        assert seq == f"{ESC}]11;#0a1929{BEL}"

    def test_osc_fg_sequence(self):
        seq = _osc("10", "#ffffff")
        assert seq == f"{ESC}]10;#ffffff{BEL}"

    def test_osc_ansi_slot_sequence(self):
        seq = _osc("4", "0", "#ff0000")
        assert seq == f"{ESC}]4;0;#ff0000{BEL}"

    def test_apply_palette_emits_sequences(self):
        palette = {"bg": "#000", "fg": "#fff", "ansi": ["#111"] * 16}
        with patch("code_puppy.plugins.theme.osc_palette._emit") as mock_emit:
            apply_palette(palette, persist=False, register_reset=False)
        assert mock_emit.call_count == 18  # 1 bg + 1 fg + 16 ansi

    def test_reset_palette_emits_resets(self):
        with patch("code_puppy.plugins.theme.osc_palette._emit") as mock_emit:
            reset_palette(persist=False)
        assert mock_emit.call_count == 3  # ansi + bg + fg

    def test_get_saved_palette_returns_none_when_empty(self):
        with patch("code_puppy.plugins.theme.osc_palette.get_value", return_value=None):
            assert get_saved_palette() is None

    def test_get_saved_palette_returns_dict(self):
        import json

        data = {"bg": "#000", "fg": "#fff"}
        with patch(
            "code_puppy.plugins.theme.osc_palette.get_value",
            return_value=json.dumps(data),
        ):
            result = get_saved_palette()
        assert result == data


# ---------------------------------------------------------------------------
# register_callbacks.py
# ---------------------------------------------------------------------------
class TestRegisterCallbacks:
    def test_prompt_text_uses_active_terminal_foreground(self):
        from code_puppy.plugins.theme.register_callbacks import _prompt_text_color

        with patch(
            "code_puppy.plugins.theme.register_callbacks._active_terminal_palette",
            return_value=("green-screen", GREEN_SCREEN),
        ):
            assert _prompt_text_color(None) == "#6a9955"

    def test_green_screen_highlighter_removes_monokai_white(self):
        from termflow.syntax import Highlighter

        from code_puppy.plugins.theme.register_callbacks import _termflow_highlighter

        with patch(
            "code_puppy.plugins.theme.register_callbacks._active_terminal_palette",
            return_value=("green-screen", GREEN_SCREEN),
        ):
            highlighter = _termflow_highlighter(Highlighter())

        rendered = highlighter.highlight_line("plain code", "text")
        assert "38;2;114;168;91" in rendered
        assert "38;2;255;255;255" not in rendered

    def test_green_screen_highlighter_uses_phosphor_intensities(self):
        from termflow.syntax import Highlighter

        from code_puppy.plugins.theme.register_callbacks import _termflow_highlighter

        with patch(
            "code_puppy.plugins.theme.register_callbacks._active_terminal_palette",
            return_value=("green-screen", GREEN_SCREEN),
        ):
            highlighter = _termflow_highlighter(Highlighter())

        rendered = highlighter.highlight_line(
            "# dim comment\ndef glowing():\n    return 42", "python"
        )
        assert "38;2;69;107;79" in rendered  # dark phosphor comment
        assert "38;2;57;231;95" in rendered  # bright keyword
        assert "38;2;138;203;114" in rendered  # normal literal

    def test_solarized_light_code_uses_dark_default_foreground(self):
        from termflow.syntax import Highlighter

        from code_puppy.plugins.theme.register_callbacks import _termflow_highlighter

        with patch(
            "code_puppy.plugins.theme.register_callbacks._active_terminal_palette",
            return_value=("solarized-light", SOLARIZED_LIGHT),
        ):
            highlighter = _termflow_highlighter(Highlighter())

        rendered = highlighter.highlight_line("palette = Palette()", "python")
        assert "38;2;101;123;131" in rendered  # dark base foreground
        assert "38;2;238;232;213" not in rendered  # near-background ANSI white

    def test_termflow_style_uses_active_terminal_palette(self):
        from termflow.render.style import RenderStyle

        from code_puppy.plugins.theme.register_callbacks import _termflow_style

        default = RenderStyle.default()
        with (
            patch(
                "code_puppy.config.get_value",
                return_value="green-screen",
            ),
            patch(
                "code_puppy.plugins.theme.osc_palette.get_saved_palette",
                return_value=GREEN_SCREEN,
            ),
        ):
            style = _termflow_style(default)

        assert style is not default
        assert style.bright == "#6a9955"
        assert style.head == "#00ff00"
        assert style.symbol == "#6a9955"
        assert style.dark == "#000000"
        assert style.link == "#6a9955"
        assert style.error == "#6a9955"

    def test_termflow_style_preserves_default_without_active_theme(self):
        from termflow.render.style import RenderStyle

        from code_puppy.plugins.theme.register_callbacks import _termflow_style

        default = RenderStyle.default()
        with patch(
            "code_puppy.config.get_value",
            return_value="default",
        ):
            assert _termflow_style(default) is default

    def test_prompt_toolkit_style_shim_delegates_to_merge(self):
        """The lazy shim must forward its argument to merge_with_active_style.

        Regression guard: an earlier version used ``*args, **kwargs`` which
        silently accepted signatures that would have TypeError'd against the
        real callable. Keeping this test in place ensures the shim stays a
        1:1 stand-in.
        """
        from code_puppy.plugins.theme.register_callbacks import (
            _prompt_toolkit_style,
        )

        sentinel = object()
        with patch(
            "code_puppy.plugins.theme.prompt_toolkit_theme.merge_with_active_style",
            return_value=sentinel,
        ) as mock_merge:
            result = _prompt_toolkit_style("input-style")

        assert result is sentinel
        mock_merge.assert_called_once_with("input-style")

    def test_prompt_toolkit_style_shim_reports_real_callback_name(self):
        """code_puppy.callbacks logs callback.__name__ on failure; the shim
        preserves the real symbol name so error output stays useful."""
        from code_puppy.plugins.theme.register_callbacks import (
            _prompt_toolkit_style,
        )

        assert _prompt_toolkit_style.__name__ == "merge_with_active_style"

    def test_first_run_applies_tokyo_night(self):
        from code_puppy.plugins.theme.register_callbacks import (
            _apply_default_theme_on_first_run,
        )

        with (
            patch(
                "code_puppy.config.get_value",
                return_value=None,
            ),
            patch("code_puppy.plugins.theme.themes.apply") as mock_apply,
            patch(
                "code_puppy.plugins.theme.content_styles.apply_content_styles"
            ) as mock_cs_apply,
            patch("code_puppy.plugins.theme.rich_themes.apply_remap") as mock_rt_apply,
            patch(
                "code_puppy.plugins.theme.osc_palette.get_saved_palette",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.theme.osc_palette.apply_palette"
            ) as mock_osc_apply,
            patch("code_puppy.config.set_config_value") as mock_set,
        ):
            _apply_default_theme_on_first_run()

        mock_apply.assert_called_once_with(colors_for("tokyo-night"))
        mock_cs_apply.assert_called_once_with(content_styles_for("tokyo-night"))
        mock_rt_apply.assert_called_once_with(color_remap_for("tokyo-night"))
        mock_osc_apply.assert_called_once_with(terminal_palette_for("tokyo-night"))
        mock_set.assert_called_once_with("theme_active_theme", "tokyo-night")

    def test_default_theme_preserves_saved_choice(self):
        from code_puppy.plugins.theme.register_callbacks import (
            _apply_default_theme_on_first_run,
        )

        with (
            patch(
                "code_puppy.config.get_value",
                return_value="purple-puppy",
            ),
            patch("code_puppy.plugins.theme.themes.apply") as mock_apply,
        ):
            _apply_default_theme_on_first_run()

        mock_apply.assert_not_called()

    def test_default_theme_preserves_legacy_palette(self):
        from code_puppy.plugins.theme.register_callbacks import (
            _apply_default_theme_on_first_run,
        )

        with (
            patch(
                "code_puppy.config.get_value",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.theme.osc_palette.get_saved_palette",
                return_value={"bg": "#123456"},
            ),
            patch("code_puppy.plugins.theme.themes.apply") as mock_apply,
            patch("code_puppy.config.set_config_value") as mock_set,
        ):
            _apply_default_theme_on_first_run()

        mock_apply.assert_not_called()
        mock_set.assert_called_once_with("theme_active_theme", "legacy-custom")

    def test_custom_help_returns_theme_entry(self):
        from code_puppy.plugins.theme.register_callbacks import _custom_help

        entries = dict(_custom_help())
        assert "theme" in entries

    def test_handle_theme_ignores_other_commands(self):
        from code_puppy.plugins.theme.register_callbacks import _handle_theme

        assert _handle_theme("/colors", "colors") is None

    def test_handle_theme_show(self):
        from code_puppy.plugins.theme.register_callbacks import _handle_theme

        with patch("code_puppy.messaging.emit_info") as mock_info:
            result = _handle_theme("/theme show", "theme")
        assert result is True
        assert mock_info.called

    def test_handle_theme_unknown_warns(self):
        from code_puppy.plugins.theme.register_callbacks import _handle_theme

        with patch("code_puppy.messaging.emit_warning") as mock_warn:
            result = _handle_theme("/theme bogus_theme", "theme")
        assert result is True
        assert mock_warn.called

    def test_handle_theme_by_name_applies(self):
        from code_puppy.plugins.theme.register_callbacks import _handle_theme

        with (
            patch("code_puppy.plugins.theme.themes.apply") as mock_apply,
            patch("code_puppy.plugins.theme.content_styles.apply_content_styles"),
            patch("code_puppy.plugins.theme.rich_themes.apply_remap"),
            patch("code_puppy.plugins.theme.osc_palette.apply_palette"),
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.messaging.emit_info"),
        ):
            result = _handle_theme("/theme ocean", "theme")
        assert result is True
        mock_apply.assert_called_once()

    def test_handle_theme_interactive_cancel(self):
        from code_puppy.plugins.theme.register_callbacks import _handle_theme

        with (
            patch(
                "code_puppy.plugins.theme.register_callbacks._run_interactive_picker",
                return_value=None,
            ),
            patch("code_puppy.messaging.emit_info") as mock_info,
        ):
            result = _handle_theme("/theme", "theme")
        assert result is True
        assert "unchanged" in str(mock_info.call_args)
