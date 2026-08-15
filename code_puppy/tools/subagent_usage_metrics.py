"""Per-run token usage/latency extraction for ``invoke_agent_with_model``.

This module is deliberately self-contained: pure functions that map a
pydantic-ai usage object to our schema fields, plus the output-builder that
decides which :class:`AgentInvokeOutput` subtype a caller gets back. None of
this depends on the agent-run orchestration in ``subagent_invocation.py``, so
it lives separately to keep both files focused and under the puppy bloat
line.

Scope reminder: this instrumentation is used ONLY by ``invoke_agent_with_model``
(via ``include_usage_metrics=True`` in ``_invoke_agent_impl``). ``invoke_agent``
never calls into this module at all -- see ``build_invoke_output``'s
``include_usage_metrics=False`` branch, which returns a plain
``AgentInvokeOutput`` without touching any of these helpers.
"""

from typing import Any

from code_puppy.tools.agent_tools import AgentInvokeOutput, AgentInvokeWithModelOutput

_ESTIMATE_CHARS_PER_TOKEN = 2.5

_EMPTY_USAGE_METRICS: dict[str, int | None] = {
    "input_tokens": None,
    "cache_read_input_tokens": None,
    "cache_creation_input_tokens": None,
    "output_tokens": None,
    "total_tokens": None,
    "num_requests": None,
}


def _coerce_token_count(value: Any) -> int | None:
    """Coerce a usage value to an ``int``, or ``None`` if it isn't usable.

    Token/request counts are semantically integers. ``bool`` is rejected even
    though it subclasses ``int`` (``True`` must not silently become ``1``), and
    non-finite floats (``nan``/``inf``) are treated as missing. Anything that
    is not a real number (e.g. a ``Mock``) is treated as missing too.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        import math

        if not math.isfinite(value):
            return None
        return int(value)
    return None


def _pick_reported_tokens(
    usage: Any, detail_keys: tuple[str, ...], attr: str
) -> int | None:
    """Return a reported token count, preferring the provider ``details`` dict.

    The ``details`` dict only contains keys a provider actually sent, so when a
    key is present it is the authoritative signal for presence: a key present
    with value ``0`` is a genuine "provider reported zero" and is kept. The
    normalized first-class attribute (e.g. ``cache_read_tokens``) is used as a
    fallback, and only when it is positive, because its dataclass default of
    ``0`` is indistinguishable from "not reported" -- so for providers that only
    surface a bucket via the first-class attribute (OpenAI cache reads), a
    genuine zero is reported as ``None`` rather than a fabricated ``0``.
    """
    details = getattr(usage, "details", None)
    if isinstance(details, dict):
        for key in detail_keys:
            if key in details:
                coerced = _coerce_token_count(details[key])
                if coerced is not None:
                    return coerced
    fallback = _coerce_token_count(getattr(usage, attr, None))
    if fallback is not None and fallback > 0:
        return fallback
    return None


def _extract_usage_metrics(usage: Any) -> dict[str, int | None]:
    """Map a pydantic-ai usage object to our schema fields, defensively.

    Token buckets are normalized so they never overlap: pydantic-ai (via
    genai-prices) folds cached tokens INTO ``input_tokens`` for every provider
    we use (Anthropic, OpenAI/codex, Gemini), so we subtract the cache
    components back out to keep ``input_tokens`` strictly non-cached. That way
    ``input_tokens + cache_read_input_tokens + cache_creation_input_tokens``
    reflects total input without double-counting.

    Cache buckets are sourced per provider (verified against the installed
    pydantic-ai + genai-prices):
    - cache reads: Anthropic emits ``cache_read_input_tokens``, Gemini emits
      ``cached_content_tokens``, and OpenAI exposes ``cache_read_tokens``;
      adapters may place any of these aliases in ``details`` instead of the
      normalized first-class attribute.
    - cache creation: Anthropic emits ``cache_creation_input_tokens`` (or
      ``cache_write_tokens`` after normalization); OpenAI and Gemini have no
      such concept, so that field stays ``None``.
    """
    metrics: dict[str, int | None] = dict(_EMPTY_USAGE_METRICS)
    if usage is None:
        return metrics

    cache_read = _pick_reported_tokens(
        usage,
        (
            "cache_read_input_tokens",
            "cache_read_tokens",
            "cached_read_tokens",
            "cached_tokens",
            "cached_content_tokens",
        ),
        "cache_read_tokens",
    )
    cache_creation = _pick_reported_tokens(
        usage,
        (
            "cache_creation_input_tokens",
            "cache_creation_tokens",
            "cache_write_tokens",
            "cached_write_tokens",
        ),
        "cache_write_tokens",
    )

    # pydantic-ai reports a combined input count that already includes the
    # cached tokens; subtract them back out so the buckets don't overlap.
    combined_input = _coerce_token_count(getattr(usage, "input_tokens", None))
    if combined_input is None:
        combined_input = _coerce_token_count(getattr(usage, "request_tokens", None))
    input_tokens = combined_input
    if combined_input is not None:
        input_tokens = max(
            combined_input - (cache_read or 0) - (cache_creation or 0), 0
        )

    output_tokens = _coerce_token_count(getattr(usage, "output_tokens", None))
    if output_tokens is None:
        output_tokens = _coerce_token_count(getattr(usage, "response_tokens", None))

    total_tokens = _coerce_token_count(getattr(usage, "total_tokens", None))
    if total_tokens is None:
        parts = [
            p
            for p in (input_tokens, cache_read, cache_creation, output_tokens)
            if p is not None
        ]
        if parts:
            total_tokens = sum(parts)

    metrics["input_tokens"] = input_tokens
    metrics["cache_read_input_tokens"] = cache_read
    metrics["cache_creation_input_tokens"] = cache_creation
    metrics["output_tokens"] = output_tokens
    metrics["total_tokens"] = total_tokens
    metrics["num_requests"] = _coerce_token_count(getattr(usage, "requests", None))
    return metrics


def _estimate_tokens(text: Any) -> int:
    """Estimate tokens without depending on a provider tokenizer."""
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    return max(1, int(len(text) / _ESTIMATE_CHARS_PER_TOKEN))


def _part_text(part: Any) -> str:
    """Extract useful text from a pydantic-ai message part."""
    content = getattr(part, "content", None)
    if content is not None:
        return content if isinstance(content, str) else str(content)

    for attr in ("args", "args_json", "content_delta", "args_delta"):
        value = getattr(part, attr, None)
        if value is not None:
            return value if isinstance(value, str) else str(value)
    return ""


def _message_tokens(message: Any) -> int:
    """Estimate tokens in every part of one model message."""
    return sum(
        _estimate_tokens(_part_text(part))
        for part in (getattr(message, "parts", None) or [])
    )


def _is_model_response(message: Any) -> bool:
    """Avoid importing pydantic-ai message classes in this compatibility shim."""
    return type(message).__name__ == "ModelResponse"


def _estimate_result_metrics(result: Any) -> dict[str, int]:
    """Estimate usage from the completed run when the provider reports zeroes.

    ``RunUsage`` initializes every counter to zero, even when the provider did
    not send usage metadata. The completed message list is still available, so
    use it as a provider-neutral fallback. Input is accumulated at each model
    response (the approximate context sent for that request), while output is
    counted from response parts. These values are estimates, not fabricated
    provider usage.
    """
    try:
        messages = result.all_messages()
    except Exception:
        return {"input_tokens": 0, "output_tokens": 0, "num_requests": 0}

    input_tokens = 0
    output_tokens = 0
    prefix_tokens = 0
    requests = 0

    for message in messages or []:
        message_tokens = _message_tokens(message)
        if _is_model_response(message):
            input_tokens += prefix_tokens
            output_tokens += message_tokens
            requests += 1
        prefix_tokens += message_tokens

    # A custom model may return a final string without a response part in its
    # reconstructed message history. Keep output useful in that case.
    if output_tokens == 0:
        output_tokens = _estimate_tokens(getattr(result, "output", None))

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "num_requests": requests,
    }


def _safe_usage_metrics(result: Any) -> dict[str, int | None]:
    """Extract usage, estimating missing zero-valued provider counters."""
    try:
        usage = result.usage()
    except Exception:
        # Preserve the existing contract for a genuinely unavailable usage
        # object. The zero-valued RunUsage sentinel is handled below.
        return _extract_usage_metrics(None)

    metrics = _extract_usage_metrics(usage)
    fallback = _estimate_result_metrics(result)
    for key in ("input_tokens", "output_tokens"):
        if not metrics[key] and fallback[key] > 0:
            metrics[key] = fallback[key]

    if not metrics["total_tokens"]:
        parts = [
            value
            for value in (
                metrics["input_tokens"],
                metrics["cache_read_input_tokens"],
                metrics["cache_creation_input_tokens"],
                metrics["output_tokens"],
            )
            if value is not None
        ]
        if parts:
            metrics["total_tokens"] = sum(parts)

    if not metrics["num_requests"] and fallback["num_requests"] > 0:
        metrics["num_requests"] = fallback["num_requests"]

    # Do not expose pydantic-ai's all-zero sentinel when no usable fallback
    # exists. ``None`` means unavailable; zero is reserved for a real count.
    for key in ("input_tokens", "output_tokens", "total_tokens", "num_requests"):
        if metrics[key] == 0:
            metrics[key] = None
    return metrics


def build_invoke_output(
    *,
    include_usage_metrics: bool,
    response: str | None,
    agent_name: str,
    session_id: str | None = None,
    model_name: str | None = None,
    error: str | None = None,
    usage_metrics: dict[str, int | None] | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    duration_ms: float | None = None,
) -> AgentInvokeOutput:
    """Build the correct output type for the calling tool.

    ``invoke_agent`` always gets a plain :class:`AgentInvokeOutput` -- the
    original five-field contract, completely untouched. Only
    ``invoke_agent_with_model`` (``include_usage_metrics=True``) gets the
    extra token-usage/timing fields via :class:`AgentInvokeWithModelOutput`.
    """
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
        total_tokens=metrics["total_tokens"],
        num_requests=metrics["num_requests"],
        start_time=start_time,
        end_time=end_time,
        duration_ms=duration_ms,
    )
