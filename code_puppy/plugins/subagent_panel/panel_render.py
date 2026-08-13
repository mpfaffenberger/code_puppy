"""Rendering helpers for the sub-agent panel (live rows + transcript).

Pure presentation: tree ordering, model-name shorthand, and the aligned
one-line-per-agent row renderer shared by the live bottom-bar panel and
the frozen transcript records. No I/O, no state mutation — that lives in
``register_callbacks`` / ``state``.
"""

from __future__ import annotations


from . import state


def _banner_color():
    try:
        from code_puppy.config import get_banner_color

        return get_banner_color("invoke_agent")
    except Exception:
        return "blue"


# Hierarchy helpers (true parent -> child tree)
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


def _model_short(model):
    """Return the model identifier verbatim for the panel display.

    Deliberately a passthrough: whatever the user picked with ``/model <key>``
    is what shows up in the subagent panel. No parsing, no title-casing, no
    tier/env extraction -- previous versions built a curated shorthand from
    a hard-coded allowlist of tier tokens (nano/mini/flash/...) plus an env
    allowlist ('stage'), which silently dropped any suffix outside the lists
    (e.g. -stage). Users would rather see the raw config key and trust their
    own eyes; that also removes an allowlist maintenance chore forever.
    Empty / None inputs collapse to an empty string so the panel column
    doesn't render the literal 'None'.
    """
    return str(model) if model else ""


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
        # Keep status rows single-line; crop visually for the terminal but retain
        # full status in state.
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
    "_ordered_tree",
    "_row_lines",
]
