"""Steer-injection capability: land queued mid-turn steers as durable user messages.

When the user presses Ctrl+T and submits a steering message, the message
lands in ``PauseController``'s steer queue. ``SteerInjection`` — registered
in ``_builder.py`` AFTER compaction — drains the queue before every model
request and appends pending steers as user messages right before the model
sees them.

Effect: the model sees the steer as if the user had naturally followed up
with a new message, on the next model invocation within the same
``agent.run()``. No cancellation, no lost work, mid-turn pivots Just Work.

Why ``before_model_request`` (and not the runtime's between-turns
while-loop)? Because ``agent.run()`` is atomic across a multi-tool-call
turn — it doesn't return until the model decides it's done. The old
between-turns approach left steers stuck in the queue for the entire
duration of a long turn. ``before_model_request`` fires before EVERY model
call (including between tool calls within one turn), so the steer lands at
the next safe boundary. This is the exact seam ``ProcessHistory`` uses, so
registration order against the compaction capability is preserved: wire
this capability AFTER compaction so a fresh steer can't be compacted away
on the same call.

Unlike ephemeral tail-injection (e.g. harness ``SystemReminders``), steers
are REAL user messages and must be durable: they are appended to the
per-request message list AND mirrored into the caller's message history so
they persist across the turn boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import RunContext

from code_puppy.command_line.attachments import resolve_steer_content
from code_puppy.messaging import emit_info
from code_puppy.messaging.pause_controller import get_pause_controller


def _drain_now_steers() -> List[str]:
    """Default drain: ONLY ``now``-mode steers from the global controller.

    The between-turns loop in ``_runtime._do_run`` owns ``queue``-mode
    ones — draining both here would double-inject.
    """
    return get_pause_controller().drain_pending_steer_now()


@dataclass
class SteerInjection(AbstractCapability[Any]):
    """Inject queued steering messages as durable user messages mid-run.

    Drains pending steers on every model request and appends each as a
    discrete ``ModelRequest`` carrying the in-effect instructions, so the
    very next model response answers the steer.

    ```python
    agent = PydanticAgent(
        ...,
        capabilities=[
            ProcessHistory(compaction),  # compaction FIRST
            SteerInjection(mirror=mirror),  # steers must survive compaction
        ],
    )
    ```
    """

    drain: Optional[Callable[[], List[str]]] = None
    """Source of pending steer texts. ``None`` uses the global
    ``PauseController``'s ``now``-mode queue."""

    mirror: Optional[Callable[[List[ModelMessage]], None]] = None
    """Called with the injected messages so the host can persist them into
    its durable message history (steers must survive the turn boundary).
    ``None`` skips mirroring."""

    async def before_model_request(
        self,
        ctx: RunContext[Any],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        """Append pending steers to the outbound request, mirroring them out."""
        pending = (self.drain or _drain_now_steers)()
        if not pending:
            return request_context

        messages = request_context.messages

        # CRITICAL: carry the in-effect instructions onto the injected request.
        # pydantic-ai resolves the system prompt from the MOST RECENT
        # ModelRequest; ``instructions=None`` silently drops it — most models
        # get one amnesiac turn, claude-code OAuth models hard-fail (the
        # endpoint fingerprints the "You are Claude Code..." prompt and
        # stealth-rejects as fake ``overloaded_error``s).
        last_instructions = next(
            (
                m.instructions
                for m in reversed(messages)
                if isinstance(m, ModelRequest) and m.instructions is not None
            ),
            None,
        )

        # One user message per steer (each shows as a discrete turn — clearer
        # than concatenating). Attachments resolve just like the main prompt
        # path, so steering with a pasted screenshot Just Works.
        injected: List[ModelMessage] = []
        for steer_text in pending:
            content, preview_text = resolve_steer_content(steer_text)
            n_extras = len(content) - 1 if isinstance(content, list) else 0
            suffix = f" (+{n_extras} attachment(s))" if n_extras else ""
            preview = preview_text[:80] + ("..." if len(preview_text) > 80 else "")
            emit_info(f"Injecting steer mid-turn — model will see: {preview!r}{suffix}")
            injected.append(
                ModelRequest(
                    parts=[UserPromptPart(content=content)],
                    instructions=last_instructions,
                )
            )

        # Append AFTER existing messages; pydantic-ai sends them on this
        # exact request, so the very next response answers the steer.
        request_context.messages = list(messages) + injected

        # Mirror out so the steer persists across the turn boundary (matches
        # the compaction processor's direct history mutation).
        if self.mirror is not None:
            self.mirror(injected)

        return request_context

    @classmethod
    def get_serialization_name(cls) -> Optional[str]:
        """Not spec-serializable: seams take arbitrary callables."""
        return None


def build_steer_injection(agent: Any) -> SteerInjection:
    """Build the steer-injection capability wired to ``agent``'s history.

    The mirror writes injected steers into ``agent._message_history`` so
    they survive the turn boundary; agents without that attribute (bare
    mocks, probes) get injection without persistence.
    """

    def mirror(injected: List[ModelMessage]) -> None:
        if hasattr(agent, "_message_history"):
            agent._message_history = list(agent._message_history) + injected

    return SteerInjection(mirror=mirror)


__all__ = ["SteerInjection", "build_steer_injection"]
