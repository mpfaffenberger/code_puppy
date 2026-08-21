"""Interrupted-sub-agent notes as a first-class pydantic-ai capability.

Ctrl+C cancels both a delegated sub-agent task and the parent run, and the
parent's return-less ``invoke_agent`` tool call is pruned from history as a
dangling call -- so without help the model would have no memory that it ever
delegated. ``subagent_invocation`` records each interrupted session; this
module surfaces those records to the model as one plain user-message note per
session (the same injection shape the steer processor uses).

Previously ``_run_signals.inject_interrupted_subagent_notes`` appended the
notes to ``agent._message_history`` eagerly at run start. Now the notes ride
a :class:`InterruptedSubagentNotes` capability on pydantic-ai's
``before_model_request`` seam:

* :func:`build_interrupt_note_observation` runs at the exact old call site
  (run start, never nested) and keeps the old drain + ``emit_info`` timing
  byte-identical. It packages the notes into a per-turn
  :class:`InterruptNoteObservation` instead of mutating history.
* :class:`InterruptedSubagentNotes` (stateless, shared across turns) resolves
  the observation from a ``ContextVar`` installed around the run task and
  splices the notes into the outbound messages immediately before the turn's
  own user request -- the exact position the eager append produced. Returned
  ``before_model_request`` messages feed the run's state, so the notes
  persist into ``result.all_messages()`` (verified against pydantic-ai
  2.31.0) and every later request of the turn.
* At injection time the notes are also mirrored into
  ``agent._message_history`` (the steer-processor pattern) so a
  ``streaming_retry`` re-entry -- which re-seeds from that list -- keeps
  them. :func:`mirror_uninjected` is the custody-boundary fallback: if the
  turn dies before any model request fired, the runtime's ``finally`` mirrors
  the notes so they surface on the *next* turn, exactly like a note the old
  eager path had baked but the model never got to read.

Bounded divergences (all documented, none model-visible in practice):

* The ``model_select`` hook fires before any model request, so it now sees
  the pre-note history. The notes are a few short user messages; nothing in
  tree routes models off them.
* A *nested* ``run_with_mcp`` run (a plugin starting a run inside the outer
  run's task) inherits the ambient observation but never matches the outer
  turn's prompt anchor, so it cannot steal the injection; the notes wait for
  the outer run's own first request. Should that request never come, the
  custody fallback applies.
* Sub-agents built by ``subagent_invocation`` deliberately do NOT get this
  capability: the notes belong to the main conversation, and injecting them
  into a sub-agent's transcript (while mirroring into the main agent's
  history) would be wrong on both ends.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterator, List, Optional

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import RunContext

from code_puppy.messaging import emit_info


@dataclass
class InterruptNoteObservation:
    """Per-turn state: the notes awaiting injection and how to persist them.

    Built once per (non-nested) ``run_with_mcp`` turn when interrupted
    sub-agent records exist. ``mirror`` appends messages to the owning
    agent's ``_message_history`` -- injectable so tests can observe custody
    without a full ``BaseAgent``.
    """

    notes: List[ModelRequest]
    mirror: Callable[[List[ModelMessage]], None]
    # The turn's ``run()`` prompt payload (str or [prompt, *attachments]),
    # set by the runtime once the payload is built. Anchors the splice: the
    # notes go immediately before the ModelRequest carrying this content.
    turn_prompt: Any = None
    injected: bool = field(default=False)


_note_observation: ContextVar[Optional[InterruptNoteObservation]] = ContextVar(
    "interrupt_note_observation", default=None
)


def current_observation() -> Optional[InterruptNoteObservation]:
    """Return the ambient observation for this turn, if any."""
    return _note_observation.get()


@contextmanager
def install_interrupt_note_observation(
    observation: Optional[InterruptNoteObservation],
) -> Iterator[None]:
    """Install ``observation`` for the enclosed block (``None`` is a no-op).

    Wrap the ``create_task`` call so the run task's context snapshot carries
    the observation (the #835/#839 pattern); nested installs shadow.
    """
    if observation is None:
        yield
        return
    token = _note_observation.set(observation)
    try:
        yield
    finally:
        _note_observation.reset(token)


def build_interrupt_note_observation(
    agent: Any,
) -> Optional[InterruptNoteObservation]:
    """Drain interrupted-sub-agent records into a per-turn observation.

    Runs at the exact old ``inject_interrupted_subagent_notes`` call site
    (run start, never nested), preserving its behaviour byte-for-byte:

    * an agent without ``_message_history`` leaves the records queued;
    * each record becomes one plain user-message note (same text, same
      ``emit_info``);
    * no records -> ``None`` (the capability stays inert for the turn).
    """
    from code_puppy.tools.subagent_invocation import drain_interrupted_subagents

    if not hasattr(agent, "_message_history"):
        return None
    records = drain_interrupted_subagents()
    if not records:
        return None

    notes: List[ModelRequest] = []
    for rec in records:
        session_id = rec["session_id"]
        saved = rec["saved_count"]
        saved_phrase = (
            f"{saved} message(s) of its work were saved"
            if saved is not None
            else "no completed messages had been produced yet"
        )
        note = (
            f"[system note] The sub-agent '{rec['agent_name']}' you invoked was "
            f"interrupted by the user before it finished; {saved_phrase}. Its "
            f"partial session is saved as '{session_id}'."
        )
        notes.append(ModelRequest(parts=[UserPromptPart(content=note)]))
        emit_info(
            f"Noting interrupted sub-agent '{rec['agent_name']}' "
            f"(session {session_id}) for the agent's next turn."
        )

    def _mirror(messages: List[ModelMessage]) -> None:
        agent._message_history = list(agent._message_history) + list(messages)

    return InterruptNoteObservation(notes=notes, mirror=_mirror)


def mirror_uninjected(observation: Optional[InterruptNoteObservation]) -> None:
    """Custody-boundary fallback: persist notes that never reached a request.

    Called from the run task's ``finally`` (before the interrupted-tool-call
    prune, mirroring the runtime's existing boundary order). If the turn
    ended -- cancel, crash, or a model that was never reached -- without the
    capability firing, append the notes to history so they surface on the
    next turn instead of vanishing with the drained records. Idempotent via
    the ``injected`` flag.
    """
    if observation is None or observation.injected:
        return
    observation.injected = True
    observation.mirror(observation.notes)


def _is_turn_request(message: ModelMessage, turn_prompt: Any) -> bool:
    """Whether ``message`` is the ModelRequest carrying this turn's prompt."""
    if not isinstance(message, ModelRequest):
        return False
    return any(
        isinstance(part, UserPromptPart) and part.content == turn_prompt
        for part in message.parts
    )


@dataclass
class InterruptedSubagentNotes(AbstractCapability[Any]):
    """Splice this turn's interrupted-sub-agent notes into the model request.

    Stateless: all per-turn state lives on the ambient
    :class:`InterruptNoteObservation`. Wire it before the compaction
    ``ProcessHistory`` so compaction sees the notes exactly as it saw the old
    eager append.
    """

    async def before_model_request(
        self,
        ctx: RunContext[Any],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        observation = _note_observation.get()
        if observation is None or observation.injected:
            return request_context

        messages = request_context.messages
        if messages and _is_turn_request(messages[-1], observation.turn_prompt):
            # Normal turn: notes sit immediately before the new user request,
            # the exact position the old eager history-append produced.
            new_messages = (
                list(messages[:-1]) + list(observation.notes) + [messages[-1]]
            )
        elif not observation.turn_prompt:
            # Degenerate empty-prompt turn: no user request to anchor on; the
            # old path appended the notes at the end of history, so do the same.
            new_messages = list(messages) + list(observation.notes)
        else:
            # Not this turn's request (e.g. a nested run that inherited the
            # ambient observation). Leave the notes for the outer run's own
            # first request; the custody fallback covers the never-fires case.
            return request_context

        observation.injected = True
        # Mirror now (steer-processor pattern) so a streaming_retry re-entry,
        # which re-seeds from ``agent._message_history``, keeps the notes.
        observation.mirror(observation.notes)
        return replace(request_context, messages=new_messages)

    def get_serialization_name(self) -> Optional[str]:
        # Not spec-constructible: useless without the runtime-installed
        # observation (SteerInjection/HistoryCompaction precedent).
        return None


__all__ = [
    "InterruptNoteObservation",
    "InterruptedSubagentNotes",
    "build_interrupt_note_observation",
    "current_observation",
    "install_interrupt_note_observation",
    "mirror_uninjected",
]
