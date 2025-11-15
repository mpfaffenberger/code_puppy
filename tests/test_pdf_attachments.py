"""Tests for PDF attachment parsing in command line interface."""

import tempfile
from pathlib import Path

import pytest
from pypdf import PdfWriter

from code_puppy.command_line.attachments import parse_prompt_attachments


@pytest.fixture
def test_pdf():
    """Create a test PDF file."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_metadata(
            {
                "/Title": "Test PDF",
                "/Author": "Test Author",
            }
        )
        writer.write(tmp)
        tmp_path = Path(tmp.name)

    yield tmp_path
    tmp_path.unlink()


def test_parse_pdf_attachment(test_pdf):
    """Test parsing a prompt with a PDF attachment."""
    prompt = f"Analyze this document {test_pdf}"
    result = parse_prompt_attachments(prompt)

    assert len(result.pdf_texts) == 1
    assert "# PDF Document:" in result.pdf_texts[0]
    assert test_pdf.name in result.pdf_texts[0]
    # PDF text should be appended to prompt
    assert "# PDF Document:" in result.prompt
    assert "Analyze this document" in result.prompt


def test_parse_pdf_attachment_quoted_path(test_pdf):
    """Test parsing PDF attachment with quoted path."""
    prompt = f'Summarize "{test_pdf}"'
    result = parse_prompt_attachments(prompt)

    assert len(result.pdf_texts) == 1
    assert "Summarize" in result.prompt
    assert "# PDF Document:" in result.prompt


def test_parse_pdf_attachment_with_spaces(tmp_path):
    """Test parsing PDF attachment with spaces in filename."""
    pdf_path = tmp_path / "test file with spaces.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    # Escape spaces as terminal would
    prompt = f"Review {str(pdf_path).replace(' ', r'\ ')}"
    result = parse_prompt_attachments(prompt)

    assert len(result.pdf_texts) == 1
    assert "test file with spaces.pdf" in result.pdf_texts[0]


def test_parse_multiple_pdf_attachments(tmp_path):
    """Test parsing multiple PDF attachments."""
    pdf1 = tmp_path / "doc1.pdf"
    pdf2 = tmp_path / "doc2.pdf"

    for pdf in [pdf1, pdf2]:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with open(pdf, "wb") as f:
            writer.write(f)

    prompt = f"Compare {pdf1} and {pdf2}"
    result = parse_prompt_attachments(prompt)

    assert len(result.pdf_texts) == 2
    assert "doc1.pdf" in result.pdf_texts[0]
    assert "doc2.pdf" in result.pdf_texts[1]
    # Both should be in the prompt
    assert result.pdf_texts[0] in result.prompt
    assert result.pdf_texts[1] in result.prompt


def test_parse_pdf_only_prompt(test_pdf):
    """Test parsing prompt with only PDF (no text)."""
    prompt = str(test_pdf)
    result = parse_prompt_attachments(prompt)

    assert len(result.pdf_texts) == 1
    # Prompt should contain the PDF content
    assert "# PDF Document:" in result.prompt
    assert test_pdf.name in result.prompt


def test_parse_invalid_pdf_attachment(tmp_path):
    """Test parsing an invalid PDF file."""
    invalid_pdf = tmp_path / "invalid.pdf"
    invalid_pdf.write_text("Not a real PDF")

    prompt = f"Check {invalid_pdf}"
    result = parse_prompt_attachments(prompt)

    # Should have a warning about the failed parse
    assert len(result.warnings) > 0
    assert any("Failed to parse PDF" in w for w in result.warnings)
    # PDF should not be in pdf_texts
    assert len(result.pdf_texts) == 0


def test_parse_mixed_attachments(test_pdf, tmp_path):
    """Test parsing prompt with both PDF and image attachments."""
    # Create a dummy image file
    image_path = tmp_path / "test.png"
    # Create a minimal PNG (1x1 pixel, red)
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf"
        b"\xc0\x00\x00\x00\x00\xff\xffEND\xaeB`\x82"
    )
    image_path.write_bytes(png_data)

    prompt = f"Analyze {test_pdf} and {image_path}"
    result = parse_prompt_attachments(prompt)

    # PDF should be parsed as text
    assert len(result.pdf_texts) == 1
    # Image should be binary attachment
    assert len(result.attachments) == 1
    assert result.attachments[0].content.media_type.startswith("image/")


def test_pdf_extension_case_insensitive(tmp_path):
    """Test that PDF extension matching is case-insensitive."""
    pdf_upper = tmp_path / "test.PDF"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_upper, "wb") as f:
        writer.write(f)

    prompt = f"Review {pdf_upper}"
    result = parse_prompt_attachments(prompt)

    assert len(result.pdf_texts) == 1
    assert "test.PDF" in result.pdf_texts[0]


def test_pdf_with_user_prompt(test_pdf):
    """Test PDF attachment with detailed user prompt."""
    prompt = f"Please provide a detailed analysis of {test_pdf}, focusing on the main themes and arguments"
    result = parse_prompt_attachments(prompt)

    assert len(result.pdf_texts) == 1
    # User's prompt should be preserved
    assert "detailed analysis" in result.prompt
    assert "main themes and arguments" in result.prompt
    # PDF content should be appended
    assert "# PDF Document:" in result.prompt


def test_nonexistent_pdf_path():
    """Test that non-existent PDF paths are handled gracefully."""
    prompt = "Analyze /tmp/nonexistent_file_12345.pdf"
    result = parse_prompt_attachments(prompt)

    # Should not crash, just treat as regular text since file doesn't exist
    assert len(result.pdf_texts) == 0
    assert "nonexistent_file_12345.pdf" in result.prompt or result.prompt == "Analyze"


def test_pdf_attachment_preserves_prompt_structure(test_pdf):
    """Test that PDF attachment parsing preserves complex prompt structure."""
    prompt = f"""Here's what I need:
1. Summarize {test_pdf}
2. Extract key points
3. Provide recommendations"""

    result = parse_prompt_attachments(prompt)

    assert len(result.pdf_texts) == 1
    # Original structure should be somewhat preserved
    assert "Summarize" in result.prompt
    assert "Extract key points" in result.prompt or "key" in result.prompt.lower()
    assert "PDF Document:" in result.prompt

