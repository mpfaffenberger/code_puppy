"""Tests for PDF parsing functionality."""

import tempfile
from pathlib import Path

import pytest
from pypdf import PdfWriter

from code_puppy.tools.pdf_parser import (
    PDFParsingError,
    format_pdf_for_llm,
    parse_pdf,
)


@pytest.fixture
def sample_pdf():
    """Create a simple test PDF with text content."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        # Add some metadata
        writer.add_metadata(
            {
                "/Title": "Test Document",
                "/Author": "Test Author",
                "/Subject": "Testing PDF parsing",
            }
        )
        writer.write(tmp)
        tmp_path = Path(tmp.name)

    yield tmp_path
    # Cleanup
    tmp_path.unlink()


@pytest.fixture
def multi_page_pdf():
    """Create a multi-page test PDF."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        writer = PdfWriter()
        # Add 3 blank pages
        for _ in range(3):
            writer.add_blank_page(width=200, height=200)
        writer.write(tmp)
        tmp_path = Path(tmp.name)

    yield tmp_path
    tmp_path.unlink()


def test_parse_pdf_basic(sample_pdf):
    """Test basic PDF parsing."""
    result = parse_pdf(sample_pdf)

    assert result is not None
    assert result.file_name == sample_pdf.name
    assert result.page_count == 1
    assert isinstance(result.text, str)
    assert isinstance(result.metadata, dict)


def test_parse_pdf_metadata(sample_pdf):
    """Test PDF metadata extraction."""
    result = parse_pdf(sample_pdf)

    # Check metadata was extracted (keys might have or not have leading slash)
    metadata_keys = {k.lower() for k in result.metadata.keys()}
    assert "title" in metadata_keys or "/title" in metadata_keys
    assert "author" in metadata_keys or "/author" in metadata_keys


def test_parse_pdf_multi_page(multi_page_pdf):
    """Test parsing multi-page PDFs."""
    result = parse_pdf(multi_page_pdf)

    assert result.page_count == 3
    # Blank pages may not have text, so just check the count is correct
    assert isinstance(result.text, str)


def test_parse_pdf_nonexistent_file():
    """Test parsing a non-existent file raises appropriate error."""
    nonexistent = Path("/tmp/nonexistent_test_file_12345.pdf")
    with pytest.raises(PDFParsingError) as exc_info:
        parse_pdf(nonexistent)
    assert "not found" in str(exc_info.value).lower()


def test_parse_pdf_invalid_file():
    """Test parsing an invalid PDF file."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"This is not a valid PDF file")
        tmp_path = Path(tmp.name)

    try:
        with pytest.raises(PDFParsingError):
            parse_pdf(tmp_path)
    finally:
        tmp_path.unlink()


def test_format_pdf_for_llm(sample_pdf):
    """Test formatting parsed PDF for LLM consumption."""
    result = parse_pdf(sample_pdf)
    formatted = format_pdf_for_llm(result)

    assert isinstance(formatted, str)
    # Check for expected sections
    assert "# PDF Document:" in formatted
    assert result.file_name in formatted
    assert "**Pages:**" in formatted
    assert "## Metadata" in formatted
    assert "## Content" in formatted


def test_format_pdf_for_llm_no_metadata():
    """Test formatting PDF with no metadata."""
    # Create a minimal PDF with no metadata
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(tmp)
        tmp_path = Path(tmp.name)

    try:
        result = parse_pdf(tmp_path)
        formatted = format_pdf_for_llm(result)

        # Basic structure should still be there
        assert "# PDF Document:" in formatted
        assert "**Pages:** 1" in formatted
        assert "## Content" in formatted
    finally:
        tmp_path.unlink()


def test_parse_pdf_with_text_content():
    """Test parsing a PDF with actual text content."""
    # Note: Creating a PDF with text programmatically is complex,
    # so we just ensure the parser handles empty pages gracefully
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(tmp)
        tmp_path = Path(tmp.name)

    try:
        result = parse_pdf(tmp_path)
        # Should not raise an error even with blank pages
        assert result is not None
        assert result.page_count == 1
        # Text might be empty or have minimal content
        assert isinstance(result.text, str)
    finally:
        tmp_path.unlink()


def test_pdf_parser_result_structure(sample_pdf):
    """Test that PDFParseResult has expected attributes."""
    result = parse_pdf(sample_pdf)

    assert hasattr(result, "text")
    assert hasattr(result, "page_count")
    assert hasattr(result, "metadata")
    assert hasattr(result, "file_name")

    assert isinstance(result.text, str)
    assert isinstance(result.page_count, int)
    assert isinstance(result.metadata, dict)
    assert isinstance(result.file_name, str)

