"""Per-run token usage/latency extraction for ``invoke_agent_with_model``.

Pure functions mapping a pydantic-ai usage object to our schema fields, plus
the output builder. ``invoke_agent`` never calls into this module.

Two invariants drive everything here:

**Availability is per field.** ``RunUsage`` counters each default to ``0``, so a
bare ``0`` may mean "reported zero" or "not reported at all". Each counter
resolves independently, so a provider that reports input but omits output
yields ``output_tokens=None`` rather than a fabricated ``0``.

**No aggregate total.** Each bucket is priced differently, so a sum cannot be
turned back into a cost. ``UsageBase.total_tokens`` is no substitute: it is a
property defined as ``input_tokens + output_tokens``, so it reports a confident
number for a run whose output was never measured. Run totals are likewise
insufficient for pricing -- rates can depend on a single call's context length,
and a run may switch models partway -- which is why
:func:`extract_per_request_usage` exists. Upstream agrees, warning on
``RequestUsage.__add__`` that it "CANNOT be used to sum multiple requests
without breaking some pricing calculations".
"""

import math
from typing import Any

from pydantic_ai.messages import ModelResponse

from code_puppy.tools.agent_tools import (
    AgentInvokeOutput,
    AgentInvokeWithModelOutput,
    SubagentRequestUsage,
)

# Distinguishes "attribute absent" from "attribute present and falsy"; ``None``
# cannot, and a provider legitimately reporting ``None`` must not read as absent.
_MISSING = object()

# The four billable buckets. ``num_requests`` is NOT one of them: it is run-level
# bookkeeping, meaningless for a single call, so per-request extraction reuses
# the buckets alone.
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

# Attribute scan order per counter: modern pydantic-ai name first, deprecated
# alias second (consulted only when the modern attribute is absent entirely).
# Detail keys are provider aliases used when no positive attribute was found.
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
        if not math.isfinite(value):
            return None
        return int(value)
    return None


def _pick_reported_counter(
    usage: Any,
    attrs: tuple[str, ...],
    detail_keys: tuple[str, ...] = (),
) -> int | None:
    """Read one reported counter, or ``None`` when nothing trustworthy exists.

    Only the FIRST PRESENT attribute is consulted; later aliases are fallbacks
    for objects lacking the modern name entirely, not second opinions. On
    ``RunUsage`` the deprecated aliases are properties that re-read the modern
    field and warn on access, so probing them is noisy and pointless.

    A present attribute is trusted only when POSITIVE (zero is ambiguous). An
    ambiguous zero falls through to ``detail_keys``: a key explicitly present in
    ``usage.details`` is a real provider reading, trusted even at ``0``.
    """
    for attr in attrs:
        raw = getattr(usage, attr, _MISSING)
        if raw is _MISSING:
            continue
        normalized = _coerce_token_count(raw)
        if normalized is not None and normalized > 0:
            return normalized
        # Present but ambiguous (zero or unusable): this attribute is the
        # authoritative source for the counter, so stop probing aliases.
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
    """Map a pydantic-ai usage object to the four billable buckets.

    Works for both ``RunUsage`` (run totals) and ``RequestUsage`` (one call);
    they share attribute names, so per-request extraction inherits these rules.

    pydantic-ai folds cached tokens INTO ``input_tokens`` for every provider we
    use, so the cache components are subtracted back out and the buckets never
    overlap. Cache creation is Anthropic-only; OpenAI and Gemini leave it
    ``None``. Aliases may arrive as attributes or in ``details``.
    """
    metrics: dict[str, int | None] = dict(_EMPTY_TOKEN_BUCKETS)
    if usage is None:
        return metrics

    cache_read = _pick_reported_counter(
        usage, _CACHE_READ_ATTRS, _CACHE_READ_DETAIL_KEYS
    )
    cache_creation = _pick_reported_counter(
        usage, _CACHE_CREATION_ATTRS, _CACHE_CREATION_DETAIL_KEYS
    )

    # Availability is decided on the RAW combined input, before subtraction: a
    # post-subtraction zero is a real reading (all input was cached), while an
    # unavailable raw input must stay None. Input has NO details fallback:
    # ``usage.input_tokens`` is combined, but a detail key of the same name
    # (Anthropic) is base-only, so sourcing it would subtract cache twice.
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
    """Run-level metrics: the billable buckets plus the request count.

    ``num_requests`` belongs only to run totals. ``RequestUsage`` exposes it as
    a property hardcoded to ``1``, so including it per call would report a
    constant dressed up as a measurement.
    """
    metrics: dict[str, int | None] = dict(_EMPTY_USAGE_METRICS)
    metrics.update(_extract_token_buckets(usage))
    if usage is not None:
        metrics["num_requests"] = _coerce_token_count(getattr(usage, "requests", None))
    return metrics


def _safe_usage_metrics(result: Any) -> dict[str, int | None]:
    """Extract usage for a completed run, without inventing billable tokens.

    Availability is already resolved per field during extraction, so there is no
    global "was anything reported?" rescue pass. ``num_requests`` is normalized
    here because it is local bookkeeping, not a provider figure: a completed run
    reporting zero requests is the dataclass default showing through.
    """
    try:
        usage = result.usage()
    except Exception:
        return _extract_usage_metrics(None)

    metrics = _extract_usage_metrics(usage)
    if metrics["num_requests"] == 0:
        metrics["num_requests"] = None
    return metrics


def extract_per_request_usage(messages: Any) -> list[SubagentRequestUsage] | None:
    """Break a run's message history into one usage entry per model call.

    pydantic-ai appends one ``ModelResponse`` per completed call, each carrying
    its own ``RequestUsage`` and ``model_name`` -- the per-call detail that run
    totals destroy.

    Entries are kept even when every bucket is unavailable: dropping one would
    recast "usage unknown" as "call never happened" and break the correspondence
    with ``num_requests``. ``None`` means the history was unreadable; ``[]``
    means there were no calls.
    """
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
    """Tokens occupying the context window when the run finished.

    The final :class:`ModelResponse`'s *raw combined* input plus its output.

    Deliberately not built from :func:`_extract_token_buckets`: those subtract
    cached tokens out for pricing, but cached tokens still OCCUPY the window.
    For a 1000-token prompt with 500 cache-read and 300 cache-write, the buckets
    say 200 where the model actually saw 1000. Nor is it the run totals, which
    sum across calls.

    ``None`` unless BOTH halves were reported: a partial sum would understate
    occupancy while looking authoritative.
    """
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
    """Build the correct output type for the calling tool.

    ``invoke_agent`` keeps its original five-field contract; only
    ``invoke_agent_with_model`` gets the usage/timing fields.
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
        num_requests=metrics["num_requests"],
        per_request_usage=per_request_usage,
        final_context_tokens=final_context_tokens,
        start_time=start_time,
        end_time=end_time,
        duration_ms=duration_ms,
    )
