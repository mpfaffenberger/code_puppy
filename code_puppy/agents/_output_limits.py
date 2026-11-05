"""Harness output-limit capabilities: bound oversized payloads at the source.

Finishes the compaction migration started in ``_compaction.py``. The
hand-rolled ``filter_huge_messages`` pass (shrink/drop >50k-token messages
inside the history processor) is replaced by two pure pydantic-ai-harness
capabilities:

* ``ToolOutputLimits`` -- reduces an oversized tool return when it is
  produced (``after_tool_execute``), so it never enters history at all. The
  default band spills the full payload to a private file -- losslessly
  readable back through the harness ``read_tool_result`` tool -- and falls
  back to a bounded truncation when the store write fails.
* ``ClampOversizedMessages`` -- head/tail-clamps a runaway model-response
  part (degenerate generation, giant tool-call args) at request time
  (``before_model_request``). Clamping keeps the message intact where the
  old filter dropped it outright.

Neither capability touches user prompts, and tool errors (``ModelRetry``)
bypass reduction entirely, so recovery payloads stay intact.

Transitional note: a >50k-token tool return already sitting in a *restored
legacy session's* recent tail is no longer shrunk (that was the old filter's
job). New sessions cannot produce one -- ``ToolOutputLimits`` bounds every
tool return at production time.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import List

from pydantic_ai_harness.compaction import ClampOversizedMessages
from pydantic_ai_harness.tool_output_limits import (
    Band,
    LocalFileStore,
    Spill,
    ToolOutputLimits,
    Truncate,
)

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition

from code_puppy.agents._code_mode import _sandbox_tool
from code_puppy.agents._code_mode_guidance import RUN_CODE_TOOL_NAME
from code_puppy.config import (
    CONFIG_DIR,
    get_speculative_code_mode_enabled,
    get_tool_output_limit_chars,
)

# Same per-part budget the old filter_huge_messages enforced per message.
CLAMP_MAX_PART_TOKENS = 50_000

# Spilled payloads live under the config dir (runtime state never sits in the
# project tree) and expire after a week -- long enough to cover a resumed
# session, short enough that the directory cannot grow without bound.
SPILL_DIR_NAME = "tool_output_spill"
SPILL_TTL = timedelta(days=7)


def reaches_the_model(ctx: RunContext[object], tool_def: ToolDefinition) -> bool:
    """Whether a tool's return lands in the model's context, under code mode.

    Sandboxed tools are only reachable from inside ``run_code``, where their
    results are Python values the snippet slices and filters. Spilling them
    there hands the code a handle string instead of the dict it asked for, and
    costs a ``read_tool_result`` round trip. Bound what the model actually
    sees instead: ``run_code``'s own return and the native tools.
    """
    return tool_def.name == RUN_CODE_TOOL_NAME or not _sandbox_tool(ctx, tool_def)


def build_tool_output_limits() -> List[ToolOutputLimits]:
    """Build the production-time tool-return reducer, or ``[]`` when disabled.

    The threshold comes from the ``tool_output_limit_chars`` config key
    (default 10,000 chars; zero or negative disables). With code mode on,
    only returns that reach the model are bounded (see
    :func:`reaches_the_model`). Returned as a list so
    the caller can splice it into ``capabilities=[...]`` unconditionally.
    """
    threshold = get_tool_output_limit_chars()
    if threshold <= 0:
        return []
    store = LocalFileStore(
        base_dir=Path(CONFIG_DIR) / SPILL_DIR_NAME,
        cleanup_after=SPILL_TTL,
    )
    return [
        ToolOutputLimits(
            bands=[Band(over=threshold, action=Spill(then=Truncate()))],
            store=store,
            tool_filter=reaches_the_model
            if get_speculative_code_mode_enabled()
            else "all",
        )
    ]


def build_response_clamp() -> ClampOversizedMessages:
    """Build the request-time clamp for runaway model-response parts."""
    return ClampOversizedMessages(max_part_tokens=CLAMP_MAX_PART_TOKENS)
