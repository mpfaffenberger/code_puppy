"""Interactive TUI for configuring per-model settings.

Provides a beautiful interface for viewing and modifying model-specific
settings like temperature and seed on a per-model basis.
"""

import sys
import time
from typing import Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.config import (
    get_all_model_settings,
    get_global_model_name,
    get_openai_reasoning_effort,
    get_openai_verbosity,
    model_supports_setting,
    set_model_setting,
    set_openai_reasoning_effort,
    set_openai_verbosity,
)
from code_puppy.messaging import emit_info
from code_puppy.model_factory import ModelFactory
from code_puppy.tools.command_runner import set_awaiting_user_input

# Pagination config
MODELS_PER_PAGE = 15

# Setting definitions with metadata
# Numeric settings have min/max/step, choice settings have choices list
SETTING_DEFINITIONS: Dict[str, Dict] = {
    "temperature": {
        "name": "Temperature",
        "description": "Controls randomness. Lower = more deterministic, higher = more creative.",
        "type": "numeric",
        "min": 0.0,
        "max": 1.0,  # Clamped to 0-1 per user request
        "step": 0.1,
        "default": None,  # None means use model default
        "format": "{:.1f}",
    },
    "seed": {
        "name": "Seed",
        "description": "Random seed for reproducible outputs. Set to same value for consistent results.",
        "type": "numeric",
        "min": 0,
        "max": 999999,
        "step": 1,
        "default": None,
        "format": "{:.0f}",
    },
    "reasoning_effort": {
        "name": "Reasoning Effort",
        "description": "Controls how much effort GPT-5 models spend on reasoning. Higher = more thorough but slower.",
        "type": "choice",
        "choices": ["minimal", "low", "medium", "high", "xhigh"],
        "default": "medium",
    },
    "verbosity": {
        "name": "Verbosity",
        "description": "Controls response length. Low = concise, Medium = balanced, High = verbose.",
        "type": "choice",
        "choices": ["low", "medium", "high"],
        "default": "medium",
    },
    "extended_thinking": {
        "name": "Extended Thinking",
        "description": "Enable Claude's extended thinking mode for complex reasoning tasks.",
        "type": "boolean",
        "default": True,
    },
    "budget_tokens": {
        "name": "Thinking Budget (tokens)",
        "description": "Max tokens for extended thinking. Only used when extended_thinking is enabled.",
        "type": "numeric",
        "min": 1024,
        "max": 131072,
        "step": 1024,
        "default": 10000,
        "format": "{:.0f}",
    },
    "interleaved_thinking": {
        "name": "Interleaved Thinking",
        "description": "Enable thinking between tool calls (Claude 4 only: Opus 4.5, Opus 4.1, Opus 4, Sonnet 4). Adds beta header. WARNING: On Vertex/Bedrock, this FAILS for non-Claude 4 models!",
        "type": "boolean",
        "default": False,
    },
}


def _load_all_model_names() -> List[str]:
    """Load all available model names from config."""
    models_config = ModelFactory.load_config()
    return list(models_config.keys())


def _get_setting_choices(
    setting_key: str, model_name: Optional[str] = None
) -> List[str]:
    """Get the available choices for a setting, filtered by model capabilities.

    For reasoning_effort, only codex models support 'xhigh' - regular GPT-5.2
    models are capped at 'high'.

    Args:
        setting_key: The setting name (e.g., 'reasoning_effort', 'verbosity')
        model_name: Optional model name to filter choices for

    Returns:
        List of valid choices for this setting and model combination.
    """
    setting_def = SETTING_DEFINITIONS.get(setting_key, {})
    if setting_def.get("type") != "choice":
        return []

    base_choices = setting_def.get("choices", [])

    # For reasoning_effort, filter 'xhigh' based on model support
    if setting_key == "reasoning_effort" and model_name:
        models_config = ModelFactory.load_config()
        model_config = models_config.get(model_name, {})

        # Check if model supports xhigh reasoning
        supports_xhigh = model_config.get("supports_xhigh_reasoning", False)

        if not supports_xhigh:
            # Remove xhigh from choices for non-codex models
            return [c for c in base_choices if c != "xhigh"]

    return base_choices


class ModelSettingsMenu:
    """Interactive TUI for model settings configuration.

    Two-level navigation:
    - Level 1: List of all available models (paginated)
    - Level 2: Settings for the selected model
    """

    def __init__(self):
        """Initialize the settings menu."""
        self.all_models = _load_all_model_names()
        self.current_model_name = get_global_model_name()

        # Navigation state
        self.view_mode = "models"  # "models" or "settings"
        self.model_index = 0  # Index in model list (absolute)
        self.setting_index = 0  # Index in settings list

        # Pagination state
        self.page = 0
        self.page_size = MODELS_PER_PAGE

        # Try to pre-select the current model and set correct page
        if self.current_model_name in self.all_models:
            self.model_index = self.all_models.index(self.current_model_name)
            self.page = self.model_index // self.page_size

        # Editing state
        self.editing_mode = False
        self.edit_value: Optional[float] = None
        self.result_changed = False

        # Cache for selected model's settings
        self.selected_model: Optional[str] = None
        self.supported_settings: List[str] = []
        self.current_settings: Dict = {}

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        if not self.all_models:
            return 1
        return (len(self.all_models) + self.page_size - 1) // self.page_size

    @property
    def page_start(self) -> int:
        """Get the starting index for the current page."""
        return self.page * self.page_size

    @property
    def page_end(self) -> int:
        """Get the ending index (exclusive) for the current page."""
        return min(self.page_start + self.page_size, len(self.all_models))

    @property
    def models_on_page(self) -> List[str]:
        """Get the models visible on the current page."""
        return self.all_models[self.page_start : self.page_end]

    def _ensure_selection_visible(self):
        """Ensure the current selection is on the visible page."""
        if self.model_index < self.page_start:
            self.page = self.model_index // self.page_size
        elif self.model_index >= self.page_end:
            self.page = self.model_index // self.page_size

    def _get_supported_settings(self, model_name: str) -> List[str]:
        """Get list of settings supported by a model."""
        supported = []
        for setting_key in SETTING_DEFINITIONS:
            if model_supports_setting(model_name, setting_key):
                supported.append(setting_key)
        return supported

    def _load_model_settings(self, model_name: str):
        """Load settings for a specific model."""
        self.selected_model = model_name
        self.supported_settings = self._get_supported_settings(model_name)
        self.current_settings = get_all_model_settings(model_name)

        # Add global OpenAI settings if model supports them
        if model_supports_setting(model_name, "reasoning_effort"):
            self.current_settings["reasoning_effort"] = get_openai_reasoning_effort()
        if model_supports_setting(model_name, "verbosity"):
            self.current_settings["verbosity"] = get_openai_verbosity()

        self.setting_index = 0

    def _get_current_value(self, setting: str):
        """Get the current value for a setting."""
        return self.current_settings.get(setting)

    def _format_value(self, setting: str, value) -> str:
        """Format a setting value for display."""
        setting_def = SETTING_DEFINITIONS[setting]
        if value is None:
            default = setting_def.get("default")
            if default is not None:
                return f"(default: {default})"
            return "(model default)"

        if setting_def.get("type") == "choice":
            return str(value)

        if setting_def.get("type") == "boolean":
            return "Enabled" if value else "Disabled"

        fmt = setting_def.get("format", "{:.2f}")
        return fmt.format(value)

    def _render_main_list(self) -> List:
        """Render the main list panel (models or settings)."""
        lines = []

        if self.view_mode == "models":
            # Header with page indicator
            lines.append(("bold cyan", " 🐕 Select a Model to Configure"))
            if self.total_pages > 1:
                lines.append(
                    (
                        "fg:ansibrightblack",
                        f"  (Page {self.page + 1}/{self.total_pages})",
                    )
                )
            lines.append(("", "\n\n"))

            if not self.all_models:
                lines.append(("fg:ansiyellow", "  No models available."))
                lines.append(("", "\n\n"))
                self._add_model_nav_hints(lines)
                return lines

            # Only render models on the current page
            for i, model_name in enumerate(self.models_on_page):
                absolute_index = self.page_start + i
                is_selected = absolute_index == self.model_index
                is_current = model_name == self.current_model_name

                prefix = " › " if is_selected else "   "
                style = "fg:ansiwhite bold" if is_selected else "fg:ansibrightblack"

                # Check if model has any custom settings
                model_settings = get_all_model_settings(model_name)
                has_settings = len(model_settings) > 0

                lines.append((style, f"{prefix}{model_name}"))

                # Show indicators
                if is_current:
                    lines.append(("fg:ansigreen", " (active)"))
                if has_settings:
                    lines.append(("fg:ansicyan", " ⚙"))

                lines.append(("", "\n"))

            lines.append(("", "\n"))
            self._add_model_nav_hints(lines)
        else:
            # Settings view
            lines.append(("bold cyan", f" ⚙ Settings for {self.selected_model}"))
            lines.append(("", "\n\n"))

            if not self.supported_settings:
                lines.append(
                    ("fg:ansiyellow", "  No configurable settings for this model.")
                )
                lines.append(("", "\n\n"))
                self._add_settings_nav_hints(lines)
                return lines

            for i, setting_key in enumerate(self.supported_settings):
                setting_def = SETTING_DEFINITIONS[setting_key]
                is_selected = i == self.setting_index
                current_value = self._get_current_value(setting_key)

                # Show editing state if in edit mode for this setting
                if is_selected and self.editing_mode:
                    display_value = self._format_value(setting_key, self.edit_value)
                    prefix = " ✏️ "
                    style = "fg:ansigreen bold"
                else:
                    display_value = self._format_value(setting_key, current_value)
                    prefix = " › " if is_selected else "   "
                    style = "fg:ansiwhite" if is_selected else "fg:ansibrightblack"

                # Setting name and value
                lines.append((style, f"{prefix}{setting_def['name']}: "))
                if current_value is not None or (is_selected and self.editing_mode):
                    lines.append(("fg:ansicyan", display_value))
                else:
                    lines.append(("fg:ansibrightblack dim", display_value))
                lines.append(("", "\n"))

            lines.append(("", "\n"))
            self._add_settings_nav_hints(lines)

        return lines

    def _add_model_nav_hints(self, lines: List):
        """Add navigation hints for model list view."""
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓  "))
        lines.append(("", "Navigate models\n"))
        if self.total_pages > 1:
            lines.append(("fg:ansibrightblack", "  PgUp/PgDn  "))
            lines.append(("", "Change page\n"))
        lines.append(("fg:ansigreen", "  Enter  "))
        lines.append(("", "Configure model\n"))
        lines.append(("fg:ansiyellow", "  Esc  "))
        lines.append(("", "Exit\n"))

    def _add_settings_nav_hints(self, lines: List):
        """Add navigation hints for settings view."""
        lines.append(("", "\n"))

        if self.editing_mode:
            lines.append(("fg:ansibrightblack", "  ←/→  "))
            lines.append(("", "Adjust value\n"))
            lines.append(("fg:ansigreen", "  Enter  "))
            lines.append(("", "Save\n"))
            lines.append(("fg:ansiyellow", "  Esc  "))
            lines.append(("", "Cancel edit\n"))
            lines.append(("fg:ansired", "  d  "))
            lines.append(("", "Reset to default\n"))
        else:
            lines.append(("fg:ansibrightblack", "  ↑/↓  "))
            lines.append(("", "Navigate settings\n"))
            lines.append(("fg:ansigreen", "  Enter  "))
            lines.append(("", "Edit setting\n"))
            lines.append(("fg:ansired", "  d  "))
            lines.append(("", "Reset to default\n"))
            lines.append(("fg:ansiyellow", "  Esc  "))
            lines.append(("", "Back to models\n"))

    def _render_details_panel(self) -> List:
        """Render the details/help panel."""
        lines = []

        if self.view_mode == "models":
            lines.append(("bold cyan", " Model Info"))
            lines.append(("", "\n\n"))

            if not self.all_models:
                lines.append(("fg:ansibrightblack", "  No models available."))
                return lines

            model_name = self.all_models[self.model_index]
            is_current = model_name == self.current_model_name

            lines.append(("bold", f"  {model_name}"))
            lines.append(("", "\n\n"))

            if is_current:
                lines.append(("fg:ansigreen", "  ✓ Currently active model"))
                lines.append(("", "\n\n"))

            # Show current settings for this model
            model_settings = get_all_model_settings(model_name)
            if model_settings:
                lines.append(("bold", "  Custom Settings:"))
                lines.append(("", "\n"))
                for setting_key, value in model_settings.items():
                    setting_def = SETTING_DEFINITIONS.get(setting_key, {})
                    name = setting_def.get("name", setting_key)
                    fmt = setting_def.get("format", "{:.2f}")
                    lines.append(("fg:ansicyan", f"    {name}: {fmt.format(value)}"))
                    lines.append(("", "\n"))
            else:
                lines.append(("fg:ansibrightblack", "  Using all default settings"))
                lines.append(("", "\n"))

            # Show supported settings
            supported = self._get_supported_settings(model_name)
            lines.append(("", "\n"))
            lines.append(("bold", "  Configurable Settings:"))
            lines.append(("", "\n"))
            if supported:
                for s in supported:
                    setting_def = SETTING_DEFINITIONS.get(s, {})
                    name = setting_def.get("name", s)
                    lines.append(("fg:ansibrightblack", f"    • {name}"))
                    lines.append(("", "\n"))
            else:
                lines.append(("fg:ansibrightblack dim", "    None"))
                lines.append(("", "\n"))

            # Show pagination info at the bottom of details
            if self.total_pages > 1:
                lines.append(("", "\n"))
                lines.append(
                    (
                        "fg:ansibrightblack dim",
                        f"  Model {self.model_index + 1} of {len(self.all_models)}",
                    )
                )
                lines.append(("", "\n"))

        else:
            # Settings detail view
            lines.append(("bold cyan", " Setting Details"))
            lines.append(("", "\n\n"))

            if not self.supported_settings:
                lines.append(
                    ("fg:ansibrightblack", "  This model doesn't expose any settings.")
                )
                return lines

            setting_key = self.supported_settings[self.setting_index]
            setting_def = SETTING_DEFINITIONS[setting_key]
            current_value = self._get_current_value(setting_key)

            # Setting name
            lines.append(("bold", f"  {setting_def['name']}"))
            lines.append(("", "\n"))

            # Show if this is a global setting
            if setting_key in ("reasoning_effort", "verbosity"):
                lines.append(
                    (
                        "fg:ansiyellow",
                        "  ⚠ Global setting (applies to all GPT-5 models)",
                    )
                )
            lines.append(("", "\n\n"))

            # Description
            lines.append(("fg:ansibrightblack", f"  {setting_def['description']}"))
            lines.append(("", "\n\n"))

            # Range/choices info
            if setting_def.get("type") == "choice":
                lines.append(("bold", "  Options:"))
                lines.append(("", "\n"))
                # Get filtered choices based on model capabilities
                choices = _get_setting_choices(setting_key, self.selected_model)
                lines.append(
                    (
                        "fg:ansibrightblack",
                        f"    {' | '.join(choices)}",
                    )
                )
            elif setting_def.get("type") == "boolean":
                lines.append(("bold", "  Options:"))
                lines.append(("", "\n"))
                lines.append(
                    (
                        "fg:ansibrightblack",
                        "    Enabled | Disabled",
                    )
                )
            else:
                lines.append(("bold", "  Range:"))
                lines.append(("", "\n"))
                lines.append(
                    (
                        "fg:ansibrightblack",
                        f"    Min: {setting_def['min']}  Max: {setting_def['max']}  Step: {setting_def['step']}",
                    )
                )
            lines.append(("", "\n\n"))

            # Current value
            lines.append(("bold", "  Current Value:"))
            lines.append(("", "\n"))
            if current_value is not None:
                lines.append(
                    (
                        "fg:ansicyan",
                        f"    {self._format_value(setting_key, current_value)}",
                    )
                )
            else:
                lines.append(("fg:ansibrightblack dim", "    (using model default)"))
            lines.append(("", "\n\n"))

            # Editing hint
            if self.editing_mode:
                lines.append(("fg:ansigreen bold", "  ✏️  EDITING MODE"))
                lines.append(("", "\n"))
                if self.edit_value is not None:
                    lines.append(
                        (
                            "fg:ansicyan",
                            f"    New value: {self._format_value(setting_key, self.edit_value)}",
                        )
                    )
                else:
                    lines.append(
                        ("fg:ansibrightblack", "    New value: (model default)")
                    )
                lines.append(("", "\n"))

        return lines

    def _enter_settings_view(self):
        """Enter settings view for the selected model."""
        if not self.all_models:
            return
        model_name = self.all_models[self.model_index]
        self._load_model_settings(model_name)
        self.view_mode = "settings"

    def _back_to_models(self):
        """Go back to model list view."""
        self.view_mode = "models"
        self.editing_mode = False
        self.edit_value = None

    def _start_editing(self):
        """Enter editing mode for the selected setting."""
        if not self.supported_settings:
            return

        setting_key = self.supported_settings[self.setting_index]
        setting_def = SETTING_DEFINITIONS[setting_key]
        current = self._get_current_value(setting_key)

        # Start with current value, or default if not set
        if current is not None:
            self.edit_value = current
        elif setting_def.get("type") == "choice":
            # For choice settings, start with the default (using filtered choices)
            choices = _get_setting_choices(setting_key, self.selected_model)
            self.edit_value = setting_def.get(
                "default", choices[0] if choices else None
            )
        elif setting_def.get("type") == "boolean":
            # For boolean settings, start with the default
            self.edit_value = setting_def.get("default", False)
        else:
            # Default to a sensible starting point for numeric
            if setting_key == "temperature":
                self.edit_value = 0.7
            elif setting_key == "seed":
                self.edit_value = 42
            elif setting_key == "budget_tokens":
                self.edit_value = 10000
            else:
                self.edit_value = (setting_def["min"] + setting_def["max"]) / 2

        self.editing_mode = True

    def _adjust_value(self, direction: int):
        """Adjust the current edit value."""
        if not self.editing_mode or self.edit_value is None:
            return

        setting_key = self.supported_settings[self.setting_index]
        setting_def = SETTING_DEFINITIONS[setting_key]

        if setting_def.get("type") == "choice":
            # Cycle through filtered choices based on model capabilities
            choices = _get_setting_choices(setting_key, self.selected_model)
            current_idx = (
                choices.index(self.edit_value) if self.edit_value in choices else 0
            )
            new_idx = (current_idx + direction) % len(choices)
            self.edit_value = choices[new_idx]
        elif setting_def.get("type") == "boolean":
            # Toggle boolean
            self.edit_value = not self.edit_value
        else:
            # Numeric adjustment
            step = setting_def["step"]
            new_value = self.edit_value + (direction * step)
            # Clamp to range
            new_value = max(setting_def["min"], min(setting_def["max"], new_value))
            self.edit_value = new_value

    def _save_edit(self):
        """Save the current edit value."""
        if not self.editing_mode or self.selected_model is None:
            return

        setting_key = self.supported_settings[self.setting_index]

        # Handle global OpenAI settings specially
        if setting_key == "reasoning_effort":
            if self.edit_value is not None:
                set_openai_reasoning_effort(self.edit_value)
        elif setting_key == "verbosity":
            if self.edit_value is not None:
                set_openai_verbosity(self.edit_value)
        else:
            # Standard per-model setting
            set_model_setting(self.selected_model, setting_key, self.edit_value)

        # Update local cache
        if self.edit_value is not None:
            self.current_settings[setting_key] = self.edit_value
        elif setting_key in self.current_settings:
            del self.current_settings[setting_key]

        self.result_changed = True
        self.editing_mode = False
        self.edit_value = None

    def _cancel_edit(self):
        """Cancel the current edit."""
        self.editing_mode = False
        self.edit_value = None

    def _reset_to_default(self):
        """Reset the current setting to model default."""
        if not self.supported_settings or self.selected_model is None:
            return

        setting_key = self.supported_settings[self.setting_index]
        setting_def = SETTING_DEFINITIONS.get(setting_key, {})

        if self.editing_mode:
            # Reset edit value to default
            default = setting_def.get("default")
            self.edit_value = default
        else:
            # Handle global OpenAI settings - reset to their defaults
            if setting_key == "reasoning_effort":
                set_openai_reasoning_effort("medium")  # Default
                self.current_settings[setting_key] = "medium"
            elif setting_key == "verbosity":
                set_openai_verbosity("medium")  # Default
                self.current_settings[setting_key] = "medium"
            else:
                # Standard per-model setting
                set_model_setting(self.selected_model, setting_key, None)
                if setting_key in self.current_settings:
                    del self.current_settings[setting_key]
            self.result_changed = True

    def _page_up(self):
        """Go to previous page."""
        if self.page > 0:
            self.page -= 1
            # Move selection to first item on new page
            self.model_index = self.page_start

    def _page_down(self):
        """Go to next page."""
        if self.page < self.total_pages - 1:
            self.page += 1
            # Move selection to first item on new page
            self.model_index = self.page_start

    def update_display(self):
        """Update the display."""
        self.menu_control.text = self._render_main_list()
        self.details_control.text = self._render_details_panel()

    def run(self) -> bool:
        """Run the interactive settings menu.

        Returns:
            True if settings were changed, False otherwise.
        """
        # Build UI
        self.menu_control = FormattedTextControl(text="")
        self.details_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=40)
        )
        details_window = Window(
            content=self.details_control, wrap_lines=True, width=Dimension(weight=60)
        )

        menu_frame = Frame(menu_window, width=Dimension(weight=40), title="Models")
        details_frame = Frame(
            details_window, width=Dimension(weight=60), title="Details"
        )

        root_container = VSplit([menu_frame, details_frame])

        # Key bindings
        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            if self.view_mode == "models":
                if self.model_index > 0:
                    self.model_index -= 1
                    self._ensure_selection_visible()
                    self.update_display()
            else:
                if not self.editing_mode and self.setting_index > 0:
                    self.setting_index -= 1
                    self.update_display()

        @kb.add("down")
        def _(event):
            if self.view_mode == "models":
                if self.model_index < len(self.all_models) - 1:
                    self.model_index += 1
                    self._ensure_selection_visible()
                    self.update_display()
            else:
                if (
                    not self.editing_mode
                    and self.setting_index < len(self.supported_settings) - 1
                ):
                    self.setting_index += 1
                    self.update_display()

        @kb.add("pageup")
        def _(event):
            if self.view_mode == "models":
                self._page_up()
                self.update_display()

        @kb.add("pagedown")
        def _(event):
            if self.view_mode == "models":
                self._page_down()
                self.update_display()

        @kb.add("left")
        def _(event):
            if self.view_mode == "settings" and self.editing_mode:
                self._adjust_value(-1)
                self.update_display()
            elif self.view_mode == "models":
                # Left arrow also goes to previous page
                self._page_up()
                self.update_display()

        @kb.add("right")
        def _(event):
            if self.view_mode == "settings" and self.editing_mode:
                self._adjust_value(1)
                self.update_display()
            elif self.view_mode == "models":
                # Right arrow also goes to next page
                self._page_down()
                self.update_display()

        @kb.add("enter")
        def _(event):
            if self.view_mode == "models":
                self._enter_settings_view()
                self.update_display()
            else:
                if self.editing_mode:
                    self._save_edit()
                else:
                    self._start_editing()
                self.update_display()

        @kb.add("escape")
        def _(event):
            if self.view_mode == "settings":
                if self.editing_mode:
                    self._cancel_edit()
                    self.update_display()
                else:
                    self._back_to_models()
                    self.update_display()
            else:
                # At model list level, ESC closes the TUI
                event.app.exit()

        @kb.add("d")
        def _(event):
            if self.view_mode == "settings":
                self._reset_to_default()
                self.update_display()

        @kb.add("c-c")
        def _(event):
            if self.editing_mode:
                self._cancel_edit()
            event.app.exit()

        layout = Layout(root_container)
        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
        )

        set_awaiting_user_input(True)

        # Enter alternate screen buffer
        sys.stdout.write("\033[?1049h")
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            self.update_display()
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            app.run(in_thread=True)

        finally:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
            set_awaiting_user_input(False)

        return self.result_changed


def interactive_model_settings(model_name: Optional[str] = None) -> bool:
    """Show interactive TUI to configure model settings.

    Args:
        model_name: Deprecated - the TUI now shows all models.
                    This parameter is ignored.

    Returns:
        True if settings were changed, False otherwise.
    """
    menu = ModelSettingsMenu()
    return menu.run()


def show_model_settings_summary(model_name: Optional[str] = None) -> None:
    """Print a summary of current model settings to the console.

    Args:
        model_name: Model to show settings for. If None, uses current global model.
    """
    model = model_name or get_global_model_name()
    settings = get_all_model_settings(model)

    if not settings:
        emit_info(f"No custom settings configured for {model} (using model defaults)")
        return

    emit_info(f"Settings for {model}:")
    for setting_key, value in settings.items():
        setting_def = SETTING_DEFINITIONS.get(setting_key, {})
        name = setting_def.get("name", setting_key)
        fmt = setting_def.get("format", "{:.2f}")
        emit_info(f"  {name}: {fmt.format(value)}")
