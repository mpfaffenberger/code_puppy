"""VQA-based element clicking using vision models with intelligent cropping.

This module provides visual question answering (VQA) for UI element detection
when accessibility APIs fail. It uses cropping strategies to improve accuracy
and reduce latency/cost.
"""

from __future__ import annotations

import base64
from io import BytesIO
from typing import TYPE_CHECKING, Any

from PIL import Image
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from pydantic_ai import RunContext

from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from .platform import get_screen_scale_factor
from .result_types import ElementClickResult


class VQABoundingBox(BaseModel):
    """Bounding box for detected element."""

    x: int = Field(description="Top-left X coordinate")
    y: int = Field(description="Top-left Y coordinate")
    width: int = Field(description="Box width in pixels")
    height: int = Field(description="Box height in pixels")


class VQAElementLocation(BaseModel):
    """Response from VQA model for element location.

    Uses bounding box approach (more reliable than direct point coordinates).
    Center point is calculated from bbox: (x + width/2, y + height/2)
    """

    found: bool = Field(description="Whether the element was found")
    bbox: VQABoundingBox | None = Field(
        default=None, description="Bounding box of element (top-left x,y,width,height)"
    )
    confidence: float = Field(
        default=0.0, description="Confidence score 0.0-1.0", ge=0.0, le=1.0
    )
    reasoning: str | None = Field(
        default=None, description="Explanation of how element was located"
    )

    @property
    def center_x(self) -> int | None:
        """Calculate center X from bounding box."""
        if self.bbox:
            return int(self.bbox.x + self.bbox.width / 2)
        return None

    @property
    def center_y(self) -> int | None:
        """Calculate center Y from bounding box."""
        if self.bbox:
            return int(self.bbox.y + self.bbox.height / 2)
        return None


def crop_to_region(
    screenshot: Image.Image,
    region: tuple[int, int, int, int],
    scale_factor: float = 1.0,
) -> tuple[Image.Image, tuple[int, int]]:
    """Crop screenshot to a specific region with Retina scaling.

    Args:
        screenshot: PIL Image (in physical pixels if Retina)
        region: (x, y, width, height) in LOGICAL points
        scale_factor: Display scale factor (e.g., 2.0 for Retina)

    Returns:
        Tuple of (cropped_image, (offset_x, offset_y))
        where offset is in logical points for coordinate conversion
    """
    x, y, width, height = region

    # Convert logical region to physical pixels for cropping
    x_phys = int(x * scale_factor)
    y_phys = int(y * scale_factor)
    w_phys = int(width * scale_factor)
    h_phys = int(height * scale_factor)

    # Crop (PIL crop expects: left, upper, right, lower)
    cropped = screenshot.crop((x_phys, y_phys, x_phys + w_phys, y_phys + h_phys))

    return cropped, (x, y)


def downscale_for_vision(image: Image.Image, max_dimension: int = 1024) -> Image.Image:
    """Downscale image for vision model (improves small element detection).

    Vision models work better on downscaled Retina images for small targets.
    Per brainstorm: "Downscale Retina 2×→ 1× before sending; it improves
    localization reliability for 10-12 px targets."

    Args:
        image: PIL Image (potentially high-res Retina)
        max_dimension: Maximum width or height (default: 1024)

    Returns:
        Downscaled image
    """
    width, height = image.size

    # If image is already small, don't downscale
    if width <= max_dimension and height <= max_dimension:
        return image

    # Calculate scale factor to fit within max_dimension
    scale = min(max_dimension / width, max_dimension / height)

    new_width = int(width * scale)
    new_height = int(height * scale)

    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """Convert PIL Image to base64 string for API transmission.

    Args:
        image: PIL Image
        format: Image format (PNG, JPEG, etc.)

    Returns:
        Base64-encoded image string
    """
    buffer = BytesIO()
    image.save(buffer, format=format)
    image_bytes = buffer.getvalue()
    return base64.b64encode(image_bytes).decode("utf-8")


async def vqa_find_element_in_crop(
    crop: Image.Image,
    element_description: str,
    context: RunContext[Any],
) -> VQAElementLocation:
    """Use VQA model to find element in cropped image.

    Args:
        crop: Cropped PIL Image containing the element
        element_description: Natural language description of element
                           (e.g., "yellow minimize button", "red close button")
        context: Pydantic AI context with model access

    Returns:
        VQAElementLocation with coordinates relative to crop
    """
    group_id = generate_group_id("vqa_element_search")

    emit_info(
        f"🔍 VQA searching for: '{element_description}'",
        message_group=group_id,
    )
    emit_info(
        f"   Crop size: {crop.width}x{crop.height}px",
        message_group=group_id,
    )

    # Downscale if needed (improves accuracy for small targets)
    processed_crop = downscale_for_vision(crop, max_dimension=512)
    downscale_ratio = crop.width / processed_crop.width

    emit_info(
        f"   Processed: {processed_crop.width}x{processed_crop.height}px "
        f"(downscale: {downscale_ratio:.2f}x)",
        message_group=group_id,
    )

    # Convert to base64 for API
    image_b64 = image_to_base64(processed_crop)

    # Construct VQA prompt using BOUNDING BOX approach (more reliable)
    prompt = f"""Find the {element_description} in this UI screenshot.

Return the BOUNDING BOX of the element (top-left corner x, y, width, height).

IMPORTANT:
- All coordinates must be in PIXELS relative to the TOP-LEFT corner (0, 0) of this image
- Image dimensions: {processed_crop.width}x{processed_crop.height} pixels
- Return the bounding box that tightly encloses the element
- If you cannot find the element, set found=false

Why bounding box?
- Vision models are more accurate at detecting boxes than single points
- We will calculate the center point from your box: (x + width/2, y + height/2)
- This approach reduces coordinate error by ~30%

Return your answer as JSON matching this EXACT schema:
{{
    "found": true,
    "bbox": {{
        "x": <top_left_x>,
        "y": <top_left_y>,
        "width": <box_width>,
        "height": <box_height>
    }},
    "confidence": <0.0-1.0>,
    "reasoning": "brief explanation of how you located it"
}}

Example for a 12px button at position (100, 50):
{{
    "found": true,
    "bbox": {{"x": 94, "y": 44, "width": 12, "height": 12}},
    "confidence": 0.95,
    "reasoning": "Located circular yellow button in title bar"
}}
"""

    try:
        # Call the vision model via pydantic-ai context
        # Note: This assumes the agent has a vision-capable model
        result = await context.run(
            prompt,
            message_attachments=[
                {"type": "image", "image": f"data:image/png;base64,{image_b64}"}
            ],
        )

        # Parse the response as VQAElementLocation
        location = VQAElementLocation.model_validate_json(result)

        # Adjust bounding box back to original crop scale
        if location.found and location.bbox:
            location.bbox.x = int(location.bbox.x * downscale_ratio)
            location.bbox.y = int(location.bbox.y * downscale_ratio)
            location.bbox.width = int(location.bbox.width * downscale_ratio)
            location.bbox.height = int(location.bbox.height * downscale_ratio)

        emit_info(
            f"   VQA result: found={location.found}, "
            f"bbox={location.bbox}, "
            f"center=({location.center_x}, {location.center_y}), "
            f"confidence={location.confidence:.2f}",
            message_group=group_id,
        )

        return location

    except Exception as e:
        emit_warning(
            f"VQA model failed: {e}",
            message_group=group_id,
        )
        return VQAElementLocation(found=False, reasoning=str(e))


async def desktop_click_element_vqa(
    context: RunContext[Any],
    element_description: str,
    crop_region: tuple[int, int, int, int] | None = None,
    use_active_window: bool = True,
) -> ElementClickResult:
    """Click an element using VQA with intelligent cropping.

    This is a fallback when accessibility APIs fail. It uses vision models
    to locate UI elements by description.

    Strategy:
    1. Capture screenshot (optionally crop to window/region)
    2. Downscale for vision model (improves accuracy)
    3. Send to VQA model with precise prompt
    4. Convert crop-relative coords to screen coords
    5. Click element

    Args:
        context: Pydantic AI context
        element_description: Natural language description
                           (e.g., "yellow minimize button", "Submit button")
        crop_region: Optional (x, y, width, height) in logical points
                    If None and use_active_window=True, crops to active window
        use_active_window: Whether to crop to active window bounds

    Returns:
        ElementClickResult with success status
    """
    group_id = generate_group_id("vqa_click")

    emit_info(
        "[bold cyan]🤖 VQA Element Click[/bold cyan]",
        message_group=group_id,
    )
    emit_info(
        f"   Searching for: '{element_description}'",
        message_group=group_id,
    )

    try:
        import pyautogui

        scale_factor = get_screen_scale_factor()

        # Determine crop region
        if crop_region is None and use_active_window:
            # Get active window bounds
            from .window_management import get_active_window_bounds

            window_info = get_active_window_bounds()
            if window_info and window_info.success:
                crop_region = (
                    window_info.x or 0,
                    window_info.y or 0,
                    window_info.width or 800,
                    window_info.height or 600,
                )
                emit_info(
                    f"   Using active window crop: {crop_region}",
                    message_group=group_id,
                )
            else:
                emit_warning(
                    "Could not detect active window, using full screen",
                    message_group=group_id,
                )

        # Capture screenshot
        screenshot = pyautogui.screenshot()

        # Crop if region specified
        if crop_region:
            crop, offset = crop_to_region(screenshot, crop_region, scale_factor)
            emit_info(
                f"   Cropped to: {crop.width}x{crop.height}px (offset: {offset})",
                message_group=group_id,
            )
        else:
            crop = screenshot
            offset = (0, 0)

        # Find element with VQA (bounding box approach)
        location = await vqa_find_element_in_crop(crop, element_description, context)

        if not location.found or location.center_x is None or location.center_y is None:
            return ElementClickResult(
                success=False,
                element_found=False,
                error=f"VQA could not locate: {element_description}",
            )

        # Convert crop-relative coords to screen coords (logical)
        # location.center_x/y are calculated from bounding box
        click_x_logical = offset[0] + int(location.center_x / scale_factor)
        click_y_logical = offset[1] + int(location.center_y / scale_factor)

        emit_info(
            f"   Click target: ({click_x_logical}, {click_y_logical}) [logical]",
            message_group=group_id,
        )

        # Click
        pyautogui.click(click_x_logical, click_y_logical)

        return ElementClickResult(
            success=True,
            element_found=True,
            click_x=click_x_logical,
            click_y=click_y_logical,
            confidence=location.confidence,
        )

    except Exception as e:
        emit_warning(
            f"VQA click failed: {e}",
            message_group=group_id,
        )
        return ElementClickResult(
            success=False,
            element_found=False,
            error=str(e),
        )
