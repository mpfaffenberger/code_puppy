"""Sub-agent session persistence as a first-class pydantic-ai capability.

Previously the sub-agent invocation layer persisted sessions eagerly around
the run: a success-path ``_save_session_history`` call after rendering and
usage capture, plus ``_save_partial_session`` calls in the ``except
BaseException`` block for crashes and interruptions. That worked, but the
persistence contract ("the transcript survives however the run ends") lived
as scattered call sites instead of riding the run itself.

:class:`SubagentSessionPersistence` moves the contract onto pydantic-ai's
``wrap_run`` seam -- the documented home for cancellation-safe cleanup: the
handler task delivers run failures *and* ``CancelledError`` into the wrapping
coroutine, so one ``try``/``except`` owns every exit path of the run proper.

* **Success** -- the full transcript from ``result.all_messages()`` is saved
  at the run boundary (byte-identical payload to the old post-render save).
* **Failure / cancellation** -- the partial progress checkpointed on
  ``agent_config._message_history`` by the history processor is saved via
  the same ``_save_partial_session`` helper the eager path used.

The invocation layer keeps all messaging (interrupt warnings, resume hints,
breadcrumbs) and reads this capability's custody records via
:meth:`SubagentSessionPersistence.recorded_save` after the run unwinds. The
eager save calls are demoted to a fallback for exits the run boundary never
sees -- failures before/after the run itself (agent build, MCP autostart,
rendering) -- mirroring the explicit-when-ours / fallback-for-guests split
used by earlier capability conversions.

Bounded divergences from the eager implementation (all documented in tests):

* Transient failures that ``streaming_retry`` goes on to retry now checkpoint
  partial progress at each failed attempt (the eager path saved only when the
  failure escaped every retry). The final file state converges; intermediate
  saves are atomic overwrites of the same session file.
* The success save now happens inside the run boundary, before high-mode
  fallback rendering and usage capture (the eager save ran after both). For
  ``invoke_agent_with_model`` callers this folds one atomic local file write
  into ``duration_ms``.
* A crash between a successful run and the invocation layer's bookkeeping
  used to overwrite the session with the (possibly older) live checkpoint;
  the run-boundary save now stands, so the persisted transcript keeps the
  final response.

Save helpers are resolved through ``code_puppy.tools.subagent_invocation`` at
call time so test patches on that module's attributes keep intercepting the
writes, exactly as they did for the eager calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, WrapRunHandler
from pydantic_ai.run import AgentRunResult


@dataclass
class SubagentSessionPersistence(AbstractCapability[Any]):
    """Persist one sub-agent invocation's session at the run boundary.

    Constructed per invocation (the sub-agent's pydantic agent is itself
    per-invocation), so instance state is naturally run-scoped: the default
    ``for_run`` returns ``self`` and the custody records written by
    ``wrap_run`` are readable on the very instance the invocation layer
    holds. One instance may see several ``wrap_run`` calls when
    ``streaming_retry`` re-invokes the run; the latest attempt's record wins,
    which is exactly what the post-run reader needs.
    """

    agent_config: Any
    session_id: str
    agent_name: str
    baseline_count: int
    initial_prompt: Optional[str]

    # Custody records, read by the invocation layer after the run unwinds.
    final_saved: bool = field(default=False, init=False)
    final_saved_count: Optional[int] = field(default=None, init=False)
    partial_save_attempted: bool = field(default=False, init=False)
    partial_saved_count: Optional[int] = field(default=None, init=False)

    async def wrap_run(
        self,
        ctx: RunContext[Any],
        *,
        handler: WrapRunHandler,
    ) -> AgentRunResult[Any]:
        try:
            result = await handler()
        except BaseException as error:
            # Everything the run can die of funnels through here, including
            # CancelledError (the seam's documented cleanup contract). The
            # save is synchronous, so it is safe mid-cancellation.
            if self._should_record(error):
                self.record_partial_save()
            raise
        self._save_final(result)
        return result

    @staticmethod
    def _should_record(error: BaseException) -> bool:
        """Mirror the invocation layer's save triage exactly.

        Crashes (``Exception``) and interruptions (``KeyboardInterrupt``,
        ``CancelledError`` -- possibly nested in a ``BaseExceptionGroup``
        from async teardown) persist progress. Other ``BaseException``s
        (``SystemExit``, ``GeneratorExit``) pass through untouched, just as
        the eager ``except`` block re-raised them without saving.
        """
        from code_puppy.tools import subagent_invocation as _invocation

        if isinstance(error, (Exception, KeyboardInterrupt)):
            return True
        return _invocation._contains_cancellation(error)

    def record_partial_save(self) -> None:
        """Persist pre-exit progress off the live history checkpoint.

        Delegates to the invocation module's ``_save_partial_session`` --
        the exact helper the eager path called -- which never raises and
        returns the saved message count (or ``None`` when nothing new was
        persisted). ``partial_save_attempted`` flips regardless so the
        invocation layer's fallback does not double-save.
        """
        from code_puppy.tools import subagent_invocation as _invocation

        self.partial_save_attempted = True
        self.partial_saved_count = _invocation._save_partial_session(
            agent_config=self.agent_config,
            session_id=self.session_id,
            agent_name=self.agent_name,
            baseline_count=self.baseline_count,
            initial_prompt=self.initial_prompt,
        )

    def _save_final(self, result: AgentRunResult[Any]) -> None:
        """Save the complete transcript produced by a successful run.

        A save failure here propagates: the eager path likewise turned a
        failed post-run save into a failed invocation (the parent gets an
        error output, and the fallback partial save still runs).
        """
        from code_puppy.tools import subagent_invocation as _invocation

        history = list(result.all_messages())
        _invocation._save_session_history(
            session_id=self.session_id,
            message_history=history,
            agent_name=self.agent_name,
            initial_prompt=self.initial_prompt,
        )
        self.final_saved = True
        self.final_saved_count = len(history)

    def recorded_save(self) -> Tuple[bool, Optional[int]]:
        """Return ``(handled, saved_count)`` for the invocation layer.

        ``handled`` is ``True`` when the run boundary already persisted the
        session (fully or partially); the caller must then skip its eager
        fallback -- re-saving would overwrite a complete transcript with the
        possibly older live checkpoint. ``saved_count`` feeds the user-facing
        "N message(s) saved" messaging and may be ``None`` when the boundary
        ran but had nothing new to persist.
        """
        if self.final_saved:
            return True, self.final_saved_count
        if self.partial_save_attempted:
            return True, self.partial_saved_count
        return False, None

    @classmethod
    def get_serialization_name(cls) -> str | None:
        # Carries live references (the BaseAgent config wrapper); not
        # spec-constructible.
        return None


__all__ = ["SubagentSessionPersistence"]
