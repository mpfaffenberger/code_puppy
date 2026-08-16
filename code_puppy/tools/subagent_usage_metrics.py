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

Central invariant -- availability is tracked PER FIELD
------------------------------------------------------
pydantic-ai's ``RunUsage`` is a dataclass whose counters each default to ``0``
independently, so a bare ``0`` is ambiguous: it may mean "the provider reported
zero" or "the provider reported nothing at all". A provider that supplies
input usage but omits output usage must not surface ``output_tokens=0`` as if
it were a real reading. Each counter therefore resolves its own availability
via :func:`_pick_reported_counter`:

- a POSITIVE value on the first PRESENT attribute is trustworthy;
- a zero there is ambiguous, and later aliases are not probed: they are
  fallbacks for objects lacking the modern attribute entirely, not second
  opinions (and on ``RunUsage`` they are deprecated properties that merely
  re-read the modern field, warning on access);
- a key explicitly present in ``details`` is a real provider reading and is
  trusted even when its value is ``0``.

``total_tokens`` is deliberately NOT reported. Providers price each bucket at a
different per-token rate -- cache reads are heavily discounted, cache writes
carry a premium, output usually costs the most -- so a single summed number
cannot be turned back into a cost without being decomposed again. Nor can the
upstream figure be trusted in its place: ``UsageBase.total_tokens`` (inherited
by ``RunUsage``) is a property defined as ``input_tokens + output_tokens``,
which cannot distinguish an omitted counter from a zero one and so reports a
confident ``500`` for a run whose output was never measured. Reporting the four
billable buckets and nothing else keeps the output honest.

Run totals are not enough either. Several models charge a higher rate once a
single call's context crosses a length threshold, and a run may switch models
partway through, so summing calls destroys what pricing depends on -- upstream
puts it plainly on ``RequestUsage.__add__``: "this CANNOT be used to sum
multiple requests without breaking some pricing calculations." The totals stay
(useful for coarse telemetry), and :func:`extract_per_request_usage` recovers
the per-call detail that exact costing needs.

Deliberate asymmetry: input has no ``details`` fallback
-------------------------------------------------------
``usage.input_tokens`` is COMBINED (cached tokens folded in), whereas a provider
detail key such as Anthropic's ``details["input_tokens"]`` is BASE-only (cache
excluded). Same name, different semantics. Because the combined value feeds the
cache-subtraction below, sourcing input from ``details`` would subtract the
cache components a second time and silently undercount non-cached input. Input
is therefore read from ordered attributes only. Output has no such mismatch --
nothing is subtracted from it -- so it keeps its ``details`` fallback, which is
what lets a genuine explicit ``output_tokens: 0`` survive.

The cost of that conservatism is that an explicit zero for input alone reports
as ``None``. Under-reporting is acceptable; fabricating a billable ``0`` is not.
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
    "cached_read_tokens",
    "cached_tokens",
    "cached_content_tokens",
)
_CACHE_CREATION_ATTRS = ("cache_write_tokens",)
_CACHE_CREATION_DETAIL_KEYS = (
    "cache_creation_input_tokens",
    "cache_creation_tokens",
    "cache_write_tokens",
    "cached_write_tokens",
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

    ``attrs`` are tried in priority order (modern name first, deprecated aliases
    after), but only the FIRST ONE PRESENT is consulted -- later aliases exist
    for objects that never had the modern attribute at all, not as a second
    opinion. That matters for ``RunUsage``, whose deprecated ``request_tokens``/
    ``response_tokens`` are properties that merely re-read the modern field and
    emit a ``DeprecationWarning`` on access; probing them would be both noisy
    and pointless.

    A present counter is accepted only when POSITIVE, because ``RunUsage``
    defaults every field to ``0`` and an attribute reading of zero cannot be
    told apart from "never populated". An ambiguous zero falls through to
    ``detail_keys``, which are matched against ``usage.details``: a key that is
    explicitly PRESENT is a genuine provider reading and is trusted even when
    its value is ``0``.

    Callers whose counter has no semantically-equivalent detail key simply pass
    none (see the input asymmetry in the module docstring); an empty tuple means
    "no safe details source", not a special case.
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

    Works for BOTH ``RunUsage`` (run totals) and ``RequestUsage`` (one call):
    the two share the same token attribute names, so per-request extraction
    inherits every rule below for free rather than reimplementing them.
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

    Every bucket resolves its own availability, so a provider reporting input
    but omitting output yields ``output_tokens=None`` rather than a fabricated
    ``0``. No aggregate total is produced: the four buckets are the billable
    dimensions, and each is priced differently.
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
    # post-subtraction zero is a real reading (every input token was cached),
    # whereas an unavailable raw input must stay None. Input deliberately has
    # no details fallback -- see the module docstring.
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

    Token availability is resolved per field during extraction (see the module
    docstring), so there is no global "was anything reported?" rescue pass here:
    an ambiguous zero has already become ``None`` by this point, and a genuine
    zero -- fully cached input, or an explicit provider detail -- has already
    been preserved.

    ``num_requests`` is the one counter still normalized here. It is a local
    ``RunUsage`` bookkeeping field rather than a provider billing figure, and a
    completed run reporting zero requests is the dataclass default showing
    through, so it reports as unavailable.
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

    Run totals cannot be priced when the rate depends on a single call's
    context length, or when the run switched models partway through. Message
    history still holds the per-call truth: pydantic-ai appends one
    ``ModelResponse`` per completed call, each carrying its own
    ``RequestUsage`` and ``model_name``.

    Entries are kept even when every bucket is unavailable. A response in the
    history means the call happened; dropping it would silently recast "usage
    unknown" as "call never occurred" and break the one-entry-per-request
    correspondence with ``num_requests``.

    Returns ``None`` when the history cannot be read at all -- unavailable is
    not the same as "there were no calls", which is an empty list.
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

    Measured as the final :class:`ModelResponse`'s *raw combined* input plus
    that same response's output.

    Deliberately NOT built from :func:`_extract_token_buckets`. Those buckets
    subtract cached tokens out of ``input_tokens`` so the four billable
    categories never overlap -- correct for pricing, wrong here. Cached tokens
    still OCCUPY the window; they are merely billed at a different rate. For a
    1000-token prompt of which 500 was cache-read and 300 cache-write, the
    buckets say 200 but the model actually saw 1000.

    Nor is it the run totals: those sum every request, so a four-call run
    reports several times the context that was ever live at once.

    Returns ``None`` unless BOTH halves were genuinely reported -- a partial
    sum would understate occupancy while looking authoritative.
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
        num_requests=metrics["num_requests"],
        per_request_usage=per_request_usage,
        final_context_tokens=final_context_tokens,
        start_time=start_time,
        end_time=end_time,
        duration_ms=duration_ms,
    )
