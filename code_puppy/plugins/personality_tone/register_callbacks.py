"""Plugin for controlling Code Puppy's response tone.

The core Code Puppy prompt intentionally has a playful personality. This plugin
keeps that prompt unchanged and appends a configurable tone override through the
existing load_prompt hook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from code_puppy.callbacks import register_callback
from code_puppy.config import get_value, set_config_value
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

CONFIG_KEY = "personality_tone"
DEFAULT_TONE = "default"


@dataclass(frozen=True)
class ToneProfile:
    description: str
    prompt: str


TONE_PROFILES: dict[str, ToneProfile] = {
    "professional": ToneProfile(
        description="Dry, direct, business-professional responses",
        prompt="""
## Tone Override

This section supersedes earlier playful or sassy personality guidance.
- Use a business-professional tone: direct, concise, objective, and practical.
- Avoid sass, sarcasm, cutesy phrasing, pet/dog jokes, playful metaphors, and emojis unless the user explicitly asks.
- Keep the focus on the engineering objective, tradeoffs, risks, verification, and next steps.
- Do not mention this tone policy unless the user asks about it.
""",
    ),
    "neutral": ToneProfile(
        description="Friendly and restrained, with minimal personality",
        prompt="""
## Tone Override

This section supersedes earlier playful or sassy personality guidance.
- Use a friendly but restrained tone.
- Keep humor and personality light, rare, and secondary to technical clarity.
- Avoid sarcasm, cutesy phrasing, pet/dog jokes, and emojis unless the user explicitly asks.
- Do not mention this tone policy unless the user asks about it.
""",
    ),
    "default": ToneProfile(
        description="Native Code Puppy personality with no extra override",
        prompt="",
    ),
    "playful": ToneProfile(
        description="Explicitly playful, while staying useful and concise",
        prompt="""
## Tone Override

Use Code Puppy's playful personality, but keep it useful.
- Light humor is fine when it does not distract from the task.
- Keep technical answers accurate, actionable, and concise.
- Do not let jokes, sass, or roleplay obscure risks, bugs, commands, or next steps.
""",
    ),
}

ALIASES: dict[str, str] = {
    "0": "professional",
    "business": "professional",
    "business-professional": "professional",
    "dry": "professional",
    "direct": "professional",
    "serious": "professional",
    "1": "neutral",
    "balanced": "neutral",
    "friendly": "neutral",
    "minimal": "neutral",
    "2": "default",
    "native": "default",
    "normal": "default",
    "off": "default",
    "reset": "default",
    "3": "playful",
    "fun": "playful",
    "sassy": "playful",
    "spunky": "playful",
}


def normalize_tone(value: str | None) -> str:
    """Return a supported tone name, falling back to the default tone."""
    if value is None:
        return DEFAULT_TONE

    normalized = value.strip().lower()
    if not normalized:
        return DEFAULT_TONE
    if normalized in TONE_PROFILES:
        return normalized
    return ALIASES.get(normalized, DEFAULT_TONE)


def get_current_tone() -> str:
    """Read the configured tone from persistent config."""
    return normalize_tone(get_value(CONFIG_KEY))


def get_tone_prompt_addition() -> str:
    """Return the prompt addition for the current tone.

    load_prompt callbacks must return a string. Returning an empty string keeps
    the default prompt behavior unchanged while still satisfying the hook.
    """
    return TONE_PROFILES[get_current_tone()].prompt


def _custom_help() -> list[tuple[str, str]]:
    return [
        (
            "tone",
            "Set response tone: professional, neutral, default, playful",
        )
    ]


def _available_tones_text() -> str:
    lines = ["Available tones:"]
    for tone_name in ("professional", "neutral", "default", "playful"):
        profile = TONE_PROFILES[tone_name]
        lines.append(f"  - {tone_name}: {profile.description}")
    lines.append("")
    lines.append("Usage: /tone <professional|neutral|default|playful>")
    lines.append("Aliases: /tone 0, /tone 1, /tone 2, /tone 3")
    return "\n".join(lines)


def _show_tone() -> None:
    tone = get_current_tone()
    emit_info(f"Personality tone: {tone}")
    emit_info(_available_tones_text())


def _reload_current_agent() -> None:
    try:
        from code_puppy.agents import get_current_agent

        get_current_agent().reload_code_generation_agent()
        emit_info("Agent reloaded with updated tone prompt.")
    except Exception as exc:
        emit_warning(f"Tone saved, but agent reload failed: {exc}")


def _set_tone(
    raw_tone: str, reload_agent: Callable[[], None] = _reload_current_agent
) -> None:
    tone = normalize_tone(raw_tone)
    if tone == DEFAULT_TONE and raw_tone.strip().lower() not in {
        DEFAULT_TONE,
        *ALIASES,
    }:
        valid = ", ".join(TONE_PROFILES)
        emit_error(f"Unknown tone '{raw_tone}'. Valid tones: {valid}")
        return

    set_config_value(CONFIG_KEY, tone)
    emit_success(f"Personality tone set to {tone}.")
    reload_agent()


def _handle_custom_command(command: str, name: str) -> bool | None:
    if name != "tone":
        return None

    parts = command.split()
    if len(parts) == 1 or parts[1].lower() in {"show", "list", "help"}:
        _show_tone()
        return True

    if len(parts) > 2:
        emit_error("Usage: /tone <professional|neutral|default|playful>")
        return True

    _set_tone(parts[1])
    return True


register_callback("load_prompt", get_tone_prompt_addition)
register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
