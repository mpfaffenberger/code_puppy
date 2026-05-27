"""Token usage calculation for the current agent's context window.

Kept separate from ``register_callbacks.py`` so this stays unit-testable in
isolation and so callbacks file remains thin.

Design note — *why* we re-implement the token counting locally:

``/context`` is supposed to be a *consistent*, model-agnostic view of how
full the context window is. The core runtime has two layers that make
token counts vary between models:

1. The ``token_ratio_learner`` plugin monkeypatches
   ``_history.estimate_tokens`` to use *learned* chars-per-token ratios
   per model. Great for compaction decisions — terrible for a
   user-facing dashboard, because the same conversation reports
   different token counts on different models.

2. ``_history._apply_multiplier`` bumps some models (e.g. Opus 4.7 by
   1.35×) to compensate for tokenizers that over-tokenize relative to
   our heuristic. Again: useful for safety margins, lousy for
   "consistency between models".

To keep ``/context`` honest and stable across model switches, this
module uses its OWN raw ``max(1, floor(len(text) / 2.5))`` estimator
and applies NO multiplier. Other parts of the system (compaction,
summarization triggers) still use the calibrated values — that's
intentional.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, List, Optional

# Thresholds (fractions of context window). Match the visual indicator buckets:
#   <30% green, 30–<65% yellow, ≥65% red.
# Boundaries are exclusive on the upper end: e.g. exactly 0.30 → yellow,
# exactly 0.65 → red. Keep ``_format_usage_report`` legend in sync.
GREEN_THRESHOLD = 0.30
YELLOW_THRESHOLD = 0.65

GREEN_CIRCLE = "🟢"
YELLOW_CIRCLE = "🟡"
RED_CIRCLE = "🔴"

# Classic char/token heuristic used throughout. Kept here as a private
# constant so /context's numbers don't drift if the core estimator is
# patched at runtime by the token_ratio_learner plugin.
_CHARS_PER_TOKEN = 2.5


@dataclass(frozen=True)
class ContextUsage:
    """Snapshot of how full the current agent's context window is.

    ``overhead_tokens`` is the *sum* of the per-bucket breakdown fields. The
    breakdown fields are optional (default 0) so legacy call sites that only
    care about the aggregate keep working without changes.
    """

    used_tokens: int
    overhead_tokens: int
    capacity: int
    # Optional per-bucket breakdown (sum == overhead_tokens when populated).
    system_prompt_tokens: int = 0
    agents_md_tokens: int = 0
    pydantic_tools_tokens: int = 0
    mcp_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.used_tokens + self.overhead_tokens

    @property
    def proportion(self) -> float:
        if self.capacity <= 0:
            return 0.0
        return self.total_tokens / self.capacity

    @property
    def percent(self) -> float:
        return self.proportion * 100.0

    @property
    def indicator(self) -> str:
        return pick_indicator(self.proportion)


def pick_indicator(proportion: float) -> str:
    """Pick the colored-circle emoji for a given usage proportion (0..1)."""
    if proportion < GREEN_THRESHOLD:
        return GREEN_CIRCLE
    if proportion < YELLOW_THRESHOLD:
        return YELLOW_CIRCLE
    return RED_CIRCLE


# ---------------------------------------------------------------------------
# Raw token estimation (model-agnostic, never patched)
# ---------------------------------------------------------------------------
def _raw_estimate_tokens(text: str) -> int:
    """Pure char/2.5 heuristic. Identical for every model, every time.

    Mirrors the *original* ``_history.estimate_tokens`` before any plugin
    patches it. We deliberately don't import it — the whole point of this
    function is to stay immune to the token_ratio_learner monkeypatch.
    """
    if not text:
        return 0
    return max(1, math.floor(len(text) / _CHARS_PER_TOKEN))


def _raw_tokens_for_message(message: Any) -> int:
    """Sum raw tokens across a message's parts via the canonical stringifier."""
    # ``stringify_part`` is a pure formatter — safe to import directly.
    from code_puppy.agents._history import stringify_part

    total = 0
    for part in getattr(message, "parts", []) or []:
        part_str = stringify_part(part)
        if part_str:
            total += _raw_estimate_tokens(part_str)
    return total


def _raw_tokens_for_pydantic_tools(tools: Optional[dict]) -> int:
    """Estimate tokens contributed by pydantic-ai registered tools.

    Mirrors ``_history.estimate_context_overhead`` but uses the raw
    estimator and skips the model multiplier.
    """
    if not tools:
        return 0
    from code_puppy.agents._history import (
        _extract_tool_description,
        _extract_tool_json_schema,
    )

    total = 0
    for tool_name, tool_obj in tools.items():
        total += _raw_estimate_tokens(tool_name)
        desc = _extract_tool_description(tool_obj)
        if desc:
            total += _raw_estimate_tokens(desc)
        schema = _extract_tool_json_schema(tool_obj)
        if schema is not None:
            try:
                total += _raw_estimate_tokens(json.dumps(schema))
            except (TypeError, ValueError):
                total += _raw_estimate_tokens(repr(schema))
        else:
            annotations = getattr(tool_obj, "__annotations__", None)
            if annotations:
                total += _raw_estimate_tokens(str(annotations))
    return total


def _raw_tokens_for_mcp_servers(mcp_servers: Optional[List[Any]]) -> int:
    """Estimate tokens contributed by MCP toolsets — raw, no multiplier."""
    if not mcp_servers:
        return 0

    total = 0
    for server in mcp_servers:
        cached = getattr(server, "_cached_tools", None)
        if not cached:
            continue
        prefix = getattr(server, "tool_prefix", None) or ""
        for mcp_tool in cached:
            name = getattr(mcp_tool, "name", "") or ""
            full_name = f"{prefix}_{name}" if prefix else name
            if full_name:
                total += _raw_estimate_tokens(full_name)
            description = getattr(mcp_tool, "description", "") or ""
            if description:
                total += _raw_estimate_tokens(description)
            schema = getattr(mcp_tool, "inputSchema", None)
            if schema:
                try:
                    total += _raw_estimate_tokens(json.dumps(schema, sort_keys=True))
                except (TypeError, ValueError):
                    total += _raw_estimate_tokens(repr(schema))
    return total


# ---------------------------------------------------------------------------
# Overhead breakdown
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OverheadBreakdown:
    """Per-bucket overhead estimate. All values are RAW (no multiplier)."""

    system_prompt_tokens: int
    agents_md_tokens: int
    pydantic_tools_tokens: int
    mcp_tokens: int

    @property
    def total(self) -> int:
        return (
            self.system_prompt_tokens
            + self.agents_md_tokens
            + self.pydantic_tools_tokens
            + self.mcp_tokens
        )


def _resolved_system_prompt(agent) -> str:
    """Return the agent's system prompt after model-specific prep.

    Mirrors what ``_estimate_context_overhead`` does, so the bucket counts
    line up with what actually gets shipped to the model.
    """
    system_prompt = agent.get_full_system_prompt()
    try:
        from code_puppy.model_utils import prepare_prompt_for_model

        prepared = prepare_prompt_for_model(
            model_name=agent.get_model_name() or "",
            system_prompt=system_prompt,
            user_prompt="",
            prepend_system_to_user=False,
        )
        return prepared.instructions or system_prompt
    except Exception:
        return system_prompt


def _live_mcp_servers_for(agent):
    """Return the *current* MCP server toolsets bound to ``agent``.

    Bypasses ``agent._mcp_servers`` (set only at pydantic-agent build time)
    so the ``/context`` breakdown reflects the live state after
    ``/mcp bind`` / ``/mcp unbind`` / ``/mcp start`` / ``/mcp stop``.

    Calls the MCP manager directly rather than going through
    ``load_mcp_servers``, which would also kick off autostart side effects —
    we want a read-only view here.  Falls back to the cached list if the
    live lookup blows up.
    """
    try:
        from code_puppy.config import get_value
        from code_puppy.mcp_ import get_mcp_manager

        mcp_disabled = get_value("disable_mcp_servers")
        if mcp_disabled and str(mcp_disabled).lower() in ("1", "true", "yes", "on"):
            return None

        agent_name = getattr(agent, "name", None)
        manager = get_mcp_manager()
        servers = manager.get_servers_for_agent(agent_name=agent_name) or []
        if servers:
            return servers
    except Exception:
        pass
    return getattr(agent, "_mcp_servers", None) or None


def _agent_tools(agent):
    """Best-effort pydantic-tool dict for the agent (or ``None``)."""
    try:
        from code_puppy.agents.base_agent import _extract_pydantic_agent_tools
    except Exception:
        return None

    tools_source = getattr(agent, "pydantic_agent", None)
    if tools_source is None:
        probe_getter = getattr(agent, "_get_tool_probe", None)
        if callable(probe_getter):
            try:
                tools_source = probe_getter()
            except Exception:
                tools_source = None
    if tools_source is None:
        return None
    try:
        return _extract_pydantic_agent_tools(tools_source)
    except Exception:
        return None


def compute_overhead_breakdown(agent) -> OverheadBreakdown:
    """Compute per-bucket overhead in raw tokens for the active agent.

    Each bucket is estimated via the local raw heuristic — no learned
    ratios, no per-model multiplier. This keeps ``/context`` consistent
    when switching between models.
    """
    from code_puppy.agents._builder import load_puppy_rules

    # System prompt (resolved for the active model).
    try:
        resolved = _resolved_system_prompt(agent)
        system_tokens = _raw_estimate_tokens(resolved)
    except Exception:
        system_tokens = 0

    # AGENTS.md / puppy rules — separate bucket so users can see how much of
    # their context budget is being eaten by project rules.
    try:
        rules = load_puppy_rules() or ""
        agents_md_tokens = _raw_estimate_tokens(rules) if rules else 0
    except Exception:
        agents_md_tokens = 0

    # Pydantic-registered tools.
    try:
        pydantic_tools_tokens = _raw_tokens_for_pydantic_tools(_agent_tools(agent))
    except Exception:
        pydantic_tools_tokens = 0

    # MCP toolsets — fetch a LIVE server list rather than trusting
    # ``agent._mcp_servers`` (only refreshed at pydantic-agent build time).
    try:
        mcp_tokens = _raw_tokens_for_mcp_servers(_live_mcp_servers_for(agent))
    except Exception:
        mcp_tokens = 0

    return OverheadBreakdown(
        system_prompt_tokens=int(system_tokens),
        agents_md_tokens=int(agents_md_tokens),
        pydantic_tools_tokens=int(pydantic_tools_tokens),
        mcp_tokens=int(mcp_tokens),
    )


def get_current_usage() -> Optional[ContextUsage]:
    """Compute current context-window usage for the active agent.

    Returns ``None`` whenever any required piece of data is unavailable —
    missing agent, missing model config, or *any* exception while estimating
    history/overhead/capacity. We deliberately do **not** fall back to
    zero on partial failures: a misleading 🟢 indicator is worse than no
    indicator at all (the prompt simply hides the badge).

    All token counts are computed with the raw model-agnostic heuristic
    so the badge stays stable when the user switches models mid-session.
    """
    try:
        from code_puppy.agents.agent_manager import get_current_agent
    except Exception:
        return None

    try:
        agent = get_current_agent()
    except Exception:
        return None
    if agent is None:
        return None

    try:
        history = agent.get_message_history() or []
        used = sum(_raw_tokens_for_message(m) for m in history)
        capacity = agent._get_model_context_length()
    except Exception:
        return None

    if capacity <= 0:
        return None

    try:
        breakdown = compute_overhead_breakdown(agent)
    except Exception:
        return None

    return ContextUsage(
        used_tokens=int(used),
        overhead_tokens=breakdown.total,
        capacity=int(capacity),
        system_prompt_tokens=breakdown.system_prompt_tokens,
        agents_md_tokens=breakdown.agents_md_tokens,
        pydantic_tools_tokens=breakdown.pydantic_tools_tokens,
        mcp_tokens=breakdown.mcp_tokens,
    )
