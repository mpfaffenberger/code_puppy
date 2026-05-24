"""Token usage calculation for the current agent's context window.

Kept separate from ``register_callbacks.py`` so this stays unit-testable in
isolation and so callbacks file remains thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Thresholds (fractions of context window). Match the visual indicator buckets:
#   <30% green, 30–<65% yellow, ≥65% red.
# Boundaries are exclusive on the upper end: e.g. exactly 0.30 → yellow,
# exactly 0.65 → red. Keep ``_format_usage_report`` legend in sync.
GREEN_THRESHOLD = 0.30
YELLOW_THRESHOLD = 0.65

GREEN_CIRCLE = "🟢"
YELLOW_CIRCLE = "🟡"
RED_CIRCLE = "🔴"


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
# Overhead breakdown
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OverheadBreakdown:
    """Per-bucket overhead estimate, all already multiplier-adjusted."""

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
    """Compute per-bucket overhead in tokens for the active agent.

    Each bucket is estimated independently and the per-model multiplier is
    applied to each, so the sum may differ from a single combined estimate
    by a token or two (floor rounding). That's fine — these numbers are
    advisory.
    """
    from code_puppy.agents._builder import load_puppy_rules
    from code_puppy.agents._history import (
        _apply_multiplier,
        _estimate_mcp_tool_tokens,
        estimate_context_overhead,
        estimate_tokens,
    )

    model_name = agent.get_model_name()

    # System prompt (resolved for the active model).
    try:
        resolved = _resolved_system_prompt(agent)
        system_tokens = _apply_multiplier(estimate_tokens(resolved), model_name)
    except Exception:
        system_tokens = 0

    # AGENTS.md / puppy rules — separate bucket so users can see how much of
    # their context budget is being eaten by project rules. Note that the
    # core ``_estimate_context_overhead`` currently *omits* this; the badge
    # was under-reporting before. We fix that here by adding it explicitly.
    try:
        rules = load_puppy_rules() or ""
        agents_md_tokens = (
            _apply_multiplier(estimate_tokens(rules), model_name) if rules else 0
        )
    except Exception:
        agents_md_tokens = 0

    # Pydantic-registered tools.
    try:
        tools = _agent_tools(agent)
        pydantic_tools_tokens = (
            estimate_context_overhead("", tools, model_name, mcp_servers=None)
            if tools
            else 0
        )
    except Exception:
        pydantic_tools_tokens = 0

    # MCP toolsets — fetch a LIVE server list rather than trusting
    # ``agent._mcp_servers`` (which is only refreshed at pydantic-agent build
    # time, so bind/unbind/start/stop after that would otherwise show stale
    # numbers in ``/context``). Falls back to the cached list if the live
    # lookup blows up for any reason.
    try:
        mcp_servers = _live_mcp_servers_for(agent)
        mcp_raw = _estimate_mcp_tool_tokens(mcp_servers) if mcp_servers else 0
        mcp_tokens = _apply_multiplier(mcp_raw, model_name) if mcp_raw else 0
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
    history/used/overhead/capacity. We deliberately do **not** fall back to
    zero on partial failures: a misleading 🟢 indicator is worse than no
    indicator at all (the prompt simply hides the badge).
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
        used = sum(agent.estimate_tokens_for_message(m) for m in history)
        # We still call the canonical overhead estimator first so any
        # exception bubbles up the same way it did before — preserves the
        # "all-or-nothing" semantics the badge relies on.
        overhead = agent._estimate_context_overhead()
        capacity = agent._get_model_context_length()
    except Exception:
        return None

    if capacity <= 0:
        return None

    # Breakdown is best-effort: if it explodes we still want to show the
    # aggregate. Fall back to a zero-filled breakdown in that case.
    try:
        breakdown = compute_overhead_breakdown(agent)
    except Exception:
        breakdown = OverheadBreakdown(0, 0, 0, 0)

    # Prefer the breakdown total when it's available and non-zero, because
    # it also accounts for AGENTS.md (which the legacy estimator omits).
    final_overhead = breakdown.total if breakdown.total else int(overhead)

    return ContextUsage(
        used_tokens=int(used),
        overhead_tokens=final_overhead,
        capacity=int(capacity),
        system_prompt_tokens=breakdown.system_prompt_tokens,
        agents_md_tokens=breakdown.agents_md_tokens,
        pydantic_tools_tokens=breakdown.pydantic_tools_tokens,
        mcp_tokens=breakdown.mcp_tokens,
    )
