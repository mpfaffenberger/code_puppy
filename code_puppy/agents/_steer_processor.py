"""History processor that injects queued steering messages into agent runs.

When the user presses Ctrl+T and submits a steering message, the message
lands in ``PauseController``'s steer queue. This processor — wired into the
agent's ``history_processors`` list AFTER compaction — drains the queue on
every model call and appends pending steers as user messages right before
the model sees them.

Effect: the model sees the steer as if the user had naturally followed up
with a new message, on the next model invocation within the same
``agent.run()``. No cancellation, no lost work, mid-turn pivots Just Work.

Why a history processor (and not the runtime's between-turns while-loop)?
Because ``agent.run()`` is atomic across a multi-tool-call turn — it doesn't
return until the model decides it's done. The old between-turns approach
left steers stuck in the queue for the entire duration of a long turn.
``history_processors`` fire before EVERY model call (including between
tool calls within one turn), so the steer lands at the next safe boundary.
"""

from __future__ import annotations

from typing import Any, Callable, List

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from code_puppy.messaging import emit_info
from code_puppy.messaging.pause_controller import get_pause_controller


def make_steer_history_processor(agent: Any) -> Callable[..., List[ModelMessage]]:
    """Build a history processor that injects queued steers as user messages.

    Returns a closure suitable for pydantic-ai's ``history_processors`` list.
    Wire it AFTER compaction so steers don't get compacted away on the same
    call.
    """

    def steer_history_processor(messages: List[ModelMessage]) -> List[ModelMessage]:
        # Drain ONLY ``now``-mode steers. ``queue``-mode steers are owned
        # by ``_runtime._do_run``'s between-turns loop; draining both here
        # would double-inject them.
        pending = get_pause_controller().drain_pending_steer_now()
        if not pending:
            return messages

        # Build one user message per steer (so each shows up as a discrete
        # turn in the model's view of the conversation — clearer than
        # concatenating them).
        injected: List[ModelMessage] = []
        for steer_text in pending:
            preview = steer_text[:80] + ("..." if len(steer_text) > 80 else "")
            emit_info(f"🎯 Injecting steer mid-turn — model will see: {preview!r}")
            injected.append(ModelRequest(parts=[UserPromptPart(content=steer_text)]))

        # Append AFTER the existing messages. pydantic-ai passes this list
        # to the model on this exact call, so the model's very next response
        # will answer the steer.
        new_messages = list(messages) + injected

        # Mirror into agent._message_history so the steer persists across
        # the turn boundary (matches how the compaction processor mutates
        # the field directly).
        if hasattr(agent, "_message_history"):
            agent._message_history = list(agent._message_history) + injected

        return new_messages

    return steer_history_processor


__all__ = ["make_steer_history_processor"]
