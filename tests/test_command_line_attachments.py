"""Tests for CLI attachment parsing and execution helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import BinaryContent, DocumentUrl, ImageUrl

from code_puppy.command_line.attachments import (
    DEFAULT_ACCEPTED_IMAGE_EXTENSIONS,
    parse_prompt_attachments,
)
from code_puppy.main import run_prompt_with_attachments


@pytest.mark.parametrize("extension", sorted(DEFAULT_ACCEPTED_IMAGE_EXTENSIONS))
def test_parse_prompt_attachments_handles_images(tmp_path: Path, extension: str) -> None:
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


def test_parse_prompt_detects_links() -> None:
    url = "https://example.com/cute-puppy.png"
    processed = parse_prompt_attachments(f"describe {url}")

    assert processed.prompt == "describe"
    assert processed.attachments == []
    assert [link.url_part for link in processed.link_attachments] == [ImageUrl(url=url)]


@pytest.mark.asyncio
async def test_run_prompt_with_attachments_passes_binary(tmp_path: Path) -> None:
    image_path = tmp_path / "dragged.png"
    image_path.write_bytes(b"png-bytes")

    raw_prompt = f"Check this {image_path}"

    fake_agent = AsyncMock()
    fake_result = AsyncMock()
    fake_agent.run_with_mcp.return_value = fake_result

    with patch("code_puppy.messaging.emit_warning") as mock_warn, patch(
        "code_puppy.messaging.emit_system_message"
    ) as mock_system:
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

    with patch("code_puppy.messaging.spinner.ConsoleSpinner") as mock_spinner, patch(
        "code_puppy.messaging.emit_system_message"
    ), patch("code_puppy.messaging.emit_warning"):
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

    with patch("code_puppy.messaging.emit_warning") as mock_warn, patch(
        "code_puppy.messaging.emit_system_message"
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
    "raw, expected_url_type",
    [
        ("https://example.com/file.pdf", DocumentUrl),
        ("https://example.com/image.png", ImageUrl),
    ],
)
def test_parse_prompt_returns_correct_link_types(raw: str, expected_url_type: type[Any]) -> None:
    processed = parse_prompt_attachments(raw)

    assert processed.prompt == ""
    assert len(processed.link_attachments) == 1
    assert isinstance(processed.link_attachments[0].url_part, expected_url_type)
