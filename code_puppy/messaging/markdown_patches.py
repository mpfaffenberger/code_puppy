"""Patches for Rich's Markdown rendering.

This module provides customizations to Rich's default Markdown rendering,
particularly for header justification which is hardcoded to center in Rich.
"""

from rich import box
from rich.markdown import Heading, Markdown
from rich.panel import Panel
from rich.text import Text


class LeftJustifiedHeading(Heading):
    """A heading that left-justifies text instead of centering.

    Rich's default Heading class hardcodes `text.justify = 'center'`,
    which can look odd in a CLI context. This subclass overrides that
    to use left justification instead.
    """

    def __rich_console__(self, console, options):
        """Render the heading with left justification."""
        text = self.text
        text.justify = "left"  # Override Rich's default 'center'

        if self.tag == "h1":
            # Draw a border around h1s (same as Rich default)
            yield Panel(
                text,
                box=box.HEAVY,
                style="markdown.h1.border",
            )
        else:
            # Styled text for h2 and beyond (same as Rich default)
            if self.tag == "h2":
                yield Text("")
            yield text


_patched = False


def patch_markdown_headings():
    """Patch Rich's Markdown to use left-justified headings.

    This function is idempotent - calling it multiple times has no effect
    after the first call.
    """
    global _patched
    if _patched:
        return

    Markdown.elements["heading_open"] = LeftJustifiedHeading
    _patched = True


__all__ = ["patch_markdown_headings", "LeftJustifiedHeading"]
