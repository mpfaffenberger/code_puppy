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
        # Check for multi-line text
        is_multiline = bbox.height > (SmartClickCalculator.TYPICAL_LINE_HEIGHT * 1.5)

        # Calculate base offsets based on element type
        if element_type == "button":
            # Buttons: Click slightly above center to avoid bottom padding
            offset_factor = 0.15 if use_conservative_offsets else 0.2
            offset_x = 0
            offset_y = -int(bbox.height * offset_factor)
            strategy = "button_above_center"
            reasoning = (
                f"Button strategy: Click {int(offset_factor * 100)}% above center "
                f"to avoid bottom padding. Offset: ({offset_x}, {offset_y})"
            )

        elif element_type == "link":
            # Links: Click left edge to avoid right-side padding
            offset_x = -int(bbox.width * 0.3)
            offset_y = 0
            strategy = "link_left_edge"
            reasoning = (
                f"Link strategy: Click left edge (30% from center) "
                f"to avoid right-side text overflow. Offset: ({offset_x}, {offset_y})"
            )

        elif element_type in ("checkbox", "radio_button"):
            # Checkboxes/Radio: Click far left where the box/circle is
            # Checkbox is typically to the left of the label text
            offset_factor = 0.6 if use_conservative_offsets else 0.8
            offset_x = -int(bbox.width * offset_factor)
            offset_y = 0
            strategy = "checkbox_left"
            reasoning = (
                f"Checkbox/Radio strategy: Click {int(offset_factor * 100)}% to the left "
                f"of text center (where the box/circle is). Offset: ({offset_x}, {offset_y})"
            )

        elif element_type == "text_field":
            # Text fields: Click center-left for cursor positioning
            offset_x = -int(bbox.width * 0.2)
            offset_y = 0
            strategy = "text_field_center_left"
            reasoning = (
                f"Text field strategy: Click 20% left of center "
                f"for cursor positioning. Offset: ({offset_x}, {offset_y})"
            )

        elif element_type == "dropdown":
            # Dropdowns: Click right side where the arrow usually is
            offset_x = int(bbox.width * 0.3)
            offset_y = 0
            strategy = "dropdown_right"
            reasoning = (
                f"Dropdown strategy: Click 30% to the right "
                f"(where dropdown arrow is). Offset: ({offset_x}, {offset_y})"
            )

        elif element_type == "icon":
            # Icons: Use exact center (no text padding issues)
            offset_x = 0
            offset_y = 0
            strategy = "icon_center"
            reasoning = "Icon strategy: Use exact center (icons have minimal padding)"

        elif element_type == "menu_item":
            # Menu items: Click center-left
            offset_x = -int(bbox.width * 0.2)
            offset_y = 0
            strategy = "menu_item_center_left"
            reasoning = (
                f"Menu item strategy: Click 20% left of center. "
                f"Offset: ({offset_x}, {offset_y})"
            )

        elif element_type == "tab":
            # Tabs: Click center, but slightly up
            offset_x = 0
            offset_y = -int(bbox.height * 0.1)
            strategy = "tab_above_center"
            reasoning = (
                f"Tab strategy: Click 10% above center. "
                f"Offset: ({offset_x}, {offset_y})"
            )

        else:  # generic
            # Default: Use center with no offset
            offset_x = 0
            offset_y = 0
            strategy = "generic_center"
            reasoning = "Generic element: Using bounding box center"

        # Multi-line text correction
        if is_multiline and element_type not in ("text_field", "dropdown"):
            # For multi-line text (except fields), use upper third instead of center
            multiline_offset_y = -int(bbox.height * 0.25)  # Move to upper 25%
            offset_y = min(offset_y, multiline_offset_y)  # Use more conservative offset
            strategy += "_multiline_adjusted"
            reasoning += f" | Multi-line detected (height={bbox.height}px), adjusted Y to upper portion."

        # Calculate final coordinates
        click_x = bbox.center_x + offset_x
        click_y = bbox.center_y + offset_y

        # Ensure we stay within the bounding box (safety bounds check)
        click_x = max(bbox.x, min(click_x, bbox.x + bbox.width))
        click_y = max(bbox.y, min(click_y, bbox.y + bbox.height))

        # Calculate confidence based on OCR confidence and element type
        # Some element types are more forgiving than others
        base_confidence = bbox.confidence
        if element_type in ("button", "link", "menu_item"):
            # These are generally large and forgiving
            confidence = min(base_confidence + 0.1, 1.0)
        elif element_type in ("checkbox", "radio_button"):
            # These require precise clicking
            confidence = base_confidence * 0.9
        else:
            confidence = base_confidence

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
