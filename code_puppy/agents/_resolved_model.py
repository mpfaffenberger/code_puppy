"""Model delivery as a first-class pydantic-ai capability.

Both agent construction paths (``agents/_builder.py`` and
``tools/subagent_invocation.py``) used to hand their fully resolved
pydantic-ai model to the ``Agent(model=...)`` constructor kwarg.
:class:`ResolvedModel` moves that delivery onto the dedicated ``get_model()``
capability seam instead, so the model travels with the rest of the agent's
capabilities.

The *resolution* logic is deliberately untouched:
``_builder.load_model_with_fallback`` still owns requested-model loading, the
global-model/any-configured-model fallback chain, and the per-conversation
warning dedup, and ``subagent_invocation`` still resolves pins and explicit
overrides before calling it. This capability only owns the last mile: handing
the resolved ``Model`` instance to pydantic-ai.

Parity notes (pydantic-ai 2.31.0):

* **Static contribution, resolved once per run.** A non-callable
  ``get_model()`` return is used directly as the run's model
  (``Agent._evaluate_model_contribution``), exactly as the agent-slot model
  was. No selector semantics are introduced; ``_check_dynamic_model_resume``
  is a no-op for static contributions.
* **``run(model=...)`` and ``Agent.override(model=...)`` stay
  authoritative.** Both set ``model_is_explicit``, which short-circuits
  capability contribution evaluation entirely -- the same precedence the
  old constructor kwarg had. Pinned by tests.
* **Enter/exit lifecycle is preserved.** ``Agent.__aenter__`` enters a
  static capability model's context exactly as it entered the agent-slot
  model, so provider HTTP clients are opened and closed identically.
* **One observable divergence:** the built agent's ``.model`` property now
  reads ``None`` -- the model no longer occupies the agent slot. No
  code_puppy call site reads it (everything goes through
  ``BaseAgent.cur_model``, which ``build_pydantic_agent`` still sets).
  One *plugin* reader exists: wiggum's ``_resolve_judges`` probes
  ``get_pydantic_agent().model.model_name`` for its default-judge fallback
  and now takes its own next fallback, ``BaseAgent.get_model_name()`` --
  the configured model name, which is what judge configs resolve against
  anyway. Pinned by a regression test so the trade-off stays visible.

``get_serialization_name()`` returns ``None``: the capability holds a live,
provider-configured ``Model`` instance (HTTP clients and all), so it is
deliberately not spec-constructible -- the same precedent as
``SteerInjection`` and ``HistoryCompaction``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import Model


@dataclass
class ResolvedModel(AbstractCapability[Any]):
    """Deliver an already-resolved pydantic-ai ``Model`` via ``get_model()``.

    ``model`` is the final ``Model`` instance -- callers finish all
    resolution (fallback chain, pins, explicit overrides) before
    constructing this capability.
    """

    model: Model

    def get_model(self) -> Model:
        return self.model

    @classmethod
    def get_serialization_name(cls) -> Optional[str]:
        # Holds a live Model instance; opt out of spec-based construction.
        return None
