"""Best-effort inline image display for modern terminals."""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path


def _terminal_kind() -> str | None:
    program = os.environ.get("TERM_PROGRAM", "").casefold()
    term = os.environ.get("TERM", "").casefold()
    if os.environ.get("ITERM_SESSION_ID") or program == "iterm.app":
        return "iterm"
    if (
        program in {"ghostty", "wezterm"}
        or os.environ.get("KITTY_WINDOW_ID")
        or "ghostty" in term
        or "kitty" in term
    ):
        return "kitty"
    return None


def emit_inline_image(path: str | Path) -> bool:
    """Render a PNG using iTerm2 or Kitty graphics escape sequences."""
    image_path = Path(path)
    kind = _terminal_kind()
    if kind is None or not sys.stdout.isatty() or not image_path.is_file():
        return False

    try:
        if kind == "iterm":
            data = base64.b64encode(image_path.read_bytes()).decode("ascii")
            name = base64.b64encode(image_path.name.encode()).decode("ascii")
            sequence = (
                f"\033]1337;File=name={name};inline=1;width=50%;"
                f"preserveAspectRatio=1:{data}\a\n"
            )
        else:
            encoded_path = base64.b64encode(str(image_path.resolve()).encode()).decode(
                "ascii"
            )
            # Direct file transmission keeps the full screenshot out of the terminal
            # stream; q=2 suppresses replies, c/r bound it to a compact PiP preview.
            sequence = f"\033_Ga=T,t=f,f=100,q=2,c=64,r=22;{encoded_path}\033\\\n"

        from code_puppy.messaging.run_ui import suspended_run_ui

        with suspended_run_ui():
            sys.stdout.write(sequence)
            sys.stdout.flush()
    except Exception:
        return False
    return True
