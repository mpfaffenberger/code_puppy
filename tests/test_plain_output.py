"""Code Puppy's own text is printed as written.

Rich runs a "repr" highlighter over every ``str`` it prints unless told not
to: ``/new`` turns magenta as a path, ``0.70.0`` cyan as a number, and
``de:c`` in ``claude-code:claude`` green as an IPv6 address. Each test prints
the same thing to a console with that highlighter on and to one with it off;
the output must not differ.
"""

from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from rich.console import Console

from code_puppy import branding, messaging


def printed(show: Callable[[Console], None], *, highlight: bool) -> str:
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        color_system="truecolor",
        force_terminal=True,
        width=120,
        highlight=highlight,
    )
    show(console)
    return buffer.getvalue()


def test_the_welcome_is_printed_as_written(
    installed_distribution: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pydantic_ai_pax.ui.rendering import welcome

    # The runtime's project report is not Code Puppy's text.
    monkeypatch.setattr(welcome, "_report_project", lambda project, console: None)

    def show(console: Console) -> None:
        branding.print_welcome(None, console)  # type: ignore[arg-type]

    assert printed(show, highlight=True) == printed(show, highlight=False)


def test_the_narrow_banner_is_printed_as_written(installed_distribution: None) -> None:
    def show(console: Console) -> None:
        console.width = 10
        branding.print_banner(console)

    assert printed(show, highlight=True) == printed(show, highlight=False)


@pytest.mark.parametrize(
    "text",
    [
        "Loaded 3 hooks from /tmp/plugins in 0.5s",
        "Use claude-code:claude-opus-5-5 [/not-markup]",
    ],
)
def test_a_0_0_x_plugins_message_is_printed_as_written(text: str) -> None:
    def show(console: Console) -> None:
        messaging.set_console(console)
        messaging.emit_info(text)
        messaging.emit_warning(text)

    assert printed(show, highlight=True) == printed(show, highlight=False)
