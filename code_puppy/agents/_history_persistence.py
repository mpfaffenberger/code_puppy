"""Success-path conversation-history custody as a pydantic-ai capability.

After each successful ``Agent.run()`` on the MAIN conversation path, the
durable history on the owning :class:`~code_puppy.agents.base_agent.BaseAgent`
must absorb ``result.all_messages()`` — the complete run transcript including
the trailing final response, which never passes through a
``before_model_request`` hook (there is no subsequent request to carry it).

Historically that writeback was duplicated across seven eager call sites:

- ``_run_signals.prepare_queued_steer_injection`` (persist-before-steer side
  effect, only when a queued steer was pending),
- ``_runtime._do_run``'s hook-retry branch (persist before the follow-up run),
- four turn-end sites in ``cli_runner`` (initial command, interactive turn,
  continuation loop, headless run).

:class:`HistoryPersistence` promotes the feature onto pydantic-ai's
``after_run`` capability seam: the write happens exactly once per successful
run, at the moment the run commits its result — with the *identical*
``AgentRunResult`` object the caller receives (``after_run`` contract,
verified empirically on pydantic-ai 2.31.0). The eager sites are demoted to
the :func:`persist_result_history` guest fallback, which steps aside when the
capability already persisted that exact result (identity gate) and otherwise
performs the old write verbatim — so wrappers that bypass capabilities keep
byte-identical behavior.

Scope: MAIN construction site only (``_builder.build_pydantic_agent``).
Sub-agent invocations own their history through session persistence and the
result-scoped bookkeeping in ``tools/subagent_invocation.py``; they get no
``HistoryPersistence`` (pinned by test).

Concurrency note: the capability's default ``for_run`` returns ``self``, so
one instance observes every run of its agent. The main conversation loop is
strictly sequential (one turn at a time), so the single ``_last_persisted``
slot cannot race.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic_ai.capabilities import AbstractCapability

__all__ = ["HistoryPersistence", "persist_result_history"]


def _write_history(agent: Any, result: Any) -> None:
    """Replace ``agent``'s durable history with ``result.all_messages()``.

    Uses the public ``set_message_history`` setter when the agent exposes one
    (the cli_runner sites' spelling); falls back to the direct attribute
    assignment the runtime sites used. Both are plain assignments on
    ``BaseAgent`` — this just preserves each call site's exact semantics for
    test doubles.
    """
    messages = list(result.all_messages())
    setter = getattr(agent, "set_message_history", None)
    if callable(setter):
        setter(messages)
    else:
        agent._message_history = messages


@dataclass
class HistoryPersistence(AbstractCapability[Any]):
    """Persist each successful run's ``all_messages()`` into durable history.

    Holds a live reference to the owning ``BaseAgent``-shaped config, so it is
    deliberately not spec-constructible (``get_serialization_name() -> None``).
    """

    agent: Any
    _last_persisted: Optional[Any] = field(default=None, init=False, repr=False)

    def get_serialization_name(self) -> Optional[str]:
        # Live agent reference — never constructible from a serialized spec.
        return None

    async def after_run(self, ctx: Any, *, result: Any) -> Any:
        # ``after_run`` fires once per successful ``Agent.run()`` with the
        # identical result object the caller receives; it is NOT called when
        # the run ends without a result, so cancelled/crashed runs keep their
        # existing checkpoint/prune custody untouched.
        if hasattr(result, "all_messages"):
            _write_history(self.agent, result)
            self._last_persisted = result
        return result

    def persisted(self, result: Any) -> bool:
        """True when this capability already persisted exactly ``result``.

        Identity-gated (``is``): a different result object — including a new
        run's result — never matches. A stale match is impossible to abuse:
        the same object implies the same messages, and the write is
        idempotent.
        """
        return result is not None and self._last_persisted is result


def persist_result_history(agent: Any, result: Any) -> bool:
    """Persist ``result``'s messages unless the capability already did.

    Shared fallback for the previously-eager call sites. Returns ``True``
    when the history is known to hold ``result.all_messages()`` afterwards
    (either persisted here or already persisted by the capability), ``False``
    when ``result`` carries no messages to persist.
    """
    if result is None or not hasattr(result, "all_messages"):
        return False
    persistence = getattr(agent, "_history_persistence", None)
    if persistence is not None and persistence.persisted(result):
        return True
    _write_history(agent, result)
    return True
