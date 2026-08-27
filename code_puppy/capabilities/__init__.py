"""Pure pydantic-ai capabilities staged for upstreaming.

Every module in this package is written for extraction into
``pydantic-ai-harness`` and MUST NOT import anything from ``code_puppy``.

The decoupling contract (see the 2026-08-27 capability events lifecycle
hook coverage audit):

* App-specific state and policy are injected through small protocols and
  constructor callables — never imported.
* App-facing side effects (rendering, spinners, plugin hooks, telemetry)
  are communicated exclusively through typed ``CapabilityEvent`` families
  (pydantic-ai #7794). The application subscribes with ``@on_event``
  listeners (see ``code_puppy.events.bridge``) or its event stream
  handler; capabilities never call back into the application.
* Decision points are inline-dispatched events (``dispatch='inline'``)
  that listeners may cancel before the operation commits. Everything
  else is observe-only stream dispatch.

CI enforces the import boundary via ``tests/capabilities/test_purity.py``.
"""

from code_puppy.capabilities.compaction import (
    BeforeCompactionEvent,
    CompactionCompletedEvent,
    CompactionFailedEvent,
    CompactionStore,
    ContextUsageMeasuredEvent,
    HistoryCompaction,
    HistoryProcessingCompletedEvent,
    HistoryProcessingStartedEvent,
)

__all__ = [
    "BeforeCompactionEvent",
    "CompactionCompletedEvent",
    "CompactionFailedEvent",
    "CompactionStore",
    "ContextUsageMeasuredEvent",
    "HistoryCompaction",
    "HistoryProcessingCompletedEvent",
    "HistoryProcessingStartedEvent",
]
