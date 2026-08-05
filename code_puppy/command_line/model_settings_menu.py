"""Interactive TUI for configuring per-model settings.

Provides a beautiful interface for viewing and modifying model-specific
settings like temperature and seed on a per-model basis.
"""

import sys
import time
from typing import Dict, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.filters import Condition
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
from code_puppy.config import (
    CUSTOM_MODEL_SETTING,
    get_all_model_settings,
    get_custom_model_settings,
    get_global_model_name,
    get_value,
    model_supports_setting,
    parse_config_scalar,
    reset_value,
    set_custom_model_setting,
    set_model_setting,
    set_value,
)
from code_puppy.messaging import emit_info
from code_puppy.model_factory import ModelFactory
from code_puppy.tools.command_runner import set_awaiting_user_input
from code_puppy.callbacks import on_prompt_toolkit_style

# Pagination config
MODELS_PER_PAGE = 15

# Setting definitions with metadata
# Numeric settings have min/max/step, choice settings have choices list
SETTING_DEFINITIONS: Dict[str, Dict] = {
    "temperature": {
        "name": "Temperature",
        "description": "Controls randomness (0.0-1.0). Lower = more deterministic, higher = more creative.",
        "type": "numeric",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "default": None,  # None means use model default
        "format": "{:.2f}",
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
    "top_p": {
        "name": "Top-P (Nucleus Sampling)",
        "description": "Controls token diversity. 0.0 = least random (only most likely tokens), 1.0 = most random (sample from all tokens).",
        "type": "numeric",
        "min": 0.0,
        "max": 1.0,
        "step": 0.05,
        "default": None,
        "format": "{:.2f}",
    },
    "reasoning_effort": {
        "name": "Reasoning Effort",
        "description": "Controls how much effort GPT-5 models spend on reasoning. Higher = more thorough but slower.",
        "type": "choice",
        "choices": ["none", "low", "medium", "high", "xhigh", "max"],
        "default": "medium",
    },
    "reasoning_context": {
        "name": "Reasoning Context",
        "description": "Controls which prior reasoning is retained for GPT-5.6 Responses models. All turns preserves reasoning across the conversation.",
        "type": "choice",
        "choices": ["all_turns", "current_turn", "auto"],
        "default": "all_turns",
    },
    "reasoning_mode": {
        "name": "Reasoning Mode",
        "description": "Controls the GPT-5.6 reasoning mode. Standard is the default; Pro spends more compute and is only available on supported variants.",
        "type": "choice",
        "choices": ["standard", "pro"],
        "default": "standard",
    },
    "summary": {
        "name": "Reasoning Summary",
        "description": "Controls whether OpenAI Responses models return auto, concise, or detailed reasoning summaries.",
        "type": "choice",
        "choices": ["auto", "concise", "detailed"],
        "default": "auto",
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
        "description": "Controls extended thinking mode. 'enabled' = classic thinking with budget_tokens, 'adaptive' = model decides when/how much to think (no budget), 'off' = disabled.",
        "type": "choice",
        "choices": ["enabled", "adaptive", "off"],
        "default": "enabled",
    },
    "budget_tokens": {
        "name": "Thinking Budget (tokens)",
        "description": "Max tokens for extended thinking. Only used when extended_thinking is 'enabled'.",
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
    "clear_thinking": {
        "name": "Clear Thinking",
        "description": "False = Preserved Thinking (keep <think> blocks visible). True = strip thinking from responses.",
        "type": "boolean",
        "default": False,
    },
    "thinking_type": {
        "name": "Thinking Type (GLM)",
        "description": "GLM deep-thinking mode. 'enabled' (default) = model auto-decides whether to think (forced on for GLM-4.7/4.5V regardless). 'disabled' = direct answers, no thinking.",
        "type": "choice",
        "choices": ["enabled", "disabled"],
        "default": "enabled",
    },
    "glm_reasoning_effort": {
        "name": "Reasoning Effort (GLM-5.2+)",
        "description": "Chain-of-thought reasoning effort, GLM-5.2+ only. 'max' is default/recommended. none/minimal skip thinking; low/medium are mapped to high server-side; xhigh is mapped to max.",
        "type": "choice",
        "choices": ["max", "xhigh", "high", "medium", "low", "minimal", "none"],
        "default": "max",
    },
    "thinking_enabled": {
        "name": "Thinking Enabled",
        "description": "Enable thinking mode for Gemini 3 Pro models. When enabled, the model will show its reasoning process.",
        "type": "boolean",
        "default": True,
    },
    "thinking_level": {
        "name": "Thinking Level",
        "description": "Controls the depth of thinking for Gemini 3 Pro models. Low = faster responses, High = more thorough reasoning.",
        "type": "choice",
        "choices": ["low", "high"],
        "default": "low",
    },
    "effort": {
        "name": "Effort",
        "description": "Controls how much effort the model spends on its response (Opus 4-6 only). Low = fast, Max = most thorough.",
        "type": "choice",
        "choices": ["low", "medium", "high", "max"],
        "default": "high",
    },
    "retry_main_strategy": {
        "name": "Retry Strategy (main agent)",
        "description": (
            "Per-model streaming-retry backoff when THIS model runs as the main "
            "agent (overrides the global /set value). Exponential-with-jitter, "
            "capped at 30s between retries. Leave unset to use the global setting."
        ),
        "type": "choice",
        "choices": ["gentle", "balanced", "aggressive"],
        "default": None,
    },
    "retry_main_max_attempts": {
        "name": "Retry Max Attempts (main agent)",
        "description": (
            "Per-model max streaming-retry attempts (1-100) when THIS model runs "
            "as the main agent, including the first try. Overrides the global "
            "/set value. Leave unset to use the global setting."
        ),
        "type": "numeric",
        "min": 1,
        "max": 100,
        "step": 1,
        "default": None,
        "format": "{:.0f}",
    },
    "retry_subagent_strategy": {
        "name": "Retry Strategy (sub-agent)",
        "description": (
            "Per-model streaming-retry backoff when THIS model runs as a "
            "sub-agent (overrides the global /set value). Sub-agents usually want "
            "a longer budget -- losing their work to a blip is expensive. Leave "
            "unset to use the global setting."
        ),
        "type": "choice",
        "choices": ["gentle", "balanced", "aggressive"],
        "default": None,
    },
    "retry_subagent_max_attempts": {
        "name": "Retry Max Attempts (sub-agent)",
        "description": (
            "Per-model max streaming-retry attempts (1-100) when THIS model runs "
            "as a sub-agent, including the first try. Overrides the global /set "
            "value. Leave unset to use the global setting."
        ),
        "type": "numeric",
        "min": 1,
        "max": 100,
        "step": 1,
        "default": None,
        "format": "{:.0f}",
    },
    CUSTOM_MODEL_SETTING: {
        "name": "Custom Params",
        "description": (
            "Free-form key = value params merged into the request body via "
            "extra_body. Dotted keys nest: 'chat_template_kwargs.thinking = medium' "
            "becomes {'chat_template_kwargs': {'thinking': 'medium'}}. Values "
            "parse as bool/int/float; anything else stays a string. Applied "
            "last, so they override built-in settings on conflict."
        ),
        "type": "custom",
        "default": None,
    },
}


def _format_custom_value(value) -> str:
    """Format a custom param value so it round-trips through parse_config_scalar."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format_custom_pairs(pairs: Dict) -> str:
    """Render a custom-params dict as a compact 'k=v; k=v' summary string."""
    return "; ".join(f"{k}={_format_custom_value(v)}" for k, v in pairs.items())


def _load_all_model_names(models_config: Optional[dict] = None) -> List[str]:
    """Load all available model names from config."""
    if models_config is None:
        models_config = ModelFactory.load_config()
    return list(models_config.keys())


def _supports_setting(
    model_name: str, setting: str, models_config: Optional[dict] = None
) -> bool:
    """Check capability against one preloaded model-catalog snapshot."""
    try:
        return model_supports_setting(model_name, setting, models_config=models_config)
    except TypeError:
        # Preserve compatibility with older plugin overrides/test doubles that
        # still implement the historical two-argument callable.
        return model_supports_setting(model_name, setting)


# Per-model retry override keys are handled specially: they live in the dedicated
# ``retry_model_<model>_<role>_<field>`` namespace (see
# retry_profiles.per_model_key), NOT the generic ``model_settings_`` namespace, so
# they can never leak into the ModelSettings sent to the provider. Maps the menu
# setting key -> (role, config field).
_RETRY_MENU_KEYS: Dict[str, tuple] = {
    "retry_main_strategy": ("main", "strategy"),
    "retry_main_max_attempts": ("main", "max_attempts"),
    "retry_subagent_strategy": ("subagent", "strategy"),
    "retry_subagent_max_attempts": ("subagent", "max_attempts"),
}


def _read_per_model_retry(model_name: str, menu_key: str):
    """Read a per-model retry override, or None if unset. Parses ints."""
    from code_puppy.agents.retry_profiles import per_model_key

    role, field = _RETRY_MENU_KEYS[menu_key]
    raw = get_value(per_model_key(model_name, role, field))
    if raw is None or not str(raw).strip():
        return None
    if field == "max_attempts":
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None
    return str(raw).strip()


def _write_per_model_retry(model_name: str, menu_key: str, value) -> None:
    """Write (or clear, when value is None) a per-model retry override."""
    from code_puppy.agents.retry_profiles import per_model_key

    role, field = _RETRY_MENU_KEYS[menu_key]
    key = per_model_key(model_name, role, field)
    if value is None:
        reset_value(key)
    else:
        set_value(key, str(value))


def _get_model_display_settings(
    model_name: str, models_config: Optional[dict] = None
) -> Dict:
    """Get configured model settings plus model-specific display defaults."""
    settings = get_all_model_settings(model_name)

    if _supports_setting(model_name, "reasoning_context", models_config):
        settings.setdefault("reasoning_context", "all_turns")
    if _supports_setting(model_name, "reasoning_mode", models_config):
        settings.setdefault("reasoning_mode", "standard")
    # Per-model retry overrides live in their own namespace, so inject their
    # current values here (only when actually set -- unset shows the default).
    for menu_key in _RETRY_MENU_KEYS:
        val = _read_per_model_retry(model_name, menu_key)
        if val is not None:
            settings[menu_key] = val

    # Custom params are a JSON blob in their own reserved key -- inject the
    # parsed dict (only when non-empty) so displays can summarize it.
    custom = get_custom_model_settings(model_name)
    if custom:
        settings[CUSTOM_MODEL_SETTING] = custom

    return settings


def _get_setting_choices(
    setting_key: str,
    model_name: Optional[str] = None,
    models_config: Optional[dict] = None,
) -> List[str]:
    """Get the available choices for a setting, filtered by model capabilities.

    Reasoning effort is capability-gated: xhigh is available to codex and
    GPT-5.4+ models, while max is reserved for GPT-5.6+ variants.

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

    if setting_key == "reasoning_effort" and model_name:
        if models_config is None:
            models_config = ModelFactory.load_config()
        model_config = models_config.get(model_name, {})
        unsupported_choices = set()
        if not model_config.get("supports_xhigh_reasoning", False):
            unsupported_choices.add("xhigh")
        if not model_config.get("supports_max_reasoning", False):
            unsupported_choices.add("max")
        return [choice for choice in base_choices if choice not in unsupported_choices]

    return base_choices


def _get_setting_default(setting_key: str, model_name: Optional[str] = None):
    """Resolve the effective default for a setting, per-model when applicable.

    Most settings have a static default declared in SETTING_DEFINITIONS, but
    some (like ``extended_thinking``) have model-specific runtime defaults —
    e.g. Opus 4.6/4.7 default to ``"adaptive"`` while other Claude models
    default to ``"enabled"``. We defer to ``get_default_extended_thinking``
    as the single source of truth so the UI and runtime never disagree.

    Args:
        setting_key: The setting name (e.g. ``"extended_thinking"``).
        model_name: Optional model name for per-model defaults.

    Returns:
        The default value (may be ``None``).
    """
    if setting_key == "extended_thinking" and model_name:
        # Import here to avoid a circular import at module load.
        from code_puppy.model_utils import get_default_extended_thinking

        return get_default_extended_thinking(model_name)

    setting_def = SETTING_DEFINITIONS.get(setting_key, {})
    return setting_def.get("default")


class ModelSettingsMenu:
    """Interactive TUI for model settings configuration.

    Two-level navigation:
    - Level 1: List of all available models (paginated)
    - Level 2: Settings for the selected model
    """

    def __init__(self):
        """Initialize the settings menu."""
        # Model config callbacks may perform network discovery. Snapshot once
        # for this menu session; render/key paths must stay pure and immediate.
        self.models_config = ModelFactory.load_config()
        try:
            self.all_models = _load_all_model_names(self.models_config)
        except TypeError:
            # Compatibility for older overrides/test doubles with no snapshot
            # parameter. Production uses the one-load path above.
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
            self.page = get_page_for_index(self.model_index, self.page_size)

        # Editing state
        self.editing_mode = False
        self.edit_value: Optional[float] = None
        self.result_changed = False

        # Custom params view state
        self.custom_settings: Dict = {}
        self.custom_index = 0
        self.custom_input: Optional[str] = None  # None = not typing
        self.custom_editing_key: Optional[str] = None  # original key being edited
        self.custom_error: Optional[str] = None

        # Cache for selected model's settings
        self.selected_model: Optional[str] = None
        self.supported_settings: List[str] = []
        self.current_settings: Dict = {}

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        return get_total_pages(len(self.all_models), self.page_size)

    @property
    def page_start(self) -> int:
        """Get the starting index for the current page."""
        start, _ = get_page_bounds(self.page, len(self.all_models), self.page_size)
        return start

    @property
    def page_end(self) -> int:
        """Get the ending index (exclusive) for the current page."""
        _, end = get_page_bounds(self.page, len(self.all_models), self.page_size)
        return end

    @property
    def models_on_page(self) -> List[str]:
        """Get the models visible on the current page."""
        return self.all_models[self.page_start : self.page_end]

    def _ensure_selection_visible(self):
        """Ensure the current selection is on the visible page."""
        self.page = ensure_visible_page(
            self.model_index,
            self.page,
            len(self.all_models),
            self.page_size,
        )

    def _get_supported_settings(self, model_name: str) -> List[str]:
        """Get list of settings supported by a model."""
        supported = []
        for setting_key in SETTING_DEFINITIONS:
            # Retry overrides and custom params apply to every model, so
            # they're always offered regardless of model capability flags.
            if (
                setting_key == CUSTOM_MODEL_SETTING
                or setting_key in _RETRY_MENU_KEYS
                or _supports_setting(model_name, setting_key, self.models_config)
            ):
                supported.append(setting_key)
        return supported

    def _load_model_settings(self, model_name: str):
        """Load settings for a specific model."""
        self.selected_model = model_name
        self.supported_settings = self._get_supported_settings(model_name)
        self.current_settings = _get_model_display_settings(
            model_name, self.models_config
        )
        self.custom_settings = get_custom_model_settings(model_name)

        self.setting_index = 0

    def _get_current_value(self, setting: str):
        """Get the current value for a setting."""
        return self.current_settings.get(setting)

    def _format_value(self, setting: str, value) -> str:
        """Format a setting value for display."""
        setting_def = SETTING_DEFINITIONS.get(setting)
        if setting_def is None:
            # Unknown/stale setting from saved config — just stringify it
            return str(value) if value is not None else "(unknown)"

        if setting == CUSTOM_MODEL_SETTING:
            if isinstance(value, dict) and value:
                return _format_custom_pairs(value)
            return "(none)"

        if value is None:
            # Per-model retry overrides fall back to the global /set value, not a
            # model default -- say so explicitly to avoid confusion.
            if setting in _RETRY_MENU_KEYS:
                return "(uses global)"
            default = _get_setting_default(setting, self.selected_model)
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
            lines.append(("class:tui.header", " 🐕 Select a Model to Configure"))
            if self.total_pages > 1:
                lines.append(
                    (
                        "class:tui.muted",
                        f"  (Page {self.page + 1}/{self.total_pages})",
                    )
                )
            lines.append(("", "\n\n"))

            if not self.all_models:
                lines.append(("class:tui.warning", "  No models available."))
                lines.append(("", "\n\n"))
                self._add_model_nav_hints(lines)
                return lines

            from code_puppy.model_descriptions import get_model_description

            # Only render models on the current page
            for i, model_name in enumerate(self.models_on_page):
                absolute_index = self.page_start + i
                is_selected = absolute_index == self.model_index
                is_current = model_name == self.current_model_name

                prefix = " › " if is_selected else "   "
                style = "class:tui.selected" if is_selected else "class:tui.body"

                # Check if model has any configured settings (incl. custom params)
                has_settings = bool(
                    get_all_model_settings(model_name)
                    or get_custom_model_settings(model_name)
                )

                lines.append((style, f"{prefix}{model_name}"))

                # Show indicators
                if is_current:
                    lines.append(("class:tui.success", " (active)"))
                if has_settings:
                    lines.append(("class:tui.body", " ⚙"))

                lines.append(("", "\n"))

                if is_selected:
                    description = get_model_description(self.models_config, model_name)
                    lines.append(("class:tui.body", f"      {description}\n"))

            lines.append(("", "\n"))
            self._add_model_nav_hints(lines)
        elif self.view_mode == "custom":
            lines.extend(self._render_custom_list())
        else:
            # Settings view
            lines.append(("class:tui.header", f"  Settings for {self.selected_model}"))
            lines.append(("", "\n\n"))

            if not self.supported_settings:
                lines.append(
                    ("class:tui.warning", "  No configurable settings for this model.")
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
                    style = "class:tui.success"
                else:
                    display_value = self._format_value(setting_key, current_value)
                    prefix = " › " if is_selected else "   "
                    style = "class:tui.selected" if is_selected else "class:tui.body"

                # Setting name and value
                lines.append((style, f"{prefix}{setting_def['name']}: "))
                if current_value is not None or (is_selected and self.editing_mode):
                    lines.append(("class:tui.body", display_value))
                else:
                    lines.append(("class:tui.muted", display_value))
                lines.append(("", "\n"))

            lines.append(("", "\n"))
            self._add_settings_nav_hints(lines)

        return lines

    def _render_custom_list(self) -> List:
        """Render the custom params list (custom view mode)."""
        lines: List = []
        lines.append(("class:tui.header", f"  Custom Params for {self.selected_model}"))
        lines.append(("", "\n\n"))

        keys = list(self.custom_settings)
        for i, key in enumerate(keys):
            is_selected = i == self.custom_index and self.custom_input is None
            prefix = " › " if is_selected else "   "
            style = "class:tui.selected" if is_selected else "class:tui.body"
            display_value = _format_custom_value(self.custom_settings[key])
            lines.append((style, f"{prefix}{key} = {display_value}"))
            lines.append(("", "\n"))

        add_selected = self.custom_index == len(keys) and self.custom_input is None
        prefix = " › " if add_selected else "   "
        style = "class:tui.selected" if add_selected else "class:tui.muted"
        lines.append((style, f"{prefix}+ Add new param"))
        lines.append(("", "\n"))

        if self.custom_input is not None:
            lines.append(("", "\n"))
            lines.append(("class:tui.success", "   "))
            lines.append(("class:tui.body", self.custom_input))
            lines.append(("class:tui.selected", "█"))
            lines.append(("", "\n"))

        if self.custom_error:
            lines.append(("class:tui.warning", f"  {self.custom_error}"))
            lines.append(("", "\n"))

        lines.append(("", "\n"))
        self._add_custom_nav_hints(lines)
        return lines

    def _add_custom_nav_hints(self, lines: List):
        """Add navigation hints for the custom params view."""
        lines.append(("", "\n"))
        if self.custom_input is not None:
            lines.append(("class:tui.help-key", "  Type  "))
            lines.append(("class:tui.help", "key = value\n"))
            lines.append(("class:tui.help-key", "  Enter  "))
            lines.append(("class:tui.help", "Save\n"))
            lines.append(("class:tui.help-key", "  Esc  "))
            lines.append(("class:tui.help", "Cancel\n"))
        else:
            lines.append(("class:tui.help-key", "  ↑/↓  "))
            lines.append(("class:tui.help", "Navigate params\n"))
            lines.append(("class:tui.help-key", "  Enter  "))
            lines.append(("class:tui.help", "Add / edit param\n"))
            lines.append(("class:tui.help-key", "  d  "))
            lines.append(("class:tui.help", "Delete param\n"))
            lines.append(("class:tui.help-key", "  Esc  "))
            lines.append(("class:tui.help", "Back to settings\n"))

    def _add_model_nav_hints(self, lines: List):
        """Add navigation hints for model list view."""
        lines.append(("", "\n"))
        lines.append(("class:tui.help-key", "  ↑/↓  "))
        lines.append(("class:tui.help", "Navigate models\n"))
        if self.total_pages > 1:
            lines.append(("class:tui.help-key", "  PgUp/PgDn  "))
            lines.append(("class:tui.help", "Change page\n"))
        lines.append(("class:tui.help-key", "  Enter  "))
        lines.append(("class:tui.help", "Configure model\n"))
        lines.append(("class:tui.help-key", "  Esc  "))
        lines.append(("class:tui.help", "Exit\n"))

    def _add_settings_nav_hints(self, lines: List):
        """Add navigation hints for settings view."""
        lines.append(("", "\n"))

        if self.editing_mode:
            lines.append(("class:tui.help-key", "  ←/→  "))
            lines.append(("class:tui.help", "Adjust value\n"))
            lines.append(("class:tui.help-key", "  Enter  "))
            lines.append(("class:tui.help", "Save\n"))
            lines.append(("class:tui.help-key", "  Esc  "))
            lines.append(("class:tui.help", "Cancel edit\n"))
            lines.append(("class:tui.help-key", "  d  "))
            lines.append(("class:tui.help", "Reset to default\n"))
        else:
            lines.append(("class:tui.help-key", "  ↑/↓  "))
            lines.append(("class:tui.help", "Navigate settings\n"))
            lines.append(("class:tui.help-key", "  Enter  "))
            lines.append(("class:tui.help", "Edit setting\n"))
            lines.append(("class:tui.help-key", "  d  "))
            lines.append(("class:tui.help", "Reset to default\n"))
            lines.append(("class:tui.help-key", "  Esc  "))
            lines.append(("class:tui.help", "Back to models\n"))

    def _render_details_panel(self) -> List:
        """Render the details/help panel."""
        lines = []

        if self.view_mode == "models":
            lines.append(("class:tui.title", " Model Info"))
            lines.append(("", "\n\n"))

            if not self.all_models:
                lines.append(("class:tui.muted", "  No models available."))
                return lines

            model_name = self.all_models[self.model_index]
            is_current = model_name == self.current_model_name

            lines.append(("class:tui.label", f"  {model_name}"))
            lines.append(("", "\n\n"))

            if is_current:
                lines.append(("class:tui.success", "  ✓ Currently active model"))
                lines.append(("", "\n\n"))

            # Show current settings for this model
            model_settings = _get_model_display_settings(model_name, self.models_config)
            if model_settings:
                lines.append(("class:tui.label", "  Effective Settings:"))
                lines.append(("", "\n"))
                for setting_key, value in model_settings.items():
                    setting_def = SETTING_DEFINITIONS.get(setting_key, {})
                    name = setting_def.get("name", setting_key)
                    display = self._format_value(setting_key, value)
                    lines.append(("class:tui.body", f"    {name}: {display}"))
                    lines.append(("", "\n"))
            else:
                lines.append(("class:tui.muted", "  Using all default settings"))
                lines.append(("", "\n"))

            # Show supported settings
            supported = self._get_supported_settings(model_name)
            lines.append(("", "\n"))
            lines.append(("class:tui.label", "  Configurable Settings:"))
            lines.append(("", "\n"))
            if supported:
                for s in supported:
                    setting_def = SETTING_DEFINITIONS.get(s, {})
                    name = setting_def.get("name", s)
                    lines.append(("class:tui.muted", f"    • {name}"))
                    lines.append(("", "\n"))
            else:
                lines.append(("class:tui.muted", "    None"))
                lines.append(("", "\n"))

            # Show pagination info at the bottom of details
            if self.total_pages > 1:
                lines.append(("", "\n"))
                lines.append(
                    (
                        "class:tui.muted",
                        f"  Model {self.model_index + 1} of {len(self.all_models)}",
                    )
                )
                lines.append(("", "\n"))

        else:
            # Settings detail view
            lines.append(("class:tui.title", " Setting Details"))
            lines.append(("", "\n\n"))

            if not self.supported_settings:
                lines.append(
                    ("class:tui.muted", "  This model doesn't expose any settings.")
                )
                return lines

            setting_key = self.supported_settings[self.setting_index]
            setting_def = SETTING_DEFINITIONS[setting_key]
            current_value = self._get_current_value(setting_key)

            # Setting name
            lines.append(("class:tui.label", f"  {setting_def['name']}"))
            lines.append(("", "\n"))

            lines.append(("", "\n\n"))

            # Description
            lines.append(("class:tui.muted", f"  {setting_def['description']}"))
            lines.append(("", "\n\n"))

            # Range/choices info
            if setting_def.get("type") == "choice":
                lines.append(("class:tui.label", "  Options:"))
                lines.append(("", "\n"))
                # Get filtered choices based on model capabilities
                choices = _get_setting_choices(
                    setting_key, self.selected_model, self.models_config
                )
                lines.append(
                    (
                        "class:tui.muted",
                        f"    {' | '.join(choices)}",
                    )
                )
            elif setting_def.get("type") == "boolean":
                lines.append(("class:tui.label", "  Options:"))
                lines.append(("", "\n"))
                lines.append(
                    (
                        "class:tui.muted",
                        "    Enabled | Disabled",
                    )
                )
            elif setting_def.get("type") == "custom":
                lines.append(("class:tui.label", "  Configured Params:"))
                lines.append(("", "\n"))
                if self.custom_settings:
                    for key, val in self.custom_settings.items():
                        lines.append(
                            (
                                "class:tui.muted",
                                f"    {key} = {_format_custom_value(val)}\n",
                            )
                        )
                else:
                    lines.append(("class:tui.muted", "    (none yet)\n"))
            else:
                lines.append(("class:tui.label", "  Range:"))
                lines.append(("", "\n"))
                lines.append(
                    (
                        "class:tui.muted",
                        f"    Min: {setting_def['min']}  Max: {setting_def['max']}  Step: {setting_def['step']}",
                    )
                )
            lines.append(("", "\n\n"))

            # Current value
            lines.append(("class:tui.label", "  Current Value:"))
            lines.append(("", "\n"))
            if current_value is not None:
                lines.append(
                    (
                        "class:tui.body",
                        f"    {self._format_value(setting_key, current_value)}",
                    )
                )
            else:
                lines.append(("class:tui.muted", "    (using model default)"))
            lines.append(("", "\n\n"))

            # Editing hint
            if self.editing_mode:
                lines.append(("class:tui.success", "  ✏️  EDITING MODE"))
                lines.append(("", "\n"))
                if self.edit_value is not None:
                    lines.append(
                        (
                            "class:tui.body",
                            f"    New value: {self._format_value(setting_key, self.edit_value)}",
                        )
                    )
                else:
                    lines.append(("class:tui.muted", "    New value: (model default)"))
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
        if setting_key == CUSTOM_MODEL_SETTING:
            # Custom params have their own view; Enter routes there instead.
            return
        setting_def = SETTING_DEFINITIONS[setting_key]
        current = self._get_current_value(setting_key)

        # Start with current value, or default if not set
        if current is not None:
            self.edit_value = current
        elif setting_def.get("type") == "choice":
            # For choice settings, start with the default (using filtered choices)
            choices = _get_setting_choices(
                setting_key, self.selected_model, self.models_config
            )
            resolved = _get_setting_default(setting_key, self.selected_model)
            self.edit_value = resolved or (choices[0] if choices else None)
        elif setting_def.get("type") == "boolean":
            resolved = _get_setting_default(setting_key, self.selected_model)
            self.edit_value = bool(resolved) if resolved is not None else False
        else:
            # Default to a sensible starting point for numeric
            if setting_key == "temperature":
                self.edit_value = 0.7
            elif setting_key == "top_p":
                self.edit_value = 0.9  # Common default for top_p
            elif setting_key == "seed":
                self.edit_value = 42
            elif setting_key == "budget_tokens":
                self.edit_value = 10000
            elif setting_key in _RETRY_MENU_KEYS:
                # Seed from the effective (resolved) value as an INT -- never the
                # (min+max)/2 midpoint, which produces a .5 float that {:.0f}
                # banker's-rounds so +1 steps look like +2 and stall.
                role, _ = _RETRY_MENU_KEYS[setting_key]
                from code_puppy.agents.retry_profiles import resolve

                self.edit_value = int(resolve(role, self.selected_model).max_attempts)
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
            choices = _get_setting_choices(
                setting_key, self.selected_model, self.models_config
            )
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
            # Integer-step settings stay ints -- a stray float would make the
            # {:.0f} display banker's-round and appear to step by 2 / stall.
            if isinstance(step, int) and isinstance(setting_def["min"], int):
                new_value = int(round(new_value))
            self.edit_value = new_value

    def _save_edit(self):
        """Save the current edit value."""
        if not self.editing_mode or self.selected_model is None:
            return

        setting_key = self.supported_settings[self.setting_index]

        if setting_key in _RETRY_MENU_KEYS:
            # Per-model retry override -> dedicated retry_model_ namespace.
            _write_per_model_retry(self.selected_model, setting_key, self.edit_value)
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

    def _enter_custom_view(self):
        """Enter the custom params view for the selected model."""
        self._reload_custom()
        self.view_mode = "custom"
        self.custom_index = 0
        self.custom_input = None
        self.custom_editing_key = None
        self.custom_error = None

    def _reload_custom(self):
        """Re-read custom params from config and sync the display cache."""
        self.custom_settings = get_custom_model_settings(self.selected_model)
        if self.custom_settings:
            self.current_settings[CUSTOM_MODEL_SETTING] = self.custom_settings
        else:
            self.current_settings.pop(CUSTOM_MODEL_SETTING, None)

    def _start_custom_input(self):
        """Begin typing a new pair, or editing the selected existing one."""
        keys = list(self.custom_settings)
        if self.custom_index < len(keys):
            key = keys[self.custom_index]
            self.custom_editing_key = key
            value = _format_custom_value(self.custom_settings[key])
            self.custom_input = f"{key} = {value}"
        else:
            self.custom_editing_key = None
            self.custom_input = ""
        self.custom_error = None

    def _save_custom_input(self):
        """Parse 'key = value' from the input buffer and persist it."""
        if self.selected_model is None:
            return
        text = (self.custom_input or "").strip()
        key, sep, value = (part.strip() for part in text.partition("="))
        if not sep or not key or not value:
            self.custom_error = "Expected format: key = value"
            return
        if self.custom_editing_key and self.custom_editing_key != key:
            # Renamed: drop the old key so it doesn't linger.
            set_custom_model_setting(self.selected_model, self.custom_editing_key, None)
        set_custom_model_setting(self.selected_model, key, parse_config_scalar(value))
        self._reload_custom()
        keys = list(self.custom_settings)
        self.custom_index = keys.index(key) if key in keys else 0
        self.custom_input = None
        self.custom_editing_key = None
        self.custom_error = None
        self.result_changed = True

    def _cancel_custom_input(self):
        """Abort typing without saving."""
        self.custom_input = None
        self.custom_editing_key = None
        self.custom_error = None

    def _delete_custom_pair(self):
        """Delete the currently selected custom param."""
        if self.selected_model is None:
            return
        keys = list(self.custom_settings)
        if self.custom_index >= len(keys):
            return
        set_custom_model_setting(self.selected_model, keys[self.custom_index], None)
        self._reload_custom()
        self.custom_index = min(self.custom_index, len(self.custom_settings))
        self.result_changed = True

    def _reset_to_default(self):
        """Reset the current setting to model default."""
        if not self.supported_settings or self.selected_model is None:
            return

        setting_key = self.supported_settings[self.setting_index]

        if self.editing_mode:
            # Reset edit value to default
            self.edit_value = _get_setting_default(setting_key, self.selected_model)
        else:
            if setting_key == CUSTOM_MODEL_SETTING:
                # "Default" for custom params is having none at all.
                for key in list(get_custom_model_settings(self.selected_model)):
                    set_custom_model_setting(self.selected_model, key, None)
                self._reload_custom()
            elif setting_key in _RETRY_MENU_KEYS:
                # Clear the per-model retry override -> falls back to global.
                _write_per_model_retry(self.selected_model, setting_key, None)
                if setting_key in self.current_settings:
                    del self.current_settings[setting_key]
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

        # True while the user is typing a custom param in the custom view.
        # Printable-char bindings (like 'd') must yield to text entry.
        text_editing = Condition(lambda: self.custom_input is not None)

        @kb.add("up")
        @kb.add("c-p")  # Ctrl+P = previous (Emacs-style)
        def _(event):
            if self.view_mode == "models":
                if self.model_index > 0:
                    self.model_index -= 1
                    self._ensure_selection_visible()
                    self.update_display()
            elif self.view_mode == "custom":
                if self.custom_input is None and self.custom_index > 0:
                    self.custom_index -= 1
                    self.update_display()
            else:
                if not self.editing_mode and self.setting_index > 0:
                    self.setting_index -= 1
                    self.update_display()

        @kb.add("down")
        @kb.add("c-n")  # Ctrl+N = next (Emacs-style)
        def _(event):
            if self.view_mode == "models":
                if self.model_index < len(self.all_models) - 1:
                    self.model_index += 1
                    self._ensure_selection_visible()
                    self.update_display()
            elif self.view_mode == "custom":
                # Max index == len(pairs), i.e. the '+ Add new param' row.
                if self.custom_input is None and self.custom_index < len(
                    self.custom_settings
                ):
                    self.custom_index += 1
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
            elif self.view_mode == "custom":
                if self.custom_input is not None:
                    self._save_custom_input()
                else:
                    self._start_custom_input()
            elif self.editing_mode:
                self._save_edit()
            elif (
                self.supported_settings
                and self.supported_settings[self.setting_index] == CUSTOM_MODEL_SETTING
            ):
                self._enter_custom_view()
            else:
                self._start_editing()
            self.update_display()

        @kb.add("escape")
        def _(event):
            if self.view_mode == "custom":
                if self.custom_input is not None:
                    self._cancel_custom_input()
                else:
                    self.view_mode = "settings"
                self.update_display()
            elif self.view_mode == "settings":
                if self.editing_mode:
                    self._cancel_edit()
                    self.update_display()
                else:
                    self._back_to_models()
                    self.update_display()
            else:
                # At model list level, ESC closes the TUI
                event.app.exit()

        @kb.add("d", filter=~text_editing)
        def _(event):
            if self.view_mode == "settings":
                self._reset_to_default()
                self.update_display()
            elif self.view_mode == "custom":
                self._delete_custom_pair()
                self.update_display()

        @kb.add("backspace", filter=text_editing)
        def _(event):
            self.custom_input = (self.custom_input or "")[:-1]
            self.custom_error = None
            self.update_display()

        @kb.add("<any>", filter=text_editing)
        def _(event):
            data = event.data or ""
            if data.isprintable():
                self.custom_input = (self.custom_input or "") + data
                self.custom_error = None
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
            style=on_prompt_toolkit_style(),
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

        # Clear exit message
        from code_puppy.messaging import emit_info

        emit_info("✓ Exited model settings")

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
    settings = _get_model_display_settings(model)

    if not settings:
        emit_info(f"No custom settings configured for {model} (using model defaults)")
        return

    emit_info(f"Settings for {model}:")
    for setting_key, value in settings.items():
        setting_def = SETTING_DEFINITIONS.get(setting_key, {})
        name = setting_def.get("name", setting_key)
        setting_type = setting_def.get("type")
        if setting_type == "custom":
            display = _format_custom_pairs(value) if isinstance(value, dict) else ""
        elif setting_type in ("choice", "boolean"):
            display = (
                str(value)
                if setting_type == "choice"
                else ("Enabled" if value else "Disabled")
            )
        else:
            fmt = setting_def.get("format", "{:.2f}")
            display = fmt.format(value)
        emit_info(f"  {name}: {display}")
