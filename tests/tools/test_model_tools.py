"""Tests for safe model discovery tools."""

from unittest.mock import MagicMock, patch

from code_puppy.tools.model_tools import (
    AvailableModelInfo,
    ListAvailableModelsOutput,
    project_available_model,
    register_list_available_models,
)


def _capture_tool(register_func):
    agent = MagicMock()
    registered = None

    def capture(func):
        nonlocal registered
        registered = func
        return func

    agent.tool = capture
    register_func(agent)
    return registered


def test_project_available_model_uses_strict_safe_allowlist():
    raw = {
        "type": "custom_openai",
        "provider": "internal",
        "name": "provider-model-id",
        "description": "Internal model",
        "context_length": 128000,
        "supported_settings": ["temperature", "top_p", 123, None],
        "custom_endpoint": {
            "url": "https://secret.internal/v1",
            "headers": {"Authorization": "Bearer $SECRET_TOKEN"},
            "api_key": "literal-secret",
        },
        "api_key": "$DIRECT_SECRET_ENV",
    }

    projected = project_available_model("internal-alias", raw)
    dumped = projected.model_dump_json()

    assert projected == AvailableModelInfo(
        name="internal-alias",
        type="custom_openai",
        provider="internal",
        description="Internal model",
        context_length=128000,
        supported_settings=["temperature", "top_p"],
    )
    assert "secret.internal" not in dumped
    assert "SECRET_TOKEN" not in dumped
    assert "literal-secret" not in dumped
    assert "DIRECT_SECRET_ENV" not in dumped
    assert "custom_endpoint" not in dumped
    assert "api_key" not in dumped
    assert "headers" not in dumped


def test_project_available_model_handles_non_dict_config():
    assert project_available_model("weird", None) == AvailableModelInfo(name="weird")


def test_list_available_models_tool_returns_safe_projection():
    list_available_models = _capture_tool(register_list_available_models)

    with (
        patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={
                "z-model": {
                    "type": "openai",
                    "description": "Useful model",
                    "context_length": 42,
                },
                "a-secret-model": {
                    "type": "custom_openai",
                    "custom_endpoint": {"api_key": "nope"},
                },
            },
        ),
        patch("code_puppy.tools.model_tools.emit_info"),
    ):
        result = list_available_models(MagicMock())

    assert isinstance(result, ListAvailableModelsOutput)
    assert result.error is None
    assert [model.name for model in result.models] == ["a-secret-model", "z-model"]
    assert "nope" not in result.model_dump_json()


def test_list_available_models_tool_returns_error_on_failure():
    list_available_models = _capture_tool(register_list_available_models)

    with (
        patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            side_effect=RuntimeError("boom"),
        ),
        patch("code_puppy.tools.model_tools.emit_error") as emit_error,
    ):
        result = list_available_models(MagicMock())

    assert result.models == []
    assert result.error is not None
    assert "boom" in result.error
    assert emit_error.called
