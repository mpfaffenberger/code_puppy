"""Code Puppy's per-model tuning as a first-class pydantic-ai capability.

:func:`code_puppy.model_factory.make_model_settings` assembles the per-model
``ModelSettings`` payload: the auto-derived ``max_tokens`` budget, GPT-5
reasoning effort/verbosity, Anthropic extended-thinking, GLM ``extra_body``
riders, Copilot API translation, and the yolo-mode ``parallel_tool_calls``
gate. Historically that payload rode in on the ``Agent(model_settings=...)``
constructor kwarg; :class:`PerModelSettings` promotes it to the
``get_model_settings`` capability seam so it lives in the same
``capabilities=[...]`` block as the rest of the agent's behavior.

Feature-parity notes:

* **Identical merged payload.** pydantic-ai layers settings agent ->
  capability -> run on top of the model's own base settings
  (``_layer_model_settings``). Nothing else contributes capability-level
  settings, so moving ours from the agent slot to the capability slot
  produces a byte-identical merge result on the wire.
* **Identical snapshot timing.** The constructor kwarg froze settings at
  agent-build time. A capability's ``get_model_settings`` is re-extracted on
  every run (``for_run`` re-resolution), which would silently pick up config
  edits mid-session. ``__post_init__`` therefore computes the payload once,
  and the seam returns that snapshot -- config changes keep applying on
  agent rebuild, exactly as before.
* **List position is inert.** ``get_model_settings`` is a configuration
  seam, not a request hook, so ordering relative to the history processors
  and clamps in the capabilities block does not matter.

The inherited :meth:`~pydantic_ai.capabilities.AbstractCapability.get_serialization_name`
default is deliberately kept: the only fields are plain data
(``model_name``/``max_tokens``), so the capability stays spec-constructible;
a spec-built instance recomputes its snapshot from the same config the
constructor path reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings

from code_puppy.model_factory import make_model_settings


@dataclass
class PerModelSettings(AbstractCapability[Any]):
    """Supply Code Puppy's per-model ``ModelSettings`` via the capability seam.

    Wraps :func:`code_puppy.model_factory.make_model_settings`; see the module
    docstring for the parity contract.
    """

    model_name: str
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        # Snapshot at construction: parity with the old constructor-kwarg
        # path, where settings were computed once per agent build. Stored as
        # a plain attribute (not a dataclass field) so __init__/repr/eq keep
        # describing the capability by its inputs, not its derived payload.
        self._settings: ModelSettings = make_model_settings(
            self.model_name, self.max_tokens
        )

    def get_model_settings(self) -> ModelSettings:
        return self._settings
