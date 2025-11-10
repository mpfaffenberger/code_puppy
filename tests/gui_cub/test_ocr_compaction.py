"""Tests for GUI-Cub OCR result compaction.

These tests validate success-conditional compaction of OCR results:
- Success: Returns compact data (key elements only) - 90% token reduction
- Failure: Returns full diagnostic data (all text elements)

This is critical for GUI-Cub context management since OCR can produce
200+ text elements (50k+ tokens) but we only need top 10 key elements
on success.
"""

import pytest
from code_puppy.tools.gui_cub.ocr.result_types import OCRExtractResult, TextBoundingBox
from code_puppy.tools.gui_cub.ocr.extraction import _compact_ocr_extract_result


class TestOCRResultCompaction:
    """Test OCR result compaction for context optimization."""

    def test_compact_returns_top_10_high_confidence_elements(self):
        """Should return only top 10 elements with confidence > 0.7."""
        # Create full OCR result with 50 elements
        text_elements = []
        for i in range(50):
            text_elements.append(
                TextBoundingBox(
                    text=f"Element {i}",
                    confidence=0.95 - (i * 0.01),  # Descending confidence
                    x=i * 10,
                    y=i * 10,
                    width=100,
                    height=20,
                    center_x=i * 10 + 50,
                    center_y=i * 10 + 10,
                )
            )

        full_result = OCRExtractResult(
            success=True,
            found_count=50,
            text_elements=text_elements,
            full_text=" ".join(e.text for e in text_elements),
            average_confidence=0.85,
        )

        # Compact the result
        compact = _compact_ocr_extract_result(full_result)

        # Should keep only top 10 high-confidence elements
        assert len(compact.key_elements) <= 10
        assert compact.found_count == 50  # Still reports total
        assert compact.full_text != ""  # NOW KEPT for validation!
        assert compact.text_elements == []  # Stripped

        # Verify we kept highest confidence elements (now dicts with text, x, y)
        element_texts = [e["text"] for e in compact.key_elements]
        assert "Element 0" in element_texts  # Highest confidence
        assert "Element 1" in element_texts

    def test_filters_low_confidence_elements(self):
        """Elements with confidence <= 0.7 should be filtered."""
        text_elements = [
            TextBoundingBox(
                text="High confidence",
                confidence=0.95,
                x=0,
                y=0,
                width=100,
                height=20,
                center_x=50,
                center_y=10,
            ),
            TextBoundingBox(
                text="Low confidence",
                confidence=0.5,  # Too low
                x=100,
                y=0,
                width=100,
                height=20,
                center_x=150,
                center_y=10,
            ),
            TextBoundingBox(
                text="Borderline",
                confidence=0.7,  # Exactly 0.7 - filtered
                x=200,
                y=0,
                width=100,
                height=20,
                center_x=250,
                center_y=10,
            ),
        ]

        full_result = OCRExtractResult(
            success=True,
            text_elements=text_elements,
            average_confidence=0.72,
        )

        compact = _compact_ocr_extract_result(full_result)

        # Only high confidence element should be kept (now dicts)
        element_texts = [e["text"] for e in compact.key_elements]
        assert "High confidence" in element_texts
        assert "Low confidence" not in element_texts
        assert "Borderline" not in element_texts

    def test_filters_short_text_elements(self):
        """Elements with length 0 should be filtered (whitespace), but >= 1 char allowed."""
        text_elements = [
            TextBoundingBox(
                text="ab",  # NOW ALLOWED (min_length changed from 3 to 1)
                confidence=0.95,
                x=0,
                y=0,
                width=20,
                height=20,
                center_x=10,
                center_y=10,
            ),
            TextBoundingBox(
                text="Valid text",
                confidence=0.95,
                x=100,
                y=0,
                width=100,
                height=20,
                center_x=150,
                center_y=10,
            ),
        ]

        full_result = OCRExtractResult(
            success=True,
            text_elements=text_elements,
            average_confidence=0.95,
        )

        compact = _compact_ocr_extract_result(full_result)

        # Both should be kept now (min_length = 1)
        element_texts = [e["text"] for e in compact.key_elements]
        assert "Valid text" in element_texts
        assert "ab" in element_texts  # NOW INCLUDED!

    def test_token_reduction_calculation(self):
        """Verify ~90% token reduction on compaction."""
        # Create result with 100 elements (simulating real OCR)
        text_elements = [
            TextBoundingBox(
                text=f"Element number {i} with some descriptive text",
                confidence=0.95,
                x=i * 10,
                y=i * 10,
                width=200,
                height=20,
                center_x=i * 10 + 100,
                center_y=i * 10 + 10,
            )
            for i in range(100)
        ]

        full_result = OCRExtractResult(
            success=True,
            found_count=100,
            text_elements=text_elements,
            full_text=" ".join(e.text for e in text_elements),
            average_confidence=0.95,
        )

        compact = _compact_ocr_extract_result(full_result)

        # key_elements is now list of dicts, not strings
        element_texts = [e["text"] for e in compact.key_elements]

        # Calculate approximate token counts (rough estimate)
        full_tokens = len(full_result.full_text.split()) + (len(text_elements) * 10)
        compact_tokens = len(" ".join(element_texts).split()) + 5

        reduction = (full_tokens - compact_tokens) / full_tokens

        # Should achieve at least 80% reduction (actually better now with coords!)
        assert reduction > 0.8
        assert len(compact.key_elements) <= 10

    def test_preserves_success_and_error_status(self):
        """Compaction should preserve success/error status."""
        full_result = OCRExtractResult(
            success=False,
            error="OCR engine failed",
            text_elements=[],
        )

        compact = _compact_ocr_extract_result(full_result)

        assert compact.success is False
        assert compact.error == "OCR engine failed"

    def test_generates_summary(self):
        """Should generate a brief summary of OCR results."""
        text_elements = [
            TextBoundingBox(
                text="Important",
                confidence=0.95,
                x=0,
                y=0,
                width=100,
                height=20,
                center_x=50,
                center_y=10,
            ),
        ]

        full_result = OCRExtractResult(
            success=True,
            text_elements=text_elements,
            average_confidence=0.95,
        )

        compact = _compact_ocr_extract_result(full_result)

        # Summary is now a CompactSummary dict (not string)
        assert isinstance(compact.summary, dict)
        assert compact.summary["tool"] == "ocr_extract"
        assert "text elements" in compact.summary["one_line"].lower()

    def test_empty_result_handling(self):
        """Handle OCR results with no text found."""
        full_result = OCRExtractResult(
            success=True,
            found_count=0,
            text_elements=[],
            full_text="",
            average_confidence=0.0,
        )

        compact = _compact_ocr_extract_result(full_result)

        assert compact.found_count == 0
        assert compact.key_elements == []
        assert compact.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
