"""Tests for the Textual prompt's drag-and-drop attachment placeholders.

These mirror the classic prompt_toolkit `[png image]` display: dragged image/
document paths become friendly placeholders in the buffer, then expand back to
real paths at submit time so attachment parsing still loads the bytes.
"""

from __future__ import annotations

import os

import pytest

from code_puppy.command_line.attachments import parse_prompt_attachments
from code_puppy.tui.app import PromptArea, build_app
from code_puppy.tui.attachments import (
    expand_placeholders,
    placeholder_spans,
    transform_dragged_paths,
)


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "shot.png"
    p.write_bytes(b"\x89PNG\r\n")
    return str(p)


@pytest.fixture
def spaced_jpg(tmp_path):
    p = tmp_path / "my pic.jpg"
    p.write_bytes(b"\xff\xd8\xff")
    return str(p)


def test_empty_text_is_noop():
    assert transform_dragged_paths("") == ("", [])


def test_single_image_becomes_placeholder(png):
    display, mapping = transform_dragged_paths(png)
    assert display == "[png image]"
    assert mapping == [("[png image]", png)]


def test_surrounding_text_is_preserved(png):
    display, mapping = transform_dragged_paths(f"describe {png} please")
    assert display == "describe [png image] please"
    assert expand_placeholders(display, mapping) == f"describe {png} please"


def test_pdf_becomes_document_chip(tmp_path):
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 hello")
    display, mapping = transform_dragged_paths(f"summarise {pdf}")
    assert display == "summarise [pdf document]"
    expanded = expand_placeholders(display, mapping)
    processed = parse_prompt_attachments(expanded)
    assert processed.prompt == "summarise"
    assert len(processed.attachments) == 1
    assert processed.attachments[0].content.media_type == "application/pdf"


def test_text_file_is_not_attached(tmp_path):
    # Text/code files stay as raw paths (read_file's job), not binary chips.
    txt = tmp_path / "notes.txt"
    txt.write_text("hello")
    display, mapping = transform_dragged_paths(f"read {txt}")
    assert display == f"read {txt}"
    assert mapping == []


def test_nonexistent_path_is_not_transformed():
    display, mapping = transform_dragged_paths("/nope/notreal.png")
    assert display == "/nope/notreal.png"
    assert mapping == []


def test_escaped_spaces_roundtrip_to_escaped_path(spaced_jpg):
    dragged = spaced_jpg.replace(" ", r"\ ")
    display, mapping = transform_dragged_paths(dragged)
    assert display == "[jpg image]"
    expanded = expand_placeholders(display, mapping)
    # Spaces are re-escaped so the attachment parser tokenises correctly.
    assert expanded == spaced_jpg.replace(" ", r"\ ")


def test_two_images_map_back_in_order(tmp_path):
    a = tmp_path / "a.png"
    a.write_bytes(b"a")
    b = tmp_path / "b.png"
    b.write_bytes(b"b")
    display, mapping = transform_dragged_paths(f"{a} {b}")
    assert display == "[png image] [png image]"
    assert expand_placeholders(display, mapping) == f"{a} {b}"


def test_stale_placeholder_is_skipped(png):
    _display, mapping = transform_dragged_paths(png)
    # User deleted the placeholder before submitting -> nothing to expand.
    assert expand_placeholders("just words", mapping) == "just words"


def test_placeholder_spans_finds_every_occurrence():
    plain = "look [png image] and [png image] plus [jpg image]"
    spans = placeholder_spans(plain, ["[png image]", "[jpg image]"])
    # Two png + one jpg occurrences.
    assert len(spans) == 3
    for start, end in spans:
        assert plain[start:end] in ("[png image]", "[jpg image]")


def test_placeholder_spans_empty_when_absent():
    assert placeholder_spans("no placeholders here", ["[png image]"]) == []
    assert placeholder_spans("text", []) == []


def test_placeholder_spans_styles_rich_text():
    from rich.style import Style
    from rich.text import Text

    line = Text("see [png image] now")
    style = Style(color="cyan", italic=True)
    for start, end in placeholder_spans(line.plain, ["[png image]"]):
        line.stylize(style, start, end)
    # The placeholder span carries the italic-cyan style; surrounding text not.
    styled = {(s.start, s.end, s.style) for s in line.spans}
    assert (4, 15, style) in styled


def test_end_to_end_loads_attachment(spaced_jpg):
    dragged = "look at " + spaced_jpg.replace(" ", r"\ ")
    display, mapping = transform_dragged_paths(dragged)
    expanded = expand_placeholders(display, mapping)
    processed = parse_prompt_attachments(expanded)
    assert processed.prompt == "look at"
    assert len(processed.attachments) == 1
    assert processed.attachments[0].content.media_type == "image/jpeg"
    assert os.path.basename(processed.attachments[0].placeholder) == "my pic.jpg"


@pytest.mark.asyncio
async def test_buffer_path_is_transformed_live(png):
    """A path landing in the prompt (drag/paste/typing) becomes a chip."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", PromptArea)
        prompt.text = f"what is in {png}"
        await pilot.pause()
        # Buffer now shows the friendly placeholder, not the raw path.
        assert prompt.text == "what is in [png image]"
        assert app._attachment_placeholders == [("[png image]", png)]


@pytest.mark.asyncio
async def test_submit_expands_placeholder_to_real_path(monkeypatch, png):
    captured = {}

    async def fake_run(_agent, task, *, display_console=None, use_run_ui=True):
        captured["task"] = task

        class _R:
            output = "ok"

            def all_messages(self):
                return []

        return _R(), None

    class _Agent:
        def set_message_history(self, _h):
            pass

    monkeypatch.setattr("code_puppy.agents.get_current_agent", lambda: _Agent())
    monkeypatch.setattr("code_puppy.cli_runner.run_prompt_with_attachments", fake_run)
    monkeypatch.setattr("code_puppy.config.auto_save_session_if_enabled", lambda: None)

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", PromptArea)
        prompt.text = f"describe {png}"
        await pilot.pause()
        assert prompt.text == "describe [png image]"
        app.submit_prompt(prompt.text)
        for _ in range(60):
            await pilot.pause(0.02)
            if "task" in captured:
                break
        # The agent receives the REAL path, not the placeholder.
        assert captured["task"] == f"describe {png}"
        # Mapping is consumed after submit.
        assert app._attachment_placeholders == []
