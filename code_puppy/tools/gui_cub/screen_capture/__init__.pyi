"""Type stubs for screen capture and analysis.

Provides screenshot capture and visual analysis tools.
"""

from typing import Any, Literal
from .result_types import ScreenshotResult

def screenshot(
    save_path: str | None = ...,
    mode: Literal["full_screen", "active_window", "region"] = ...,
    x: int | None = ...,
    y: int | None = ...,
    width: int | None = ...,
    height: int | None = ...,
) -> ScreenshotResult:
    """Take a screenshot of screen or region.

    Args:
        save_path: Optional path to save screenshot
        mode: Capture mode (default: "full_screen")
        x: Left coordinate for region mode
        y: Top coordinate for region mode
        width: Width for region mode
        height: Height for region mode

    Returns:
        ScreenshotResult with success status and path

    Example:
        screenshot()  # Full screen
        screenshot(mode="active_window")  # Active window only
        screenshot(mode="region", x=100, y=100, width=500, height=300)  # Region
    """
    ...

async def screenshot_analyze(
    question: str | None = ...,
    mode: Literal["full_screen", "active_window", "region"] = ...,
    x: int | None = ...,
    y: int | None = ...,
    width: int | None = ...,
    height: int | None = ...,
) -> dict[str, Any]:
    """Take screenshot and analyze with VQA or OCR.

    Args:
        question: Optional question for VQA analysis. If None, uses OCR.
        mode: Capture mode
        x: Left coordinate for region mode
        y: Top coordinate for region mode
        width: Width for region mode
        height: Height for region mode

    Returns:
        Analysis results with extracted text or VQA answer

    Example:
        # OCR mode (no question)
        result = await screenshot_analyze()
        print(result["full_text"])

        # VQA mode (with question)
        result = await screenshot_analyze(question="Where is the Submit button?")
        print(result["answer"])
    """
    ...

def get_screen_size() -> tuple[int, int]:
    """Get screen dimensions.

    Returns:
        Tuple of (width, height) in pixels
    """
    ...
