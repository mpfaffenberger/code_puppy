"""Usage extraction for ``invoke_agent_with_model``."""

import math
from typing import Any

from pydantic_ai.messages import ModelResponse

from code_puppy.tools.agent_tools import (
    AgentInvokeOutput,
    AgentInvokeWithModelOutput,
    SubagentRequestUsage,
)

# Distinguishes an absent attribute from a reported None.
_MISSING = object()

_EMPTY_TOKEN_BUCKETS: dict[str, int | None] = {
    "input_tokens": None,
    "cache_read_input_tokens": None,
    "cache_creation_input_tokens": None,
    "output_tokens": None,
}

_EMPTY_USAGE_METRICS: dict[str, int | None] = {
    **_EMPTY_TOKEN_BUCKETS,
    "num_requests": None,
}

_INPUT_ATTRS = ("input_tokens", "request_tokens")
_OUTPUT_ATTRS = ("output_tokens", "response_tokens")
_OUTPUT_DETAIL_KEYS = ("output_tokens", "response_tokens")
_CACHE_READ_ATTRS = ("cache_read_tokens",)
_CACHE_READ_DETAIL_KEYS = (
    "cache_read_input_tokens",
    "cache_read_tokens",
    "cached_tokens",
    "cached_content_tokens",
)
_CACHE_CREATION_ATTRS = ("cache_write_tokens",)
_CACHE_CREATION_DETAIL_KEYS = (
    "cache_creation_input_tokens",
    "cache_write_tokens",
)


def _coerce_token_count(value: Any) -> int | None:
    """Return a usable integer count, rejecting booleans and non-finite values."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return int(value)
    return None


def _pick_reported_counter(
    usage: Any,
    attrs: tuple[str, ...],
    detail_keys: tuple[str, ...] = (),
) -> int | None:
    """Read the first present attribute, falling back to explicit detail keys."""
    for attr in attrs:
        raw = getattr(usage, attr, _MISSING)
        if raw is _MISSING:
            continue
        normalized = _coerce_token_count(raw)
        if normalized is not None and normalized > 0:
            return normalized
        break

    details = getattr(usage, "details", None)
    if isinstance(details, dict):
        for key in detail_keys:
            if key in details:
                coerced = _coerce_token_count(details[key])
                if coerced is not None:
                    return coerced
    return None


def _extract_token_buckets(usage: Any) -> dict[str, int | None]:
    """Return non-overlapping buckets for a run or one request."""
    metrics: dict[str, int | None] = dict(_EMPTY_TOKEN_BUCKETS)
    if usage is None:
        return metrics

    cache_read = _pick_reported_counter(
        usage, _CACHE_READ_ATTRS, _CACHE_READ_DETAIL_KEYS
    )
    cache_creation = _pick_reported_counter(
        usage, _CACHE_CREATION_ATTRS, _CACHE_CREATION_DETAIL_KEYS
    )

    # Anthropic's input detail is base-only; the attribute includes cache.
    combined_input = _pick_reported_counter(usage, _INPUT_ATTRS)
    input_tokens = combined_input
    if combined_input is not None:
        input_tokens = max(
            combined_input - (cache_read or 0) - (cache_creation or 0), 0
        )

    output_tokens = _pick_reported_counter(usage, _OUTPUT_ATTRS, _OUTPUT_DETAIL_KEYS)

    metrics["input_tokens"] = input_tokens
    metrics["cache_read_input_tokens"] = cache_read
    metrics["cache_creation_input_tokens"] = cache_creation
    metrics["output_tokens"] = output_tokens
    return metrics


def _extract_usage_metrics(usage: Any) -> dict[str, int | None]:
    """Return run-level buckets and request count."""
    metrics: dict[str, int | None] = dict(_EMPTY_USAGE_METRICS)
    metrics.update(_extract_token_buckets(usage))
    if usage is not None:
        metrics["num_requests"] = _coerce_token_count(getattr(usage, "requests", None))
    return metrics


def _safe_usage_metrics(result: Any) -> dict[str, int | None]:
    """Extract optional usage without failing a successful invocation."""
    try:
        # Calling result.usage is deprecated in pydantic-ai 1.107+.
        metrics = _extract_usage_metrics(result.usage)
    except Exception:
        return _extract_usage_metrics(None)

    if metrics["num_requests"] == 0:
        metrics["num_requests"] = None
    return metrics


def extract_per_request_usage(messages: Any) -> list[SubagentRequestUsage] | None:
    """Return one usage entry per response; ``None`` means unreadable history."""
    try:
        history = list(messages)
    except TypeError:
        return None

    entries: list[SubagentRequestUsage] = []
    for message in history:
        if not isinstance(message, ModelResponse):
            continue
        buckets = _extract_token_buckets(getattr(message, "usage", None))
        entries.append(
            SubagentRequestUsage(
                model_name=getattr(message, "model_name", None),
                **buckets,
            )
        )
    return entries


def extract_final_context_tokens(messages: Any) -> int | None:
    """Return the final response's raw input plus output when both are known."""
    try:
        history = list(messages)
    except TypeError:
        return None

    last_usage = None
    for message in history:
        if isinstance(message, ModelResponse):
            last_usage = getattr(message, "usage", None)
    if last_usage is None:
        return None

    combined_input = _pick_reported_counter(last_usage, _INPUT_ATTRS)
    output_tokens = _pick_reported_counter(
        last_usage, _OUTPUT_ATTRS, _OUTPUT_DETAIL_KEYS
    )
    if combined_input is None or output_tokens is None:
        return None
    return combined_input + output_tokens


def build_invoke_output(
    *,
    include_usage_metrics: bool,
    response: str | None,
    agent_name: str,
    session_id: str | None = None,
    model_name: str | None = None,
    error: str | None = None,
    usage_metrics: dict[str, int | None] | None = None,
    per_request_usage: list[SubagentRequestUsage] | None = None,
    final_context_tokens: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    duration_ms: float | None = None,
) -> AgentInvokeOutput:
    """Build the plain or usage-aware invocation output."""
    if not include_usage_metrics:
        return AgentInvokeOutput(
            response=response,
            agent_name=agent_name,
            session_id=session_id,
            model_name=model_name,
            error=error,
        )
    metrics = usage_metrics or _EMPTY_USAGE_METRICS
    return AgentInvokeWithModelOutput(
        response=response,
        agent_name=agent_name,
        session_id=session_id,
        model_name=model_name,
        error=error,
        input_tokens=metrics["input_tokens"],
        cache_read_input_tokens=metrics["cache_read_input_tokens"],
        cache_creation_input_tokens=metrics["cache_creation_input_tokens"],
        output_tokens=metrics["output_tokens"],
        num_requests=metrics["num_requests"],
        per_request_usage=per_request_usage,
        final_context_tokens=final_context_tokens,
        start_time=start_time,
        end_time=end_time,
        duration_ms=duration_ms,
    )
