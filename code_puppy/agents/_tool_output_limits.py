"""Oversized tool returns — delegated to pydantic-ai-harness.

An oversized tool return persists in message history and is re-sent on every
later model request, paying its token cost for the rest of the run. The
``ToolOutputLimits`` capability from ``pydantic_ai_harness.tool_output_limits``
intercepts a return when it is produced and reduces it ONCE, so the reduced
form is what persists.

The default band is ``Spill(then=Truncate())``: the full payload is written to
a private overflow store and the model gets a handle plus a bounded preview.
Spilled payloads are read back on demand through the capability's own
``read_tool_result(handle, offset, limit, from_end, pattern)`` tool — lossless,
unlike a history-time clamp. When the store write fails, the return is
truncated instead; never a silent drop.

What lives here is the Code Puppy-specific glue:

  * the threshold comes from ``puppy.cfg`` (``tool_output_limit_chars``,
    ``/set``-able, 0 disables the capability entirely);
  * spilled payloads land under ``~/.code_puppy/tool_output_overflow/`` (the
    config dir, per the runtime-state convention) instead of the harness's
    shared temp-dir default, with an age-based TTL so the directory does not
    grow forever.

History-time protection (``_history.filter_huge_messages``) stays: it defends
against oversized messages that predate this capability — resumed sessions,
histories imported from other tools — which production-time reduction can
never see.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Optional

from pydantic_ai_harness.tool_output_limits import (
    Band,
    LocalFileStore,
    Spill,
    ToolOutputLimits,
    Truncate,
)

from code_puppy.config import CONFIG_DIR, get_tool_output_limit_chars

# Subdirectory of CONFIG_DIR that holds spilled payloads. Deliberately under
# ~/.code_puppy so runtime state stays out of project working trees.
OVERFLOW_DIR_NAME = "tool_output_overflow"

# Spilled files older than this are pruned (best-effort, off the hot path) on
# the next write. Long enough to outlive any plausible session resume; short
# enough that the directory cannot grow without bound.
SPILL_TTL = timedelta(days=7)


def build_tool_output_limits() -> Optional[ToolOutputLimits]:
    """Config → ``ToolOutputLimits`` wiring, or ``None`` when disabled.

    Called per agent build (each pydantic agent gets its own capability
    instance); the overflow store root is stable across instances, so a
    ``read_tool_result`` handle minted by one build resolves in the next.
    """
    threshold = get_tool_output_limit_chars()
    if threshold <= 0:
        return None
    return ToolOutputLimits(
        bands=[Band(over=threshold, action=Spill(then=Truncate()))],
        store=LocalFileStore(
            base_dir=Path(CONFIG_DIR) / OVERFLOW_DIR_NAME,
            cleanup_after=SPILL_TTL,
        ),
    )
