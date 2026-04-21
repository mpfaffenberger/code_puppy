"""Agent run orchestration: streaming retries, signal/key cancellation, DBOS.

Replaces the monolithic ``BaseAgent.run_with_mcp`` coroutine. Everything here
is a free function; the agent is passed in explicitly. Integration points
preserved verbatim:

- DBOS workflow ID via ``SetWorkflowID(group_id)``
- DBOS MCP toolset injection (temp ``_toolsets`` swap with try/finally restore)
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
from typing import Any, Callable, List, Optional, Sequence, Type, Union

import httpcore
import httpx
import mcp
from dbos import DBOS, SetWorkflowID
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
from code_puppy.agents.event_stream_handler import event_stream_handler
from code_puppy.callbacks import (
    on_agent_run_end,
    on_agent_run_result,
    on_agent_run_start,
)
from code_puppy.config import (
    get_enable_streaming,
    get_max_hook_retries,
    get_message_limit,
    get_use_dbos,
)
from code_puppy.keymap import cancel_agent_uses_signal
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.agent_tools import _active_subagent_tasks
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
)

_RETRYABLE_EXCEPTIONS: tuple = (
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
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


def should_retry_streaming(exc: Exception) -> bool:
    """Decide whether ``exc`` is a transient streaming hiccup worth retrying."""
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

    return False


def streaming_retry(
    max_attempts: int = 3,
    delays: Sequence[float] = (1, 2, 4),
) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
    """Wrap a no-arg async callable with streaming-retry semantics."""

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
                    if attempt < max_attempts - 1:
                        delay = delays[attempt] if attempt < len(delays) else delays[-1]
                        emit_warning(
                            f"⚡ Streaming interrupted, auto-retrying in {delay}s... "
                            f"(attempt {attempt + 1}/{max_attempts})"
                        )
                        await asyncio.sleep(delay)
                    else:
                        emit_error(f"❌ Streaming failed after {max_attempts} attempts")
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


async def run_with_mcp(
    agent: Any,
    prompt: str,
    *,
    attachments: Optional[Sequence[BinaryContent]] = None,
    link_attachments: Optional[Sequence[Union[ImageUrl, DocumentUrl]]] = None,
    output_type: Optional[Type[Any]] = None,
    **kwargs: Any,
) -> Any:
    """Run ``agent`` against ``prompt`` with full MCP + cancellation support."""

    prompt = _sanitize_prompt(prompt)
    group_id = str(uuid.uuid4())

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
        # DBOS renders its own output at construction time, so skip there.
        skip_fallback_render = get_use_dbos()

        @streaming_retry()
        async def _call() -> Any:
            return await pydantic_agent.run(
                prompt_to_use,
                message_history=agent._message_history,
                usage_limits=usage_limits,
                event_stream_handler=stream_handler,
                **kwargs,
            )

        result = await _call()

        for _ in range(get_max_hook_retries()):
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

            @streaming_retry()
            async def _retry_call() -> Any:
                return await pydantic_agent.run(
                    retry_prompt,
                    message_history=agent._message_history,
                    usage_limits=usage_limits,
                    event_stream_handler=stream_handler,
                    **kwargs,
                )

            result = await _retry_call()

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

            use_dbos = get_use_dbos()
            mcp_servers = getattr(agent, "_mcp_servers", None) or []

            if use_dbos and mcp_servers:
                # DBOS path: inject MCP via the private _toolsets swap, then
                # restore unconditionally so future runs aren't corrupted.
                original_toolsets = pydantic_agent._toolsets
                pydantic_agent._toolsets = original_toolsets + mcp_servers
                try:
                    with SetWorkflowID(group_id):
                        return await _do_run(prompt_payload)
                finally:
                    pydantic_agent._toolsets = original_toolsets
            elif use_dbos:
                with SetWorkflowID(group_id):
                    return await _do_run(prompt_payload)
            else:
                return await _do_run(prompt_payload)
        except* UsageLimitExceeded as ule:
            emit_info(f"Usage limit exceeded: {ule}", group_id=group_id)
            emit_info(
                "The agent has reached its usage limit. You can ask it to continue "
                "by saying 'please continue' or similar.",
                group_id=group_id,
            )
        except* mcp.shared.exceptions.McpError as mcp_error:
            emit_info(f"MCP server error: {mcp_error}", group_id=group_id)
            emit_info("Try disabling any malfunctioning MCP servers", group_id=group_id)
        except* asyncio.CancelledError:
            emit_info("Cancelled")
            if get_use_dbos():
                await DBOS.cancel_workflow_async(group_id)
        except* InterruptedError as ie:
            emit_info(f"Interrupted: {ie}")
            if get_use_dbos():
                await DBOS.cancel_workflow_async(group_id)
        except* Exception as other:
            unexpected = _collect_exceptions(
                other,
                lambda e: not isinstance(
                    e, (asyncio.CancelledError, UsageLimitExceeded)
                ),
            )
            for exc in unexpected:
                emit_exception_diagnostics(exc, group_id=group_id)
        finally:
            agent._message_history = _history.prune_interrupted_tool_calls(
                agent._message_history
            )

    agent_task = asyncio.create_task(run_agent_task())

    try:
        await on_agent_run_start(
            agent_name=agent.name,
            model_name=agent.get_model_name(),
            session_id=group_id,
        )
    except Exception:
        # Hook failures never block the agent.
        pass

    loop = asyncio.get_running_loop()

    def schedule_agent_cancel() -> None:
        from code_puppy.tools.command_runner import _RUNNING_PROCESSES

        if _RUNNING_PROCESSES:
            emit_warning(
                "Refusing to cancel Agent while a shell command is running — "
                "press Ctrl+X to cancel the shell command."
            )
            return
        if agent_task.done():
            return
        if _active_subagent_tasks:
            emit_warning(
                f"Cancelling {len(_active_subagent_tasks)} active subagent task(s)..."
            )
            for task in list(_active_subagent_tasks):
                if not task.done():
                    loop.call_soon_threadsafe(task.cancel)
        loop.call_soon_threadsafe(agent_task.cancel)

    def keyboard_interrupt_handler(_sig, _frame):
        # Let input() handle its own KeyboardInterrupt if we're mid-prompt.
        if is_awaiting_user_input():
            return
        schedule_agent_cancel()

    def graceful_sigint_handler(_sig, _frame):
        from code_puppy.keymap import get_cancel_agent_display_name
        from code_puppy.terminal_utils import reset_windows_terminal_full

        reset_windows_terminal_full()
        emit_info(f"Use {get_cancel_agent_display_name()} to cancel the agent task.")

    original_handler = None
    key_listener_stop_event: Optional[threading.Event] = None
    key_listener_thread: Optional[threading.Thread] = None

    run_success = False
    run_error: Optional[BaseException] = None
    run_response_text = ""

    try:
        if cancel_agent_uses_signal():
            original_handler = signal.signal(signal.SIGINT, keyboard_interrupt_handler)
        else:
            original_handler = signal.signal(signal.SIGINT, graceful_sigint_handler)
            key_listener_stop_event = threading.Event()
            key_listener_thread = _key_listeners.spawn_key_listener(
                key_listener_stop_event,
                on_escape=lambda: None,  # Ctrl+X handled by command_runner
                on_cancel_agent=schedule_agent_cancel,
            )

        result = await agent_task
        run_success = True
        run_response_text = _extract_response_text(result)
        return result
    except asyncio.CancelledError:
        run_response_text = ""
        agent_task.cancel()
    except KeyboardInterrupt:
        run_response_text = ""
        if not agent_task.done():
            agent_task.cancel()
    except Exception as e:
        run_error = e
        raise
    finally:
        try:
            await on_agent_run_end(
                agent_name=agent.name,
                model_name=agent.get_model_name(),
                session_id=group_id,
                success=run_success,
                error=run_error,
                response_text=run_response_text,
                metadata={"model": agent.get_model_name()},
            )
        except Exception:
            pass

        if key_listener_stop_event is not None:
            key_listener_stop_event.set()
        if key_listener_thread is not None:
            key_listener_thread.join(timeout=1.0)
        if original_handler is not None:  # SIG_DFL is 0/falsy — explicit check!
            signal.signal(signal.SIGINT, original_handler)
