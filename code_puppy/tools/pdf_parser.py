"""PDF parsing utilities for extracting text and metadata from PDF documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader


@dataclass
class PDFParseResult:
    """Result of parsing a PDF document."""

    text: str
    page_count: int
    metadata: dict[str, Any]
    file_name: str


class PDFParsingError(Exception):
    """Raised when PDF parsing fails."""


def parse_pdf(file_path: Path) -> PDFParseResult:
    """
    Extract text and metadata from a PDF file.

    Args:
        file_path: Path to the PDF file

    Returns:
        PDFParseResult containing extracted text, page count, and metadata

    Raises:
        PDFParsingError: If the PDF cannot be parsed
    """
    try:
        reader = PdfReader(file_path)

        # Extract text from all pages
        text_parts: list[str] = []
        for page_num, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text()
                if page_text.strip():
                    text_parts.append(f"--- Page {page_num} ---\n{page_text}\n")
            except Exception as e:
                # Continue even if a single page fails
                text_parts.append(
                    f"--- Page {page_num} ---\n[Error extracting text: {str(e)}]\n"
                )

        full_text = "\n".join(text_parts)

        # Extract metadata
        metadata = {}
        if reader.metadata:
            for key, value in reader.metadata.items():
                # Clean up metadata keys (remove leading slash)
                clean_key = key.lstrip("/") if isinstance(key, str) else str(key)
                metadata[clean_key] = value

        return PDFParseResult(
            text=full_text,
            page_count=len(reader.pages),
            metadata=metadata,
            file_name=file_path.name,
        )

    except FileNotFoundError as e:
        raise PDFParsingError(f"PDF file not found: {file_path}") from e
    except Exception as e:
        raise PDFParsingError(f"Failed to parse PDF {file_path}: {str(e)}") from e


def format_pdf_for_llm(parse_result: PDFParseResult) -> str:
    """
    Format parsed PDF content in a way that's optimal for LLM consumption.

    Args:
        parse_result: The parsed PDF result

    Returns:
        Formatted string with PDF metadata and content
    """
    lines = [
        f"# PDF Document: {parse_result.file_name}",
        "",
        f"**Pages:** {parse_result.page_count}",
        "",
    ]

    # Add metadata if available
    if parse_result.metadata:
        lines.append("## Metadata")
        for key, value in parse_result.metadata.items():
            lines.append(f"- **{key}:** {value}")
        lines.append("")

    # Add content
    lines.append("## Content")
    lines.append("")
    lines.append(parse_result.text.strip())

    return "\n".join(lines)


__all__ = ["parse_pdf", "format_pdf_for_llm", "PDFParseResult", "PDFParsingError"]

