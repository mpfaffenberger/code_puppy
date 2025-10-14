"""Tests for CLI attachment parsing and execution helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import BinaryContent

from code_puppy.command_line.attachments import (
    DEFAULT_ACCEPTED_IMAGE_EXTENSIONS,
    parse_prompt_attachments,
)
from code_puppy.main import run_prompt_with_attachments


@pytest.mark.parametrize("extension", sorted(DEFAULT_ACCEPTED_IMAGE_EXTENSIONS))
def test_parse_prompt_attachments_handles_images(
    tmp_path: Path, extension: str
) -> None:
    attachment_path = tmp_path / f"image{extension}"
    attachment_path.write_bytes(b"fake-bytes")

    processed = parse_prompt_attachments(str(attachment_path))

    assert processed.prompt == "Describe the attached files in detail."
    assert processed.attachments
    assert processed.attachments[0].content.media_type.startswith("image/")
    assert processed.warnings == []


def test_parse_prompt_attachments_handles_unquoted_spaces(tmp_path: Path) -> None:
    file_path = tmp_path / "cute pupper image.png"
    file_path.write_bytes(b"imaginary")

    raw_prompt = f"please inspect {file_path} right now"

    processed = parse_prompt_attachments(raw_prompt)

    assert processed.prompt == "please inspect right now"
    assert len(processed.attachments) == 1
    assert processed.attachments[0].content.media_type.startswith("image/")
    assert processed.warnings == []


def test_parse_prompt_handles_dragged_escaped_spaces(tmp_path: Path) -> None:
    # Simulate a path with backslash-escaped spaces as produced by drag-and-drop
    file_path = tmp_path / "cute pupper image.png"
    file_path.write_bytes(b"imaginary")

    # Simulate terminal drag-and-drop: insert backslash before spaces
    escaped_display_path = str(file_path).replace(" ", r"\ ")
    raw_prompt = f"please inspect {escaped_display_path} right now"

    processed = parse_prompt_attachments(raw_prompt)

    assert processed.prompt == "please inspect right now"
    assert len(processed.attachments) == 1
    assert processed.attachments[0].content.media_type.startswith("image/")
    assert processed.warnings == []


def test_parse_prompt_attachments_trims_trailing_punctuation(tmp_path: Path) -> None:
    file_path = tmp_path / "doggo photo.png"
    file_path.write_bytes(b"bytes")

    processed = parse_prompt_attachments(f"look {file_path}, please")

    assert processed.prompt == "look please"
    assert len(processed.attachments) == 1
    assert processed.attachments[0].content.media_type.startswith("image/")
    assert processed.warnings == []


def test_parse_prompt_skips_unsupported_types(tmp_path: Path) -> None:
    unsupported = tmp_path / "notes.xyz"
    unsupported.write_text("hello")

    processed = parse_prompt_attachments(str(unsupported))

    assert processed.prompt == str(unsupported)
    assert processed.attachments == []
    assert "Unsupported attachment type" in processed.warnings[0]


def test_parse_prompt_leaves_urls_untouched() -> None:
    url = "https://example.com/cute-puppy.png"
    processed = parse_prompt_attachments(f"describe {url}")

    assert processed.prompt == f"describe {url}"
    assert processed.attachments == []
    assert processed.link_attachments == []


@pytest.mark.asyncio
async def test_run_prompt_with_attachments_passes_binary(tmp_path: Path) -> None:
    image_path = tmp_path / "dragged.png"
    image_path.write_bytes(b"png-bytes")

    raw_prompt = f"Check this {image_path}"

    fake_agent = AsyncMock()
    fake_result = AsyncMock()
    fake_agent.run_with_mcp.return_value = fake_result

    with (
        patch("code_puppy.messaging.emit_warning") as mock_warn,
        patch("code_puppy.messaging.emit_system_message") as mock_system,
    ):
        result = await run_prompt_with_attachments(
            fake_agent,
            raw_prompt,
            spinner_console=None,
        )

    assert result is fake_result
    fake_agent.run_with_mcp.assert_awaited_once()
    _, kwargs = fake_agent.run_with_mcp.await_args
    assert kwargs["attachments"]
    assert isinstance(kwargs["attachments"][0], BinaryContent)
    assert kwargs["link_attachments"] == []
    mock_warn.assert_not_called()
    mock_system.assert_called_once()


@pytest.mark.asyncio
async def test_run_prompt_with_attachments_uses_spinner(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF")

    fake_agent = AsyncMock()
    fake_agent.run_with_mcp.return_value = AsyncMock()

    dummy_console = object()

    with (
        patch("code_puppy.messaging.spinner.ConsoleSpinner") as mock_spinner,
        patch("code_puppy.messaging.emit_system_message"),
        patch("code_puppy.messaging.emit_warning"),
    ):
        await run_prompt_with_attachments(
            fake_agent,
            f"please summarise {pdf_path}",
            spinner_console=dummy_console,
            use_spinner=True,
        )

    mock_spinner.assert_called_once()
    args, kwargs = mock_spinner.call_args
    assert kwargs["console"] is dummy_console


@pytest.mark.asyncio
async def test_run_prompt_with_attachments_warns_on_blank_prompt() -> None:
    fake_agent = AsyncMock()

    with (
        patch("code_puppy.messaging.emit_warning") as mock_warn,
        patch("code_puppy.messaging.emit_system_message"),
    ):
        result = await run_prompt_with_attachments(
            fake_agent,
            "   ",
            spinner_console=None,
            use_spinner=False,
        )

    assert result is None
    fake_agent.run_with_mcp.assert_not_called()
    mock_warn.assert_called_once()


@pytest.mark.parametrize(
    "raw",
    [
        "https://example.com/file.pdf",
        "https://example.com/image.png",
    ],
)
def test_parse_prompt_does_not_parse_urls_anymore(raw: str) -> None:
    processed = parse_prompt_attachments(raw)

    assert processed.prompt == raw
    assert processed.link_attachments == []


def test_parse_prompt_handles_very_long_tokens() -> None:
    """Test that extremely long tokens don't cause ENAMETOOLONG errors."""
    # Create a token longer than MAX_PATH_LENGTH (1024)
    long_garbage = "a" * 2000
    prompt = f"some text {long_garbage} more text"

    # Should not raise, should just skip the long token
    processed = parse_prompt_attachments(prompt)

    # The long token should be preserved in output since it's not a valid path
    assert "some text" in processed.prompt
    assert "more text" in processed.prompt
    assert processed.attachments == []


def test_parse_prompt_handles_long_paragraph_paste() -> None:
    """Test that pasting long error messages doesn't cause slowdown."""
    # Simulate pasting a long error message with fake paths
    long_text = (
        "File /Users/testuser/.code-puppy-venv/lib/python3.13/site-packages/prompt_toolkit/layout/processors.py, "
        "line 948, in apply_transformation return processor.apply_transformation(ti) "
        * 20
    )

    # Should handle gracefully without errors
    processed = parse_prompt_attachments(long_text)

    # Should preserve the text (paths won't exist so won't be treated as attachments)
    assert "apply_transformation" in processed.prompt
    assert processed.attachments == []
