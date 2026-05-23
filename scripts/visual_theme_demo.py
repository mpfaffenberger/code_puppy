"""Visual smoke test for the new ANSI code-theme resolver.

Renders the same Markdown block under three conditions so you can
eyeball-verify Catppuccin Latte (light) actually stays readable:

  1. Whatever the terminal autodetects (CODE_PUPPY_TERMINAL_BG / COLORFGBG)
  2. Forced 'ansi_dark'
  3. Forced 'ansi_light'

Run with:

    .venv/bin/python scripts/visual_theme_demo.py

Not part of the test suite; just a one-shot eyeball check.
"""

from __future__ import annotations

import os

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule

from code_puppy.messaging.terminal_theme import (
    detect_terminal_bg,
    resolve_code_theme,
)

SAMPLE_MD = """\
# Theming smoke test 🐶

Some inline `code` should be visible without straining — this used to be
`cyan on black` in Rich, which rendered as **green on grey** under
Catppuccin Latte (a red–green CVD nightmare). It is now `bold reverse`,
which respects the terminal's own fg/bg pair.

Keyboard shortcuts like <kbd>Ctrl+C</kbd> get the same treatment.

```python
def greet(name: str) -> str:
    \"\"\"Return a friendly greeting for the given name.\"\"\"
    pieces = ["Hello", name, "—", "have", "a", "great", "day!"]
    return " ".join(pieces)


if __name__ == "__main__":
    for who in ("Jeff", "Tizzy", "the world"):
        print(greet(who))
```

```bash
# Shell highlighting too
grep -rn "monokai" code_puppy/ || echo "no truecolor lock-in here"
```

A regular paragraph with **bold**, *italic*, and ~~strikethrough~~ — these
should all use the terminal palette, not hard-coded RGB.
"""


def _render(console: Console, label: str, theme: str) -> None:
    """Render the sample markdown with a fixed pygments theme + a label."""
    console.print(
        Rule(f"[bold]{label}[/bold]  ([cyan]code_theme={theme}[/cyan])"),
    )
    console.print(Markdown(SAMPLE_MD, code_theme=theme))
    console.print()


def main() -> None:
    console = Console()
    console.print(
        Panel.fit(
            f"COLORFGBG={os.environ.get('COLORFGBG', '<unset>')!r}\n"
            f"CODE_PUPPY_TERMINAL_BG={os.environ.get('CODE_PUPPY_TERMINAL_BG', '<unset>')!r}\n"
            f"detect_terminal_bg() => {detect_terminal_bg()!r}\n"
            f"resolve_code_theme(None) => {resolve_code_theme(None)!r}",
            title="terminal_theme detection",
            border_style="dim",
        )
    )

    auto_theme = resolve_code_theme(None)
    _render(console, "AUTODETECTED", auto_theme)
    _render(console, "FORCED ansi_dark", "ansi_dark")
    _render(console, "FORCED ansi_light", "ansi_light")


if __name__ == "__main__":
    main()
