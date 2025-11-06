"""Shared pytest fixtures for desktop automation tests."""

import pytest
from unittest.mock import MagicMock

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@pytest.fixture
def mock_pyautogui(monkeypatch):
    """Mock pyautogui to prevent actual mouse/keyboard actions."""
    mock_pag = MagicMock()

    # Mock common functions
    mock_pag.size.return_value = (1920, 1080)
    mock_pag.position.return_value = (100, 100)

    if PIL_AVAILABLE:
        mock_pag.screenshot.return_value = create_test_image()
    else:
        mock_pag.screenshot.return_value = None

    # Mock the module-level functions
    try:
        import pyautogui

        monkeypatch.setattr(pyautogui, "size", mock_pag.size)
        monkeypatch.setattr(pyautogui, "position", mock_pag.position)
        monkeypatch.setattr(pyautogui, "screenshot", mock_pag.screenshot)
        monkeypatch.setattr(pyautogui, "moveTo", mock_pag.moveTo)
        monkeypatch.setattr(pyautogui, "click", mock_pag.click)
        monkeypatch.setattr(pyautogui, "typewrite", mock_pag.typewrite)
    except ImportError:
        pass  # pyautogui not available, tests will skip if needed

    return mock_pag


@pytest.fixture
def mock_tesseract(monkeypatch):
    """Mock pytesseract for OCR tests."""
    mock_tess = MagicMock()

    mock_tess.image_to_string.return_value = "Test OCR Text"
    mock_tess.image_to_data.return_value = {
        "text": ["Test", "OCR", "Text"],
        "conf": [95, 90, 92],
        "left": [10, 50, 90],
        "top": [10, 10, 10],
        "width": [30, 30, 30],
        "height": [20, 20, 20],
    }

    try:
        import pytesseract

        monkeypatch.setattr(pytesseract, "image_to_string", mock_tess.image_to_string)
        monkeypatch.setattr(pytesseract, "image_to_data", mock_tess.image_to_data)
    except ImportError:
        pass  # pytesseract not available

    return mock_tess


@pytest.fixture
def test_image():
    """Create a test PIL Image."""
    if not PIL_AVAILABLE:
        pytest.skip("PIL not available")
    return create_test_image()


@pytest.fixture
def mock_appkit(monkeypatch):
    """Mock AppKit for macOS accessibility tests."""
    import sys

    if sys.platform != "darwin":
        pytest.skip("macOS only test")

    # Mock AppKit imports if needed
    pass


def create_test_image(width=800, height=600):
    """Helper to create a test PIL Image."""
    if not PIL_AVAILABLE:
        return None
    img = Image.new("RGB", (width, height), color="white")
    return img


@pytest.fixture
def mock_platform_macos(monkeypatch):
    """Mock sys.platform to be macOS."""
    monkeypatch.setattr("sys.platform", "darwin")


@pytest.fixture
def mock_platform_windows(monkeypatch):
    """Mock sys.platform to be Windows."""
    monkeypatch.setattr("sys.platform", "win32")


@pytest.fixture
def mock_platform_linux(monkeypatch):
    """Mock sys.platform to be Linux."""
    monkeypatch.setattr("sys.platform", "linux")
