#!/usr/bin/env python3
"""Render a colorized /flux/status panel for the terminal.

This is the code-puppy equivalent of Wibey's native `ui-mode: flux-status`
renderer. Wibey draws an interactive Ink overlay; code-puppy can't host an
interactive UI, so this script prints a static but fully-colored panel.

Data model (all under ~/.flux/<flattened-cwd>/):
  todo/*.md                 -> frontmatter `stage` + `status`
  done/<timestamp>/*.md     -> completed tasks, grouped by run timestamp
  review/<severity>/*.md    -> severity is the folder name

Usage:
  flux_status.py [--base DIR] [--sections todo,done,review] [--no-color]

If --base is omitted, the flux base is derived from the current working
directory exactly the way the //flux commands do it (every run of
non-alphanumeric chars in the absolute path becomes a single hyphen).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# --- ANSI palette -----------------------------------------------------------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
MAGENTA = "\033[1;35m"
CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
ORANGE = "\033[38;5;208m"
TEAL = "\033[38;5;43m"
GREY = "\033[90m"
WHITE = "\033[1;37m"

# --- glyphs (escaped so emoji-stripping file writers leave them intact) -----
FRAKTUR_F = "\U0001d571"  # mathematical bold fraktur capital F
ICON_PROGRESS = "\U0001f504"  # clockwise arrows
ICON_DONE = "\u2705"  # white heavy check mark on green
ICON_REWORK = "\U0001f501"  # repeat
DOT = "\u25cf"  # solid circle

STATUS_STYLE = {
    "in-progress": (ICON_PROGRESS, ORANGE),
    "needs-rework": (ICON_REWORK, RED),
    "done": (ICON_DONE, GREEN),
    "completed": (ICON_DONE, GREEN),
}

SEVERITIES = ("critical", "high", "medium", "low")
SEVERITY_COLOR = {
    "critical": RED,
    "high": ORANGE,
    "medium": TEAL,
    "low": GREEN,
}
# column header label -> fixed display width for the review grid
SEV_COL_WIDTH = {"critical": 10, "high": 6, "medium": 8, "low": 5}

# Panel layout constants (named so a column-width tweak can't silently break
# the header/rule alignment).
_SECTION_PAD = 18  # extra width added to name_w + stage_w for section rules
_MIN_PANEL_W = 48  # floor so short content still frames nicely


class Theme:
    """Wraps color usage so --no-color collapses every code to ''."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"{code}{text}{RESET}"


def flatten_cwd(cwd: str) -> str:
    """Replace runs of non-alphanumerics with single hyphens (flux convention)."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", cwd)


def derive_base(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    home = Path.home()
    return home / ".flux" / flatten_cwd(os.getcwd())


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Read the leading `--- ... ---` YAML-ish block into a flat dict."""
    data: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return data
    if not text.startswith("---"):
        return data
    lines = text.splitlines()
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, val = line.partition(":")
            data[key.strip()] = val.strip()
    return data


def status_cell(status: str, theme: Theme) -> str:
    icon, color = STATUS_STYLE.get(status, ("", GREY))
    label = theme(color, status) if status else theme(GREY, "(unknown)")
    return f"{icon}  {label}".strip() if icon else label


def rule(width: int, char: str, color: str, theme: Theme) -> str:
    return theme(color, char * width)


def visible_len(name: str) -> int:
    return len(name)


def collect_todos(base: Path) -> list[tuple[str, str, str]]:
    rows = []
    todo = base / "todo"
    if not todo.is_dir():
        return rows
    for md in sorted(todo.glob("*.md")):
        fm = parse_frontmatter(md)
        rows.append((md.stem, fm.get("stage", ""), fm.get("status", "")))
    return rows


def collect_done(base: Path) -> list[tuple[str, list[tuple[str, str, str]]]]:
    """Returns [(timestamp_label, [(name, stage, status), ...]), ...]."""
    groups = []
    done = base / "done"
    if not done.is_dir():
        return groups
    for ts_dir in sorted(done.iterdir(), reverse=True):
        if not ts_dir.is_dir():
            continue
        rows = []
        for md in sorted(ts_dir.glob("*.md")):
            fm = parse_frontmatter(md)
            rows.append((md.stem, fm.get("stage", ""), fm.get("status", "completed")))
        if rows:
            groups.append((format_timestamp(ts_dir.name), rows))
    return groups


def format_timestamp(dirname: str) -> str:
    """`2026-04-29-16-57` -> `2026-04-29 16:57`; pass through anything odd."""
    parts = dirname.split("-")
    if len(parts) == 5:
        return f"{parts[0]}-{parts[1]}-{parts[2]} {parts[3]}:{parts[4]}"
    return dirname


def collect_reviews(base: Path) -> list[tuple[str, str]]:
    """Returns [(review_name, severity), ...] ordered critical->low."""
    out = []
    review = base / "review"
    if not review.is_dir():
        return out
    for sev in SEVERITIES:
        sev_dir = review / sev
        if not sev_dir.is_dir():
            continue
        for md in sorted(sev_dir.glob("*.md")):
            out.append((md.stem, sev))
    return out


def render(base: Path, sections: set[str], theme: Theme) -> str:
    todos = collect_todos(base) if "todo" in sections else []
    done_groups = collect_done(base) if "done" in sections else []
    reviews = collect_reviews(base) if "review" in sections else []

    # column width across everything we will print on the left
    names = [r[0] for r in todos]
    names += [r[0] for g in done_groups for r in g[1]]
    names += [r[0] for r in reviews]
    name_w = max([visible_len(n) for n in names] + [len("TODO-FILE")]) + 2
    name_w = min(name_w, 50)
    stage_w = 8
    total_w = max(name_w + stage_w + _SECTION_PAD, _MIN_PANEL_W)

    lines: list[str] = []
    lines.append(theme(MAGENTA, f"{FRAKTUR_F} FLUX STATUS"))
    lines.append(rule(total_w, "\u2550", MAGENTA, theme))
    rendered_any = False  # have we emitted a body section yet?

    # --- TODO section -------------------------------------------------------
    if "todo" in sections:
        rendered_any = True
        header = (
            theme(WHITE, "TODO-FILE".ljust(name_w))
            + theme(WHITE, "STAGE".ljust(stage_w))
            + theme(WHITE, "STATUS")
        )
        lines.append("")
        lines.append(header)
        lines.append(rule(total_w, "\u2500", GREY, theme))
        if not todos:
            lines.append(theme(GREY, "(no todos)"))
        for name, stage, status in todos:
            lines.append(
                theme(CYAN, name.ljust(name_w))
                + stage.ljust(stage_w)
                + status_cell(status, theme)
            )

    # --- COMPLETED section --------------------------------------------------
    if "done" in sections and done_groups:
        lines.append("")
        if rendered_any:
            lines.append(rule(total_w, "\u2550", MAGENTA, theme))
        rendered_any = True
        lines.append(theme(MAGENTA, "COMPLETED TASKS"))
        lines.append("")
        lines.append(
            theme(WHITE, "TASK-FILE".ljust(name_w))
            + theme(WHITE, "STAGE".ljust(stage_w))
            + theme(WHITE, "STATUS")
        )
        for ts_label, rows in done_groups:
            lines.append(theme(GREY, f"\u2500\u2500 {ts_label} \u2500\u2500"))
            for name, stage, status in rows:
                lines.append(
                    theme(CYAN, name.ljust(name_w))
                    + stage.ljust(stage_w)
                    + status_cell(status, theme)
                )

    # --- REVIEW section -----------------------------------------------------
    if "review" in sections and reviews:
        lines.append("")
        if rendered_any:
            lines.append(rule(total_w, "\u2550", MAGENTA, theme))
        rendered_any = True
        lines.append(theme(ORANGE, "REVIEW TASKS"))
        lines.append("")
        # column header
        head = theme(WHITE, "REVIEW-FILE".ljust(name_w))
        for sev in SEVERITIES:
            head += theme(SEVERITY_COLOR[sev], sev.upper().ljust(SEV_COL_WIDTH[sev]))
        lines.append(head)
        # Underline width is derived from the ACTUAL review columns (name +
        # every severity column), not the generic section total_w -- otherwise
        # the rule is short by a few cols and drifts whenever SEV_COL_WIDTH
        # changes.
        review_w = max(name_w + sum(SEV_COL_WIDTH[s] for s in SEVERITIES), _MIN_PANEL_W)
        lines.append(rule(review_w, "\u2500", GREY, theme))
        for name, sev in reviews:
            row = theme(CYAN, name.ljust(name_w))
            for col in SEVERITIES:
                if col == sev:
                    cell = theme(SEVERITY_COLOR[sev], DOT)
                    row += cell + " " * (SEV_COL_WIDTH[col] - 1)
                else:
                    row += " " * SEV_COL_WIDTH[col]
            lines.append(row.rstrip())

    lines.append(rule(total_w, "\u2550", MAGENTA, theme))
    return "\n".join(lines)


def force_utf8_stdout() -> None:
    """Reconfigure stdout to UTF-8 so emoji survive legacy Windows codepages.

    Under the exec runner the env already forces UTF-8 (PYTHONIOENCODING);
    this covers standalone runs in a cp1252 console, where printing a single
    emoji or box-drawing glyph would otherwise raise UnicodeEncodeError.
    Best-effort by design -- these scripts must never crash on an IO quirk.
    (Duplicated across the flux_* scripts on purpose: each is a standalone,
    dependency-free file.)
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description="Render /flux/status panel")
    parser.add_argument("--base", default=None, help="Explicit flux base dir")
    parser.add_argument(
        "--sections",
        default="todo,done,review",
        help="Comma list of: todo,done,review (default: all)",
    )
    parser.add_argument(
        "sections_pos",
        nargs="*",
        default=[],
        help="Optional positional section filter (todo/done/review); overrides --sections.",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color")
    args = parser.parse_args(argv)

    # valid_sections is defined by hand rather than via argparse `choices=`:
    # combining choices with nargs='*' rejects the empty-list default. The
    # resolved set is validated below, after merging both input paths.
    valid_sections = {"todo", "done", "review"}

    base = derive_base(args.base)
    # Positional section args (e.g. `flux_status.py todo review`) override
    # --sections so command-line callers don't need to remember the flag name.
    if args.sections_pos:
        sections = {s.strip() for s in args.sections_pos if s.strip()}
    else:
        sections = {s.strip() for s in args.sections.split(",") if s.strip()}

    # Validate the resolved set once so a typo via EITHER input path (positional
    # or --sections) fails loudly instead of silently rendering a blank panel.
    bad = sorted(sections - valid_sections)
    if bad:
        parser.error(
            f"invalid section(s): {', '.join(bad)} "
            f"(choose from {', '.join(sorted(valid_sections))})"
        )

    # The code-puppy exec runner captures stdout via a pipe and injects
    # FORCE_COLOR=1 (see _run_exec_directive), so color stays on in that
    # environment even though isatty() is False. flux_about.py documents the
    # same contract via Rich's force_terminal=True -- keep the FORCE_COLOR branch
    # so colorized panels don't silently degrade to monochrome under the runner.
    color_on = not args.no_color and (
        sys.stdout.isatty() or os.environ.get("FORCE_COLOR")
    )
    theme = Theme(bool(color_on))

    if not base.exists():
        print(theme(GREY, f"(no flux state at {base})"))
        return 0

    print(render(base, sections, theme))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
