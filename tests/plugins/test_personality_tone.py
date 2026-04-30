"""Tests for the personality tone plugin."""

from __future__ import annotations

from unittest.mock import Mock, patch

from code_puppy.plugins.personality_tone import register_callbacks as plugin


def test_normalize_tone_accepts_names_and_aliases():
    assert plugin.normalize_tone("professional") == "professional"
    assert plugin.normalize_tone("dry") == "professional"
    assert plugin.normalize_tone("1") == "neutral"
    assert plugin.normalize_tone("off") == "default"
    assert plugin.normalize_tone("spunky") == "playful"


def test_normalize_tone_defaults_unknown_values():
    assert plugin.normalize_tone(None) == "default"
    assert plugin.normalize_tone("") == "default"
    assert plugin.normalize_tone("unknown") == "default"


def test_default_tone_preserves_existing_prompt_behavior():
    with patch(
        "code_puppy.plugins.personality_tone.register_callbacks.get_value",
        return_value="default",
    ):
        assert plugin.get_tone_prompt_addition() == ""


def test_professional_tone_adds_override():
    with patch(
        "code_puppy.plugins.personality_tone.register_callbacks.get_value",
        return_value="professional",
    ):
        prompt = plugin.get_tone_prompt_addition()

    assert "Tone Override" in prompt
    assert "business-professional" in prompt
    assert "supersedes earlier playful or sassy" in prompt
    assert "Avoid sass" in prompt


def test_handle_tone_show_emits_current_tone_and_options():
    with (
        patch(
            "code_puppy.plugins.personality_tone.register_callbacks.get_value",
            return_value="neutral",
        ),
        patch(
            "code_puppy.plugins.personality_tone.register_callbacks.emit_info"
        ) as emit_info,
    ):
        result = plugin._handle_custom_command("/tone", "tone")

    assert result is True
    assert "Personality tone: neutral" in str(emit_info.call_args_list[0])
    assert "Available tones" in str(emit_info.call_args_list[1])


def test_handle_tone_sets_config_and_reloads():
    reload_agent = Mock()

    with (
        patch(
            "code_puppy.plugins.personality_tone.register_callbacks.set_config_value"
        ) as set_config,
        patch(
            "code_puppy.plugins.personality_tone.register_callbacks.emit_success"
        ),
    ):
        plugin._set_tone("dry", reload_agent=reload_agent)

    set_config.assert_called_once_with(plugin.CONFIG_KEY, "professional")
    reload_agent.assert_called_once_with()


def test_handle_tone_rejects_unknown_tone():
    reload_agent = Mock()

    with (
        patch(
            "code_puppy.plugins.personality_tone.register_callbacks.set_config_value"
        ) as set_config,
        patch(
            "code_puppy.plugins.personality_tone.register_callbacks.emit_error"
        ) as emit_error,
    ):
        plugin._set_tone("weird", reload_agent=reload_agent)

    set_config.assert_not_called()
    reload_agent.assert_not_called()
    assert "Unknown tone" in str(emit_error.call_args)


def test_custom_help_includes_tone_command():
    entries = dict(plugin._custom_help())
    assert "tone" in entries


def test_handle_custom_command_ignores_other_commands():
    assert plugin._handle_custom_command("/other", "other") is None

