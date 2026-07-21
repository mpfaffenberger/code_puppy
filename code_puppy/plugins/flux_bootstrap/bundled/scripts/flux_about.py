#!/usr/bin/env python3
"""Render the /flux/about overview using Rich's markdown renderer.

This is the deterministic, AI-free renderer for /flux/about. The previous
hand-rolled ANSI version was rough on tables (column widths didn't account
for ANSI escapes around cell contents). Rich does the heavy lifting properly:
real tables, syntax-highlighted code fences, headings, bullets -- all aligned.

Single source of truth: the overview text lives in about.md. We read it at
runtime, strip the YAML frontmatter + the AI-only preamble, normalize the
wibey //cmd refs to /cmd, and hand the rest to ``rich.markdown.Markdown``.

Usage:
  flux_about.py [--source PATH] [--width N] [--no-color]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown


def _default_source() -> str:
    """Resolve about.md under code-puppy's (XDG-aware) config dir.

    Runs inside the code-puppy venv, so importing the canonical resolver is the
    single source of truth for the config location -- honoring XDG overrides
    instead of assuming a hard-coded ~/.code_puppy. Falls back to the legacy
    layout only if that import fails (e.g. run standalone).
    """
    try:
        from code_puppy.config import CONFIG_DIR

        return os.path.join(CONFIG_DIR, "commands", "flux", "about.md")
    except Exception:
        return os.path.join(
            os.path.expanduser("~"), ".code_puppy", "commands", "flux", "about.md"
        )


DEFAULT_SOURCE = _default_source()
DEFAULT_WIDTH = 120  # most modern terminals are at least this wide

# YAML frontmatter block at the top of the file
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# Wibey //cmd -> /cmd, URL-safe (won't touch https://, example.com//, etc.)
SLASH_CMD_RE = re.compile(r"(?<![:\w/])//(?=\w)")
# The AI instruction preamble we skip when rendering directly
PREAMBLE_RE = re.compile(r"^Output the following overview exactly")


def extract_body(raw: str) -> str:
    """Strip YAML frontmatter and normalize //cmd -> /cmd."""
    body = FRONTMATTER_RE.sub("", raw, count=1).strip()
    return SLASH_CMD_RE.sub("/", body)


def drop_ai_preamble(body: str) -> str:
    """Skip the 'Output the following overview exactly...' block + its --- rule.

    The preamble exists solely to instruct an LLM; when a script is doing the
    rendering it's just noise. If the preamble isn't present (someone edited
    it out) the body is returned unchanged.
    """
    lines = body.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if not skipping and PREAMBLE_RE.match(line):
            skipping = True
            continue
        if skipping:
            # The preamble ends at the first standalone --- horizontal rule
            if line.strip() == "---":
                skipping = False
            continue
        out.append(line)
    return "\n".join(out).strip()


def resolve_width(cli_width: int | None) -> int:
    """CLI flag wins; else $COLUMNS; else our DEFAULT_WIDTH."""
    if cli_width and cli_width > 0:
        return cli_width
    env_cols = os.environ.get("COLUMNS")
    if env_cols and env_cols.isdigit() and int(env_cols) > 0:
        return int(env_cols)
    return DEFAULT_WIDTH


def force_utf8_stdout() -> None:
    """Reconfigure stdout to UTF-8 so emoji survive legacy Windows codepages.

    Under the exec runner the env already forces UTF-8 (PYTHONIOENCODING);
    this covers standalone runs in a cp1252 console, where printing a single
    emoji would otherwise raise UnicodeEncodeError. Best-effort by design --
    these scripts must never crash on an IO quirk. (Duplicated across the
    flux_* scripts on purpose: each is a standalone, dependency-free file.)
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdout()
    parser = argparse.ArgumentParser(description="Render /flux/about overview")
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"Path to about.md (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help=f"Render width in cols (default: $COLUMNS or {DEFAULT_WIDTH})",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color")
    args = parser.parse_args(argv)

    source = Path(args.source).expanduser()
    if not source.is_file():
        print(f"(about.md not found at {source})")
        return 1

    raw = source.read_text(encoding="utf-8", errors="replace")
    cleaned = drop_ai_preamble(extract_body(raw))

    # ``force_terminal=True`` makes Rich emit ANSI even though our stdout is a
    # pipe (the code-puppy exec runner captures it). ``no_color`` honors --no-color.
    # ``legacy_windows=False`` keeps Rich off the win32 LegacyWindowsTerm path:
    # our stdout is a pipe, not a console handle, so that path both loses the
    # ANSI the runner re-renders AND crashes encoding emoji on cp1252. Plain
    # ANSI bytes through the pipe are exactly what the runner contract wants.
    console = Console(
        force_terminal=True,
        legacy_windows=False,
        color_system=None if args.no_color else "truecolor",
        width=resolve_width(args.width),
        no_color=args.no_color,
        # Avoid stripping the user's content when stdout isn't a real TTY.
        soft_wrap=False,
    )
    console.print(Markdown(cleaned))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
