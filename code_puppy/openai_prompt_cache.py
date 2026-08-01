"""Focused GPT-5.6 prompt-cache compatibility for pydantic-ai 1.56.

The pinned OpenAI adapter discards :class:`CachePoint` markers and does not
copy OpenAI's nested cache-write count into ``RequestUsage``.  These subclasses
backport only those two behaviours; other OpenAI models keep the stock adapter.
"""

from dataclasses import fields
from typing import Any, Sequence

from pydantic_ai import CachePoint
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIResponsesModel,
    OpenAIResponsesStreamedResponse,
    OpenAIStreamedResponse,
)

CACHE_ANCHOR = "Use the existing CodePuppy instructions."


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
