#!/usr/bin/env python3
"""Render the //flux cheatsheet (pipeline flows) colorized for the terminal.

This is the code-puppy equivalent of Wibey's native cheatsheet panel. Wibey
shows clickable PIPELINE A/B/C/D tabs; code-puppy can't host interactive tabs,
so this prints all pipelines stacked (or one, via --pipeline).

SINGLE SOURCE OF TRUTH: the pipeline definitions are parsed at runtime from
`pipeline.md` in the flux _docs directory. Editing that doc changes this output
automatically -- nothing is hardcoded here except presentation.

Wibey writes commands as `/flux/<cmd>`; code-puppy's namespaced slash commands
use a single leading slash, so every command is normalized to `/flux/<cmd>`
before display -- exactly what a code-puppy user types to run it.

The flux _docs directory defaults to code-puppy's config dir (XDG-aware) rather
than any hard-coded home path; ``--docs`` overrides it. The command wiring
passes it explicitly via a ``{command:flux/_docs}`` token.

Usage:
  flux_cheatsheet.py [--docs DIR] [--pipeline A|B|C|D] [--no-color]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# --- ANSI palette -----------------------------------------------------------
RESET = "\033[0m"
MAGENTA = "\033[1;35m"
CYAN = "\033[1;36m"
GREEN = "\033[32m"
WHITE = "\033[1;37m"
GREY = "\033[90m"

FRAKTUR_F = "\U0001d571"  # mathematical bold fraktur capital F


def _default_docs() -> str:
    """Resolve the flux _docs dir under code-puppy's (XDG-aware) config dir.

    Runs inside the code-puppy venv, so importing the canonical resolver is the
    single source of truth. Falls back to the legacy ~/.code_puppy layout only
    if that import somehow fails (e.g. run standalone).
    """
    try:
        from code_puppy.config import CONFIG_DIR

        return os.path.join(CONFIG_DIR, "commands", "flux", "_docs")
    except Exception:
        return os.path.join(
            os.path.expanduser("~"), ".code_puppy", "commands", "flux", "_docs"
        )


DEFAULT_DOCS = _default_docs()

# matches `/flux/`, `/flux/`, etc. -> we normalize to `/flux/` (the single-slash
# namespaced command code-puppy users actually type).
SLASH_CMD = re.compile(r"/+flux/")
PIPELINE_HEADING = re.compile(r"^##\s+PIPELINE\s+([A-Za-z0-9]+)\s*:")


class Theme:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, code: str, text: str) -> str:
        return f"{code}{text}{RESET}" if self.enabled else text


def strip_slashes(line: str) -> str:
    """`/flux/new` -> `/flux/new`, `/flux/review <PR#>` -> `/flux/review <PR#>`.

    Collapses any run of leading slashes to the single-slash namespaced form
    code-puppy dispatches (``/flux/<cmd>``).
    """
    return SLASH_CMD.sub("/flux/", line)


def parse_pipelines(md_text: str) -> list[tuple[str, str, list[str]]]:
    """Return [(letter, description, [flow_line, ...]), ...] in document order."""
    lines = md_text.splitlines()
    pipelines: list[tuple[str, str, list[str]]] = []

    i = 0
    n = len(lines)
    while i < n:
        m = PIPELINE_HEADING.match(lines[i])
        if not m:
            i += 1
            continue
        letter = m.group(1).upper()
        i += 1

        # find the description: first meaningful line before the code fence
        description = ""
        while i < n and not PIPELINE_HEADING.match(lines[i]):
            stripped = lines[i].strip()
            if stripped.startswith("```"):
                break
            if stripped and stripped != "---" and not stripped.startswith("#"):
                description = stripped
                i += 1
                break
            i += 1

        # find and capture the first fenced code block = the flow
        flow: list[str] = []
        while i < n and not PIPELINE_HEADING.match(lines[i]):
            if lines[i].strip().startswith("```"):
                i += 1  # enter the fence
                while i < n and not lines[i].strip().startswith("```"):
                    flow.append(lines[i])
                    i += 1
                i += 1  # exit the fence
                break
            i += 1

        # trim leading/trailing blank lines inside the flow
        while flow and not flow[0].strip():
            flow.pop(0)
        while flow and not flow[-1].strip():
            flow.pop()

        pipelines.append((letter, description, flow))
    return pipelines


def render_flow_line(raw: str, theme: Theme) -> str:
    """Colorize one flow line: comments dim, command flow green, slashes stripped."""
    if not raw.strip():
        return ""
    if raw.strip().startswith("#"):
        # keep the comment's indentation, dim the text
        return theme(GREY, strip_slashes(raw))
    return theme(GREEN, strip_slashes(raw))


def render(pipelines: list[tuple[str, str, list[str]]], theme: Theme) -> str:
    width = 60
    out: list[str] = []
    out.append(theme(MAGENTA, f"{FRAKTUR_F} FLUX CHEATSHEET"))
    out.append(theme(MAGENTA, "\u2550" * width))

    for idx, (letter, desc, flow) in enumerate(pipelines):
        if idx > 0:
            out.append("")
            out.append(theme(GREY, "\u2500" * width))
        out.append("")
        out.append(theme(CYAN, f"PIPELINE {letter}"))
        if desc:
            out.append(theme(WHITE, desc))
        out.append("")
        for line in flow:
            out.append(render_flow_line(line, theme))

    out.append("")
    out.append(theme(MAGENTA, "\u2550" * width))
    return "\n".join(out)


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
    parser = argparse.ArgumentParser(description="Render //flux cheatsheet panel")
    parser.add_argument("--docs", default=DEFAULT_DOCS, help="flux _docs directory")
    parser.add_argument(
        "--pipeline",
        default=None,
        help="Show only one pipeline (A, B, C, or D)",
    )
    parser.add_argument(
        "pipeline_pos",
        nargs="?",
        default=None,
        help="Optional positional pipeline filter (a/b/c/d); overrides --pipeline.",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color")
    args = parser.parse_args(argv)

    # Positional pipeline arg (e.g. `flux_cheatsheet.py a`) wins over --pipeline
    # so command-line callers don't have to remember the flag name.
    selected_pipeline = args.pipeline_pos or args.pipeline
    if selected_pipeline is not None:
        normalized = selected_pipeline.strip().upper()
        if normalized not in {"A", "B", "C", "D"}:
            parser.error(
                f"invalid pipeline: {selected_pipeline!r} (choose from A, B, C, D)"
            )
        args.pipeline = normalized

    docs_dir = Path(args.docs).expanduser()
    pipeline_md = docs_dir / "pipeline.md"

    # The code-puppy exec runner captures stdout via a pipe and injects
    # FORCE_COLOR=1 (see _run_exec_directive), so color stays on in that
    # environment even though isatty() is False. flux_about.py documents the
    # same contract via Rich's force_terminal=True -- keep the FORCE_COLOR branch
    # so the cheatsheet doesn't silently degrade to monochrome under the runner.
    color_on = not args.no_color and (
        sys.stdout.isatty() or os.environ.get("FORCE_COLOR")
    )
    theme = Theme(bool(color_on))

    if not pipeline_md.is_file():
        print(theme(GREY, f"(pipeline doc not found at {pipeline_md})"))
        return 1

    pipelines = parse_pipelines(
        pipeline_md.read_text(encoding="utf-8", errors="replace")
    )

    if args.pipeline:
        # Already validated + normalized above
        want = args.pipeline
        pipelines = [p for p in pipelines if p[0] == want]
        if not pipelines:
            print(theme(GREY, f"(no PIPELINE {want} found)"))
            return 1

    if not pipelines:
        print(theme(GREY, "(no pipelines found in pipeline.md)"))
        return 1

    print(render(pipelines, theme))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
