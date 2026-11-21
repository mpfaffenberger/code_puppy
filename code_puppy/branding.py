"""What Code Puppy prints about itself: the banner and the welcome lines."""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

from pyfiglet import Figlet
from rich.text import Text

from code_puppy import identity

if TYPE_CHECKING:
    from pydantic_ai_pax.config.project_settings import ProjectSettings
    from pydantic_ai_pax.runtime.worktrees import Worktree
    from rich.console import Console

BANNER_TEXT = "CODE PUPPY"
BANNER_COMPACT = "PUP"
RUNTIME_DISTRIBUTION = "pydantic-ai-pax"


def version_line() -> str:
    """Code Puppy's version and the runtime underneath, for bug reports."""
    try:
        runtime = metadata.version(RUNTIME_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        runtime = "unknown"
    return f"{identity.DISTRIBUTION} {identity.version()} ({RUNTIME_DISTRIBUTION} {runtime})"


def print_banner(console: Console) -> None:
    """Print the wordmark, falling back to shorter forms on a narrow terminal."""
    from pydantic_ai_pax.ui.rendering import theme

    figlet = Figlet(font="ansi_shadow", width=200)
    with theme.branded():
        for text in (BANNER_TEXT, BANNER_COMPACT):
            lines = figlet.renderText(text).splitlines()
            if console.width >= max(map(len, lines)):
                for index, line in enumerate(lines):
                    console.print(Text(line, style=theme.BANNER[min(index // 2, 2)]))
                return
        console.print(identity.DISPLAY_NAME, style=theme.LOGO, highlight=False)


def print_welcome(
    project: ProjectSettings, console: Console, *, worktree: Worktree | None = None
) -> None:
    """The banner, version and hints a fresh launch and ``/clear`` show."""
    from pydantic_ai_pax.ui.rendering import theme, welcome

    muted = theme.color(theme.MUTED)
    console.print()
    print_banner(console)
    # `highlight=False` throughout: Rich would recolour the version numbers and
    # the slash commands as if this text were a Python repr.
    console.print(version_line(), style=muted, highlight=False)
    if worktree is not None:
        # Soft wrap keeps the path copyable: hard wrapping would break it.
        console.print(
            worktree.notice, style=muted, markup=False, highlight=False, soft_wrap=True
        )
    console.print(
        "/new starts a session; /resume restores one; /exit quits. "
        "Esc or Ctrl-C interrupts a turn.",
        style=muted,
        highlight=False,
    )
    welcome._report_project(project, console)
