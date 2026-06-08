"""Model discovery tools with safe, explicit metadata projection.

Future model-routing work can extend this projection with explicit public
metadata such as standardized capability tags (for example: ``thinking``,
``vision``, ``tool-use``, ``long-context``) and higher-level profiles (for
example: ``cheap-and-fast`` or ``strong-architect``). Keep that metadata
allowlisted here instead of exposing raw model config.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info
from code_puppy.tools.common import generate_group_id


class AvailableModelInfo(BaseModel):
    """Safe model metadata exposed to agents for model selection."""

    name: str
    type: str | None = None
    provider: str | None = None
    context_length: int | None = None
    description: str | None = None
    supported_settings: list[str] = Field(default_factory=list)


class ListAvailableModelsOutput(BaseModel):
    """Output for the list_available_models tool."""

    models: list[AvailableModelInfo]
    error: str | None = None


def _safe_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _safe_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _safe_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def project_available_model(name: str, config: Any) -> AvailableModelInfo:
    """Project one raw model config into a safe allowlisted summary.

    Important: this intentionally copies only known-safe fields. Do not expose
    raw model config here; model configs may contain endpoints, headers,
    API-key env var names, literal secrets from user/plugin config, or other
    implementation details that do not belong in LLM context.
    """
    if not isinstance(config, dict):
        return AvailableModelInfo(name=name)

    return AvailableModelInfo(
        name=name,
        type=_safe_str(config.get("type")),
        provider=_safe_str(config.get("provider")),
        context_length=_safe_int(config.get("context_length")),
        description=_safe_str(config.get("description")),
        supported_settings=_safe_str_list(config.get("supported_settings")),
    )


def register_list_available_models(agent):
    """Register the list_available_models tool with the provided agent."""

    @agent.tool
    def list_available_models(context: RunContext) -> ListAvailableModelsOutput:
        """List configured model aliases usable for explicit model overrides.

        Returns safe metadata only. Endpoint, auth, API key, environment
        variable, header, and arbitrary provider/plugin configuration are
        intentionally omitted.
        """
        group_id = generate_group_id("list_available_models")

        try:
            from code_puppy.model_factory import ModelFactory

            models_config = ModelFactory.load_config()
            models = [
                project_available_model(name, cfg)
                for name, cfg in sorted(models_config.items())
            ]
            emit_info(
                f"Found {len(models)} configured model(s).",
                message_group=group_id,
            )
            return ListAvailableModelsOutput(models=models)
        except Exception as exc:
            error_msg = f"Error listing available models: {str(exc)}"
            emit_error(error_msg, message_group=group_id)
            return ListAvailableModelsOutput(models=[], error=error_msg)

    return list_available_models
