"""colors_menu is a pure data module now (the /colors TUI was removed;
theming owns banner styling). These tests pin the data contract the
theme plugin depends on."""

from code_puppy.command_line.colors_menu import (
    BANNER_COLORS,
    BANNER_DISPLAY_INFO,
    BANNER_SAMPLE_CONTENT,
)


class TestBannerDataContract:
    def test_display_info_and_samples_cover_the_same_banners(self):
        assert set(BANNER_DISPLAY_INFO) == set(BANNER_SAMPLE_CONTENT)

    def test_display_info_entries_are_label_icon_pairs(self):
        for name, value in BANNER_DISPLAY_INFO.items():
            assert isinstance(value, tuple) and len(value) == 2, name
            label, icon = value
            assert isinstance(label, str) and label, name
            assert isinstance(icon, str), name

    def test_banner_colors_are_nonempty_rich_color_names(self):
        assert BANNER_COLORS, "palette must not be empty"
        for label, rich_name in BANNER_COLORS.items():
            assert isinstance(label, str) and label
            assert isinstance(rich_name, str) and rich_name

    def test_module_stays_prompt_toolkit_free(self):
        # The whole point of the slim-down: importing this module must
        # never drag UI dependencies in.
        import sys

        import code_puppy.command_line.colors_menu as module

        source = open(module.__file__, encoding="utf-8").read()
        assert "prompt_toolkit" not in source
        assert "code_puppy.command_line.colors_menu" in sys.modules
