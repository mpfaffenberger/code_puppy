"""Focused GPT-5.6 prompt-cache compatibility for pydantic-ai 1.56.

The pinned OpenAI adapter discards :class:`CachePoint` markers and does not
copy OpenAI's nested cache-write count into ``RequestUsage``.  These subclasses
backport only those two behaviours; other OpenAI models keep the stock adapter.
"""

from dataclasses import fields
from hashlib import sha256
from typing import Any, Sequence

from pydantic_ai import CachePoint
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIResponsesModel,
    OpenAIResponsesStreamedResponse,
    OpenAIStreamedResponse,
)

CACHE_ANCHOR = "Use the existing CodePuppy instructions."
_CACHE_KEY_PREFIX = "code-puppy"
_OPENAI_MODEL_TYPES = {
    "openai",
    "azure_openai",
    "chatgpt_oauth",
    "azure_foundry_openai",
    "custom_openai",
    "custom_openai_responses",
}
_LEGACY_CUSTOM_RESPONSES_MODEL = "codex-gpt-5-codex"


def is_gpt_5_6_model(model_name: str, model_config: dict[str, Any]) -> bool:
    """Recognize GPT-5.6 through either its alias or provider model ID."""
    provider_model_name = str(model_config.get("name") or model_name)
    return "gpt-5.6" in model_name.lower() or "gpt-5.6" in provider_model_name.lower()


def supports_prompt_cache(model_name: str, model_config: dict[str, Any]) -> bool:
    """Return whether the focused GPT-5.6 cache adapter owns this model."""
    return (
        is_gpt_5_6_model(model_name, model_config)
        and model_config.get("type") in _OPENAI_MODEL_TYPES
    )


def supports_explicit_breakpoint(model_name: str, model_config: dict[str, Any]) -> bool:
    """Return whether the provider accepts explicit prompt-cache markers."""
    if not supports_prompt_cache(model_name, model_config):
        return False
    configured = model_config.get("prompt_cache_breakpoint_enabled")
    if configured is not None:
        return configured is True
    # Provider-specific OpenAI-compatible backends can expose the model slug
    # without supporting the marker. The public OpenAI API is the safe default.
    return model_config.get("type") == "openai"


def get_request_path(model_name: str, model_config: dict[str, Any]) -> str:
    """Return the OpenAI API path selected for this model configuration."""
    model_type = model_config.get("type")
    if model_type not in _OPENAI_MODEL_TYPES:
        return "provider_default"
    custom_responses = model_type == "custom_openai_responses" or (
        model_type == "custom_openai" and model_name == _LEGACY_CUSTOM_RESPONSES_MODEL
    )
    uses_responses = (
        model_type in {"chatgpt_oauth", "azure_foundry_openai"}
        or (model_type == "openai" and "codex" in model_name)
        or custom_responses
    )
    return "responses" if uses_responses else "chat_completions"


def apply_cache_key(
    settings: dict[str, Any],
    model_name: str,
    model_config: dict[str, Any],
    scope: str | None,
) -> bool:
    """Add a stable opaque routing key and return whether GPT-5.6 matched."""
    if not is_gpt_5_6_model(model_name, model_config):
        return False
    provider_model_name = str(model_config.get("name") or model_name)
    material = f"{provider_model_name.lower()}\0{scope or 'default'}"
    digest = sha256(material.encode("utf-8")).hexdigest()[:24]
    settings["openai_prompt_cache_key"] = f"{_CACHE_KEY_PREFIX}:{digest}"
    return True


def get_model_classes(
    model_name: str,
    model_config: dict[str, Any],
    chat_model_cls: type[OpenAIChatModel] = OpenAIChatModel,
    responses_model_cls: type[OpenAIResponsesModel] = OpenAIResponsesModel,
) -> tuple[type[OpenAIChatModel], type[OpenAIResponsesModel]]:
    """Select stock or cache-aware pydantic-ai OpenAI model adapters."""
    if supports_prompt_cache(model_name, model_config):
        return CacheAwareChatModel, CacheAwareResponsesModel
    return chat_model_cls, responses_model_cls


def add_cache_boundary(prompt: str | Sequence[Any]) -> list[Any]:
    """Place one explicit boundary before the current task or attachments."""
    parts = [prompt] if isinstance(prompt, str) else list(prompt)
    return [CACHE_ANCHOR, CachePoint(), *parts]


def _detail_value(details: Any, name: str) -> Any:
    if details is None:
        return None
    if isinstance(details, dict):
        return details.get(name)
    return getattr(details, name, None)


def preserve_openai_cache_tokens(mapped_usage: Any, raw_response: Any) -> Any:
    """Recover nested cache reads/writes, including explicitly reported zero."""
    raw_usage = getattr(raw_response, "usage", None)
    details = getattr(raw_usage, "input_tokens_details", None)
    if details is None:
        details = getattr(raw_usage, "prompt_tokens_details", None)

    cache_read = _detail_value(details, "cached_tokens")
    if cache_read is not None:
        mapped_usage.cache_read_tokens = int(cache_read)
        mapped_usage.details["cache_read_tokens"] = int(cache_read)

    cache_write = _detail_value(details, "cache_write_tokens")
    if cache_write is not None:
        mapped_usage.cache_write_tokens = int(cache_write)
        mapped_usage.details["cache_write_tokens"] = int(cache_write)

    return mapped_usage


def _mark_stable_anchor(
    mapped_message: dict[str, Any], original_part: Any
) -> dict[str, Any]:
    original = getattr(original_part, "content", None)
    rendered = mapped_message.get("content")
    if (
        isinstance(original, list)
        and len(original) >= 2
        and original[0] == CACHE_ANCHOR
        and isinstance(original[1], CachePoint)
        and isinstance(rendered, list)
        and rendered
    ):
        rendered[0]["prompt_cache_breakpoint"] = {"mode": "explicit"}
    return mapped_message


class CacheAwareResponsesStream(OpenAIResponsesStreamedResponse):
    def _map_usage(self, response: Any) -> Any:
        return preserve_openai_cache_tokens(super()._map_usage(response), response)


class CacheAwareChatStream(OpenAIStreamedResponse):
    def _map_usage(self, response: Any) -> Any:
        return preserve_openai_cache_tokens(super()._map_usage(response), response)


class CacheAwareResponsesModel(OpenAIResponsesModel):
    @staticmethod
    async def _map_user_prompt(part: Any) -> dict[str, Any]:
        mapped = await OpenAIResponsesModel._map_user_prompt(part)
        return _mark_stable_anchor(mapped, part)

    def _process_response(self, response: Any, *args: Any) -> Any:
        mapped = super()._process_response(response, *args)
        preserve_openai_cache_tokens(mapped.usage, response)
        return mapped

    async def _process_streamed_response(self, response: Any, *args: Any) -> Any:
        existing = await super()._process_streamed_response(response, *args)
        return CacheAwareResponsesStream(
            **{
                field.name: getattr(existing, field.name)
                for field in fields(existing)
                if field.init
            }
        )


class CacheAwareChatModel(OpenAIChatModel):
    async def _map_user_prompt(self, part: Any) -> dict[str, Any]:
        mapped = await super()._map_user_prompt(part)
        return _mark_stable_anchor(mapped, part)

    def _map_usage(self, response: Any) -> Any:
        return preserve_openai_cache_tokens(super()._map_usage(response), response)

    @property
    def _streamed_response_cls(self) -> type[OpenAIStreamedResponse]:
        return CacheAwareChatStream
