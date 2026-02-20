"""Tests for code_puppy.messaging.markdown_patches."""

from io import StringIO

from rich.console import Console
from rich.markdown import Markdown

from code_puppy.messaging.markdown_patches import (
    LeftJustifiedHeading,
    patch_markdown_headings,
)


def test_patch_markdown_headings_idempotent():
    """Calling patch_markdown_headings multiple times is safe."""
    patch_markdown_headings()
    patch_markdown_headings()  # Should be no-op
    assert Markdown.elements["heading_open"] is LeftJustifiedHeading


def test_left_justified_heading_h1():
    """H1 should render as a panel."""
    console = Console(file=StringIO(), force_terminal=False, width=80)
    patch_markdown_headings()
    md = Markdown("# Hello World")
    console.print(md)
    output = console.file.getvalue()
    assert "Hello World" in output


def test_left_justified_heading_h2():
    """H2 should render as styled text with blank line."""
    console = Console(file=StringIO(), force_terminal=False, width=80)
    patch_markdown_headings()
    md = Markdown("## Section Title")
    console.print(md)
    output = console.file.getvalue()
    assert "Section Title" in output


def test_left_justified_heading_h3():
    """H3+ should render as styled text."""
    console = Console(file=StringIO(), force_terminal=False, width=80)
    patch_markdown_headings()
    md = Markdown("### Subsection")
    console.print(md)
    output = console.file.getvalue()
    assert "Subsection" in output
