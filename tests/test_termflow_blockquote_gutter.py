"""Tests for ``patch_termflow_blockquote_gutter`` (copyable-output fix).

Real-world trigger: an agent replies with a markdown blockquote meant to be
pasted verbatim (a Slack reply, a command block) that contains a fenced code
block. Before the fix, termflow rendered every quoted line with a literal
``│`` gutter glyph that survives copy/paste, and -- because its blockquote
parser never re-runs fence detection on quoted content -- a nested fence
was misread as inline markdown, eating characters (``"*$p*"`` lost its
asterisks).

These tests render that exact shape through termflow's real ``Parser`` +
``Renderer`` (ANSI stripped, since that's what a terminal mouse-select
copies) and assert byte-for-byte fidelity with no decoration.
"""

import io
import re

import pytest

from code_puppy import pydantic_patches

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
GUTTER_CHARS = ("\u2502", "\u258c")  # │, ▌

MADISON_REPLY = (
    "Reply you can paste to Madison\n"
    "---\n"
    "> Hey Madison, your screenshots explain it. Try this:\n"
    ">\n"
    "> ```powershell\n"
    '> $mirror = "https://generic.example.com/repo"\n'
    '> if ($userPath -notlike "*$p*") { Write-Host "not found" }\n'
    "> ```\n"
)


def _render_plain(markdown_text: str, *, width: int = 80) -> str:
    """Render markdown through termflow and strip ANSI, like a mouse-select."""
    from termflow import Parser, Renderer
    from termflow.render.style import RenderFeatures

    out = io.StringIO()
    parser = Parser()
    renderer = Renderer(
        output=out, width=width, features=RenderFeatures(clipboard=False)
    )
    for line in markdown_text.split("\n"):
        renderer.render_all(parser.parse_line(line))
    renderer.render_all(parser.finalize())
    return ANSI_RE.sub("", out.getvalue())


@pytest.fixture
def restore_termflow_parser():
    """Undo the monkeypatch so other tests see termflow's stock parser."""
    from termflow.parser import Parser

    original = Parser.parse_line
    yield
    Parser.parse_line = original


def test_patch_applies(restore_termflow_parser):
    assert pydantic_patches.patch_termflow_blockquote_gutter() is True


def test_patch_is_idempotent(restore_termflow_parser):
    from termflow.parser import Parser

    assert pydantic_patches.patch_termflow_blockquote_gutter() is True
    patched = Parser.parse_line

    assert pydantic_patches.patch_termflow_blockquote_gutter() is True
    assert Parser.parse_line is patched


def test_quoted_fenced_code_has_no_gutter(restore_termflow_parser):
    pydantic_patches.patch_termflow_blockquote_gutter()

    plain = _render_plain(MADISON_REPLY)

    for gutter in GUTTER_CHARS:
        assert gutter not in plain, f"{gutter!r} gutter leaked into: {plain!r}"


def test_quoted_fenced_code_preserves_emphasis_and_quotes(restore_termflow_parser):
    pydantic_patches.patch_termflow_blockquote_gutter()

    plain = _render_plain(MADISON_REPLY)

    # The literal *$p* must survive -- not be eaten as markdown emphasis.
    assert '"*$p*"' in plain
    # Quoted strings inside the fence must survive untouched.
    assert '"https://generic.example.com/repo"' in plain
    assert '"not found"' in plain


def test_quoted_fenced_code_has_no_leading_pad(restore_termflow_parser):
    pydantic_patches.patch_termflow_blockquote_gutter()

    plain = _render_plain(MADISON_REPLY)
    code_line = next(line for line in plain.split("\n") if line.startswith("$mirror"))

    # No leading whitespace/gutter was prepended to the actual code content.
    assert code_line.startswith("$mirror ="), repr(code_line)


def test_quoted_prose_line_also_loses_its_gutter(restore_termflow_parser):
    """Non-code quoted lines are copyable too -- the whole reply, not just code."""
    pydantic_patches.patch_termflow_blockquote_gutter()

    plain = _render_plain(MADISON_REPLY)
    assert "Hey Madison, your screenshots explain it. Try this:" in plain
    prose_line = next(line for line in plain.split("\n") if "Hey Madison" in line)
    for gutter in GUTTER_CHARS:
        assert gutter not in prose_line


def test_real_top_level_code_with_literal_gt_is_untouched(restore_termflow_parser):
    """A non-quoted fence containing a literal '>' (e.g. a shell redirect)
    must not be corrupted by the blockquote-flattening logic."""
    pydantic_patches.patch_termflow_blockquote_gutter()

    sample = "```bash\necho hi > output.txt\n```\n"
    plain = _render_plain(sample)

    assert "echo hi > output.txt" in plain


def _code_lines(plain: str) -> list[str]:
    return [line.rstrip() for line in plain.split("\n")]


def test_single_quoted_fence_keeps_literal_gt_lines(restore_termflow_parser):
    """Issue #979: inside a depth-one quoted fence, only one ``>`` is the
    quote marker; a code line that itself starts with ``>`` must keep it."""
    pydantic_patches.patch_termflow_blockquote_gutter()

    sample = "> ```sh\n> > output.txt\n> >> append.txt\n> echo ok\n> ```\n"
    lines = _code_lines(_render_plain(sample))

    assert "> output.txt" in lines
    assert ">> append.txt" in lines
    assert "echo ok" in lines


def test_nested_quoted_fence_strips_only_its_depth(restore_termflow_parser):
    pydantic_patches.patch_termflow_blockquote_gutter()

    sample = "> > ```sh\n> > > output.txt\n> > echo ok\n> > ```\n"
    lines = _code_lines(_render_plain(sample))

    assert "> output.txt" in lines
    assert "echo ok" in lines


def test_indented_quoted_fence_keeps_literal_gt_lines(restore_termflow_parser):
    pydantic_patches.patch_termflow_blockquote_gutter()

    sample = "  > ```sh\n  > > output.txt\n  > ```\n"
    lines = _code_lines(_render_plain(sample))

    assert "> output.txt" in lines


def test_text_after_quoted_fence_is_still_dequoted(restore_termflow_parser):
    pydantic_patches.patch_termflow_blockquote_gutter()

    sample = "> ```sh\n> > output.txt\n> ```\n> after the fence\n"
    plain = _render_plain(sample)

    assert "after the fence" in plain
    for gutter in GUTTER_CHARS:
        assert gutter not in plain
