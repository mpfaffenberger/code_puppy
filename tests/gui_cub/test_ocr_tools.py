"""Tests for OCR tools."""

import pytest

# Provide a dummy image object for mocked screenshots
class DummyImage:
    def __init__(self, w: int = 100, h: int = 100) -> None:
        self.width = w
        self.height = h

try:
    from code_puppy.tools.gui_cub.ocr_tools import (
        TextBoundingBox,
        OCRExtractResult,
        OCRFindResult,
        find_text_in_elements,
    )
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    pytest.skip("OCR tools not available", allow_module_level=True)

from tests.gui_cub.helpers import validate_result_type


class TestTextBoundingBox:
    """Test TextBoundingBox model."""
    
    def test_can_create_text_element(self):
        """Test creating a text bounding box."""
        bbox = TextBoundingBox(
            text="Test",
            confidence=0.95,
            x=10, y=20,
            width=50, height=30,
            center_x=35, center_y=35
        )
        
        assert bbox.text == "Test"
        assert bbox.confidence == 0.95
        assert bbox.x == 10
        assert bbox.center_x == 35
    
    def test_confidence_is_float(self):
        """Test that confidence is a float 0-1."""
        bbox = TextBoundingBox(
            text="Test", confidence=0.95,
            x=0, y=0, width=10, height=10,
            center_x=5, center_y=5
        )
        
        assert isinstance(bbox.confidence, float)
        assert 0.0 <= bbox.confidence <= 1.0


class TestFindTextInElements:
    """Test the find_text_in_elements helper function."""
    
    def test_find_exact_match(self):
        """Test finding exact text match."""
        elements = [
            TextBoundingBox(
                text="Submit", confidence=0.95,
                x=100, y=200, width=50, height=20,
                center_x=125, center_y=210
            ),
            TextBoundingBox(
                text="Cancel", confidence=0.90,
                x=200, y=200, width=50, height=20,
                center_x=225, center_y=210
            ),
        ]
        
        result = find_text_in_elements("Submit", elements)
        
        validate_result_type(result, OCRFindResult)
        assert result.found is True
        assert result.total_matches == 1
        assert result.best_match.text == "Submit"
    
    def test_case_insensitive_search(self):
        """Test case-insensitive text search."""
        elements = [
            TextBoundingBox(
                text="Submit", confidence=0.95,
                x=100, y=200, width=50, height=20,
                center_x=125, center_y=210
            ),
        ]
        
        result = find_text_in_elements("submit", elements, case_sensitive=False)
        
        assert result.found is True
        assert result.best_match.text == "Submit"
    
    def test_no_match_found(self):
        """Test when text is not found."""
        elements = [
            TextBoundingBox(
                text="Submit", confidence=0.95,
                x=100, y=200, width=50, height=20,
                center_x=125, center_y=210
            ),
        ]
        
        result = find_text_in_elements("NotThere", elements)
        
        assert result.found is False
        assert result.total_matches == 0
        assert result.best_match is None
    
    def test_case_sensitive_search(self):
        """Test case-sensitive text search."""
        elements = [
            TextBoundingBox(
                text="Submit", confidence=0.95,
                x=100, y=200, width=50, height=20,
                center_x=125, center_y=210
            ),
        ]
        
        # Should not find with different case
        result = find_text_in_elements("submit", elements, case_sensitive=True)
        assert result.found is False
        
        # Should find with exact case
        result = find_text_in_elements("Submit", elements, case_sensitive=True)
        assert result.found is True


# Extended coverage: high-level desktop_* flows with mocks
from types import SimpleNamespace
from unittest.mock import patch
from code_puppy.tools.gui_cub import ocr_tools






