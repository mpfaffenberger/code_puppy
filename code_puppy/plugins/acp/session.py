"""``ACPSession`` — one client thread bound to one Code Puppy agent.

Each ACP session id maps to a single ``BaseAgent`` instance whose
``_message_history`` persists across ``session/prompt`` calls, giving native
multi-turn conversations. The session also carries the ``cwd`` the client
opened the thread in, so tools resolve paths relative to the right project.

Cancellation (``session/cancel``) is real: the prompt runs as an
``asyncio.Task`` we hold a handle to, so a cancel notification cancels that
task. pydantic-ai surfaces the ``CancelledError``, which we translate into the
``cancelled`` stop reason for the in-flight ``session/prompt`` reply.

Each turn also reports token usage (mapped from the pydantic-ai run result)
back on the ``PromptResponse`` so the client can show cost/usage.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Optional

from acp.schema import Usage

from code_puppy.plugins.acp import commands, content, persistence, state

if TYPE_CHECKING:
    from code_puppy.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ACP stop reasons a ``session/prompt`` may resolve to.
STOP_END_TURN = "end_turn"
STOP_CANCELLED = "cancelled"
STOP_REFUSAL = "refusal"


@dataclass
class PromptResult:
    """Outcome of one turn: an ACP stop reason plus optional token usage."""

    stop_reason: str
    usage: Optional[Usage] = None


class ACPSession:
    """State + run lifecycle for a single client agent thread."""

    def __init__(
        self,
        session_id: str,
        agent: "BaseAgent",
        cwd: Optional[str] = None,
        additional_directories: Optional[List[str]] = None,
        mcp_specs: Optional[List[Any]] = None,
    ) -> None:
        self.session_id = session_id
        self.agent = agent
        self.cwd = cwd
        self.additional_directories = list(additional_directories or [])
        # Raw client-injected ACP MCP specs, retained so they can be re-attached
        # if the session's agent is rebuilt (e.g. on ``session/set_mode``).
        self.mcp_specs = list(mcp_specs or [])
        # Set while a ``session/prompt`` is in flight so ``cancel`` has a task
        # to cancel. ``None`` means idle.
        self._task: Optional["asyncio.Task[Any]"] = None

    async def prompt(self, blocks: List[Any]) -> PromptResult:
        """Run the agent on a user turn and return the stop reason + usage.

        Flow:
          1. Flatten ACP content blocks into the user text.
          2. Point the messaging session context + run context at this session
             so streamed deltas and tool calls are tagged/correlated.
          3. Run ``agent.run_with_mcp(text)`` as a cancellable task — history
             stays on the agent instance, so the next turn continues.
          4. If nothing streamed (streaming disabled/empty), send the final
             result text as one ``agent_message_chunk`` so the client sees it.
        """
        from code_puppy.messaging import set_session_context

        parsed = content.parse_prompt(blocks)
        text = parsed.text
        if not text.strip() and not parsed.attachments and not parsed.link_attachments:
            return PromptResult(STOP_END_TURN)
        # A leading /slash command is executed by Code Puppy's command handler
        # (not the model), with its output forwarded to the client. If the
        # handler expands the command into a prompt (a string result, e.g. a
        # markdown/custom command), we fall through and run the model on it,
        # exactly as cli_runner does with a string command result.
        if (
            not parsed.attachments
            and not parsed.link_attachments
            and commands.is_command(text)
        ):
            expanded = await commands.run(self.session_id, text)
            if not expanded:
                return PromptResult(STOP_END_TURN)
            text = expanded
        # Resolve this session's relative paths against its own cwd -- WITHOUT
        # a process-global os.chdir (which would corrupt the SDK's own I/O,
        # subprocesses, and any concurrent session). The ContextVar is copied
        # into the run task + its tool threads.
        from code_puppy.tools.common import (
            reset_working_directory,
            set_working_directory,
        )

        cwd_token = set_working_directory(self.cwd) if self.cwd else None

        set_session_context(self.session_id)
        state.begin_run(self.session_id)
        result: Any = None
        error: Optional[BaseException] = None
        try:
            self._task = asyncio.ensure_future(
                self.agent.run_with_mcp(
                    text,
                    attachments=parsed.attachments or None,
                    link_attachments=parsed.link_attachments or None,
                )
            )
            result = await self._task
            self._absorb_history(result)
            stop_reason = STOP_END_TURN
        except asyncio.CancelledError:
            # Two ways we land here:
            #  * our own session/cancel cancelled the inner run task -> it is
            #    cancelled and we report ``cancelled``.
            #  * THIS prompt coroutine was cancelled (e.g. SDK connection
            #    teardown) while the inner task is still live -> cancel it so it
            #    can't outlive us, then propagate the cancellation rather than
            #    silently reporting a normal ``cancelled`` turn.
            task = self._task
            if task is not None and not task.cancelled():
                task.cancel()
                raise
            stop_reason = STOP_CANCELLED
        except Exception as exc:  # noqa: BLE001
            logger.exception("ACP: agent run failed")
            error = exc
            stop_reason = STOP_REFUSAL
        finally:
            streamed = state.streamed_text()
            self._task = None
            state.end_run()
            set_session_context(None)
            if cwd_token is not None:
                reset_working_directory(cwd_token)

        # Persist off the event loop so pickling a large history can't stall
        # other sessions' streaming. Best-effort; never fails the turn. (Skipped
        # on the propagate-cancellation path above, which re-raises before here.)
        try:
            await asyncio.to_thread(
                persistence.save,
                self.session_id,
                self.agent,
                self.cwd,
                self.additional_directories,
            )
        except Exception:  # noqa: BLE001
            logger.debug("ACP: async persist failed", exc_info=True)

        if stop_reason == STOP_END_TURN and not streamed and result is not None:
            await self._send_final_result(result)
        elif stop_reason == STOP_REFUSAL:
            await self._send_error_notice(error)
        return PromptResult(stop_reason, _to_acp_usage(result))

    def _absorb_history(self, result: Any) -> None:
        """Fold a completed run's full message list back into the agent.

        ``run_with_mcp`` (the shared runtime) does NOT write the turn's
        request+response back onto ``agent._message_history`` on the normal
        path -- the caller must, exactly as ``cli_runner`` does after each
        interactive turn. Without this the agent forgets every turn the moment
        it ends: the next prompt runs with empty history, and persistence saves
        a history containing only the user's prompt (no assistant reply). So we
        replace the agent's history with ``result.all_messages()`` here, which
        is what makes ACP multi-turn memory *and* load/resume replay real.
        """
        if result is None:
            return
        try:
            messages = result.all_messages()
        except Exception:  # noqa: BLE001
            return
        if messages:
            self.agent.set_message_history(list(messages))

    def cancel(self) -> None:
        """Cancel the in-flight run, if any. No-op when idle.

        Besides cancelling the asyncio task, force-kill any local shell
        processes the run spawned so they don't orphan. (Shells delegated to
        the client run client-side and are unaffected.)
        """
        task = self._task
        if task is not None and not task.done():
            task.cancel()
        try:
            from code_puppy.tools.command_runner import (
                kill_all_running_shell_processes,
            )

            kill_all_running_shell_processes()
        except Exception:  # noqa: BLE001
            logger.debug("ACP: shell kill on cancel failed", exc_info=True)

    async def _send_error_notice(self, error: Optional[BaseException]) -> None:
        """Tell the client a turn failed, so it isn't a silent empty response.

        A ``refusal`` stop reason alone renders as nothing in most clients; a
        short message chunk makes the failure visible without leaking a stack
        trace (the full traceback is logged to stderr).
        """
        from acp.helpers import update_agent_message_text

        connection = state.get_connection()
        if connection is None:
            return
        detail = f": {error}" if error else "."
        try:
            await connection.session_update(
                self.session_id,
                update_agent_message_text(f"\u26a0\ufe0f The agent run failed{detail}"),
            )
        except Exception:  # noqa: BLE001
            logger.debug("ACP: failed to send error notice", exc_info=True)

    async def _send_final_result(self, result: Any) -> None:
        """Emit the run's final text when nothing streamed during the turn."""
        from acp.helpers import update_agent_message_text

        final_text = self._extract_result_text(result)
        if not final_text:
            return
        connection = state.get_connection()
        if connection is None:
            return
        try:
            await connection.session_update(
                self.session_id, update_agent_message_text(final_text)
            )
        except Exception:  # noqa: BLE001
            logger.exception("ACP: failed to send final result")

    @staticmethod
    def _extract_result_text(result: Any) -> str:
        """Pull display text out of a pydantic-ai run result.

        Mirrors ``_runtime``'s output extraction: prefer ``output``, then the
        legacy ``data`` attribute, then ``str()``.
        """
        for attr in ("output", "data"):
            value = getattr(result, attr, None)
            if value:
                return str(value)
        return str(result) if result else ""


def _to_acp_usage(result: Any) -> Optional[Usage]:
    """Map a pydantic-ai run result's usage onto ACP's ``Usage`` model.

    Field names have drifted across pydantic-ai versions, so each ACP field is
    resolved from a list of candidate attributes. Returns ``None`` when no
    usage is available so we simply omit it from the response.
    """
    if result is None:
        return None
    try:
        usage = result.usage()
    except Exception:  # noqa: BLE001
        return None
    if usage is None:
        return None

    def pick(*names: str) -> Optional[int]:
        for name in names:
            value = getattr(usage, name, None)
            if value is not None:
                return int(value)
        return None

    return Usage(
        input_tokens=pick("input_tokens", "request_tokens", "prompt_tokens"),
        output_tokens=pick("output_tokens", "response_tokens", "completion_tokens"),
        total_tokens=pick("total_tokens"),
        cached_read_tokens=pick("cache_read_tokens", "cached_read_tokens"),
        cached_write_tokens=pick("cache_write_tokens", "cached_write_tokens"),
        thought_tokens=pick("thinking_tokens", "thought_tokens", "reasoning_tokens"),
    )
