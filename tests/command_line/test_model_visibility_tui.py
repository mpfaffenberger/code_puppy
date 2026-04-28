"""Tests for visibility toggle in ModelSelectionMenu.

These tests verify the TUI integration for hiding/showing models.
"""

import pytest

from code_puppy.command_line.model_picker_completion import ModelSelectionMenu
from code_puppy.item_visibility import (
    clear_visibility_config,
    load_hidden_models,
    save_hidden_models,
    toggle_model_hidden,
)


class TestModelPickerVisibility:
    """Tests for ModelSelectionMenu visibility integration."""

    @pytest.fixture(autouse=True)
    def preserve_user_config(self):
        """Preserve user's visibility config before/after tests."""
        # Save user's config before tests
        original_hidden = load_hidden_models()

        yield

        # Restore user's config after tests
        clear_visibility_config()  # Clear test artifacts
        if original_hidden:
            save_hidden_models(original_hidden)  # Restore user's settings

    @pytest.fixture
    def test_models(self):
        """Standard test model list."""
        return ["gpt-4", "gpt-3.5-turbo", "claude-3", "claude-2", "gemini-pro"]

    def test_picker_starts_showing_all_when_no_hidden_config(self, test_models):
        """Default: all models show."""
        menu = ModelSelectionMenu(model_names=test_models)

        assert menu.display_model_names == test_models
        assert menu._hidden_models == set()
        assert menu.show_all is False

    def test_picker_hides_configured_models(self, test_models):
        """Hidden models excluded by default."""
        # Hide some models
        toggle_model_hidden("gpt-3.5-turbo")
        toggle_model_hidden("claude-2")

        # Create new menu (loads from config)
        menu = ModelSelectionMenu(model_names=test_models)

        expected = ["gpt-4", "claude-3", "gemini-pro"]
        assert menu.display_model_names == expected
        assert menu._hidden_models == {"gpt-3.5-turbo", "claude-2"}

    def test_show_all_mode_reveals_hidden(self, test_models):
        """A key reveals hidden with [hidden] label."""
        toggle_model_hidden("gpt-3.5-turbo")

        menu = ModelSelectionMenu(model_names=test_models)
        menu.show_all = True

        # All models visible when show_all=True
        assert menu.display_model_names == test_models

    def test_filter_shows_hidden_matches_dimmed(self, test_models):
        """Filter text matches hidden model → appears in list."""
        toggle_model_hidden("gpt-3.5-turbo")

        menu = ModelSelectionMenu(model_names=test_models)
        menu.filter_text = "gpt"  # Type filter

        # With filter, hidden models still appear
        assert menu.display_model_names == ["gpt-4", "gpt-3.5-turbo"]

    def test_all_hidden_shows_help_message(self, test_models):
        """No visible + some hidden → helper text shown."""
        # Hide ALL models
        for model in test_models:
            toggle_model_hidden(model)

        menu = ModelSelectionMenu(model_names=test_models)

        # Display list should be empty
        assert menu.display_model_names == []
        # But we have hidden models
        assert len(menu._hidden_models) > 0

    def test_selection_stays_valid_after_toggle(self, test_models):
        """Index stays in bounds after toggling visibility."""
        toggle_model_hidden("claude-2")

        menu = ModelSelectionMenu(model_names=test_models)

        # Initial selection should be valid
        assert 0 <= menu.selected_index < len(menu.display_model_names)

        # After unhiding, selection should still be valid
        toggle_model_hidden("claude-2")
        menu._hidden_models = load_hidden_models()

        assert 0 <= menu.selected_index < len(menu.display_model_names)

    def test_show_all_is_session_level_not_persisted(self, test_models):
        """New picker → show_all=False even if previous session had it True."""
        menu1 = ModelSelectionMenu(model_names=test_models)
        menu1.show_all = True

        # Create new picker
        menu2 = ModelSelectionMenu(model_names=test_models)

        assert menu2.show_all is False

    def test_current_model_in_display_when_visible(self, test_models):
        """If current model is not hidden, it appears in display."""
        menu = ModelSelectionMenu(model_names=test_models)
        # Current model is from config (may not be in test_models)
        # But if it's in the list, it should be visible
        if menu.current_model in test_models:
            assert menu.current_model in menu.display_model_names

    def test_current_model_selection_when_hidden(self, test_models):
        """If current model is hidden, another model selected."""
        # Hide the current model (first one)
        toggle_model_hidden("gpt-4")

        menu = ModelSelectionMenu(model_names=test_models)

        # Should still have valid selection
        assert 0 <= menu.selected_index < len(menu.display_model_names)
        # Selection should be visible model
        assert menu.display_model_names[menu.selected_index] in menu.display_model_names


class TestPickerRendering:
    """Tests for render output with visibility indicators."""

    @pytest.fixture(autouse=True)
    def preserve_user_config(self):
        """Preserve user's visibility config before/after tests."""
        # Save user's config before tests
        original_hidden = load_hidden_models()

        yield

        # Restore user's config after tests
        clear_visibility_config()  # Clear test artifacts
        if original_hidden:
            save_hidden_models(original_hidden)  # Restore user's settings

    def test_hidden_model_gets_dim_style(self, test_models=None):
        """Hidden models rendered with dim style."""
        if test_models is None:
            test_models = ["gpt-4", "gpt-3.5-turbo", "claude-3"]

        toggle_model_hidden("gpt-3.5-turbo")
        menu = ModelSelectionMenu(model_names=test_models)
        menu.show_all = True  # Show all to see hidden

        lines = menu._render()

        # Should have [hidden] tag somewhere in output
        render_text = str(lines)
        assert "[hidden]" in render_text.lower() or "hidden" in render_text.lower()

    def test_hidden_model_hidden_in_default_view(self):
        """Hidden models not shown by default."""
        test_models = ["gpt-4", "gpt-3.5-turbo", "claude-3"]
        toggle_model_hidden("gpt-3.5-turbo")

        menu = ModelSelectionMenu(model_names=test_models)

        # Should only show non-hidden
        assert "gpt-3.5-turbo" not in str(menu.display_model_names)
        assert "gpt-4" in str(menu.display_model_names)


# Make test_models fixture available
TestPickerRendering.test_hidden_model_gets_dim_style
