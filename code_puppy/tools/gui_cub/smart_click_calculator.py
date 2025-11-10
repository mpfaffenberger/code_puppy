"""Smart click coordinate calculation with element-type-aware offset correction.

This module provides intelligent click coordinate calculation to compensate
for OCR bounding box inaccuracies (±5-10px). Different UI element types
require different offset strategies for maximum click accuracy.

IMPORTANT - HiDPI/Retina Coordinate Handling:
    Coordinates used by mouse APIs are LOGICAL screen points. Screenshots/VQA
    operate in PHYSICAL pixels. Do NOT mix these without conversion.

    - Always pass screen-absolute LOGICAL coordinates into this calculator.
    - OCR tools convert from physical screenshot pixels → logical screen points
      and rebase window-relative bounding boxes to screen space.
    - VQA is for understanding only; never use VQA pixel coordinates for clicking
      without converting back using the screen scale factor and rebasing to screen.

    Example on 2x Retina display:
    - Physical screenshot: 3456 x 2234 pixels
    - Logical screen: 1728 x 1117 points
    - OCR finds text at (940, 250) in screenshot → converted to (470, 125) logical
    - This module receives (470, 125) and calculates offsets in logical space
    - Mouse clicks at logical coordinates
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .logic.click_offsets import (
    BoundingBox as SimpleBoundingBox,
    calculate_button_offset,
    calculate_checkbox_offset,
    calculate_dropdown_offset,
    calculate_generic_offset,
    calculate_icon_offset,
    calculate_link_offset,
    calculate_menu_item_offset,
    calculate_tab_offset,
    calculate_text_field_offset,
    is_multiline_text,
    calculate_multiline_adjustment,
    apply_bounds_check,
    calculate_confidence_adjustment,
)

try:
    from .result_types import TextBoundingBox
except ImportError:
    # For type checking when result_types isn't available
    class TextBoundingBox(BaseModel):  # type: ignore
        text: str
        confidence: float
        x: int
        y: int
        width: int
        height: int
        center_x: int
        center_y: int


ElementType = Literal[
    "button",
    "link",
    "checkbox",
    "radio_button",
    "text_field",
    "dropdown",
    "icon",
    "menu_item",
    "tab",
    "generic",
]


class ClickPoint(BaseModel):
    """Calculated click coordinates with metadata."""

    x: int = Field(description="X coordinate to click")
    y: int = Field(description="Y coordinate to click")
    offset_x: int = Field(description="X offset from bounding box center")
    offset_y: int = Field(description="Y offset from bounding box center")
    strategy: str = Field(description="Strategy used to calculate offset")
    confidence: float = Field(
        description="Confidence in the calculated position (0.0-1.0)"
    )
    reasoning: str = Field(description="Human-readable explanation of calculation")


class SmartClickCalculator:
    """
    Intelligent click coordinate calculator with element-type-aware offsets.

    This class compensates for OCR bounding box inaccuracies by applying
    different offset strategies based on the type of UI element being clicked.

    OCR Characteristics:
    - Text bounding boxes are approximate (±5-10px)
    - Center calculation (x + width // 2, y + height // 2) works for single-line text
    - Multi-line text: center_y falls between lines (not clickable)
    - Buttons: Often have padding, center may be off
    - Links: Text is left-aligned, clicking right side may miss
    - Checkboxes: Clickable box is to the left of the label text

    Offset Strategies:
    - **Buttons**: Click slightly above center (avoid bottom padding)
    - **Links**: Click left edge (avoid right-side padding)
    - **Checkboxes**: Click far left (where checkbox icon is)
    - **Text fields**: Click center-left (cursor positioning)
    - **Icons**: Use exact center (no text padding)
    - **Dropdowns**: Click right side (where arrow is)
    """

    # Typical line height in pixels for detection of multi-line text
    TYPICAL_LINE_HEIGHT = 20

    @staticmethod
    def calculate_click_point(
        bbox: TextBoundingBox,
        element_type: ElementType = "generic",
        use_conservative_offsets: bool = True,
    ) -> ClickPoint:
        """
        Calculate optimal click coordinates for a UI element.

        Args:
            bbox: OCR bounding box of the element
            element_type: Type of UI element (affects offset strategy)
            use_conservative_offsets: If True, use smaller offsets (safer but less accurate)

        Returns:
            ClickPoint with calculated coordinates and metadata

        Examples:
            >>> bbox = TextBoundingBox(
            ...     text="Submit",
            ...     confidence=0.89,
            ...     x=500, y=300, width=80, height=30,
            ...     center_x=540, center_y=315
            ... )
            >>> point = SmartClickCalculator.calculate_click_point(bbox, "button")
            >>> print(f"Click at ({point.x}, {point.y})")
            Click at (540, 312)
        """
        # Convert to simple bounding box for pure logic functions
        simple_bbox = SimpleBoundingBox(
            x=bbox.x,
            y=bbox.y,
            width=bbox.width,
            height=bbox.height,
            center_x=bbox.center_x,
            center_y=bbox.center_y,
        )

        # Use extracted pure logic based on element type
        if element_type == "button":
            offset = calculate_button_offset(simple_bbox, use_conservative_offsets)
        elif element_type == "link":
            offset = calculate_link_offset(simple_bbox)
        elif element_type in ("checkbox", "radio_button"):
            offset = calculate_checkbox_offset(simple_bbox, use_conservative_offsets)
        elif element_type == "text_field":
            offset = calculate_text_field_offset(simple_bbox)
        elif element_type == "dropdown":
            offset = calculate_dropdown_offset(simple_bbox)
        elif element_type == "icon":
            offset = calculate_icon_offset(simple_bbox)
        elif element_type == "menu_item":
            offset = calculate_menu_item_offset(simple_bbox)
        elif element_type == "tab":
            offset = calculate_tab_offset(simple_bbox)
        else:  # generic
            offset = calculate_generic_offset(simple_bbox)

        offset_x = offset.offset_x
        offset_y = offset.offset_y
        strategy = offset.strategy
        reasoning = offset.reasoning

        # Multi-line text correction using extracted logic
        if is_multiline_text(bbox.height) and element_type not in (
            "text_field",
            "dropdown",
        ):
            offset_y = calculate_multiline_adjustment(simple_bbox, offset_y)
            strategy += "_multiline_adjusted"
            reasoning += f" | Multi-line detected (height={bbox.height}px), adjusted Y to upper portion."

        # Calculate final coordinates
        click_x = bbox.center_x + offset_x
        click_y = bbox.center_y + offset_y

        # Apply bounds check using extracted logic
        click_x, click_y = apply_bounds_check(click_x, click_y, simple_bbox)

        # Calculate confidence using extracted logic
        confidence = calculate_confidence_adjustment(bbox.confidence, element_type)

        return ClickPoint(
            x=click_x,
            y=click_y,
            offset_x=offset_x,
            offset_y=offset_y,
            strategy=strategy,
            confidence=confidence,
            reasoning=reasoning,
        )

    @staticmethod
    def generate_retry_points(
        bbox: TextBoundingBox,
        element_type: ElementType = "generic",
        num_points: int = 5,
    ) -> list[ClickPoint]:
        """
        Generate multiple click points for retry logic.

        Returns a list of click points to try in order, starting with
        the most likely to succeed.

        Args:
            bbox: OCR bounding box of the element
            element_type: Type of UI element
            num_points: Number of retry points to generate

        Returns:
            List of ClickPoint objects in priority order

        Example:
            >>> points = SmartClickCalculator.generate_retry_points(bbox, "button", num_points=3)
            >>> for i, point in enumerate(points, 1):
            ...     print(f"Attempt {i}: ({point.x}, {point.y}) - {point.reasoning}")
        """
        points = []

        # Primary point (optimal strategy)
        primary = SmartClickCalculator.calculate_click_point(
            bbox, element_type=element_type, use_conservative_offsets=True
        )
        points.append(primary)

        if num_points <= 1:
            return points

        # Secondary point (exact center - no offset)
        center_point = ClickPoint(
            x=bbox.center_x,
            y=bbox.center_y,
            offset_x=0,
            offset_y=0,
            strategy="fallback_center",
            confidence=bbox.confidence * 0.85,
            reasoning="Fallback: Exact bounding box center (no offset correction)",
        )
        points.append(center_point)

        if num_points <= 2:
            return points

        # Generate additional offset variations
        offsets = [
            (0, -5, "slightly_above", "Fallback: 5px above center"),
            (-5, 0, "slightly_left", "Fallback: 5px left of center"),
            (5, 0, "slightly_right", "Fallback: 5px right of center"),
            (0, 5, "slightly_below", "Fallback: 5px below center"),
            (-3, -3, "diagonal_up_left", "Fallback: Diagonal up-left"),
            (3, -3, "diagonal_up_right", "Fallback: Diagonal up-right"),
            (-3, 3, "diagonal_down_left", "Fallback: Diagonal down-left"),
            (3, 3, "diagonal_down_right", "Fallback: Diagonal down-right"),
        ]

        for offset_x, offset_y, strategy, reasoning in offsets[: num_points - 2]:
            retry_x = bbox.center_x + offset_x
            retry_y = bbox.center_y + offset_y

            # Bounds check
            retry_x = max(bbox.x, min(retry_x, bbox.x + bbox.width))
            retry_y = max(bbox.y, min(retry_y, bbox.y + bbox.height))

            points.append(
                ClickPoint(
                    x=retry_x,
                    y=retry_y,
                    offset_x=offset_x,
                    offset_y=offset_y,
                    strategy=strategy,
                    confidence=bbox.confidence * 0.7,
                    reasoning=reasoning,
                )
            )

        return points

    @staticmethod
    def analyze_bounding_box(bbox: TextBoundingBox) -> dict[str, any]:
        """
        Analyze OCR bounding box characteristics for debugging.

        Args:
            bbox: OCR bounding box to analyze

        Returns:
            Dictionary with analysis metadata

        Example:
            >>> analysis = SmartClickCalculator.analyze_bounding_box(bbox)
            >>> print(analysis['is_multiline'])
            True
            >>> print(analysis['aspect_ratio'])
            2.67
        """
        aspect_ratio = bbox.width / bbox.height if bbox.height > 0 else 0
        is_multiline = bbox.height > (SmartClickCalculator.TYPICAL_LINE_HEIGHT * 1.5)
        is_wide = aspect_ratio > 3.0
        is_tall = aspect_ratio < 0.5

        # Estimate element type based on characteristics
        estimated_type = "generic"
        if is_wide and not is_multiline:
            estimated_type = "button" if bbox.height < 50 else "text_field"
        elif is_tall:
            estimated_type = "icon"
        elif bbox.width < 30 and bbox.height < 30:
            estimated_type = "checkbox"

        return {
            "text": bbox.text,
            "confidence": bbox.confidence,
            "width": bbox.width,
            "height": bbox.height,
            "aspect_ratio": round(aspect_ratio, 2),
            "is_multiline": is_multiline,
            "is_wide": is_wide,
            "is_tall": is_tall,
            "estimated_type": estimated_type,
            "area_pixels": bbox.width * bbox.height,
            "center": (bbox.center_x, bbox.center_y),
        }
