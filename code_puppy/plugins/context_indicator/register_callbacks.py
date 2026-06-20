"""Register callbacks for the ``context_indicator`` plugin.

Hooks:

* ``startup`` — wraps ``get_prompt_with_active_model`` to inject a colored
  circle (🟢/🟡/🔴) reflecting current context-window usage.
* ``custom_command`` / ``custom_command_help`` — exposes ``/context`` for a
  detailed token-usage breakdown.

Idempotent: re-installing the prompt patch is a no-op.
"""

from __future__ import annotations

from typing import List, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.plugins.context_indicator.usage import (
    ContextUsage,
    get_current_usage,
)

_COMMAND_NAME = "context"
_PATCH_ATTR = "_context_indicator_original"


# ---------------------------------------------------------------------------
# Messaging helpers (lazy-imported to dodge circular imports at boot)
# ---------------------------------------------------------------------------
def _emit_info(message: str) -> None:
    from code_puppy.messaging import emit_info

    emit_info(message)


def _emit_system_message(message: str) -> None:
    from code_puppy.messaging import emit_system_message

    emit_system_message(message)


def _emit_error(message: str) -> None:
    from code_puppy.messaging import emit_error

    emit_error(message)


# ---------------------------------------------------------------------------
# Prompt patching
# ---------------------------------------------------------------------------
def _build_indicator_tuple(usage: ContextUsage) -> Tuple[str, str]:
    """Build the (style, text) tuple that gets inserted into the prompt."""
    return ("class:context-indicator", f"{usage.indicator} ")


def _inject_indicator(formatted_text):
    """Return a new ``FormattedText`` with the usage indicator prepended.

    Placed after the Mist symbol and before the configured agent name so the colored
    circle reads as a status badge for the prompt as a whole.
    """
    from prompt_toolkit.formatted_text import FormattedText

    usage = get_current_usage()
    if usage is None:
        return formatted_text

    try:
        parts = list(formatted_text)
        # Insert after the leading "🫧 " tuple (index 0) so the badge sits
        # right next to the puppy. Fall back to prepend if shape changed.
        insert_at = 1 if parts else 0
        parts.insert(insert_at, _build_indicator_tuple(usage))
        return FormattedText(parts)
    except Exception:
        return formatted_text


def _install_prompt_patch() -> None:
    """Monkey-patch ``get_prompt_with_active_model`` once."""
    from code_puppy.command_line import prompt_toolkit_completion as ptc

    if getattr(ptc, _PATCH_ATTR, None) is not None:
        return  # Already patched

    original = ptc.get_prompt_with_active_model
    setattr(ptc, _PATCH_ATTR, original)

    def patched(base: str = ">>> "):
        result = original(base)
        return _inject_indicator(result)

    ptc.get_prompt_with_active_model = patched


_LEGEND_TEXT = (
    "Context indicator: 🟢 <30%   🟡 30–<65%   🔴 ≥65%  "
    "(use /context for a detailed breakdown)"
)


def _announce_legend() -> None:
    try:
        _emit_system_message(_LEGEND_TEXT)
    except Exception:
        # Never crash startup over a banner line — fail gracefully per plugin rules.
        pass


def _on_startup() -> None:
    try:
        _install_prompt_patch()
    except Exception as exc:
        _emit_error(f"context_indicator: failed to install prompt patch — {exc}")
    _announce_legend()


# ---------------------------------------------------------------------------
# /context slash command
# ---------------------------------------------------------------------------
def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            _COMMAND_NAME,
            "Show context-window usage (tokens used vs. model capacity)",
        )
    ]


# Bar glyphs — kept as module constants so the legend stays DRY.
_BAR_GLYPH_OVERHEAD = "▒"  # system prompt + tool schema baseline
_BAR_GLYPH_MESSAGES = "█"  # conversation tokens
_BAR_GLYPH_EMPTY = "░"  # unused capacity
_BAR_GLYPH_THRESHOLD = "┃"  # vertical marker for compaction trigger
_BAR_WIDTH = 30


def _render_usage_bar(usage: ContextUsage, threshold: float) -> str:
    """Render the ASCII usage bar with three zones + a compaction marker.

    Zones: overhead | messages | empty. The compaction-threshold marker
    overwrites whichever cell it lands on (cosmetic; the underlying token
    counts are unchanged).
    """
    capacity = max(1, usage.capacity)
    overhead_cells = min(
        _BAR_WIDTH, int(round(usage.overhead_tokens / capacity * _BAR_WIDTH))
    )
    total_cells = min(
        _BAR_WIDTH, int(round(usage.total_tokens / capacity * _BAR_WIDTH))
    )
    # Guarantee messages cells start strictly after overhead cells.
    message_cells = max(0, total_cells - overhead_cells)
    empty_cells = _BAR_WIDTH - overhead_cells - message_cells

    cells = (
        [_BAR_GLYPH_OVERHEAD] * overhead_cells
        + [_BAR_GLYPH_MESSAGES] * message_cells
        + [_BAR_GLYPH_EMPTY] * empty_cells
    )

    threshold_clamped = max(0.0, min(1.0, threshold))
    marker_idx = min(_BAR_WIDTH - 1, int(round(threshold_clamped * _BAR_WIDTH)))
    cells[marker_idx] = _BAR_GLYPH_THRESHOLD
    return "".join(cells)


def _get_compaction_threshold() -> float:
    """Fetch compaction threshold defensively; fall back to 0.85 on any error."""
    try:
        from code_puppy.config import get_compaction_threshold

        return float(get_compaction_threshold())
    except Exception:
        return 0.85


def _format_overhead_breakdown(usage: ContextUsage) -> str:
    """Render the per-bucket overhead breakdown.

    Each non-zero bucket gets its own indented line. Zero-valued buckets are
    hidden so users with no MCP servers / no AGENTS.md aren't staring at
    noise.  We *always* show the aggregate ``Overhead`` line so the report
    structure stays consistent.
    """
    # (label, token_count) — order matters for readability.
    rows = (
        ("System prompt", usage.system_prompt_tokens),
        ("AGENTS.md     ", usage.agents_md_tokens),
        ("Kennel memory", usage.kennel_memory_tokens),
        ("Pydantic tools", usage.pydantic_tools_tokens),
        ("MCP toolsets  ", usage.mcp_tokens),
    )
    lines = [
        f"    └─ {label}: {tokens:,} tokens" for label, tokens in rows if tokens > 0
    ]
    return "\n".join(lines)


def _format_usage_report(usage: ContextUsage) -> str:
    threshold = _get_compaction_threshold()
    bar = _render_usage_bar(usage, threshold)
    legend = (
        f"  Legend   : {_BAR_GLYPH_OVERHEAD} overhead  "
        f"{_BAR_GLYPH_MESSAGES} messages  "
        f"{_BAR_GLYPH_EMPTY} free  "
        f"{_BAR_GLYPH_THRESHOLD} compaction @ {threshold:.0%}"
    )
    breakdown = _format_overhead_breakdown(usage)
    breakdown_block = f"\n{breakdown}" if breakdown else ""
    return (
        f"{usage.indicator} Context usage: {usage.percent:.1f}%\n"
        f"  [{bar}]\n"
        f"{legend}\n"
        f"  Messages : {usage.used_tokens:,} tokens\n"
        f"  Overhead : {usage.overhead_tokens:,} tokens (system prompt + AGENTS.md + kennel memory + tools + MCP)"
        f"{breakdown_block}\n"
        f"  Total    : {usage.total_tokens:,} / {usage.capacity:,} tokens\n"
        f"  Buckets  : 🟢 <30%   🟡 30–65%   🔴 ≥65%"
    )


def _handle_context_command(command: str) -> bool:
    usage = get_current_usage()
    if usage is None:
        _emit_info("🫧 No context info yet — load an agent and send a message first.")
        return True
    _emit_info(_format_usage_report(usage))
    return True


def _handle_custom_command(command: str, name: str):
    if name != _COMMAND_NAME:
        return None
    return _handle_context_command(command)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
register_callback("startup", _on_startup)
register_callback("custom_command", _handle_custom_command)
register_callback("custom_command_help", _custom_help)


__all__ = [
    "_announce_legend",
    "_build_indicator_tuple",
    "_custom_help",
    "_format_overhead_breakdown",
    "_format_usage_report",
    "_handle_context_command",
    "_handle_custom_command",
    "_inject_indicator",
    "_install_prompt_patch",
    "_on_startup",
]
