"""Tests for OCR tools."""

import pytest

# Provide a dummy image object for mocked screenshots
class DummyImage:
    def __init__(self, w: int = 100, h: int = 100) -> None:
        self.width = w
        self.height = h

try:
    from code_puppy.tools.rpa.ocr_tools import (
        TextBoundingBox,
        OCRExtractResult,
        OCRFindResult,
        find_text_in_elements,
    )
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    pytest.skip("OCR tools not available", allow_module_level=True)

from tests.rpa.helpers import validate_result_type


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
from code_puppy.tools.rpa import ocr_tools


@patch("code_puppy.tools.rpa.ocr_tools.PYAUTOGUI_AVAILABLE", True)
@patch("code_puppy.tools.rpa.ocr_tools.TESSERACT_AVAILABLE", True)
def test_desktop_extract_text_active_window(monkeypatch):
    # Mock screenshot and scaling
    monkeypatch.setattr(ocr_tools, "pyautogui", SimpleNamespace(screenshot=lambda region=None: DummyImage()))
    import code_puppy.tools.rpa.platform as platform
    monkeypatch.setattr(platform, "get_screen_scale_factor", lambda: 1.0)

    # Fake extractor
    def fake_extract(image, language, scale_factor, region_offset):
        return OCRExtractResult(success=True, full_text="hello world", text_elements=[
            TextBoundingBox(text="hello", confidence=0.9, x=10, y=10, width=20, height=10, center_x=20, center_y=15),
            TextBoundingBox(text="world", confidence=0.8, x=40, y=10, width=20, height=10, center_x=50, center_y=15),
        ], total_words=2, average_confidence=0.85, language=language)

    monkeypatch.setattr(ocr_tools, "extract_text_from_image", fake_extract)

    class DummyAgent:
        def __init__(self):
            self.tools = {}
        def tool(self, f):
            self.tools[f.__name__] = f
            return f
    agent = DummyAgent()
    ocr_tools.register_ocr_tools(agent)
    desktop_extract_text = agent.tools["desktop_extract_text"]

    res: OCRExtractResult = desktop_extract_text(context=None, use_active_window=True)
    assert res.success is True
    # Check compact fields (success-conditional compaction)
    assert res.found_count == 2  # Should have 2 elements
    assert len(res.key_elements) > 0  # Should have key elements
    assert res.summary != ""  # Should have summary


@patch("code_puppy.tools.rpa.ocr_tools.PYAUTOGUI_AVAILABLE", True)
@patch("code_puppy.tools.rpa.ocr_tools.TESSERACT_AVAILABLE", True)
def test_desktop_find_text_with_fuzzy(monkeypatch):
    monkeypatch.setattr(ocr_tools, "pyautogui", SimpleNamespace(screenshot=lambda region=None: DummyImage()))
    import code_puppy.tools.rpa.platform as platform
    monkeypatch.setattr(platform, "get_screen_scale_factor", lambda: 1.0)

    def fake_extract(image, language, scale_factor, region_offset):
        return OCRExtractResult(success=True, full_text="Save as", text_elements=[
            TextBoundingBox(text="Save", confidence=0.6, x=10, y=10, width=20, height=10, center_x=20, center_y=15),
            TextBoundingBox(text="saveAs", confidence=0.7, x=40, y=10, width=20, height=10, center_x=50, center_y=15),
        ], total_words=2, average_confidence=0.65, language=language)

    monkeypatch.setattr(ocr_tools, "extract_text_from_image", fake_extract)

    class DummyAgent:
        def __init__(self):
            self.tools = {}
        def tool(self, f):
            self.tools[f.__name__] = f
            return f
    agent = DummyAgent()
    ocr_tools.register_ocr_tools(agent)
    desktop_extract_text = agent.tools["desktop_extract_text"]
    desktop_find_text = agent.tools["desktop_find_text"]

    # Call the unified find_text tool (will use the closure-bound desktop_extract_text)
    res: OCRFindResult = desktop_find_text(context=None, search_text="save", fuzzy=True, fuzzy_threshold=0.5, use_active_window=True)
    assert res.success is True
    assert res.found is True


@patch("code_puppy.tools.rpa.ocr_tools.PYAUTOGUI_AVAILABLE", True)
@patch("code_puppy.tools.rpa.ocr_tools.TESSERACT_AVAILABLE", True)
def test_desktop_verify_text_fails_then_reports_text(monkeypatch):
    monkeypatch.setattr(ocr_tools, "pyautogui", SimpleNamespace(screenshot=lambda region=None: DummyImage()))
    import code_puppy.tools.rpa.platform as platform
    monkeypatch.setattr(platform, "get_screen_scale_factor", lambda: 1.0)

    def fake_extract(image, language, scale_factor, region_offset):
        return OCRExtractResult(success=True, full_text="Some random content", text_elements=[], total_words=3, average_confidence=0.5, language=language)

    monkeypatch.setattr(ocr_tools, "extract_text_from_image", fake_extract)

    class DummyAgent:
        def __init__(self):
            self.tools = {}
        def tool(self, f):
            self.tools[f.__name__] = f
            return f
    agent = DummyAgent()
    ocr_tools.register_ocr_tools(agent)
    desktop_extract_text = agent.tools["desktop_extract_text"]
    desktop_find_text = agent.tools["desktop_find_text"]
    desktop_verify_text = agent.tools["desktop_verify_text"]

    def fake_find_text(context, search_text, **kwargs):
        return OCRFindResult(success=True, search_text=search_text, found=False, matches=[], total_matches=0)

    # Do not monkeypatch module functions; closure will call our fake extractor
    res: OCRVerifyResult = desktop_verify_text(context=None, expected_text="Welcome", use_active_window=True)
    assert res.success is True and res.found is False
    assert "Some random content"[:10] in res.actual_text
