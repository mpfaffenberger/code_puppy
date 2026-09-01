"""Tests for agent-scoped model request settings."""

import json
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents._builder import build_pydantic_agent
from code_puppy.agents.json_agent import JSONAgent
from code_puppy.model_factory import ModelFactory, make_model_settings
from code_puppy.model_utils import PreparedPrompt


def _json_agent_config(**overrides):
    config = {
        "name": "test-agent",
        "description": "Exercises agent model settings",
        "system_prompt": "Test prompt",
        "tools": [],
    }
    config.update(overrides)
    return config


def test_json_agent_returns_defensive_model_settings_copy(tmp_path):
    agent_file = tmp_path / "test-agent.json"
    agent_file.write_text(
        json.dumps(
            _json_agent_config(
                model_settings={"reasoning_effort": "high", "verbosity": "low"}
            )
        )
    )

    agent = JSONAgent(str(agent_file))
    settings = agent.get_model_settings_overrides()

    assert settings == {"reasoning_effort": "high", "verbosity": "low"}
    settings["reasoning_effort"] = "low"
    assert agent.get_model_settings_overrides()["reasoning_effort"] == "high"


def test_json_agent_rejects_non_object_model_settings(tmp_path):
    agent_file = tmp_path / "test-agent.json"
    agent_file.write_text(json.dumps(_json_agent_config(model_settings="high")))

    with pytest.raises(ValueError, match="'model_settings' must be an object"):
        JSONAgent(str(agent_file))


def test_json_agent_rejects_unknown_model_settings_key(tmp_path):
    agent_file = tmp_path / "test-agent.json"
    agent_file.write_text(
        json.dumps(_json_agent_config(model_settings={"resoning_effort": "high"}))
    )

    with pytest.raises(ValueError, match="Unknown model_settings key"):
        JSONAgent(str(agent_file))


def test_json_agent_rejects_out_of_range_model_settings_value(tmp_path):
    agent_file = tmp_path / "test-agent.json"
    agent_file.write_text(
        json.dumps(_json_agent_config(model_settings={"temperature": 5.0}))
    )

    with pytest.raises(ValueError, match="must be <= 1.0"):
        JSONAgent(str(agent_file))


def test_json_agent_rejects_wrong_type_model_settings_value(tmp_path):
    agent_file = tmp_path / "test-agent.json"
    agent_file.write_text(
        json.dumps(_json_agent_config(model_settings={"temperature": "hot"}))
    )

    with pytest.raises(ValueError, match="must be a number"):
        JSONAgent(str(agent_file))


def test_json_agent_rejects_invalid_choice_model_settings_value(tmp_path):
    agent_file = tmp_path / "test-agent.json"
    agent_file.write_text(
        json.dumps(_json_agent_config(model_settings={"reasoning_effort": "super"}))
    )

    with pytest.raises(ValueError, match="must be one of"):
        JSONAgent(str(agent_file))


def test_agent_creator_rejects_non_object_model_settings():
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    errors = AgentCreatorAgent().validate_agent_json(
        _json_agent_config(model_settings="high")
    )

    assert "'model_settings' must be an object" in errors


def test_agent_creator_rejects_unknown_model_settings_key():
    from code_puppy.agents.agent_creator_agent import AgentCreatorAgent

    errors = AgentCreatorAgent().validate_agent_json(
        _json_agent_config(model_settings={"resoning_effort": "high"})
    )

    assert any("Unknown model_settings key" in error for error in errors)


def test_empty_catalog_does_not_reload_per_override_setting():
    """An empty-but-successfully-loaded catalog is a valid snapshot.

    ``models_config={}`` must not be coerced to ``None`` before reaching
    ``model_supports_setting``, or that function reloads the catalog once
    per override instead of reusing the (legitimately empty) snapshot --
    so the load count must stay flat as the override count grows.
    """

    def _load_count_for(overrides):
        with (
            patch.object(ModelFactory, "load_config", return_value={}) as mock_load,
            patch("code_puppy.config.get_effective_model_settings", return_value={}),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
            patch("code_puppy.model_factory.get_yolo_mode", return_value=True),
        ):
            make_model_settings("gpt-5-test", max_tokens=4096, overrides=overrides)
        return mock_load.call_count

    one_override_calls = _load_count_for({"reasoning_effort": "high"})
    three_override_calls = _load_count_for(
        {"reasoning_effort": "high", "verbosity": "low", "summary": "concise"}
    )

    assert three_override_calls == one_override_calls


def test_failed_catalog_load_does_not_drop_supported_overrides():
    """A failed catalog load must use the support-check fallback."""
    with (
        patch.object(
            ModelFactory, "load_config", side_effect=OSError("catalog unavailable")
        ),
        patch("code_puppy.config.get_effective_model_settings", return_value={}),
        patch("code_puppy.config.get_custom_model_settings", return_value={}),
        patch("code_puppy.model_factory.get_yolo_mode", return_value=True),
    ):
        settings = make_model_settings(
            "gpt-5-test",
            max_tokens=4096,
            overrides={"reasoning_effort": "high"},
        )

    assert settings["reasoning_effort"] == "high"


def test_agent_settings_override_per_model_values_before_provider_translation():
    model_config = {
        "gpt-5-test": {
            "type": "openai",
            "name": "gpt-5-test",
            "supported_settings": ["reasoning_effort", "verbosity"],
        }
    }

    with (
        patch.object(ModelFactory, "load_config", return_value=model_config),
        patch(
            "code_puppy.config.get_effective_model_settings",
            return_value={"reasoning_effort": "low", "verbosity": "low"},
        ),
        patch("code_puppy.config.get_custom_model_settings", return_value={}),
        patch("code_puppy.model_factory.get_yolo_mode", return_value=True),
    ):
        settings = make_model_settings(
            "gpt-5-test",
            max_tokens=4096,
            overrides={"reasoning_effort": "high", "unsupported": "ignored"},
        )

    assert settings["openai_reasoning_effort"] == "high"
    assert settings["extra_body"]["verbosity"] == "low"
    assert "unsupported" not in settings


def test_custom_params_remain_the_final_wire_level_override():
    model_config = {
        "gpt-5-test": {
            "type": "openai",
            "name": "gpt-5-test",
            "supported_settings": ["verbosity"],
        }
    }

    with (
        patch.object(ModelFactory, "load_config", return_value=model_config),
        patch("code_puppy.config.get_effective_model_settings", return_value={}),
        patch(
            "code_puppy.config.get_custom_model_settings",
            return_value={"verbosity": "high"},
        ),
        patch("code_puppy.model_factory.get_yolo_mode", return_value=True),
    ):
        settings = make_model_settings(
            "gpt-5-test",
            max_tokens=4096,
            overrides={"verbosity": "low"},
        )

    assert settings["extra_body"]["verbosity"] == "high"


def test_main_agent_builder_passes_agent_model_settings():
    agent = MagicMock()
    agent.name = "test-agent"
    agent.get_model_name.return_value = "gpt-5-test"
    agent.get_model_settings_overrides.return_value = {"reasoning_effort": "high"}
    agent.get_available_tools.return_value = []

    model = MagicMock()
    probe = MagicMock()
    probe._tools = {}
    final = MagicMock()
    final._tools = {}

    with (
        patch.object(ModelFactory, "load_config", return_value={"gpt-5-test": {}}),
        patch(
            "code_puppy.agents._builder.load_model_with_fallback",
            return_value=(model, "gpt-5-test"),
        ),
        patch(
            "code_puppy.agents._builder._assemble_instructions",
            return_value=PreparedPrompt(
                instructions="instructions", user_prompt="", is_claude_code=False
            ),
        ),
        patch("code_puppy.agents._builder.load_mcp_servers", return_value=[]),
        patch("code_puppy.agents._builder.make_model_settings") as make_settings,
        patch(
            "code_puppy.agents._builder.make_history_processor",
            return_value=MagicMock(),
        ),
        patch(
            "code_puppy.agents._builder.make_steer_history_processor",
            return_value=MagicMock(),
        ),
        patch("code_puppy.agents._builder.build_tool_output_limits", return_value=[]),
        patch("code_puppy.agents._builder.build_response_clamp"),
        patch(
            "code_puppy.agents._builder.PydanticAgent",
            side_effect=[probe, final],
        ),
        patch("code_puppy.tools.register_tools_for_agent"),
        patch(
            "code_puppy.agents._builder.on_wrap_pydantic_agent",
            side_effect=lambda _agent, built, **_kwargs: built,
        ),
    ):
        result = build_pydantic_agent(agent)

    assert result is final
    make_settings.assert_called_once_with(
        "gpt-5-test",
        overrides={"reasoning_effort": "high"},
    )
