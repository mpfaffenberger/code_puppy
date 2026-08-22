"""Agent run orchestration: streaming retries, signal/key cancellation.

Replaces the monolithic ``BaseAgent.run_with_mcp`` coroutine. Everything here
is a free function; the agent is passed in explicitly. Integration points
preserved verbatim:

- Plugin-supplied async context managers wrap the run (see
  ``on_agent_run_context``); used e.g. by the DBOS plugin to set a workflow
  ID and swap MCP toolsets in/out.
- SIGINT fallback-handler choice driven by ``sigint_fallback_cancels()``
  (the key listener always owns cancel; ^C is a pure keybinding)
- Windows terminal reset on graceful SIGINT
- ``is_awaiting_user_input()`` guards interrupt handling
- Subagent task cancellation via ``_active_subagent_tasks``
- ``_RUNNING_PROCESSES`` check before cancelling the agent
"""

from __future__ import annotations

import asyncio
import json
import re
import signal
import threading
import uuid
from contextlib import AsyncExitStack
from typing import Any, Callable, Iterator, List, Optional, Sequence, Type, Union

import httpcore
import httpx
import mcp
from pydantic_ai import (
    BinaryContent,
    DocumentUrl,
    ImageUrl,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UsageLimits,
)
from pydantic_ai.exceptions import RunCancelled

try:  # pragma: no cover - pydantic-ai version dependent
    from pydantic_ai.exceptions import ModelHTTPError
except ImportError:
    ModelHTTPError = None  # type: ignore[misc,assignment]

try:  # pragma: no cover - optional dependency
    from openai import APIError as OpenAIAPIError
except ImportError:
    OpenAIAPIError = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from anthropic import APIConnectionError as AnthropicAPIConnectionError
    from anthropic import APIStatusError as AnthropicAPIStatusError
except ImportError:
    AnthropicAPIConnectionError = None  # type: ignore[assignment]
    AnthropicAPIStatusError = None  # type: ignore[assignment]

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
from code_puppy.agents import _history, _key_listeners
from code_puppy.agents._builder import build_pydantic_agent
from code_puppy.agents._diagnostics import emit_exception_diagnostics
from code_puppy.agents._non_streaming_render import (
    render_result_without_streaming,
    should_render_fallback,
)
from code_puppy.agents._run_signals import (
    drain_pause_state_on_cancel,
    inject_interrupted_subagent_notes,
    make_schedule_cancel,
    prepare_queued_steer_injection,
    reset_pause_state_at_run_start,
    sigint_should_cancel,
)
from code_puppy.agents._stream_rendering import stream_observation
from code_puppy.agents.event_stream_handler import event_stream_handler
from code_puppy.callbacks import (
    on_agent_exception,
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
from code_puppy.tools.command_runner import is_awaiting_user_input

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
# VPN/WiFi blip is recoverable, never fatal.
_RETRYABLE_EXCEPTIONS: tuple = (
    httpx.NetworkError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
    httpcore.NetworkError,
    httpcore.TimeoutException,
    httpcore.RemoteProtocolError,
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

    msg = str(exc)

    # Provider-agnostic: in-band SSE 5xx lands with status_code=200 and only a
    # "[HTTP 5xx]" marker; a 4xx marker is a genuine client error — never retry.
    if _is_transient_status(_embedded_http_status(msg)):
        return True

    if isinstance(exc, UnexpectedModelBehavior):
        return _matches_retryable_snippet(msg)

    if OpenAIAPIError is not None and isinstance(exc, OpenAIAPIError):
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
    if AnthropicAPIConnectionError is not None and isinstance(
        exc, AnthropicAPIConnectionError
    ):
        return True

    # Anthropic SDK: status errors are retryable on 5xx (or unset) OR when the
    # message/body matches a gateway-transient snippet (e.g. upstream_idle_timeout).
    if AnthropicAPIStatusError is not None and isinstance(exc, AnthropicAPIStatusError):
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
    link_attachments: Optional[Sequence[Union[ImageUrl, DocumentUrl]]],
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
# plain int is race-free). Depth > 0 = NESTED run (e.g. shell_safety): those
# must NOT touch process-wide interactive state — PauseController (would
# drain the user's queued steers!), SIGINT handler, shell cancel bridge, or
# the key-listener cancel hotkey.
_active_run_depth = 0


async def run_with_mcp(
    agent: Any,
    prompt: str,
    *,
    attachments: Optional[Sequence[BinaryContent]] = None,
    link_attachments: Optional[Sequence[Union[ImageUrl, DocumentUrl]]] = None,
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
    try:
        return await _run_with_mcp_impl(
            agent,
            prompt,
            attachments=attachments,
            link_attachments=link_attachments,
            output_type=output_type,
            is_nested_run=is_nested_run,
            **kwargs,
        )
    finally:
        _active_run_depth -= 1


async def _run_with_mcp_impl(
    agent: Any,
    prompt: str,
    *,
    attachments: Optional[Sequence[BinaryContent]] = None,
    link_attachments: Optional[Sequence[Union[ImageUrl, DocumentUrl]]] = None,
    output_type: Optional[Type[Any]] = None,
    is_nested_run: bool = False,
    **kwargs: Any,
) -> Any:
    """Body of :func:`run_with_mcp` (depth bookkeeping lives in the wrapper)."""

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

    # Fire user_prompt_submit hooks BEFORE the prompt is sent; plugins (e.g.
    # claude_code_hooks) may return a replacement prompt string.
    try:
        submit_results = await on_user_prompt_submit(prompt, group_id)
        for r in submit_results:
            if isinstance(r, str) and r:
                prompt = r
    except Exception:
        # Hook failures must never block the run.
        pass

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

    if agent._code_generation_agent is None:
        build_pydantic_agent(agent)
    pydantic_agent = agent._code_generation_agent

    if output_type is not None:
        pydantic_agent = build_pydantic_agent(agent, output_type=output_type)

    prompt = _should_prepend_system_prompt(agent, prompt)
    prompt_payload = _build_prompt_payload(prompt, attachments, link_attachments)

    async def _do_run(prompt_to_use: Any) -> Any:
        """Run the agent once, then honour any plugin ``retry`` requests."""
        usage_limits = UsageLimits(request_limit=get_message_limit())

        # Streaming gate (issue #295): off → no streaming, render the final
        # result one-shot; on → the agent's StreamRendering capability streams
        # the run (observability capture + text detection included), and we
        # fall back to the one-shot render only if no text actually streamed.
        use_streaming = get_enable_streaming()
        # Plugins (e.g. DBOS) can render their own output and skip the fallback.
        skip_fallback_render = on_should_skip_fallback_render(agent)

        # User-selected retry profile for the MAIN role (per-model override
        # honoured), built once so a run has consistent backoff behaviour.
        from code_puppy.agents.retry_profiles import make_streaming_retry

        _main_retry = make_streaming_retry(
            "main",
            agent.get_model_name(),
            # Completed steps are checkpointed into _message_history, so a
            # growing history means real progress → refresh the budget.
            progress_fn=lambda: len(agent._message_history or []),
        )

        @_main_retry
        async def _call() -> Any:
            return await pydantic_agent.run(
                prompt_to_use,
                message_history=agent._message_history,
                usage_limits=usage_limits,
                **kwargs,
            )

        async def _call_with_exception_recovery() -> Any:
            """Run ``_call`` and let plugins request one exception retry."""
            try:
                return await _call()
            except Exception as exc:
                hook_results = await on_agent_exception(
                    exc,
                    agent=agent,
                    agent_name=agent.name,
                    model_name=agent.get_model_name(),
                )
                retry_req = next(
                    (r for r in hook_results if isinstance(r, dict) and r.get("retry")),
                    None,
                )
                if not retry_req:
                    raise

                retry_delay = retry_req.get("delay", 0.0)
                if retry_delay:
                    await asyncio.sleep(retry_delay)
                return await _call()

        # ``now``-mode steers are injected by make_steer_history_processor
        # (before every model call); ``queue``-mode ones drain between runs
        # below — additive, won't interrupt in-progress work.
        async def _follow_up_run(follow_up_prompt: Any) -> Any:
            @_main_retry
            async def _call_follow_up() -> Any:
                return await pydantic_agent.run(
                    follow_up_prompt,
                    message_history=agent._message_history,
                    usage_limits=usage_limits,
                    **kwargs,
                )

            return await _call_follow_up()

        # One observation spans the initial run and every follow-up, so
        # ``streamed_text`` accumulates across the sequence exactly as the
        # old shared StreamingTextDetector did. ``enabled`` keeps the
        # streaming gate, with one deliberate carve-out: a plugin that
        # renders its own output (skip_fallback_render, e.g. DBOS) used to
        # stream regardless of the gate via its wrapper's constructor-level
        # handler — the capability preserves that by enabling the stream for
        # it here.
        with stream_observation(
            event_stream_handler,
            group_id=group_id,
            enabled=use_streaming or skip_fallback_render,
        ) as observation:
            result = await _call_with_exception_recovery()

            hook_retries_used = 0
            queued_steers_used = 0
            max_hook_retries = get_max_hook_retries()
            max_queued_steers = 50  # safety cap to prevent runaway loops

            while True:
                # 1) Drain queue-mode steers FIRST (user-priority over hook retries).
                if queued_steers_used < max_queued_steers:
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

        # Fallback render when streaming didn't surface any text to the user.
        if result is not None and should_render_fallback(
            observation.detector if use_streaming else None,
            skip=skip_fallback_render,
        ):
            render_result_without_streaming(result)

        return result

    async def run_agent_task() -> Any:
        # Scope the agent for the whole task body so run-scoped plugin hooks
        # resolve it without the process-global agent manager (unsafe under
        # concurrent runs). Owning the scope here — rather than wrapping the
        # create_task call — keeps it correct regardless of how this coroutine
        # is scheduled.
        with executing_agent_context(agent):
            return await _run_agent_task_body()

    async def _run_agent_task_body() -> Any:
        try:
            agent._message_history = _history.prune_interrupted_tool_calls(
                agent._message_history
            )

            mcp_servers = getattr(agent, "_mcp_servers", None) or []
            run_ctxs = on_agent_run_context(
                agent, pydantic_agent, group_id, mcp_servers
            )
            async with AsyncExitStack() as stack:
                for cm in run_ctxs:
                    await stack.enter_async_context(cm)
                return await _do_run(prompt_payload)
        except* UsageLimitExceeded as ule:
            emit_info(f"Usage limit exceeded: {ule}", group_id=group_id)
            emit_info(
                "The agent has reached its usage limit. You can ask it to continue "
                "by saying 'please continue' or similar.",
                group_id=group_id,
            )
        except* mcp.shared.exceptions.McpError as mcp_error:
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
            drain_pause_state_on_cancel()
            await on_agent_run_cancel(group_id)
        except* RunCancelled as rc_group:
            # First-party cancellation (RunContext.cancel() from a tool or
            # capability hook). Same UX as an external cancel, but the
            # snapshot rides on the exception itself.
            _checkpoint_cancelled_history(rc_group, agent)
            emit_info("\nCancelled")
            drain_pause_state_on_cancel()
            await on_agent_run_cancel(group_id)
        except* InterruptedError as ie:
            emit_info(f"\nInterrupted: {ie}")
            drain_pause_state_on_cancel()
            await on_agent_run_cancel(group_id)
        except* Exception as other:
            unexpected = _collect_exceptions(
                other,
                lambda e: (
                    not isinstance(e, (asyncio.CancelledError, UsageLimitExceeded))
                ),
            )
            for exc in unexpected:
                emit_exception_diagnostics(exc, group_id=group_id)
            # Re-raise, else the bare except* would silently mask all errors
            # and run_with_mcp() would look like success.
            if unexpected:
                raise unexpected[0] from other
        finally:
            from code_puppy.observability import clear_agent_context

            clear_agent_context(group_id)
            agent._message_history = _history.prune_interrupted_tool_calls(
                agent._message_history
            )

    # Fire agent_run_start hooks BEFORE creating the task so plugins (token
    # refresh, credential minting) finish before any HTTP leaves — else the
    # task races ahead with stale credentials (issue #338).
    try:
        with executing_agent_context(agent):
            await on_agent_run_start(
                agent_name=agent.name,
                model_name=agent.get_model_name(),
                session_id=group_id,
            )
    except Exception:
        # Hook failures never block the agent.
        pass

    # ``build_pydantic_agent`` may have kicked off fire-and-forget MCP
    # autostarts; await them so each server's lifecycle task owns its anyio
    # cancel scope before the run task does — else unwind crashes with a
    # cross-task cancel-scope error (mirrors the sub-agent fix).
    try:
        from code_puppy.mcp_ import manager as _mcp_manager_module

        # Peek at the singleton rather than construct a manager just to ask.
        _existing_manager = _mcp_manager_module._manager_instance
        if _existing_manager is not None:
            await _existing_manager.wait_for_pending_starts()
    except Exception:
        # MCP trouble must never block the agent run itself.
        pass

    agent_task = asyncio.create_task(run_agent_task())

    loop = asyncio.get_running_loop()

    schedule_agent_cancel = make_schedule_cancel(agent_task, loop)

    # Bridge the cancel callback to the shell SIGINT handler so one Ctrl+C
    # stops the whole swarm (kill shells, then cancel every task), not just
    # the current batch. Nested runs must not clobber the outer run's bridge.
    from code_puppy.tools import command_runner as _command_runner

    if not is_nested_run:
        _command_runner.register_agent_cancel(schedule_agent_cancel)

    def keyboard_interrupt_handler(_sig, _frame):
        # Let input() handle its own KeyboardInterrupt if we're mid-prompt.
        if is_awaiting_user_input():
            return
        # Buffer-first Ctrl+C: composing input absorbs the first press
        # (clear + hint); only an empty prompt cancels the run.
        if not sigint_should_cancel():
            return
        schedule_agent_cancel()

    def graceful_sigint_handler(_sig, _frame):
        from code_puppy.keymap import get_cancel_agent_display_name
        from code_puppy.terminal_utils import reset_windows_terminal_full

        if is_awaiting_user_input():
            return
        # The full reset re-clamps raw-Ctrl+C mode itself (respects the sticky
        # clamp), so a stray SIGINT can't regress the console. No re-arming needed.
        reset_windows_terminal_full()
        # Buffer-first: composing input absorbs the press (clear + hint),
        # matching keyboard_interrupt_handler's contract.
        if not sigint_should_cancel():
            return
        emit_info(f"Use {get_cancel_agent_display_name()} to cancel the agent task.")

    original_handler = None
    key_listener_stop_event: Optional[threading.Event] = None
    key_listener_handle: Optional[_key_listeners.KeyListenerHandle] = None
    using_persistent_listener = False

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
        # Nested runs leave the SIGINT handler/cancel hotkey alone — the outer
        # run owns them, and cancelling it propagates into this awaited one.
        if not is_nested_run:
            # Ctrl+C is a PURE keybinding: with a raw-mode reader owning stdin,
            # ^C arrives as \x03 and the key listener cancels. SIGINT only
            # fires out-of-band (kill -INT, piped stdin, cooked-mode gaps) —
            # this fallback cancels when ^C IS the gesture, else hints at the
            # remapped key. Off main thread (ACP/embeds), SIGINT wiring is
            # skipped (handlers are main-thread-only in CPython).
            if threading.current_thread() is not threading.main_thread():
                pass  # original_handler stays None -> restore is a no-op
            elif sigint_fallback_cancels():
                original_handler = signal.signal(
                    signal.SIGINT, keyboard_interrupt_handler
                )
            else:
                original_handler = signal.signal(signal.SIGINT, graceful_sigint_handler)
            cancel_cb: Optional[Callable[[], None]] = schedule_agent_cancel
            # Key listener: arm the per-run cancel hotkey on a REPL-lifetime
            # listener if one owns stdin (persistent prompt), else spawn a
            # per-run one. ``acquire_listener`` decides atomically (no
            # double-reader race).
            key_listener_stop_event = threading.Event()
            handle, spawned = _key_listeners.acquire_listener(
                key_listener_stop_event,
                # Ctrl+X is the chord prefix when an editor is installed
                # (messaging.chords); this fallback only fires with no editor,
                # where chord targets don't exist — no-op is right.
                on_escape=lambda: None,
                on_cancel_agent=cancel_cb,
            )
            if spawned:
                key_listener_handle = handle
            else:
                using_persistent_listener = True
                _key_listeners.set_cancel_handler(cancel_cb)

        result = await agent_task
        run_success = True
        run_response_text = _extract_response_text(result)
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
        agent_task.cancel()
        # Nested runs never drain: the pending steers belong to the outer run.
        if not is_nested_run:
            drain_pause_state_on_cancel()
    except KeyboardInterrupt:
        run_response_text = ""
        if not agent_task.done():
            agent_task.cancel()
        if not is_nested_run:
            drain_pause_state_on_cancel()
    except Exception as e:
        run_error = e
        raise
    finally:
        if not is_nested_run:
            try:
                from code_puppy.tools import command_runner as _command_runner

                _command_runner.clear_agent_cancel()
            except Exception:
                pass
        try:
            with executing_agent_context(agent):
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

        if using_persistent_listener:
            # The REPL-lifetime listener survives the run — just disarm
            # the per-run cancel hotkey.
            _key_listeners.set_cancel_handler(None)
        elif key_listener_handle is not None:
            _key_listeners.set_active_handle(None)
            key_listener_handle.stop()
            key_listener_handle.thread.join(timeout=1.0)
        elif key_listener_stop_event is not None:
            # Handle is None (no TTY); just flip the stop event so any
            # half-spawned bits unwind cleanly.
            key_listener_stop_event.set()
        if original_handler is not None:  # SIG_DFL is 0/falsy — explicit check!
            signal.signal(signal.SIGINT, original_handler)
