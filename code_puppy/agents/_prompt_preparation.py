"""First-turn user-prompt preparation as a pydantic-ai capability.

Some model families (claude-code OAuth being the canonical example) cannot
receive code_puppy's real system prompt through the ``instructions`` channel:
the provider expects a fixed instruction string, so the actual system prompt
is folded into the *user* message of the conversation's first turn instead.
Historically ``_runtime._should_prepend_system_prompt`` baked that fold into
the prompt string before ``pydantic_agent.run()`` ever saw it.

This module promotes that delivery to a first-class
:class:`~pydantic_ai.capabilities.AbstractCapability`:

* :func:`build_prompt_observation` computes the prepared form **once per
  turn, at the exact call site the old code used** — so
  ``prepare_prompt_for_model`` (and every plugin hook behind it) fires with
  identical arguments, identical timing, and an identical call count.
* :class:`PromptPreparation` swaps ``raw -> prepared`` on the conversation's
  first user message at the ``before_model_request`` seam (send side) and
  mirrors the same swap into the recorded history at the ``after_run`` seam
  (persist side), so bytes at rest match the old baked-in behaviour.
* Callers install a :class:`PromptObservation` around their run(s) via
  :func:`observe_prompt_preparation`; the capability resolves it through a
  ``ContextVar``, so concurrent / nested runs (sub-agents, side queries)
  each see their own observation. No observation, or an inactive one, makes
  the capability a strict no-op.

Why both a send-side swap *and* a persist-side mirror? pydantic-ai records
the run's user prompt from the ``run()`` argument, not from the (possibly
transformed) request messages. Keeping the argument raw and swapping at
request time preserves model-visible bytes on every path — including
streaming-retry re-entries that resume from checkpointed history — while the
mirror restores byte-identical *stored* history whenever core takes custody
of run state (run end, cancellation checkpoint, partial-session save).

Ordering matters: the swap must run **before** history compaction so the
compactor sees the folded first message exactly as it did when the fold was
baked into the prompt. Both construction sites list ``PromptPreparation``
ahead of their ``ProcessHistory`` capabilities for that reason.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any, Iterator, List, Optional, Sequence

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

__all__ = [
    "PromptObservation",
    "PromptPreparation",
    "build_prompt_observation",
    "observe_prompt_preparation",
]


@dataclass
class PromptObservation:
    """One turn's ``raw -> prepared`` user-prompt substitution.

    ``active`` is False when there is nothing to do — either the turn did not
    qualify for preparation (non-empty history / resumed session) or the
    prepared form came back identical to the raw prompt (no plugin claimed
    the model). An inactive observation makes every operation a no-op, so
    call sites can install one unconditionally.
    """

    raw: str = ""
    prepared: str = ""
    active: bool = False

    @classmethod
    def inactive(cls) -> "PromptObservation":
        return cls()

    def __post_init__(self) -> None:
        # Identity swaps are inert; deactivate so the request path can
        # short-circuit without comparing content on every model request.
        if self.active and self.raw == self.prepared:
            self.active = False

    # ---- send side ---------------------------------------------------------

    def apply_to_request(self, messages: List[ModelMessage]) -> List[ModelMessage]:
        """Return ``messages`` with the first user message swapped to ``prepared``.

        Only the conversation's FIRST message is eligible (positionally —
        mirroring the old behaviour, which only ever folded the prompt when
        history was empty), and only when its user content still matches
        ``raw`` — so an already-swapped history, a compacted summary, or a
        later message that merely repeats the same text are all left alone.

        Fresh copies are returned; the input messages are never mutated. The
        recorded run state keeps the raw prompt until :meth:`mirror` runs at
        a custody boundary.
        """
        if not self.active or not messages:
            return messages
        first = messages[0]
        swapped = self._swapped_request(first)
        if swapped is None:
            return messages
        return [swapped, *messages[1:]]

    def _swapped_request(self, message: ModelMessage) -> Optional[ModelRequest]:
        if not isinstance(message, ModelRequest):
            return None
        new_parts: List[Any] = []
        changed = False
        for part in message.parts:
            new_content = None if changed else self._prepared_content(part)
            if new_content is not None:
                new_parts.append(replace(part, content=new_content))
                changed = True
            else:
                new_parts.append(part)
        if not changed:
            return None
        return replace(message, parts=new_parts)

    def _prepared_content(self, part: Any) -> Any:
        """Return ``part``'s content with ``raw`` swapped for ``prepared``, or None."""
        if not isinstance(part, UserPromptPart):
            return None
        content = part.content
        if isinstance(content, str):
            return self.prepared if content == self.raw else None
        if isinstance(content, Sequence):
            # Attachment payloads arrive as [prompt_str, *binary/link parts];
            # the old code folded the system prompt into that leading string.
            for i, item in enumerate(content):
                if isinstance(item, str):
                    if item == self.raw:
                        updated = list(content)
                        updated[i] = self.prepared
                        return updated
                    return None
        return None

    # ---- persist side ------------------------------------------------------

    def mirror(self, messages: Optional[Sequence[ModelMessage]]) -> None:
        """Rewrite the stored first user message to ``prepared``, in place.

        Called wherever core takes custody of run state (run end via
        ``after_run``, cancellation checkpoints, partial-session saves) so
        history at rest is byte-identical to the old baked-in prompt.
        Idempotent: once the content no longer matches ``raw`` it is left
        untouched. Mutates part content in place so every alias of the
        stored messages (``result.all_messages()``, ``agent._message_history``,
        session saves) observes the swap.
        """
        if not self.active or not messages:
            return
        first = messages[0]
        if not isinstance(first, ModelRequest):
            return
        for part in first.parts:
            new_content = self._prepared_content(part)
            if new_content is not None:
                part.content = new_content
                return


_prompt_observation: ContextVar[Optional[PromptObservation]] = ContextVar(
    "code_puppy_prompt_observation", default=None
)


def current_prompt_observation() -> Optional[PromptObservation]:
    """Return the observation installed for the current context, if any."""
    return _prompt_observation.get()


@contextmanager
def observe_prompt_preparation(observation: PromptObservation) -> Iterator[None]:
    """Install ``observation`` for the enclosed block (and tasks created in it).

    ``asyncio.create_task`` snapshots the context, so wrapping the task
    creation is enough for the run body to resolve the observation even
    after the ``with`` block exits. Nested installs (sub-agent invocations)
    shadow the outer observation for their own tasks only.
    """
    token = _prompt_observation.set(observation)
    try:
        yield
    finally:
        _prompt_observation.reset(token)


def build_prompt_observation(agent: Any, prompt: str) -> tuple[PromptObservation, str]:
    """Compute the first-turn prompt fold for ``agent`` (main-agent path).

    Returns ``(observation, prompt_to_run)``. Byte-for-byte replica of the
    old ``_should_prepend_system_prompt``: only a turn starting with an
    empty message history qualifies, and the prepared form is produced by
    ``prepare_prompt_for_model`` with the full system prompt + puppy rules.
    When the turn does not qualify the hooks are NOT fired at all —
    preserving the old call count exactly.

    ``prompt_to_run`` is normally the raw prompt (the capability performs
    the swap at request time). The one degenerate exception is an EMPTY raw
    prompt: payload building drops empty prompts, so there is no user part
    for the capability to anchor on — the fold is baked eagerly instead,
    exactly as the old code did.
    """
    if agent._message_history:
        return PromptObservation.inactive(), prompt

    from code_puppy.agents._builder import load_puppy_rules
    from code_puppy.model_utils import prepare_prompt_for_model

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
    if not prompt:
        return PromptObservation.inactive(), prepared.user_prompt
    return (
        PromptObservation(raw=prompt, prepared=prepared.user_prompt, active=True),
        prompt,
    )


@dataclass
class PromptPreparation(AbstractCapability[Any]):
    """Deliver the first-turn user-prompt fold through capability seams.

    Stateless: per-turn state lives in the installed
    :class:`PromptObservation`, resolved via ``ContextVar`` on every seam
    call. With no (or an inactive) observation the capability is inert, so
    it can sit unconditionally in every ``capabilities=[...]`` list.
    """

    async def before_model_request(self, ctx: Any, request_context: Any) -> Any:
        observation = current_prompt_observation()
        if observation is not None:
            request_context.messages = observation.apply_to_request(
                request_context.messages
            )
        return request_context

    async def after_run(self, ctx: Any, *, result: Any) -> Any:
        observation = current_prompt_observation()
        if observation is not None:
            observation.mirror(result.all_messages())
        return result

    @classmethod
    def get_serialization_name(cls) -> Optional[str]:
        return None  # Not spec-serializable (state rides a ContextVar).
