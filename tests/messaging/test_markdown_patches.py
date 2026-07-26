"""Tests for code_puppy.messaging.markdown_patches."""

from io import StringIO

from rich.console import Console
from rich.markdown import Markdown

from code_puppy.messaging.markdown_patches import (
    LeftJustifiedHeading,
    NoPadCodeBlock,
    patch_markdown,
)


def test_patch_markdown_idempotent():
    """Calling patch_markdown multiple times is safe."""
    patch_markdown()
    patch_markdown()  # Should be no-op
    assert Markdown.elements["heading_open"] is LeftJustifiedHeading
    assert Markdown.elements["fence"] is NoPadCodeBlock
    assert Markdown.elements["code_block"] is NoPadCodeBlock


def test_left_justified_heading_h1():
    """H1 should render as a panel."""
    console = Console(file=StringIO(), force_terminal=False, width=80)
    patch_markdown()
    md = Markdown("# Hello World")
    console.print(md)
    output = console.file.getvalue()
    assert "Hello World" in output


def test_left_justified_heading_h2():
    """H2 should render as styled text with blank line."""
    console = Console(file=StringIO(), force_terminal=False, width=80)
    patch_markdown()
    md = Markdown("## Section Title")
    console.print(md)
    output = console.file.getvalue()
    assert "Section Title" in output


def test_left_justified_heading_h3():
    """H3+ should render as styled text."""
    console = Console(file=StringIO(), force_terminal=False, width=80)
    patch_markdown()
    md = Markdown("### Subsection")
    console.print(md)
    output = console.file.getvalue()
    assert "Subsection" in output


def test_code_block_no_trailing_whitespace():
    """Regression for #505: code lines must not carry trailing spaces."""
    console = Console(file=StringIO(), force_terminal=False, width=40)
    patch_markdown()
    md = Markdown("```python\nprint('hi')\n```")
    console.print(md)
    output = console.file.getvalue()
    for line in output.splitlines():
        assert line == line.rstrip(), f"line has trailing whitespace: {line!r}"


def test_code_block_indented_no_trailing_whitespace():
    """Regression for #505: indented (non-fenced) code blocks too."""
    console = Console(file=StringIO(), force_terminal=False, width=40)
    patch_markdown()
    md = Markdown("    print('hi')\n    print('bye')")
    console.print(md)
    output = console.file.getvalue()
    assert "print" in output  # sanity: block actually rendered
    for line in output.splitlines():
        assert line == line.rstrip(), f"line has trailing whitespace: {line!r}"


def test_code_block_still_highlighted():
    """Removing padding must not disable syntax highlighting."""
    console = Console(
        file=StringIO(), force_terminal=True, width=40, color_system="standard"
    )
    patch_markdown()
    md = Markdown("```python\ndef foo():\n    return 1\n```")
    console.print(md)
    output = console.file.getvalue()
    assert "\x1b[" in output  # ANSI styling present => tokens still colored


def test_code_block_has_real_background_color():
    """Ragged box still paints per-character theme background (#505)."""
    console = Console(
        file=StringIO(), force_terminal=True, width=40, color_system="truecolor"
    )
    patch_markdown()
    md = Markdown("```python\nprint('hi')\n```")
    console.print(md)
    output = console.file.getvalue()
    assert "48;2;" in output  # 48;2;r;g;b = truecolor background SGR code
