"""Rendering helpers for the sub-agent panel (live rows + transcript).

Pure presentation: tree ordering, model-name shorthand, and the aligned
one-line-per-agent row renderer shared by the live bottom-bar panel and
the frozen transcript records. No I/O, no state mutation — that lives in
``register_callbacks`` / ``state``.
"""

from __future__ import annotations

import re

from . import state


def _banner_color():
    try:
        from code_puppy.config import get_banner_color

        return get_banner_color("invoke_agent")
    except Exception:
        return "blue"


# ---------------------------------------------------------------------------
# Hierarchy helpers (true parent -> child tree)
# ---------------------------------------------------------------------------
def _ordered_tree(rows):
    """Return [(entry, depth), ...] in DFS order. A row whose parent is not in
    the set (e.g. the main agent, or None) is a root (depth 0); descendants are
    indented one-liners. Cycle-safe; stable by start time."""
    by_id = {e["session_id"]: e for e in rows if e.get("session_id")}
    children = {}
    roots = []
    for e in rows:
        p = e.get("parent")
        if p and p in by_id:
            children.setdefault(p, []).append(e)
        else:
            roots.append(e)
    out = []
    seen = set()

    def walk(node, depth):
        sid = node.get("session_id")
        if sid in seen:
            return
        seen.add(sid)
        out.append((node, depth))
        for kid in sorted(children.get(sid, []), key=lambda c: c["start"]):
            walk(kid, depth + 1)

    for r in sorted(roots, key=lambda e: e["start"]):
        walk(r, 0)
    return out


# Tier/variant qualifiers that distinguish models sharing a version number
# (e.g. gpt-5.4 vs gpt-5.4-nano vs gpt-5.4-mini). Without these, three distinct
# models all collapse to "GPT 5.4" in the panel -- the exact confusion this maps
# away. key (lowercased token in the id) -> Display label.
_MODEL_VARIANTS = (
    ("nano", "Nano"),
    ("mini", "Mini"),
    ("micro", "Micro"),
    ("lite", "Lite"),
    ("turbo", "Turbo"),
    ("flash", "Flash"),
    ("instant", "Instant"),
    ("codex", "Codex"),
    ("thinking", "Thinking"),
    ("reasoning", "Reasoning"),
    ("preview", "Preview"),
    ("pro", "Pro"),
)


def _model_variant(m):
    """Extract a tier/variant qualifier (Nano, Mini, Flash, ...) from a lowercased
    model id. Matched ONLY as a hyphen/underscore/dot/space-delimited token, so
    'mini' inside 'gemini' (or 'pro' inside another word) can never false-fire.
    Returns '' when the id carries no recognised variant."""
    for key, label in _MODEL_VARIANTS:
        if re.search(rf"(?:^|[-_. ]){re.escape(key)}(?:$|[-_. ])", m):
            return label
    return ""


def _model_version(m):
    """Extract a 'major.minor' version from a lowercased model id, tolerating
    BOTH separators in the wild: a contiguous decimal ('gpt-5.4' -> '5.4') OR a
    dash-separated pair ('gpt-5-4', 'claude-4-8-opus' -> '5.4'/'4.8'). Only joins
    two integer groups when both are short (<=2 digits) so date/snapshot ids like
    'gpt-4-0125' don't get mangled into '4.0125'. Returns '' when no number."""
    dec = re.search(r"\d+\.\d+", m)
    if dec:
        return dec.group(0)
    nums = re.findall(r"\d+", m)
    if not nums:
        return ""
    if len(nums) >= 2 and len(nums[0]) <= 2 and len(nums[1]) <= 2:
        return f"{nums[0]}.{nums[1]}"
    return nums[0]


def _model_short(model):
    """Human-readable shorthand for a model id, for live readability.
    e.g. 'claude-4-8-opus' -> 'Opus 4.8', 'claude-sonnet-4-6' -> 'Sonnet 4.6',
    'gpt-5.5' -> 'GPT 5.5', 'gpt-5.4-nano' -> 'GPT 5.4-Nano'. The tier qualifier
    is preserved so same-version-different-tier models stay distinct. Falls back
    to the raw id if unrecognised."""
    if not model:
        return ""

    m = str(model).lower()
    variant = _model_variant(m)
    suffix = f"-{variant}" if variant else ""
    ver = _model_version(m)
    for key, label in (("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku")):
        if key in m:
            return f"{label} {ver}{suffix}".strip()
    if "gpt" in m:
        return (f"GPT {ver}{suffix}" if ver else f"GPT{suffix}").strip()
    if "gemini" in m:
        return (f"Gemini {ver}{suffix}" if ver else f"Gemini{suffix}").strip()
    return str(model)


def _row_lines(ordered, frame):
    """Render a list of (entry, depth) as aligned single-line rows:
        <prefix><name>   <model>   <spin|check> <mm:ss>
    The model + indicator + time columns share a per-tree tab-stop computed
    from the widest (prefix+name) AND the widest model label, so longer model
    names (e.g. 'GPT 5.4-Nano') and deeper-indented names both push the whole
    right block over together -- columns stay aligned no matter what gets added.
    Alignment is done purely with U+0020 spaces (never literal tabs), and widths
    use Rich cell_len, so the layout renders identically on Windows and macOS.
    Root rows carry the INVOKE AGENT badge; nested rows carry the tree elbow.
    Used for BOTH the live block and the transcript.
    """
    from rich.cells import cell_len
    from rich.text import Text

    color = _banner_color()
    lefts = []
    models = []
    name_w = 0
    model_w = 0
    for e, depth in ordered:
        left = Text(no_wrap=True, overflow="ellipsis")
        if depth == 0:
            left.append(" \U0001f916 INVOKE AGENT ", style=f"bold white on {color}")
            left.append(" ")
            left.append(e["name"], style="bold cyan")
        else:
            left.append("  " + "   " * (depth - 1))
            left.append("\u2514\u2500 ", style="grey50")  # tree elbow
            left.append(e["name"], style="bold cyan")
        lefts.append(left)
        ms = _model_short(e.get("model"))
        models.append(ms)
        name_w = max(name_w, left.cell_len)
        model_w = max(model_w, cell_len(ms))

    lines = []
    for (e, depth), left, ms in zip(ordered, lefts, models):
        done = bool(e.get("done"))
        failed = bool(e.get("failed"))
        line = left.copy()
        # These rows are deliberately one-line status rows: the live panel
        # rows are truncated to the terminal width by the bottom bar, and
        # transcript records must not wrap mid-column. Crop visually;
        # preserve full status in state.
        line.no_wrap = True
        line.overflow = "ellipsis"
        line.append(" " * (name_w - left.cell_len + 2))
        line.append(ms, style="magenta")
        line.append(" " * (model_w - cell_len(ms) + 2))
        if failed:
            line.append("\u2717 ", style="bold red")  # X mark
        elif done:
            line.append("\u2713 ", style="bold green")  # check
        else:
            line.append((frame or " ") + " ", style="bold cyan")
        line.append(state.fmt_elapsed_entry(e), style="dim")
        # Current action / status, color-coded (yellow=calling, magenta=thinking,
        # green=writing). Done rows show 'completed' green; failed rows 'failed' red.
        status = e.get("status", "starting")
        line.append("  ")
        if failed:
            line.append("failed", style="bold red")
        elif done:
            line.append("completed", style="green")
        else:
            line.append(status, style=state.status_style(status))
        lines.append(line)
    return lines


__all__ = [
    "_banner_color",
    "_model_short",
    "_model_variant",
    "_model_version",
    "_ordered_tree",
    "_row_lines",
]
