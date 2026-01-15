"""Tests for markdown_to_html conversion in msgraph tools."""

import pytest

from code_puppy.tools.msgraph.common import markdown_to_html


class TestMarkdownToHtml:
    """Test the markdown_to_html conversion function."""

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert markdown_to_html("") == ""

    def test_none_returns_none(self):
        """None returns None."""
        assert markdown_to_html(None) is None

    def test_bold_double_asterisk(self):
        """**bold** converts to <strong>."""
        result = markdown_to_html("This is **bold** text")
        assert "<strong>bold</strong>" in result

    def test_bold_double_underscore(self):
        """__bold__ converts to <strong>."""
        result = markdown_to_html("This is __bold__ text")
        assert "<strong>bold</strong>" in result

    def test_italic_single_asterisk(self):
        """*italic* converts to <em>."""
        result = markdown_to_html("This is *italic* text")
        assert "<em>italic</em>" in result

    def test_italic_single_underscore(self):
        """_italic_ converts to <em>."""
        result = markdown_to_html("This is _italic_ text")
        assert "<em>italic</em>" in result

    def test_inline_code(self):
        """`code` converts to styled <code>."""
        result = markdown_to_html("Use `git commit` command")
        assert "<code" in result
        assert "git commit" in result

    def test_code_block(self):
        """```code block``` converts to styled <pre>."""
        result = markdown_to_html("Here is code:\n```\nprint('hello')\n```")
        assert "<pre" in result
        assert "print" in result

    def test_header_h1(self):
        """# Header converts to <h1>."""
        result = markdown_to_html("# Main Title")
        assert "<h1>Main Title</h1>" in result

    def test_header_h2(self):
        """## Header converts to <h2>."""
        result = markdown_to_html("## Section Title")
        assert "<h2>Section Title</h2>" in result

    def test_header_h3(self):
        """### Header converts to <h3>."""
        result = markdown_to_html("### Subsection")
        assert "<h3>Subsection</h3>" in result

    def test_horizontal_rule(self):
        """--- converts to <hr>."""
        result = markdown_to_html("Above\n---\nBelow")
        assert "<hr>" in result

    def test_bullet_list(self):
        """- items convert to <ul><li>."""
        result = markdown_to_html("- Item 1\n- Item 2\n- Item 3")
        assert "<ul>" in result
        assert "<li>Item 1</li>" in result
        assert "<li>Item 2</li>" in result
        assert "</ul>" in result

    def test_numbered_list(self):
        """1. items convert to <ol><li>."""
        result = markdown_to_html("1. First\n2. Second\n3. Third")
        assert "<ol>" in result
        assert "<li>First</li>" in result
        assert "<li>Second</li>" in result
        assert "</ol>" in result

    def test_link(self):
        """[text](url) converts to <a href>."""
        result = markdown_to_html("Visit [Google](https://google.com)")
        assert '<a href="https://google.com">Google</a>' in result

    def test_html_escaping(self):
        """HTML special characters are escaped."""
        result = markdown_to_html("Use <script> and & symbols")
        assert "&lt;script&gt;" in result
        assert "&amp;" in result

    def test_code_block_preserves_content(self):
        """Code blocks preserve their content without markdown processing."""
        result = markdown_to_html("```\n**not bold** and *not italic*\n```")
        # Inside code block, markdown should NOT be processed
        assert "<strong>" not in result or "**not bold**" in result

    def test_complex_document(self):
        """Complex markdown document converts properly."""
        md = """# Trade Notes

**Project A:** This is *important* work.

**Why this matters:** It saves time.

---

**Project B:** More work here.

- Item one
- Item two

Visit [our docs](https://example.com) for more.
"""
        result = markdown_to_html(md)
        assert "<h1>Trade Notes</h1>" in result
        assert "<strong>Project A:</strong>" in result
        assert "<em>important</em>" in result
        assert "<hr>" in result
        assert "<ul>" in result
        assert '<a href="https://example.com">our docs</a>' in result
