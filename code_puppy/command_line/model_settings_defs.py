"""Setting definitions and pure helpers for the model-settings menu.

Split from :mod:`code_puppy.command_line.model_settings_menu` (which owns
the termflow UI) purely for the 600-line cap. Everything here is
UI-free and unit-testable.
"""

import inspect
from typing import Dict, List, Optional

from code_puppy.config import (
    CUSTOM_MODEL_SETTING,
    get_all_model_settings,
    get_custom_model_settings,
    get_value,
    model_supports_setting,
    reset_value,
    set_value,
)
from code_puppy.model_factory import ModelFactory

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
        "description": "Controls how much effort adaptive models spend on their response. Low = fast, Max = most thorough.",
        "type": "choice",
        "choices": ["low", "medium", "high", "xhigh", "max"],
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
    parameters = inspect.signature(model_supports_setting).parameters
    if "models_config" in parameters:
        return model_supports_setting(model_name, setting, models_config=models_config)
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

    Catalog-declared choices take precedence over legacy reasoning flags.

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

    if model_name:
        if models_config is None:
            models_config = ModelFactory.load_config()
        model_config = models_config.get(model_name, {})
        advertised = model_config.get("setting_choices", {}).get(setting_key)
        if isinstance(advertised, list):
            recognized = [choice for choice in base_choices if choice in advertised]
            if recognized:
                return recognized

        if setting_key == "reasoning_effort":
            # Prefer model-specific OpenAI effort choices, including GPT-5.6 max.
            from code_puppy.model_utils import get_openai_reasoning_effort_choices

            underlying_name = str(model_config.get("name", ""))
            dynamic_choices = get_openai_reasoning_effort_choices(model_name)
            if dynamic_choices is None:
                dynamic_choices = get_openai_reasoning_effort_choices(underlying_name)
            if dynamic_choices is not None:
                allowed = set(dynamic_choices)
                # Explicit catalog flags can still widen a recognized model's
                # choices (e.g. a custom proxy that backports "max" early).
                if model_config.get("supports_xhigh_reasoning"):
                    allowed.add("xhigh")
                if model_config.get("supports_max_reasoning"):
                    allowed.add("max")
                return [c for c in base_choices if c in allowed]

            # Preserve legacy opt-in flags for unrecognized custom models.
            unsupported_choices = set()
            if not model_config.get("supports_xhigh_reasoning", False):
                unsupported_choices.add("xhigh")
            if not model_config.get("supports_max_reasoning", False):
                unsupported_choices.add("max")
            return [
                choice for choice in base_choices if choice not in unsupported_choices
            ]

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
