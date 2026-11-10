"""Agent run orchestration: model execution, retries, and cancellation.

Replaces the monolithic ``BaseAgent.run_with_mcp`` coroutine. Everything here
is a free function; the agent is passed in explicitly. Interactive signal and
key-listener ownership lives in :mod:`code_puppy.agents._run_signals`.
"""

from __future__ import annotations

import asyncio
import json
import re
import ssl
import sys
import uuid
from typing import Any, Callable, Iterator, List, Optional, Sequence, Type, Union

import httpcore
import httpcore2
import httpx
import httpx2

try:  # pragma: no cover - mcp version dependent
    from mcp.shared.exceptions import McpError
except ImportError:  # newer mcp SDKs renamed McpError -> MCPError
    from mcp.shared.exceptions import MCPError as McpError

from pydantic_ai import (
    BinaryContent,
    DocumentUrl,
    ImageUrl,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UsageLimits,
    VideoUrl,
)
from pydantic_ai.exceptions import RunCancelled

try:  # pragma: no cover - pydantic-ai version dependent
    from pydantic_ai.exceptions import ModelHTTPError
except ImportError:
    ModelHTTPError = None  # type: ignore[misc,assignment]


try:  # pragma: no cover - pydantic-ai version dependent
    from pydantic_ai.exceptions import ModelAPIError
except ImportError:
    ModelAPIError = None  # type: ignore[misc,assignment]

# Python 3.11+ builtin; graceful fallback for 3.10
try:
    from builtins import BaseExceptionGroup  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - 3.10 only
    BaseExceptionGroup = Exception  # type: ignore[misc,assignment]

from code_puppy.agent_execution_context import executing_agent_context
from code_puppy.agents import _history
from code_puppy.agents._builder import build_pydantic_agent
from code_puppy.agents._diagnostics import emit_exception_diagnostics
from code_puppy.agents._non_streaming_render import (
    StreamingTextDetector,
    render_result_without_streaming,
    should_render_fallback,
)
from code_puppy.agents._run_signals import (
    drain_pause_state_on_cancel,
    inject_interrupted_subagent_notes,
    interactive_run_cancellation,
    prepare_queued_steer_injection,
    reset_pause_state_at_run_start,
)
from code_puppy.agents._token_limit_hint import resolve_model_name
from code_puppy.agents.event_stream_handler import event_stream_handler
from code_puppy.agents.run_invocation import ModelCall, run_with_exception_retry
from code_puppy.callbacks import (
    on_agent_event_stream_start,
    on_agent_run_cancel,
    on_agent_run_context,
    on_agent_run_end,
    on_agent_run_result,
    on_agent_run_start,
    on_should_skip_fallback_render,
    on_user_prompt_submit,
)
from code_puppy.config import (
    get_enable_streaming,
    get_max_hook_retries,
    get_message_limit,
)
from code_puppy.keymap import sigint_fallback_cancels
from code_puppy.messaging import emit_error, emit_info, emit_warning

# ---- Streaming retry helpers ------------------------------------------------

# Provider "please retry" signals or SSE/transport artifacts that reliably
# succeed on retry. Keep substring-based and lower-case.
#
# NOTE: a bare ``json.JSONDecodeError`` (malformed SSE line) doesn't match
# "malformed streamed sse event" / "extra json data in sse payload" below --
# it's classified separately via isinstance in ``_is_retryable_one``.
_RETRYABLE_SNIPPETS = (
    "streamed response ended without content",
    "malformed streamed sse event",
    "extra json data in sse payload",
    "too many requests",
    "rate limit",
    "rate limited",
    "overloaded",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "server had an error processing your request",
    "retry your request",
    "internal server error",
    # Gateway / proxy transient shapes (Anthropic edge, envoy upstreams):
    "upstream_idle_timeout",
    "upstream_stream_error",
    "upstream timeout",
    "upstream connect error",
    "no data for",
    "error decoding response body",
    "api_error",
    # Generic Anthropic SDK pre-stream wrapper message:
    "connection error",
)

# Transport failures worth a silent retry, by umbrella base class (not each
# subclass) so any dropped-socket guise or timeout is covered. A flaky
# VPN/WiFi blip is recoverable, never fatal. ``httpx2``/``httpcore2`` (used by
# the provider SDKs) share no base classes with ``httpx``/``httpcore``, so both
# families must be listed.
_RETRYABLE_EXCEPTIONS: tuple = (
    httpx.NetworkError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
    httpcore.NetworkError,
    httpcore.TimeoutException,
    httpcore.RemoteProtocolError,
    httpx2.NetworkError,
    httpx2.TimeoutException,
    httpx2.RemoteProtocolError,
    httpcore2.NetworkError,
    httpcore2.TimeoutException,
    httpcore2.RemoteProtocolError,
)

# AnyIO normally translates TLS failures through httpcore/httpx, but a failure
# while reading an established stream can escape as a raw ``ssl.SSLError``.
# Keep this allowlist narrow: certificate and protocol errors need user action,
# while a corrupted TLS record on an existing SSE stream is safe to retry.
# Only the reason observed escaping raw from AnyIO is included; add another
# reason only after confirming that it can bypass the httpx/httpcore wrappers.
_RETRYABLE_TLS_REASONS = frozenset({"DECRYPTION_FAILED_OR_BAD_RECORD_MAC"})


def _is_retryable_tls_stream_error(exc: BaseException) -> bool:
    """Return whether ``exc`` is a known transient raw TLS stream failure."""
    if not isinstance(exc, ssl.SSLError):
        return False

    reason = getattr(exc, "reason", None)
    if isinstance(reason, str) and reason.upper() in _RETRYABLE_TLS_REASONS:
        return True
    if reason is not None:
        return False

    # Hand-built exceptions and some Python/OpenSSL combinations omit
    # ``.reason`` but preserve its stable symbolic name in the message.
    message = str(exc).upper()
    return any(
        f"[SSL: {tls_reason}]" in message for tls_reason in _RETRYABLE_TLS_REASONS
    )


def _matches_retryable_snippet(msg: str) -> bool:
    """Return True if ``msg`` matches any known transient pattern.

    Also accepts the generic ``stream ... ended`` wording variants so we don't
    have to chase every phrasing tweak providers sneak in over time.
    """
    msg = msg.lower()
    if any(s in msg for s in _RETRYABLE_SNIPPETS):
        return True
    return "stream" in msg and "ended" in msg


# Matches a ``[HTTP 502]`` style marker some gateways embed in the message.
_EMBEDDED_HTTP_STATUS_RE = re.compile(r"\[HTTP\s+(\d{3})\]", re.IGNORECASE)


def _sdk_exception(module: str, name: str) -> type | None:
    """Resolve a provider-SDK exception class only if that SDK is loaded.

    An exception raised by a vendor SDK can only exist if the SDK is already
    in ``sys.modules``, so peeking there (rather than importing) keeps
    ``openai``/``anthropic`` (~200ms cold apiece) off the startup path for
    providers this run never touches. ``None`` doubles as "not installed".
    """
    loaded = sys.modules.get(module)
    return getattr(loaded, name, None) if loaded is not None else None


def _is_transient_status(status_code: object) -> bool:
    """True for HTTP statuses worth a silent retry: 429 or any 5xx."""
    return status_code == 429 or (isinstance(status_code, int) and status_code >= 500)


def _embedded_http_status(text: str) -> Optional[int]:
    """Dig a real upstream HTTP status out of a ``[HTTP NNN]`` message marker.

    A gateway (e.g. the puppy-backend ``custom_anthropic`` proxy) can deliver an
    upstream failure as an *in-band SSE ``error`` event* over a connection that
    itself returned HTTP 200. The Anthropic SDK then builds an ``APIStatusError``
    whose ``.status_code`` is 200 -- the stream's status, not the failure's --
    and whose ``body.error.type`` is a generic ``"internal_error"``. The only
    faithful trace of the real failure is a ``[HTTP 502]`` prefix baked into the
    message/body text. Without recovering it, the classifier sees a 200 with no
    matching snippet and refuses to retry, so a transient gateway 5xx crashes
    the REPL instead of getting the slow spaced-out retry.

    Returns the embedded status as an int, or ``None`` if no marker is present.
    """
    match = _EMBEDDED_HTTP_STATUS_RE.search(text or "")
    return int(match.group(1)) if match else None


def _walk_cause_chain(
    exc: BaseException, max_depth: int = 5
) -> "Iterator[BaseException]":
    """Yield ``exc`` and follow its ``__cause__`` / ``__context__`` chain.

    Depth-capped and cycle-safe (tracked by ``id``) so a pathological
    self-referencing chain can't loop forever. We walk both attributes because
    Anthropic-SDK / pydantic-ai wrap the real transport error in ``__cause__``
    (explicit ``raise X from Y``), while some libraries use the implicit
    ``__context__`` set by ``except: raise``. Cost of a false-positive cause
    match is at most 3 silent retries; cost of a false-negative is the 60-line
    REPL traceback this whole helper exists to prevent.
    """
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    for _ in range(max_depth):
        if current is None or id(current) in seen:
            return
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _is_retryable_one(exc: BaseException) -> bool:
    """Per-exception predicate: is *this single* exception transient?

    Intentionally does NOT walk the cause chain -- that's :func:`_walk_cause_chain`'s
    job, kept as a separate concern so each piece stays independently testable.
    """
    if isinstance(exc, _RETRYABLE_EXCEPTIONS):
        return True
    if _is_retryable_tls_stream_error(exc):
        return True

    msg = str(exc)

    # Provider-agnostic: in-band SSE 5xx lands with status_code=200 and only a
    # "[HTTP 5xx]" marker; a 4xx marker is a genuine client error — never retry.
    if _is_transient_status(_embedded_http_status(msg)):
        return True

    if isinstance(exc, UnexpectedModelBehavior):
        return _matches_retryable_snippet(msg)

    openai_api_error = _sdk_exception("openai", "APIError")
    if openai_api_error is not None and isinstance(exc, openai_api_error):
        # 5xx and 429 are transient regardless of wording; the SDK exposes the
        # HTTP status on APIStatusError subclasses (connection/timeout errors
        # have none and are covered by the transport branch above). Mirrors the
        # ModelHTTPError/Anthropic branches so a 502 gets the same slow retry.
        status_code = getattr(exc, "status_code", None)
        if status_code == 429 or (isinstance(status_code, int) and status_code >= 500):
            return True
        if _matches_retryable_snippet(msg):
            return True
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            body_msg = str(body.get("message", ""))
            body_type = str(body.get("type", "")).lower()
            if _matches_retryable_snippet(body_msg):
                return True
            if "rate" in body_type and "limit" in body_type:
                return True
            if body_type in {"server_error", "internal_server_error", "api_error"}:
                return _matches_retryable_snippet(body_msg)

    # Anthropic SDK: a bare APIConnectionError is, by definition, transient.
    anthropic_connection_error = _sdk_exception("anthropic", "APIConnectionError")
    if anthropic_connection_error is not None and isinstance(
        exc, anthropic_connection_error
    ):
        return True

    # Anthropic SDK: status errors are retryable on 5xx (or unset) OR when the
    # message/body matches a gateway-transient snippet (e.g. upstream_idle_timeout).
    anthropic_status_error = _sdk_exception("anthropic", "APIStatusError")
    if anthropic_status_error is not None and isinstance(exc, anthropic_status_error):
        status_code = getattr(exc, "status_code", None)
        if status_code is None or (isinstance(status_code, int) and status_code >= 500):
            return True
        if _matches_retryable_snippet(msg):
            return True
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            err = body.get("error", body)
            if isinstance(err, dict):
                if _matches_retryable_snippet(str(err.get("message", ""))):
                    return True
                # A gateway 5xx wrapped in an SSE error event over a 200 stream
                # surfaces its real status only as a "[HTTP 5xx]" marker.
                if _is_transient_status(
                    _embedded_http_status(str(err.get("message", "")))
                ):
                    return True
                if str(err.get("type", "")).lower() in {
                    "api_error",
                    "server_error",
                    "internal_server_error",
                    "internal_error",
                }:
                    return True

    # Retry on pydantic-ai ModelHTTPError rate limits (e.g. 429 from providers)
    if ModelHTTPError is not None and isinstance(exc, ModelHTTPError):
        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return True
        # Retry on 5xx server errors as well
        if isinstance(status_code, int) and status_code >= 500:
            return True
        if _matches_retryable_snippet(msg):
            return True

    # pydantic-ai wraps Anthropic APIConnectionError as
    # ModelAPIError("Connection error."): the original is usually in __cause__,
    # but match by snippet too in case the cause chain was severed.
    if ModelAPIError is not None and isinstance(exc, ModelAPIError):
        if _matches_retryable_snippet(msg):
            return True

    # Malformed/concatenated SSE line -> bare JSONDecodeError; message won't
    # match the snippets above, so check the type directly.
    if isinstance(exc, json.JSONDecodeError):
        return True

    return False


def _group_members(exc: BaseException) -> tuple:
    """Return an ExceptionGroup's sub-exceptions, or ``()`` for a plain error.

    Guards against the 3.10 fallback where ``BaseExceptionGroup`` aliases
    ``Exception`` -- there we'd otherwise treat *every* exception as a group.
    On 3.11+ (and 3.10 with the backport) real groups expose ``.exceptions``.
    """
    if BaseExceptionGroup is Exception:  # 3.10 without exceptiongroup backport
        return ()
    if isinstance(exc, BaseExceptionGroup):
        return tuple(exc.exceptions)
    return ()


def should_retry_streaming(exc: Exception) -> bool:
    """Decide whether ``exc`` (or anything it wraps) is a transient hiccup.

    Walks the ``__cause__`` / ``__context__`` chain so wrapper exception types
    like :class:`pydantic_ai.exceptions.ModelAPIError` -- which hide the
    real httpx/anthropic transport error in ``__cause__`` -- still get
    classified correctly.

    Also descends into :class:`ExceptionGroup` members. pydantic-ai runs the
    model stream inside an anyio task group, so a transient provider error
    (e.g. ``anthropic.APIStatusError`` HTTP 502 from a gateway) reaches us
    wrapped in an ``ExceptionGroup`` -- which is why ``run_agent_task`` catches
    it with ``except*``. The linear cause walker alone can't see inside
    ``.exceptions``, so a retryable 5xx used to look opaque and crash the REPL
    with a full traceback instead of getting the slow spaced-out retry.

    Returns ``True`` if *any* reachable exception is transient. Cycle-safe via
    an ``id`` set; the per-chain depth cap of :func:`_walk_cause_chain` is
    preserved (group membership is a separate traversal axis).
    """
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        for link in _walk_cause_chain(node):
            if id(link) in seen:
                continue
            seen.add(id(link))
            if _is_retryable_one(link):
                return True
            stack.extend(_group_members(link))
    return False


# Standalone default retry budget for ``streaming_retry`` with no explicit
# policy: gentle, escalating backoff. Main loop and sub-agents pass an explicit
# per-role/per-model policy from ``retry_profiles`` instead.
DEFAULT_STREAMING_RETRY_MAX_ATTEMPTS: int = 5
DEFAULT_STREAMING_RETRY_DELAYS: tuple[float, ...] = (5, 15, 30, 60)


def streaming_retry(
    max_attempts: int = DEFAULT_STREAMING_RETRY_MAX_ATTEMPTS,
    delays: Sequence[float] = DEFAULT_STREAMING_RETRY_DELAYS,
    progress_fn: Optional[Callable[[], Any]] = None,
    max_total_attempts: Optional[int] = None,
) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
    """Wrap a no-arg async callable with streaming-retry semantics.

    This is the retry *mechanism* (loop + classify + sleep + log). The retry
    *policy* -- how many attempts and how long to wait, per role and per model
    -- lives in :mod:`code_puppy.agents.retry_profiles`; production call sites go
    through ``retry_profiles.make_streaming_retry(role, model)`` rather than
    calling this directly, so user-selected profiles are honoured.

    ``max_attempts`` is the budget of consecutive retries *without net-new
    progress*. Delays escalate across a no-progress streak
    (``DEFAULT_STREAMING_RETRY_DELAYS`` -> 5, 15, 30, 60s), reusing the final
    spacing once the streak outgrows the list. That escalation is deliberate:
    gateway 5xx / rate-limit outages routinely outlast a tight 1-2-4s window.

    **Progress-aware reset.** A retried ``agent.run()`` is a whole-turn re-run,
    but code_puppy's history processor checkpoints every *completed step* into
    the agent's message history in place, so a re-run resumes from the last
    step boundary rather than from scratch. ``progress_fn`` (e.g.
    ``lambda: len(agent._message_history)``) returns a monotonic progress token;
    when it advances between failures the turn genuinely moved forward, so the
    no-progress streak resets and the budget refreshes. A step that can never
    complete never advances the token, so it still hits ``max_attempts`` and
    gives up -- no infinite loop. ``max_total_attempts`` is an absolute backstop
    against a pathological "tiny progress then die" cycle (defaults to
    ``max_attempts`` when no ``progress_fn`` is given, i.e. identical to the old
    flat budget).

    Every retry (and the final exhaustion, if it happens) is logged with full
    detail to the on-disk error log via ``log_error``. Users only see a short
    UI banner, but SRE / power-users grepping ``~/.code_puppy/logs/errors.log``
    get the exception type, message, traceback, and which attempt it was.
    """
    from code_puppy.error_logging import log_error

    if max_total_attempts is None:
        max_total_attempts = max_attempts
    # An absolute backstop can never be *smaller* than the no-progress streak
    # budget, or the streak could never be spent.
    max_total_attempts = max(max_total_attempts, max_attempts)

    def decorator(factory: Callable[[], Any]) -> Callable[[], Any]:
        async def runner() -> Any:
            streak = 0  # consecutive retriable failures with no net-new progress
            total = 0  # every retriable failure, for the absolute backstop
            last_progress: Any = None
            if progress_fn is not None:
                try:
                    last_progress = progress_fn()
                except Exception:
                    last_progress = None
            while True:
                try:
                    return await factory()
                except Exception as exc:
                    if not should_retry_streaming(exc):
                        raise
                    total += 1

                    made_progress = False
                    if progress_fn is not None:
                        try:
                            current = progress_fn()
                        except Exception:
                            current = last_progress
                        if (
                            last_progress is not None
                            and current is not None
                            and current > last_progress
                        ):
                            made_progress = True
                        last_progress = current

                    # Net-new progress refreshes the no-progress budget.
                    streak = 0 if made_progress else streak + 1

                    log_error(
                        exc,
                        context=(
                            "streaming_retry: transient exception "
                            f"(streak {streak}/{max_attempts}, "
                            f"total {total}/{max_total_attempts}, "
                            f"progressed={made_progress})"
                        ),
                    )

                    if streak >= max_attempts or total >= max_total_attempts:
                        log_error(
                            exc,
                            context=(
                                "streaming_retry: budget exhausted "
                                f"(streak {streak}/{max_attempts}, "
                                f"total {total}/{max_total_attempts}) -- "
                                "giving up and re-raising"
                            ),
                        )
                        emit_error(
                            "\u274c Streaming failed after "
                            f"{total} attempt(s) (no further progress)"
                        )
                        raise

                    # Delay indexes into the no-progress streak (so a progress
                    # reset also resets backoff). Clamp with max(0,...) and cap
                    # at the last (largest) delay — never wrap via negative
                    # indexing once the streak outgrows the list.
                    idx = max(0, streak - 1)
                    if delays:
                        delay = delays[min(idx, len(delays) - 1)]
                    else:
                        from code_puppy.agents.retry_profiles import (
                            MIN_DELAY_SECONDS,
                        )

                        delay = MIN_DELAY_SECONDS
                    emit_warning(
                        "\u26a1 Turn interrupted mid-stream, re-running from the "
                        f"last completed step in {delay}s... "
                        f"(attempt {total}, streak {streak}/{max_attempts})"
                    )
                    await asyncio.sleep(delay)

        return runner

    return decorator


# ---- Small utilities --------------------------------------------------------


def _sanitize_prompt(prompt: str) -> str:
    """Strip lone UTF-16 surrogates (common on Windows copy-paste)."""
    if not prompt:
        return prompt
    try:
        return prompt.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )
    except (UnicodeEncodeError, UnicodeDecodeError):
        return "".join(
            ch if ord(ch) < 0xD800 or ord(ch) > 0xDFFF else "\ufffd" for ch in prompt
        )


def _build_prompt_payload(
    prompt: str,
    attachments: Optional[Sequence[BinaryContent]],
    link_attachments: Optional[Sequence[Union[ImageUrl, DocumentUrl, VideoUrl]]],
) -> Union[str, List[Any]]:
    """Merge prompt + binary/link attachments into the pydantic-ai payload shape."""
    parts: List[Any] = []
    if attachments:
        parts.extend(attachments)
    if link_attachments:
        parts.extend(link_attachments)

    if not parts:
        return prompt

    payload: List[Any] = []
    if prompt:
        payload.append(prompt)
    payload.extend(parts)
    return payload


def _extract_response_text(result: Any) -> str:
    """Best-effort extraction of human-readable text from a pydantic-ai result."""
    if result is None:
        return ""
    if hasattr(result, "data"):
        return str(result.data) if result.data else ""
    if hasattr(result, "output"):
        return str(result.output) if result.output else ""
    return str(result)


def _should_prepend_system_prompt(agent: Any, prompt: str) -> str:
    """Prepend system prompt to user prompt on the first turn (claude-code etc)."""
    from code_puppy.agents._builder import load_puppy_rules
    from code_puppy.model_utils import prepare_prompt_for_model

    if agent._message_history:
        return prompt

    system_prompt = agent.get_full_system_prompt()
    rules = load_puppy_rules()
    if rules:
        system_prompt += f"\n{rules}"

    prepared = prepare_prompt_for_model(
        model_name=agent.get_model_name(),
        system_prompt=system_prompt,
        user_prompt=prompt,
        prepend_system_to_user=True,
    )
    return prepared.user_prompt


def _checkpoint_cancelled_history(exc_group: BaseException, agent: Any) -> None:
    """Preserve a cancelled run's partial work into ``agent._message_history``.

    pydantic-ai v2 attaches a ``RunCancelled`` snapshot (the full message
    history including the interrupted response and every completed tool
    return) to the propagating ``CancelledError``; a first-party
    ``RunCancelled`` carries it directly. Keep whichever history is longer:
    the ProcessHistory checkpoint already holds completed steps, but only
    the snapshot has the final partial step. Best-effort by design — the
    ``finally`` prune normalizes any dangling tool calls afterwards.
    """
    try:
        for leaf in _collect_exceptions(exc_group, lambda e: True):
            recovered = RunCancelled.from_cancellation(leaf)
            if recovered is None:
                continue
            messages = list(recovered.all_messages())
            if len(messages) > len(agent._message_history or []):
                agent._message_history = messages
            return
    except Exception:  # pragma: no cover - preservation must never mask cancel
        pass


def _is_mcp_transport_failure(exc: BaseException) -> bool:
    """True for an HTTP/SSE MCP connector that could not be reached.

    A stdio server's readiness is probed at startup, but an HTTP/SSE
    connector is only dialed when the run task enters the combined toolset.
    A 401 (expired token, wrong host), a 5xx, or a refused/timed-out
    connection therefore surfaces mid-run as a raw ``httpx`` error from
    inside the transport, not as an ``McpError`` — the protocol never got
    far enough to speak MCP.

    Without this it reaches the generic arm, prints a traceback, and ends
    the run. One unreachable connector must not do that: the model and
    every healthy toolset are still usable, so we degrade like ``McpError``.

    Matched by type rather than message so it holds across httpx versions.
    Note this is deliberately broader than ``_RETRYABLE_EXCEPTIONS``, which
    excludes ``HTTPStatusError`` because a 401 is not worth retrying — it is
    still worth surviving.
    """
    return isinstance(
        exc,
        (
            httpx.HTTPStatusError,
            httpx.TransportError,  # ConnectError, ReadTimeout, PoolTimeout, ...
            httpcore.ConnectError,
            httpcore.ConnectTimeout,
        ),
    )


def _collect_exceptions(
    group: BaseException, predicate: Callable[[BaseException], bool]
) -> List[BaseException]:
    """Flatten an ExceptionGroup tree, returning leaves matching ``predicate``."""
    out: List[BaseException] = []
    stack: List[BaseException] = [group]
    while stack:
        exc = stack.pop()
        if isinstance(exc, BaseExceptionGroup):
            stack.extend(exc.exceptions)
        elif predicate(exc):
            out.append(exc)
    return out


# ---- The main entry point ---------------------------------------------------


# Depth of in-flight ``run_with_mcp`` calls (main-loop-thread-only, so a
# plain int is race-free). Depth > 0 = NESTED run (e.g. auto_continue): those
# must NOT touch process-wide interactive state — PauseController (would
# drain the user's queued steers!), SIGINT handler, shell cancel bridge, or
# the key-listener cancel hotkey.
_active_run_depth = 0


async def run_with_mcp(
    agent: Any,
    prompt: str,
    *,
    attachments: Optional[Sequence[BinaryContent]] = None,
    link_attachments: Optional[Sequence[Union[ImageUrl, DocumentUrl, VideoUrl]]] = None,
    output_type: Optional[Type[Any]] = None,
    **kwargs: Any,
) -> Any:
    """Run ``agent`` against ``prompt`` with full MCP + cancellation support.

    Thin depth-tracking wrapper: nested calls (a run started while another
    run is already in flight on this loop) skip the interactive-state
    plumbing — see ``_active_run_depth``.
    """
    global _active_run_depth
    is_nested_run = _active_run_depth > 0
    _active_run_depth += 1

    async def run() -> Any:
        return await _run_with_mcp_impl(
            agent,
            prompt,
            attachments=attachments,
            link_attachments=link_attachments,
            output_type=output_type,
            is_nested_run=is_nested_run,
            **kwargs,
        )

    try:
        if is_nested_run:
            return await run()
        async with interactive_run_cancellation(sigint_fallback_cancels):
            return await run()
    finally:
        _active_run_depth -= 1


async def _run_with_mcp_impl(
    agent: Any,
    prompt: str,
    *,
    attachments: Optional[Sequence[BinaryContent]] = None,
    link_attachments: Optional[Sequence[Union[ImageUrl, DocumentUrl, VideoUrl]]] = None,
    output_type: Optional[Type[Any]] = None,
    is_nested_run: bool = False,
    **kwargs: Any,
) -> Any:
    """Body of :func:`run_with_mcp` (depth bookkeeping lives in the wrapper)."""

    owner_task = asyncio.current_task()
    owner_cancel_baseline = owner_task.cancelling() if owner_task is not None else 0

    def _owner_cancel_pending() -> bool:
        return (
            owner_task is not None and owner_task.cancelling() > owner_cancel_baseline
        )

    def _raise_if_owner_cancel_pending() -> None:
        if _owner_cancel_pending():
            raise asyncio.CancelledError

    # Scrub stale PauseController state from a previous cancelled run before
    # touching anything: without this, a leftover steer queue would silently
    # poison this run. NEVER from a nested run — the "stale" steers it would
    # drain are the OUTER run's live ones.
    if not is_nested_run:
        reset_pause_state_at_run_start()
        # Surface any sub-agent interrupted since the last run so the model
        # knows the delegation was stopped and where to resume it.
        inject_interrupted_subagent_notes(agent)

    prompt = _sanitize_prompt(prompt)
    group_id = str(uuid.uuid4())
    run_was_cancelled = False
    cancel_cleanup_started = False

    async def _run_cancel_cleanup(*, drain_pause: bool) -> None:
        """Apply cancellation side effects at most once for this run."""
        nonlocal cancel_cleanup_started, run_was_cancelled
        run_was_cancelled = True
        if cancel_cleanup_started:
            return
        cancel_cleanup_started = True
        if drain_pause:
            drain_pause_state_on_cancel()
        await on_agent_run_cancel(group_id)

    # Fire user_prompt_submit hooks BEFORE the prompt is sent; plugins (e.g.
    # claude_code_hooks) may return a replacement prompt string.
    try:
        submit_results = await on_user_prompt_submit(prompt, group_id)
        for r in submit_results:
            if isinstance(r, str) and r:
                prompt = r
    except asyncio.CancelledError:
        await _run_cancel_cleanup(drain_pause=not is_nested_run)
        raise
    except Exception:
        # Hook failures must never block the run.
        pass
    if _owner_cancel_pending():
        await _run_cancel_cleanup(drain_pause=not is_nested_run)
        raise asyncio.CancelledError

    # Let a ``model_select`` hook route THIS turn to a different model (e.g.
    # small-vs-large by complexity) before the pydantic agent is built. This
    # resets any prior turn's auto choice, respects an explicit runtime
    # override, and invalidates the cached agent when the model changes so the
    # build below picks it up. No-op (and near-zero cost) if no plugin
    # registered the hook.
    try:
        from code_puppy.model_switching import resolve_run_model_selection

        resolve_run_model_selection(agent, prompt, agent._message_history, group_id)
    except Exception:
        # Selection must never block a run.
        pass

    # Expose this invocation's requested contract to lifecycle hooks, even
    # when a previously built wrapper is reused unchanged.
    effective_output_type = output_type if output_type is not None else str

    if agent._code_generation_agent is None:
        build_pydantic_agent(agent)

    if output_type is not None:
        build_pydantic_agent(agent, output_type=output_type)

    # MCP lifecycle tasks can invalidate the cache during this run. Keep its
    # built client as a fallback, while still resolving live replacements lazily.
    built_client = agent._code_generation_agent
    invocation = ModelCall(
        lambda: (
            current
            if (current := agent._code_generation_agent) is not None
            else built_client
        ),
        lambda current: on_agent_run_context(
            agent, current, group_id, getattr(agent, "_mcp_servers", None) or []
        ),
    )

    prompt = _should_prepend_system_prompt(agent, prompt)
    prompt_payload = _build_prompt_payload(prompt, attachments, link_attachments)

    async def _do_run(prompt_to_use: Any) -> Any:
        """Run the agent once, then honour any plugin ``retry`` requests."""
        usage_limits = UsageLimits(request_limit=get_message_limit())

        # Streaming gate (issue #295): off → no handler, render final result;
        # on → wrap handler in a detector, fall back to one-shot render only
        # if no text actually streamed.
        use_streaming = get_enable_streaming()

        async def _hooked_event_stream_handler(ctx: Any, events: Any) -> Any:
            on_agent_event_stream_start(group_id)
            return await event_stream_handler(ctx, events)

        detector: Optional[StreamingTextDetector] = (
            StreamingTextDetector(_hooked_event_stream_handler)
            if use_streaming
            else None
        )
        stream_handler = detector if detector is not None else None
        # Plugins (e.g. DBOS) can render their own output and skip the fallback.
        skip_fallback_render = on_should_skip_fallback_render(agent)

        # User-selected retry profile for the MAIN role (per-model override
        # honoured), built once so a run has consistent backoff behaviour.
        from code_puppy.agents.retry_profiles import make_streaming_retry

        from code_puppy.agents.retry_checkpoint import RetryCheckpoint, resumable_call

        checkpoint = RetryCheckpoint(agent)
        _main_retry = make_streaming_retry(
            "main", agent.get_model_name(), progress_fn=checkpoint.progress
        )
        run_options = dict(
            usage_limits=usage_limits, event_stream_handler=stream_handler, **kwargs
        )
        _call = _main_retry(
            resumable_call(agent, invocation, prompt_to_use, **run_options)
        )

        def _raise_if_cancel_requested() -> None:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise asyncio.CancelledError

        result = await run_with_exception_retry(_call, agent=agent)
        _raise_if_cancel_requested()

        # ``now``-mode steers are injected by make_steer_history_processor
        # (before every model call); ``queue``-mode ones drain between runs
        # below — additive, won't interrupt in-progress work.
        async def _follow_up_run(follow_up_prompt: Any) -> Any:
            # A hook or retry delay may consume cancellation. Never start or
            # release another paid model call while a request remains pending.
            _raise_if_cancel_requested()
            call = _main_retry(
                resumable_call(agent, invocation, follow_up_prompt, **run_options)
            )
            follow_up_result = await run_with_exception_retry(call, agent=agent)
            _raise_if_cancel_requested()
            return follow_up_result

        hook_retries_used = 0
        queued_steers_used = 0
        max_hook_retries = get_max_hook_retries()
        max_queued_steers = 50  # safety cap to prevent runaway loops

        # A nested run (structured-output assessments, model judges, ...)
        # shares the process-wide PauseController with the outer run, but the
        # user is talking to the OUTER agent. Letting a nested run drain the
        # queue feeds the user's message to a throwaway agent whose output is
        # discarded -- the message is simply lost. Same invariant the cancel
        # path already enforces via ``drain_pause_state_on_cancel``.
        may_drain_queued_steers = not is_nested_run

        while True:
            # 1) Drain queue-mode steers FIRST (user-priority over hook retries).
            if may_drain_queued_steers and queued_steers_used < max_queued_steers:
                steer_text = prepare_queued_steer_injection(agent, result)
                if steer_text is not None:
                    queued_steers_used += 1
                    result = await _follow_up_run(steer_text)
                    continue

            # 2) Plugin-requested hook retry (cap matches original loop).
            if hook_retries_used >= max_hook_retries:
                break
            hook_results = await on_agent_run_result(
                result,
                agent_name=agent.name,
                model_name=agent.get_model_name(),
            )
            retry_req = next(
                (r for r in hook_results if isinstance(r, dict) and r.get("retry")),
                None,
            )
            if not retry_req:
                break

            retry_prompt = retry_req.get("prompt", "Please continue.")
            retry_delay = retry_req.get("delay", 1.0)
            if hasattr(result, "all_messages"):
                agent._message_history = list(result.all_messages())
            await asyncio.sleep(retry_delay)
            result = await _follow_up_run(retry_prompt)
            hook_retries_used += 1

        # Result hooks may consume cancellation without requesting a retry.
        # Route that path through normal cleanup before rendering or returning.
        _raise_if_cancel_requested()

        # Fallback render when streaming didn't surface any text to the user.
        if result is not None and should_render_fallback(
            detector, skip=skip_fallback_render
        ):
            render_result_without_streaming(result)

        return result

    async def run_agent_task() -> Any:
        # Scope the agent for the whole task body so run-scoped plugin hooks
        # resolve it without the process-global agent manager (unsafe under
        # concurrent runs). Owning the scope here — rather than wrapping the
        # create_task call — keeps it correct regardless of how this coroutine
        # is scheduled.
        with executing_agent_context(agent, output_type=effective_output_type):
            return await _run_agent_task_body()

    async def _run_agent_task_body() -> Any:
        try:
            agent._message_history = _history.prune_interrupted_tool_calls(
                agent._message_history
            )

            return await _do_run(prompt_payload)
        except* UsageLimitExceeded as ule:
            emit_info(f"Usage limit exceeded: {ule}", group_id=group_id)
            emit_info(
                "The agent has reached its usage limit. You can ask it to continue "
                "by saying 'please continue' or similar.",
                group_id=group_id,
            )
        except* McpError as mcp_error:
            # Already announced by blocking_startup.py with a /mcp logs hint —
            # just give a single short, actionable nudge.
            emit_info(
                "An MCP server failed during this run. "
                "Run [cyan]/mcp logs <name>[/cyan] for details, or unbind it "
                "via [cyan]/agents → B[/cyan].",
                group_id=group_id,
            )
            import logging as _logging

            _logging.getLogger(__name__).debug(
                "McpError during agent run: %s", mcp_error
            )
        except* asyncio.CancelledError as ce_group:
            # pydantic-ai v2 attaches the partial run state to the
            # CancelledError — checkpoint it so cancelled work survives.
            _checkpoint_cancelled_history(ce_group, agent)
            # Leading newline: a mid-stream cancel leaves the transcript cursor
            # mid-line, so without it the banner glues onto that text
            # ("...AaronCancelled"). Mirrors cli_runner's "\nCancelled".
            emit_info("\nCancelled")
            await _run_cancel_cleanup(drain_pause=not is_nested_run)
        except* RunCancelled as rc_group:
            # First-party cancellation (RunContext.cancel() from a tool or
            # capability hook). Same UX as an external cancel, but the
            # snapshot rides on the exception itself.
            _checkpoint_cancelled_history(rc_group, agent)
            emit_info("\nCancelled")
            await _run_cancel_cleanup(drain_pause=not is_nested_run)
        except* InterruptedError as ie:
            emit_info(f"\nInterrupted: {ie}")
            await _run_cancel_cleanup(drain_pause=not is_nested_run)
        except* Exception as other:
            unexpected = _collect_exceptions(
                other,
                lambda e: (
                    not isinstance(e, (asyncio.CancelledError, UsageLimitExceeded))
                ),
            )
            # An HTTP/SSE connector that 401'd or was unreachable is
            # degraded, not fatal — treat it like McpError: one short nudge,
            # no traceback, don't re-raise. Pulled out BEFORE the diagnostics
            # dump so one dead connector can't abort the turn.
            mcp_transport = [e for e in unexpected if _is_mcp_transport_failure(e)]
            unexpected = [e for e in unexpected if e not in mcp_transport]
            if mcp_transport:
                import logging as _logging

                _logging.getLogger(__name__).debug(
                    "MCP transport failure(s) during agent run: %s", mcp_transport
                )
                emit_warning(
                    "An MCP server was unreachable this turn (auth or "
                    "connection failure), so the turn stopped before the model "
                    "ran — but your session is fine. Fix or disable that "
                    "connector and resend: [cyan]/mcp status[/cyan] to see "
                    "which one, [cyan]/mcp logs <name>[/cyan] for details.",
                    group_id=group_id,
                )
            for exc in unexpected:
                emit_exception_diagnostics(
                    exc, group_id=group_id, model_name=resolve_model_name(agent)
                )
            # Re-raise, else the bare except* would silently mask all errors
            # and run_with_mcp() would look like success.
            if unexpected:
                raise unexpected[0] from other
        finally:
            agent._message_history = _history.prune_interrupted_tool_calls(
                agent._message_history
            )

    agent_task: Optional[asyncio.Task[Any]] = None
    run_success = False
    run_error: Optional[BaseException] = None
    run_response_text = ""
    run_usage_metadata: dict[str, int | None] = {
        "usage_input_tokens": None,
        "usage_output_tokens": None,
        "usage_total_tokens": None,
        "usage_cached_read_tokens": None,
        "usage_cached_write_tokens": None,
        "usage_thought_tokens": None,
    }

    try:
        # Keep lifecycle start and MCP preparation inside the cancellation
        # owner so partial starts are balanced by terminal cleanup.
        try:
            with executing_agent_context(agent, output_type=effective_output_type):
                await on_agent_run_start(
                    agent_name=agent.name,
                    model_name=agent.get_model_name(),
                    session_id=group_id,
                )
        except Exception:
            # Hook failures never block the agent.
            pass
        _raise_if_owner_cancel_pending()

        try:
            from code_puppy.mcp_ import manager as _mcp_manager_module

            existing_manager = _mcp_manager_module._manager_instance
            if existing_manager is not None:
                await existing_manager.wait_for_pending_starts()
        except Exception:
            # MCP trouble must never block the agent run itself.
            pass
        _raise_if_owner_cancel_pending()

        agent_task = asyncio.create_task(run_agent_task())
        result = await agent_task
        # Providers may consume CancelledError and return. The task's pending
        # cancellation count still owns the outcome and must win over success.
        if agent_task.cancelling():
            await _run_cancel_cleanup(drain_pause=not is_nested_run)
            result = None
            if is_nested_run and _owner_cancel_pending():
                raise asyncio.CancelledError
        run_success = not run_was_cancelled
        run_response_text = _extract_response_text(result) if run_success else ""
        if run_success and hasattr(result, "all_messages"):
            # End hooks are deliberately interruptible. Persist the completed
            # turn before dispatch so Ctrl+C cannot discard its final answer.
            agent._message_history = list(result.all_messages())
        try:
            # Property access (not a call): `result.usage()` is a deprecated
            # callable-property since pydantic-ai 1.107 and warns when called.
            usage = result.usage

            def _pick_usage_int(*names: str) -> int | None:
                for name in names:
                    value = getattr(usage, name, None)
                    if value is not None:
                        return int(value) or None
                return None

            run_usage_metadata = {
                "usage_input_tokens": _pick_usage_int(
                    "input_tokens", "request_tokens", "prompt_tokens"
                ),
                # Real billed output tokens -- calibrates the run-stats TG
                # estimate (see run_stats.snapshot_cycle_into_aggregates).
                "usage_output_tokens": _pick_usage_int(
                    "output_tokens", "response_tokens", "completion_tokens"
                ),
                "usage_total_tokens": _pick_usage_int("total_tokens"),
                "usage_cached_read_tokens": _pick_usage_int(
                    "cache_read_tokens", "cached_read_tokens"
                ),
                "usage_cached_write_tokens": _pick_usage_int(
                    "cache_write_tokens", "cached_write_tokens"
                ),
                "usage_thought_tokens": _pick_usage_int(
                    "thinking_tokens", "thought_tokens", "reasoning_tokens"
                ),
            }
        except Exception:
            pass
        return result
    except asyncio.CancelledError:
        run_response_text = ""
        if agent_task is not None:
            agent_task.cancel()
        await _run_cancel_cleanup(drain_pause=not is_nested_run)
        # Cancellation before task creation belongs to the outer owner. A
        # nested model-phase cancellation must also propagate so its parent
        # cannot resume paid work after the user cancelled the shared owner.
        if agent_task is None or (is_nested_run and _owner_cancel_pending()):
            raise
    except KeyboardInterrupt:
        run_was_cancelled = True
        run_response_text = ""
        if agent_task is not None and not agent_task.done():
            agent_task.cancel()
        if not is_nested_run:
            drain_pause_state_on_cancel()
    except Exception as e:
        run_error = e
        raise
    finally:
        try:
            with executing_agent_context(agent, output_type=effective_output_type):
                await on_agent_run_end(
                    agent_name=agent.name,
                    model_name=agent.get_model_name(),
                    session_id=group_id,
                    success=run_success,
                    error=run_error,
                    response_text=run_response_text,
                    metadata={
                        "model": agent.get_model_name(),
                        **run_usage_metadata,
                    },
                )
        except Exception:
            pass
