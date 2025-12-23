"""Tests for builtin themes and theme registry."""

from code_puppy.theming.builtin_themes import BUILTIN_THEMES, DEFAULT_THEME
from code_puppy.theming.theme_models import Theme


class TestBuiltinThemes:
    """Test builtin theme definitions and quality."""

    def test_all_builtin_themes_exist(self):
        """Test that the expected builtin themes are present."""
        expected_themes = [
            "default",
            "ocean-depths",
            "forest-night",
            "synthwave",
            "monokai-pro",
            "solarized-dark",
            "dracula",
            "nord",
            "gruvbox",
            "tokyo-night",
            "catppuccin-mocha",
        ]

        for theme_name in expected_themes:
            assert theme_name in BUILTIN_THEMES, f"Missing theme: {theme_name}"

        # Should have exactly the expected themes
        assert len(BUILTIN_THEMES) == len(expected_themes)

    def test_builtin_themes_are_valid_themes(self):
        """Test that all builtin themes are valid Theme objects."""
        for theme_name, theme in BUILTIN_THEMES.items():
            assert isinstance(theme, Theme), f"{theme_name} is not a Theme instance"

            # Check required fields
            assert hasattr(theme, "name")
            assert hasattr(theme, "display_name")
            assert hasattr(theme, "description")
            assert hasattr(theme, "colors")

            # Check non-empty fields
            assert theme.name == theme_name, (
                f"Theme name mismatch: {theme.name} != {theme_name}"
            )
            assert len(theme.display_name) > 0, f"Empty display_name for {theme_name}"
            assert len(theme.description) > 0, f"Empty description for {theme_name}"
            assert theme.colors is not None, f"Null colors for {theme_name}"

    def test_each_theme_has_all_color_slots(self):
        """Test that every theme has all required color slots populated."""
        required_color_slots = [
            "error_style",
            "warning_style",
            "success_style",
            "info_style",
            "debug_style",
            "header_style",
            "prompt_style",
            "accent_style",
            "muted_style",
            "highlight_style",
            "reasoning_header_style",
            "response_header_style",
            "file_path_style",
            "line_number_style",
            "command_style",
            "spinner_style",
            "spinner_text_style",
            "panel_border_style",
            "panel_title_style",
            "nav_key_style",
            "nav_text_style",
        ]

        for theme_name, theme in BUILTIN_THEMES.items():
            colors = theme.colors

            for color_slot in required_color_slots:
                assert hasattr(colors, color_slot), (
                    f"Missing {color_slot} in {theme_name}"
                )
                color_value = getattr(colors, color_slot)
                assert isinstance(color_value, str), (
                    f"Invalid color type for {color_slot} in {theme_name}"
                )
                assert len(color_value) > 0, (
                    f"Empty color for {color_slot} in {theme_name}"
                )

    def test_color_values_are_valid_format(self):
        """Test that theme color values follow valid CSS color formats."""
        for theme_name, theme in BUILTIN_THEMES.items():
            colors = theme.colors

            for attr_name in colors.__dict__:
                color_value = getattr(colors, attr_name)

                # Should be a string
                assert isinstance(color_value, str), (
                    f"Color {attr_name} in {theme_name} not a string"
                )

                # Remove 'bold ' prefix if present
                clean_color = color_value.replace("bold ", "").strip()

                # Should be valid hex color format
                assert clean_color.startswith("#"), (
                    f"Color {attr_name} in {theme_name} doesn't start with #"
                )
                assert len(clean_color) in [4, 7], (
                    f"Color {attr_name} in {theme_name} has invalid length"
                )

                # Should contain valid hex characters
                hex_part = clean_color[1:]
                assert all(c in "0123456789abcdefABCDEF" for c in hex_part), (
                    f"Color {attr_name} in {theme_name} has invalid hex"
                )

    def test_theme_names_follow_conventions(self):
        """Test that theme names follow expected conventions."""
        for theme_name in BUILTIN_THEMES:
            # Should be lowercase
            assert theme_name == theme_name.lower(), (
                f"Theme name {theme_name} not lowercase"
            )

            # Should use hyphens as separators
            assert "-" in theme_name or "_" not in theme_name, (
                f"Theme name {theme_name} uses underscores"
            )

            # Should be valid identifier characters
            assert theme_name.replace("-", "_").isidentifier(), (
                f"Theme name {theme_name} not valid identifier"
            )

    def test_theme_display_names_have_unique_emoji(self):
        """Test that theme display names include unique emoji for visual identification."""
        emoji_set = set()

        for theme_name, theme in BUILTIN_THEMES.items():
            display_name = theme.display_name

            # Should contain at least one emoji
            has_emoji = any(ord(char) > 127 for char in display_name)
            assert has_emoji, (
                f"Theme {theme_name} display_name lacks emoji: {display_name}"
            )

            # Extract emoji (simplified - just look for non-ASCII)
            emoji = [char for char in display_name if ord(char) > 127]
            if emoji:
                emoji_set.add(emoji[0])

        # Should have multiple unique emojis (visual distinction)
        assert len(emoji_set) >= 5, f"Not enough unique emojis: {emoji_set}"

    def test_theme_descriptions_are_meaningful(self):
        """Test that theme descriptions are descriptive and unique."""
        descriptions = set()

        for theme_name, theme in BUILTIN_THEMES.items():
            description = theme.description

            # Should be meaningful length
            assert len(description) >= 10, (
                f"Too short description for {theme_name}: {description}"
            )
            assert len(description) <= 200, (
                f"Too long description for {theme_name}: {description}"
            )

            # Should be unique
            assert description not in descriptions, (
                f"Duplicate description for {theme_name}: {description}"
            )
            descriptions.add(description)

            # Should contain relevant keywords
            assert any(
                word in description.lower()
                for word in ["color", "theme", "dark", "light", "palette", "style"]
            ), f"Description lacks keywords for {theme_name}: {description}"

    def test_theme_color_cohesion(self):
        """Test that theme colors are cohesive and visually consistent."""
        for theme_name, theme in BUILTIN_THEMES.items():
            colors = theme.colors

            # Extract base colors (without 'bold ')
            color_values = []
            for attr_name in colors.__dict__:
                color = getattr(colors, attr_name)
                clean_color = color.replace("bold ", "").strip()
                color_values.append(clean_color)

            # Should have multiple unique colors (not all the same)
            unique_colors = set(color_values)
            assert len(unique_colors) >= 10, (
                f"Not enough color variety in {theme_name}: {len(unique_colors)} unique colors"
            )

            # Should have some color harmony (related base colors)
            # This is a loose test - just ensure not all colors are wildly different
            # In a real system, you might test for complementary colors, similar hues, etc.

    def test_theme_specific_characteristics(self):
        """Test that specific themes have expected characteristics."""
        # Test dracula theme has purple/pink accents
        dracula = BUILTIN_THEMES["dracula"]
        assert (
            "#ff79c6" in dracula.colors.error_style
            or "#ff5555" in dracula.colors.error_style
        ), "Dracula should have pinkish error colors"

        # Test synthwave has neon colors
        synthwave = BUILTIN_THEMES["synthwave"]
        synthwave_colors = [
            getattr(synthwave.colors, attr).replace("bold ", "").strip()
            for attr in synthwave.colors.__dict__
        ]
        # This is a loose test - synthwave should have bright, neon-like colors
        assert len(synthwave_colors) > 0, "Synthwave should have multiple colors"

        # Test nord has cool blue tones
        nord = BUILTIN_THEMES["nord"]
        nord_colors = [
            getattr(nord.colors, attr).replace("bold ", "").strip()
            for attr in nord.colors.__dict__
        ]
        # Nord should have blue/grey color scheme (simplified test)
        assert len(nord_colors) > 0, "Nord should have multiple colors"

    def test_default_theme_is_valid(self):
        """Test that DEFAULT_THEME is properly set and valid."""
        assert DEFAULT_THEME is not None, "DEFAULT_THEME should be set"
        assert DEFAULT_THEME.name == "default", "DEFAULT_THEME should be 'default'"

        # Should be one of the builtin themes
        assert DEFAULT_THEME.name in BUILTIN_THEMES, (
            "DEFAULT_THEME should be in builtin themes"
        )

        # Should be the same object as the builtin
        assert DEFAULT_THEME is BUILTIN_THEMES["default"], (
            "DEFAULT_THEME should reference builtin default"
        )

        # Should be a valid theme
        assert hasattr(DEFAULT_THEME, "colors")
        assert DEFAULT_THEME.colors is not None

    def test_theme_consistency_across_builtins(self):
        """Test consistency requirements across all builtin themes."""
        # All themes should have the same color slot structure
        reference_colors = list(BUILTIN_THEMES["default"].colors.__dict__.keys())

        for theme_name, theme in BUILTIN_THEMES.items():
            theme_colors = list(theme.colors.__dict__.keys())
            assert set(reference_colors) == set(theme_colors), (
                f"Color slots mismatch in {theme_name}"
            )

    def test_theme_registry_consistency(self):
        """Test that the builtin theme registry is consistent."""
        # BUILTIN_THEMES should be a dict
        assert isinstance(BUILTIN_THEMES, dict), "BUILTIN_THEMES should be a dictionary"

        # All keys should be unique
        assert len(BUILTIN_THEMES) == len(set(BUILTIN_THEMES.keys())), (
            "Duplicate theme names in registry"
        )

        # All values should be Theme instances
        for theme_name, theme in BUILTIN_THEMES.items():
            assert theme.name == theme_name, (
                f"Registry key-value mismatch: {theme_name} != {theme.name}"
            )
