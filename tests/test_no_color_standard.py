"""Rich's built-in ``NO_COLOR`` support must not be overridden.

Regression coverage for consoles constructed as ``Console(no_color=False)``.
Rich auto-detects the cross-tool ``NO_COLOR`` standard (no-color.org) only
when ``no_color`` is left unset -- passing an explicit ``False`` silently
defeats it, so a user who exported ``NO_COLOR=1`` still got SGR codes.

``code_puppy/splash.py`` honors ``NO_COLOR`` already, which made the old
behavior worse than a clean miss: the splash obeyed and everything after
it did not.
"""

import io

from rich.console import Console

from code_puppy.tools.common import _no_color_setting


def test_unset_returns_none_so_rich_can_detect_no_color(monkeypatch):
    """None, not False -- False is what defeated the standard."""
    monkeypatch.delenv("CODE_PUPPY_NO_COLOR", raising=False)
    assert _no_color_setting() is None


def test_explicit_opt_in_still_forces_color_off(monkeypatch):
    """The project's own override keeps working."""
    monkeypatch.setenv("CODE_PUPPY_NO_COLOR", "1")
    assert _no_color_setting() is True


def test_no_color_env_actually_suppresses_color(monkeypatch):
    """End to end: NO_COLOR=1 means no color codes reach the terminal.

    Asserted on a color-only style on purpose. Rich's ``no_color`` strips
    color while preserving attributes such as bold, which is correct --
    the NO_COLOR standard is about color, not about all styling.
    """
    monkeypatch.delenv("CODE_PUPPY_NO_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")

    buf = io.StringIO()
    console = Console(
        no_color=_no_color_setting(), force_terminal=True, file=buf, width=40
    )
    console.print("[red]danger[/red]")

    assert "\x1b[" not in buf.getvalue()
    assert "danger" in buf.getvalue()
    assert console.no_color is True


def test_color_still_emitted_when_no_color_is_absent(monkeypatch):
    """The fix must not turn color off for everybody else."""
    monkeypatch.delenv("CODE_PUPPY_NO_COLOR", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)

    buf = io.StringIO()
    console = Console(
        no_color=_no_color_setting(), force_terminal=True, file=buf, width=40
    )
    console.print("[red]danger[/red]")

    assert "\x1b[" in buf.getvalue()
    assert console.no_color is False


def test_project_override_beats_absent_no_color(monkeypatch):
    """CODE_PUPPY_NO_COLOR=1 works even when NO_COLOR is unset."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CODE_PUPPY_NO_COLOR", "1")

    buf = io.StringIO()
    console = Console(
        no_color=_no_color_setting(), force_terminal=True, file=buf, width=40
    )
    console.print("[red]danger[/red]")

    assert "\x1b[" not in buf.getvalue()
