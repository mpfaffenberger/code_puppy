"""Patches for Rich's Markdown rendering.

- Headings: Rich hardcodes them to center-justified; we want left.
- Code blocks: Rich pads every line to fill a rectangular highlight
  background, and that padding survives copy/paste (#505). See
  ``NoPadCodeBlock``.
"""

from rich import box
from rich.markdown import CodeBlock, Heading, Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
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


class NoPadCodeBlock(CodeBlock):
    """Code block with per-character background but no padding (#505).

    Rich's default ``CodeBlock`` pads every line to width so the theme
    background fills a rectangle -- that padding survives copy/paste.
    We bypass ``Syntax``'s line-filling and yield each highlighted line
    directly: theme background stays on real characters, box is "ragged"
    (hugs each line's own width) instead of a filled rectangle. Language
    label + boundary drawn with ``Rule``.
    """

    def __rich_console__(self, console, options):
        code = str(self.text).rstrip()
        syntax = Syntax(
            code,
            self.lexer_name,
            theme=self.theme,
            word_wrap=True,
            background_color=None,
        )
        yield Rule(title=self.lexer_name, align="left", style="dim")
        for line in syntax.highlight(code).split("\n"):
            # ``Text.highlight()`` sets ``justify="left"`` for opaque
            # backgrounds, which re-pads to container width. Undo it;
            # per-character bg from the base style is unaffected.
            line.justify = None
            yield line
        yield Rule(style="dim")


_patched = False


def patch_markdown():
    """Install left-justified headings + unpadded code blocks. Idempotent."""
    global _patched
    if _patched:
        return

    Markdown.elements["heading_open"] = LeftJustifiedHeading
    Markdown.elements["fence"] = NoPadCodeBlock
    Markdown.elements["code_block"] = NoPadCodeBlock
    _patched = True


__all__ = ["patch_markdown", "LeftJustifiedHeading", "NoPadCodeBlock"]
