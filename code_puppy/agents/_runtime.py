"""Agent run orchestration: streaming retries, signal/key cancellation.

Replaces the monolithic ``BaseAgent.run_with_mcp`` coroutine. Everything here
is a free function; the agent is passed in explicitly. Integration points
preserved verbatim:

- Plugin-supplied async context managers wrap the run (see
  ``on_agent_run_context``); used e.g. by the DBOS plugin to set a workflow
  ID and swap MCP toolsets in/out.
- Signal-vs-key-listener branch driven by ``cancel_agent_uses_signal()``
- Windows terminal reset on graceful SIGINT
- ``is_awaiting_user_input()`` guards interrupt handling
- Subagent task cancellation via ``_active_subagent_tasks``
- ``_RUNNING_PROCESSES`` check before cancelling the agent
"""

from __future__ import annotations

import asyncio
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

from code_puppy.agents import _history, _key_listeners
from code_puppy.agents._builder import build_pydantic_agent
from code_puppy.agents._diagnostics import emit_exception_diagnostics
from code_puppy.agents._non_streaming_render import (
    StreamingTextDetector,
    render_result_without_streaming,
    should_render_fallback,
)
from code_puppy.agents._run_signals import (
    drain_pause_state_on_cancel,
    make_schedule_cancel,
    prepare_queued_steer_injection,
    reset_pause_state_at_run_start,
    sigint_should_cancel,
)
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
from code_puppy.keymap import cancel_agent_uses_signal
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.command_runner import is_awaiting_user_input

# ---- Streaming retry helpers ------------------------------------------------

# Every entry here is either an explicit provider "please retry" signal or an
# SSE framing / transport artifact that reliably succeeds on the next attempt.
# Keep this list substring-based and lower-case.
_RETRYABLE_SNIPPETS = (
    "streamed response ended without content",
    "malformed streamed sse event",
    "extra json data in sse payload",
    "too many requests",
    "rate limit",
    "rate limited",
    "overloaded",
    "service unavailable",
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

# Transient transport failures worth a silent retry rather than a crash.
# We list the umbrella base classes instead of individual error types so a
# dropped socket in any guise -- ReadError, WriteError, ConnectError,
# CloseError (all httpx.NetworkError) or any of the *Timeout variants
# (httpx.TimeoutException) -- is covered without us chasing each subclass.
# A flaky VPN/WiFi blip mid-stream is recoverable, never fatal.
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

    if isinstance(exc, UnexpectedModelBehavior):
        return _matches_retryable_snippet(msg)

    if OpenAIAPIError is not None and isinstance(exc, OpenAIAPIError):
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
                if str(err.get("type", "")).lower() in {
                    "api_error",
                    "server_error",
                    "internal_server_error",
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

    # pydantic-ai wraps Anthropic APIConnectionError as ModelAPIError("Connection error.").
    # The original is usually in __cause__ (caught by the walker) but match by snippet
    # too -- belt and braces for cases where the cause chain has been severed.
    if ModelAPIError is not None and isinstance(exc, ModelAPIError):
        if _matches_retryable_snippet(msg):
            return True

    return False


def should_retry_streaming(exc: Exception) -> bool:
    """Decide whether ``exc`` (or anything it wraps) is a transient hiccup.

    Walks the ``__cause__`` / ``__context__`` chain so wrapper exception types
    like :class:`pydantic_ai.exceptions.ModelAPIError` -- which hide the
    real httpx/anthropic transport error in ``__cause__`` -- still get
    classified correctly. Returns ``True`` if *any* link in the chain is
    transient.
    """
    return any(_is_retryable_one(e) for e in _walk_cause_chain(exc))


def streaming_retry(
    max_attempts: int = 3,
    delays: Sequence[float] = (1, 2, 4),
) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
    """Wrap a no-arg async callable with streaming-retry semantics.

    Every retry (and the final exhaustion, if it happens) is logged with full
    detail to the on-disk error log via ``log_error``. Users only see a short
    UI banner, but SRE / power-users grepping ``~/.code_puppy/logs/errors.log``
    get the exception type, message, traceback, and which attempt it was. The
    on-disk log is the only way to measure the upstream-blip rate after the
    classifier silently absorbs it.
    """
    from code_puppy.error_logging import log_error

    def decorator(factory: Callable[[], Any]) -> Callable[[], Any]:
        async def runner() -> Any:
            last_exc: Optional[Exception] = None
            for attempt in range(max_attempts):
                try:
                    return await factory()
                except Exception as exc:
                    if not should_retry_streaming(exc):
                        raise
                    last_exc = exc
                    log_error(
                        exc,
                        context=(
                            f"streaming_retry: transient exception on attempt "
                            f"{attempt + 1}/{max_attempts}"
                        ),
                    )
                    if attempt < max_attempts - 1:
                        delay = delays[attempt] if attempt < len(delays) else delays[-1]
                        emit_warning(
                            f"\u26a1 Streaming interrupted, auto-retrying in {delay}s... "
                            f"(attempt {attempt + 1}/{max_attempts})"
                        )
                        await asyncio.sleep(delay)
                    else:
                        log_error(
                            exc,
                            context=(
                                f"streaming_retry: exhausted all {max_attempts} "
                                "attempts -- giving up and re-raising"
                            ),
                        )
                        emit_error(
                            f"\u274c Streaming failed after {max_attempts} attempts"
                        )
            assert last_exc is not None  # loop always sets this before exiting
            raise last_exc

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


def _is_cancel_scope_corruption(exc: BaseException) -> bool:
    """True for anyio's cross-task cancel-scope ``RuntimeError``.

    pydantic-ai MCP toolsets are refcounted: whichever task takes the
    refcount 0->1 owns the underlying anyio cancel scope, and whichever
    task drops it back to 0 closes it. When an MCP server's lifecycle task
    dies mid-run (e.g. a flaky ``npx``-spawned stdio subprocess exits), the
    agent run task ends up closing a scope owned by a dead task and anyio
    raises ``RuntimeError: Attempted to exit a cancel scope that isn't the
    current task's current cancel scope``. By that point the model's
    response has already streamed — this is teardown noise, not a run
    failure, so we detect it and degrade gracefully instead of dumping a
    full exception group on the user.
    """
    return isinstance(exc, RuntimeError) and "cancel scope" in str(exc).lower()


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


# Depth of in-flight ``run_with_mcp`` calls. Only touched from the main
# event loop's thread (every run is awaited on the same loop), so a plain
# int is race-free. Depth > 0 at entry means a NESTED run — e.g. the
# shell_safety plugin assessing a command while the primary agent runs.
# Nested runs must NOT touch process-wide interactive state: the
# PauseController (it would drain the user's queued steers!), the SIGINT
# handler, the shell cancel bridge, or the key-listener cancel hotkey.
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

    # Scrub any stale PauseController state from a previously-cancelled run
    # BEFORE we touch the prompt or build the agent. The controller is a
    # process-wide singleton; without this guard a leftover steer queue
    # would silently poison this run. NEVER from a nested run: the "stale"
    # steers it would drain are the OUTER run's live ones.
    if not is_nested_run:
        reset_pause_state_at_run_start()

    prompt = _sanitize_prompt(prompt)
    group_id = str(uuid.uuid4())

    # Fire user_prompt_submit hooks BEFORE prompt is sent. Plugins (e.g. the
    # claude_code_hooks bridge) may return a string to replace the prompt —
    # this is how Claude Code-style ``UserPromptSubmit`` hooks inject
    # additional context (project constitutions, domain nudges, etc.)
    try:
        submit_results = await on_user_prompt_submit(prompt, group_id)
        for r in submit_results:
            if isinstance(r, str) and r:
                prompt = r
    except Exception:
        # Hook failures must never block the run.
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

        # Streaming config gate (issue #295). When streaming is disabled we
        # never install the stream handler at all and always render from the
        # final result. When it's enabled we wrap the handler in a detector
        # and fall back to a one-shot render only if no text actually streamed.
        use_streaming = get_enable_streaming()
        detector: Optional[StreamingTextDetector] = (
            StreamingTextDetector(event_stream_handler) if use_streaming else None
        )
        stream_handler = detector if detector is not None else None
        # Plugins (e.g. DBOS) can render their own output and ask us to skip
        # the non-streaming fallback render.
        skip_fallback_render = on_should_skip_fallback_render(agent)

        @streaming_retry()
        async def _call() -> Any:
            return await pydantic_agent.run(
                prompt_to_use,
                message_history=agent._message_history,
                usage_limits=usage_limits,
                event_stream_handler=stream_handler,
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

        result = await _call_with_exception_recovery()

        # ``now``-mode steering injection lives in ``make_steer_history_processor``
        # (fires before every model call). ``queue``-mode steers are drained
        # between ``agent.run()`` calls below — additive, won't interrupt
        # in-progress work.
        async def _follow_up_run(follow_up_prompt: Any) -> Any:
            @streaming_retry()
            async def _call_follow_up() -> Any:
                return await pydantic_agent.run(
                    follow_up_prompt,
                    message_history=agent._message_history,
                    usage_limits=usage_limits,
                    event_stream_handler=stream_handler,
                    **kwargs,
                )

            return await _call_follow_up()

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
            detector, skip=skip_fallback_render
        ):
            render_result_without_streaming(result)

        return result

    async def run_agent_task() -> Any:
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
            # Already announced once by blocking_startup.py with a /mcp logs
            # hint. Don't re-vomit the exception text — just give the user
            # a single short, actionable nudge.
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
        except* asyncio.CancelledError:
            # Leading newline: a mid-stream cancel aborts the drain tasks
            # (event_stream_handler) before the "final newline after
            # streaming" runs, so the transcript cursor is usually parked
            # mid-line on a half-streamed thinking/answer row. Without it
            # the banner glues onto that text ("...AaronCancelled").
            # Mirrors the classic cli_runner emit_warning("\nCancelled").
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
            scope_noise = [e for e in unexpected if _is_cancel_scope_corruption(e)]
            unexpected = [e for e in unexpected if e not in scope_noise]
            if scope_noise:
                import logging as _logging

                _logging.getLogger(__name__).debug(
                    "Suppressed cross-task cancel-scope error(s): %s", scope_noise
                )
                emit_warning(
                    "An MCP server connection died during this run (its async "
                    "teardown crossed task boundaries). The response above is "
                    "intact, but this turn may not be saved to history. "
                    "Check [cyan]/mcp status[/cyan] and restart the server if needed."
                )
            for exc in unexpected:
                emit_exception_diagnostics(exc, group_id=group_id)
            # Re-raise so the outer handler in run_with_mcp can propagate
            # (or re-raise) the exception to the caller. Silently returning
            # None (the implicit return after a bare except*) would mask all
            # errors and make run_with_mcp() indistinguishable from success.
            if unexpected:
                raise unexpected[0] from other
        finally:
            agent._message_history = _history.prune_interrupted_tool_calls(
                agent._message_history
            )

    # Fire agent_run_start hooks BEFORE creating the agent task so plugins
    # (e.g. token refresh, credential minting) can complete their work before
    # any HTTP request leaves the building. Otherwise the ``await`` would
    # yield control to the event loop and the agent task would race ahead
    # with stale credentials. See issue #338.
    try:
        await on_agent_run_start(
            agent_name=agent.name,
            model_name=agent.get_model_name(),
            session_id=group_id,
        )
    except Exception:
        # Hook failures never block the agent.
        pass

    # ``build_pydantic_agent`` may have kicked off fire-and-forget MCP
    # autostarts (``start_server_sync``). Await them so each server's
    # lifecycle task owns its anyio cancel scope BEFORE pydantic-ai enters
    # the toolsets inside the run task below — otherwise the run task takes
    # ownership and unwind crashes with a cross-task cancel-scope error.
    # Mirrors the fix already applied to sub-agent invocation.
    try:
        from code_puppy.mcp_ import manager as _mcp_manager_module

        # Peek at the singleton instead of get_mcp_manager() — if no manager
        # exists yet there's nothing pending, and we shouldn't pay the cost
        # of constructing one just to ask.
        _existing_manager = _mcp_manager_module._manager_instance
        if _existing_manager is not None:
            await _existing_manager.wait_for_pending_starts()
    except Exception:
        # MCP trouble must never block the agent run itself.
        pass

    agent_task = asyncio.create_task(run_agent_task())

    loop = asyncio.get_running_loop()

    schedule_agent_cancel = make_schedule_cancel(agent_task, loop)

    # Bridge the cancel callback to the shell SIGINT handler so a single
    # Ctrl+C while shells are running stops the whole agent/sub-agent swarm
    # (kill shells, then cancel every task) instead of only killing the
    # current batch of shells. Nested runs must not clobber the outer
    # run's bridge (clear_agent_cancel in their finally would disarm it).
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
        # On Windows the full reset re-clamps raw-Ctrl+C mode itself
        # (reset_windows_console_mode respects the sticky clamp), so a
        # stray SIGINT can't regress the console into event-generating
        # mode. No launcher-specific re-arming needed.
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
    run_usage_output_tokens: Optional[int] = None

    try:
        # Nested runs (e.g. shell_safety mid-run) leave the SIGINT handler
        # and cancel hotkey alone — the outer run owns them, and cancelling
        # the outer task propagates into this awaited one anyway.
        if not is_nested_run:
            if cancel_agent_uses_signal():
                original_handler = signal.signal(
                    signal.SIGINT, keyboard_interrupt_handler
                )
                cancel_cb: Optional[Callable[[], None]] = None  # SIGINT owns cancel
            else:
                original_handler = signal.signal(signal.SIGINT, graceful_sigint_handler)
                cancel_cb = schedule_agent_cancel
            # Key listener: with the persistent prompt (Phase A) a REPL-
            # lifetime listener already owns stdin — just arm the per-run
            # cancel hotkey on it. Otherwise (headless -r, classic prompt,
            # embeds) spawn a per-run listener. ``acquire_listener`` makes
            # the reuse-or-spawn decision atomic (no double-reader race).
            key_listener_stop_event = threading.Event()
            handle, spawned = _key_listeners.acquire_listener(
                key_listener_stop_event,
                # Ctrl+X: command_runner installs a dynamic handler via
                # _key_listeners.set_escape_handler() while shell commands
                # run; outside that window Ctrl+X is a no-op.
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
            # Real billed output tokens -- calibrates the run-stats TG
            # estimate (see run_stats.snapshot_cycle_into_aggregates).
            run_usage_output_tokens = (
                int(getattr(result.usage(), "output_tokens", 0) or 0) or None
            )
        except Exception:
            run_usage_output_tokens = None
        return result
    except asyncio.CancelledError:
        run_response_text = ""
        agent_task.cancel()
        # Nested runs never drain: the pending steers belong to the outer
        # run, whose own cancel path (or run end) handles them.
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
            await on_agent_run_end(
                agent_name=agent.name,
                model_name=agent.get_model_name(),
                session_id=group_id,
                success=run_success,
                error=run_error,
                response_text=run_response_text,
                metadata={
                    "model": agent.get_model_name(),
                    "usage_output_tokens": run_usage_output_tokens,
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
