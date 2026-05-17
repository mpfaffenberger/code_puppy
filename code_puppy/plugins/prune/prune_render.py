"""Pure rendering helpers for the /prune TUI.

All functions here take read-only state and return prompt_toolkit-style
formatted-text tuples. Keeping them out of the menu class keeps the
menu focused on state + key bindings, and makes the renderers easy to
unit-test with hand-built fixtures.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from code_puppy.plugins.prune.prune_model import (
    C_CHECKED,
    C_CURSOR,
    C_DIM,
    C_FOOTER_OK,
    C_FOOTER_WARN,
    C_HEADER,
    C_SHELL,
    C_TOOL,
    ContextBudget,
    MessageEntry,
    Row,
    ToolCallInfo,
)


# ── small atomic helpers ────────────────────────────────────────────────────


def ctx_indicator(entry: MessageEntry) -> Tuple[str, str]:
    """Return (glyph, style) for the in-context indicator."""
    if entry.in_context is True:
        return ("●", C_FOOTER_OK)
    if entry.in_context is False:
        return ("○", C_DIM)
    return ("·", C_DIM)


def tokens_str(entry: MessageEntry) -> str:
    if entry.tokens is None:
        return ""
    return f"~{entry.tokens}t"


def ctx_detail_text(entry: MessageEntry) -> str:
    if entry.in_context is True:
        return "  ·  ● in context"
    if entry.in_context is False:
        return "  ·  ○ out of context"
    return ""


def format_args_full(full_args: dict, fallback: str) -> List[str]:
    """Pretty-print tool args with no truncation, no JSON escaping.

    Recursive YAML-ish layout:
      * Short scalars render inline: ``key: value``
      * Multi-line / long strings render as a block scalar with native
        line breaks (no ``\\n`` escapes), indented under the key.
      * Nested dicts and lists recurse with the same rules so inner
        strings keep their native formatting too.
      * Lists use a leading ``- `` on each item.

    Returns a flat list of lines for the caller to indent/format. Falls
    back to the abbreviated preview if the full args dict isn't usable.
    """
    if not full_args:
        return [fallback or "<no args>"]
    if not isinstance(full_args, dict):
        return [fallback or str(full_args)]

    lines: List[str] = []
    for key, value in full_args.items():
        lines.extend(_format_kv(str(key), value))
    return lines or ["<no args>"]


_INLINE_STR_LIMIT = 60  # short strings render on the same line as the key
_INDENT = "  "


def _is_inline_scalar(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, str) and "\n" not in value and len(value) <= _INLINE_STR_LIMIT:
        return True
    return False


def _format_kv(key: str, value: Any) -> List[str]:
    """Render ``key: value``, recursing for complex values."""
    if _is_inline_scalar(value):
        return [f"{key}: {value}"]

    if isinstance(value, str):
        body = value.splitlines() or [value]
        return [f"{key}: |"] + [f"{_INDENT}{line}" for line in body]

    nested = _format_value_lines(value)
    if not nested:
        return [f"{key}: <empty>"]
    return [f"{key}:"] + [f"{_INDENT}{line}" for line in nested]


def _format_value_lines(value: Any) -> List[str]:
    """Render ``value`` (with no leading key) as a list of lines."""
    if _is_inline_scalar(value):
        return [str(value)]

    if isinstance(value, str):
        body = value.splitlines() or [value]
        return ["|"] + [f"{_INDENT}{line}" for line in body]

    if isinstance(value, dict):
        if not value:
            return ["{}"]
        lines: List[str] = []
        for k, v in value.items():
            lines.extend(_format_kv(str(k), v))
        return lines

    if isinstance(value, list):
        if not value:
            return ["[]"]
        lines = []
        for item in value:
            item_lines = _format_value_lines(item) or [""]
            lines.append(f"- {item_lines[0]}")
            for line in item_lines[1:]:
                lines.append(f"{_INDENT}{line}")
        return lines

    # Fallback for anything weird
    return [str(value)]


def render_budget_line(budget: ContextBudget) -> List[tuple]:
    if not budget.available or budget.context_length is None:
        return [(C_DIM, "context: unavailable\n")]

    total = budget.total_used or 0
    pct = budget.percent_used or 0.0
    if pct < 70:
        style = C_FOOTER_OK
    elif pct < 90:
        style = C_FOOTER_WARN
    else:
        style = C_SHELL

    parts: List[tuple] = [
        (
            style,
            f"context: {total:,}/{budget.context_length:,} tokens ({pct:.0f}%)",
        ),
        (C_DIM, f"   overhead: {budget.overhead_tokens or 0:,}t\n"),
    ]
    if budget.out_of_context_messages > 0:
        # On its own line — these tokens won't fit in this turn's window,
        # and the warning is too long to share a row with the main
        # context counter on most terminal widths. (Messages stay in
        # history; pop or prune newer ones to slide them back in.)
        parts.append(
            (
                C_SHELL,
                f" ↯ {budget.out_of_context_tokens:,}t in "
                f"{budget.out_of_context_messages} older msg(s) out of context\n",
            )
        )
    return parts


def render_legend() -> List[tuple]:
    """One-line legend explaining the context-window indicator glyphs.

    Placed under the budget header so a first-time pruner can map the
    dots they see in the rows to what they mean. Compact on purpose —
    legends that wrap are worse than no legend.

    Note: ``○`` messages are NOT gone — they're still in conversation
    history. They just don't fit in this turn's context window. If newer
    messages are pruned (or compacted), older ``○`` messages slide back
    into the window. The genuinely valuable prune targets for reclaiming
    budget are noisy ``●`` messages.
    """
    return [
        (C_DIM, " legend:  "),
        (C_FOOTER_OK, "● in context"),
        (C_DIM, "   "),
        (C_DIM, "○ out of context"),
        (C_DIM, "   "),
        (C_DIM, "· unknown\n"),
    ]


# ── list pane ───────────────────────────────────────────────────────────────


def render_list(menu: Any) -> List[tuple]:
    """Render the left (history list) pane.

    Reads from the menu: entries, rows, viewport_top, _visible_rows,
    cursor, selected_messages, budget.
    """
    out: List[tuple] = []
    out.append(
        (
            C_HEADER,
            " prune   ↓/↑ move  space toggle  a all  c clear  enter confirm  q quit\n",
        )
    )
    out.append(("", " "))
    out.extend(render_budget_line(menu.budget))
    out.append(("", "\n"))

    page = max(1, menu._visible_rows)
    total = len(menu.rows)
    top = menu.viewport_top
    bottom = min(total, top + page)
    hidden_above = top
    hidden_below = max(0, total - bottom)

    if hidden_above:
        out.append((C_DIM, f"   ↑ {hidden_above} more above\n"))
    else:
        out.append(("", "\n"))

    for idx in range(top, bottom):
        render_row(menu, idx, menu.rows[idx], out)

    if hidden_below:
        out.append((C_DIM, f"   ↓ {hidden_below} more below\n"))
    else:
        out.append(("", "\n"))

    msg_count = len(menu.selected_messages)
    out.append(("", "\n"))
    out.append(
        (
            C_FOOTER_OK,
            f" enter = remove {msg_count} message(s)\n",
        )
    )
    out.extend(render_legend())
    out.append((C_DIM, f" cursor {menu.cursor + 1}/{total}\n"))
    return out


def render_row(menu: Any, idx: int, row: Row, out: List[tuple]) -> None:
    is_cursor = idx == menu.cursor
    cursor_marker = "▶ " if is_cursor else "  "
    cursor_style = C_CURSOR if is_cursor else ""
    checked = menu._row_is_checked(row)

    entry = menu.entries[row.message_idx]

    # Locked rows (sys bundle or history[0]) get a distinct "locked" box
    # so the user can see at a glance that this isn't toggleable.
    if entry.is_locked:
        box, box_style = "[-] ", C_DIM
    elif checked:
        box, box_style = "[x] ", C_CHECKED
    else:
        box, box_style = "[ ] ", C_DIM

    role_short = {
        "system": "sys  ",
        "user": "user ",
        "assistant": "asst ",
        "tool-return": "tool ",
        "unknown": "?    ",
    }.get(entry.role, "?    ")
    row_style = C_CHECKED if checked else entry.role_color
    out.append((cursor_style, cursor_marker))
    out.append((box_style, box))
    ctx_glyph, ctx_style = ctx_indicator(entry)
    out.append((ctx_style, f"{ctx_glyph} "))
    idx_col = f"{entry.history_index:3d}"
    out.append(
        (
            row_style,
            f"{idx_col}  {role_short}  {entry.preview}",
        )
    )
    tok = tokens_str(entry)
    if tok:
        out.append((C_DIM, f"  {tok}"))
    out.append(("", "\n"))


# ── detail pane ─────────────────────────────────────────────────────────────


def render_detail(menu: Any) -> List[tuple]:
    """Render the right (detail) pane for whatever the cursor is on."""
    if not menu.rows:
        return [("", "")]

    row = menu.rows[menu.cursor]
    entry = menu.entries[row.message_idx]
    out: List[tuple] = []
    _render_message_detail(entry, out)

    out.append(("", "\n"))
    if menu._selection_has_side_effects():
        out.append(
            (
                C_SHELL,
                " ⚠  selection includes side-effecting tool calls; "
                "pruning does NOT roll them back\n",
            )
        )
    return out


def _render_message_detail(entry: MessageEntry, out: List[tuple]) -> None:
    out.append((C_HEADER, f" {entry.role}  (message)\n"))
    tok = f" · ~{entry.tokens}t" if entry.tokens is not None else ""
    location = f"history index {entry.history_index}"
    # Surface thinking presence in the metadata line so it's clear at a
    # glance that this assistant turn carried chain-of-thought tokens.
    thinking_note = (
        f"  ·  🧠 {len(entry.thinking_segments)} thinking block(s)"
        if entry.thinking_segments
        else ""
    )
    out.append(
        (
            C_DIM,
            f" {location}  ·  "
            f"{len(entry.tool_calls)} tool call(s){tok}{ctx_detail_text(entry)}"
            f"{thinking_note}\n\n",
        )
    )
    for line in (entry.full_text or "<empty>").splitlines() or [""]:
        out.append(("", f" {line}\n"))

    if entry.tool_calls:
        out.append(("", "\n"))
        out.append((C_HEADER, " tool calls (will go with message):\n"))
        for tc in entry.tool_calls:
            _render_tool_call_block(tc, out)


def _render_tool_call_block(tc: ToolCallInfo, out: List[tuple]) -> None:
    """Inline tool-call block inside a message detail view, full args."""
    out.append((C_TOOL, f"   {tc.icon} {tc.name}"))
    out.append(("", "\n"))
    for line in format_args_full(tc.full_args, tc.args_preview):
        out.append((C_DIM, f"       {line}\n"))


__all__ = [
    "ctx_detail_text",
    "ctx_indicator",
    "format_args_full",
    "render_budget_line",
    "render_detail",
    "render_legend",
    "render_list",
    "render_row",
    "tokens_str",
]
