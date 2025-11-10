"""Pure click offset calculation logic.

This module provides pure functions for calculating optimal click offsets
for different UI element types. All functions are pure (no I/O, no side effects)
and easily testable.

Philosophy:
- Different element types require different click strategies
- OCR bounding boxes are approximate (±5-10px)
- Offsets compensate for padding and text alignment issues
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Type definitions
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


@dataclass(frozen=True)
class BoundingBox:
    """Bounding box dimensions."""

    x: int
    y: int
    width: int
    height: int
    center_x: int
    center_y: int


@dataclass(frozen=True)
class ClickOffset:
    """Calculated offset from bounding box center."""

    offset_x: int
    offset_y: int
    strategy: str
    reasoning: str


# Constants
TYPICAL_LINE_HEIGHT = 20  # pixels


# ============================================================================
# Element-Specific Offset Calculators
# ============================================================================


def calculate_button_offset(
    bbox: BoundingBox, conservative: bool = True
) -> ClickOffset:
    """
    Calculate offset for button elements.

    Strategy: Click slightly above center to avoid bottom padding.

    Args:
        bbox: Bounding box dimensions
        conservative: If True, use smaller offset (safer)

    Returns:
        ClickOffset with calculated offsets

    Examples:
        >>> bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        >>> offset = calculate_button_offset(bbox)
        >>> offset.offset_y
        -4
    """
    offset_factor = 0.15 if conservative else 0.2
    offset_x = 0
    offset_y = -int(bbox.height * offset_factor)

    return ClickOffset(
        offset_x=offset_x,
        offset_y=offset_y,
        strategy="button_above_center",
        reasoning=(
            f"Button strategy: Click {int(offset_factor * 100)}% above center "
            f"to avoid bottom padding. Offset: ({offset_x}, {offset_y})"
        ),
    )


def calculate_link_offset(bbox: BoundingBox) -> ClickOffset:
    """
    Calculate offset for link elements.

    Strategy: Click left edge to avoid right-side padding.

    Args:
        bbox: Bounding box dimensions

    Returns:
        ClickOffset with calculated offsets

    Examples:
        >>> bbox = BoundingBox(x=100, y=50, width=100, height=20, center_x=150, center_y=60)
        >>> offset = calculate_link_offset(bbox)
        >>> offset.offset_x
        -30
    """
    offset_x = -int(bbox.width * 0.3)
    offset_y = 0

    return ClickOffset(
        offset_x=offset_x,
        offset_y=offset_y,
        strategy="link_left_edge",
        reasoning=(
            f"Link strategy: Click left edge (30% from center) "
            f"to avoid right-side text overflow. Offset: ({offset_x}, {offset_y})"
        ),
    )


def calculate_checkbox_offset(
    bbox: BoundingBox, conservative: bool = True
) -> ClickOffset:
    """
    Calculate offset for checkbox/radio button elements.

    Strategy: Click far left where the checkbox icon is.

    Args:
        bbox: Bounding box dimensions
        conservative: If True, use smaller offset (safer)

    Returns:
        ClickOffset with calculated offsets

    Examples:
        >>> bbox = BoundingBox(x=100, y=50, width=100, height=20, center_x=150, center_y=60)
        >>> offset = calculate_checkbox_offset(bbox)
        >>> offset.offset_x
        -60
    """
    offset_factor = 0.6 if conservative else 0.8
    offset_x = -int(bbox.width * offset_factor)
    offset_y = 0

    return ClickOffset(
        offset_x=offset_x,
        offset_y=offset_y,
        strategy="checkbox_left",
        reasoning=(
            f"Checkbox/Radio strategy: Click {int(offset_factor * 100)}% to the left "
            f"of text center (where the box/circle is). Offset: ({offset_x}, {offset_y})"
        ),
    )


def calculate_text_field_offset(bbox: BoundingBox) -> ClickOffset:
    """
    Calculate offset for text field elements.

    Strategy: Click center-left for cursor positioning.

    Args:
        bbox: Bounding box dimensions

    Returns:
        ClickOffset with calculated offsets

    Examples:
        >>> bbox = BoundingBox(x=100, y=50, width=200, height=30, center_x=200, center_y=65)
        >>> offset = calculate_text_field_offset(bbox)
        >>> offset.offset_x
        -40
    """
    offset_x = -int(bbox.width * 0.2)
    offset_y = 0

    return ClickOffset(
        offset_x=offset_x,
        offset_y=offset_y,
        strategy="text_field_center_left",
        reasoning=(
            f"Text field strategy: Click 20% left of center "
            f"for cursor positioning. Offset: ({offset_x}, {offset_y})"
        ),
    )


def calculate_dropdown_offset(bbox: BoundingBox) -> ClickOffset:
    """
    Calculate offset for dropdown elements.

    Strategy: Click right side where the dropdown arrow is.

    Args:
        bbox: Bounding box dimensions

    Returns:
        ClickOffset with calculated offsets

    Examples:
        >>> bbox = BoundingBox(x=100, y=50, width=150, height=30, center_x=175, center_y=65)
        >>> offset = calculate_dropdown_offset(bbox)
        >>> offset.offset_x
        45
    """
    offset_x = int(bbox.width * 0.3)
    offset_y = 0

    return ClickOffset(
        offset_x=offset_x,
        offset_y=offset_y,
        strategy="dropdown_right",
        reasoning=(
            f"Dropdown strategy: Click 30% to the right "
            f"(where dropdown arrow is). Offset: ({offset_x}, {offset_y})"
        ),
    )


def calculate_icon_offset(bbox: BoundingBox) -> ClickOffset:
    """
    Calculate offset for icon elements.

    Strategy: Use exact center (icons have minimal padding).

    Args:
        bbox: Bounding box dimensions

    Returns:
        ClickOffset with calculated offsets (zero offset)

    Examples:
        >>> bbox = BoundingBox(x=100, y=50, width=32, height=32, center_x=116, center_y=66)
        >>> offset = calculate_icon_offset(bbox)
        >>> (offset.offset_x, offset.offset_y)
        (0, 0)
    """
    return ClickOffset(
        offset_x=0,
        offset_y=0,
        strategy="icon_center",
        reasoning="Icon strategy: Use exact center (icons have minimal padding)",
    )


def calculate_menu_item_offset(bbox: BoundingBox) -> ClickOffset:
    """
    Calculate offset for menu item elements.

    Strategy: Click center-left.

    Args:
        bbox: Bounding box dimensions

    Returns:
        ClickOffset with calculated offsets

    Examples:
        >>> bbox = BoundingBox(x=10, y=100, width=180, height=25, center_x=100, center_y=112)
        >>> offset = calculate_menu_item_offset(bbox)
        >>> offset.offset_x
        -36
    """
    offset_x = -int(bbox.width * 0.2)
    offset_y = 0

    return ClickOffset(
        offset_x=offset_x,
        offset_y=offset_y,
        strategy="menu_item_center_left",
        reasoning=(
            f"Menu item strategy: Click 20% left of center. "
            f"Offset: ({offset_x}, {offset_y})"
        ),
    )


def calculate_tab_offset(bbox: BoundingBox) -> ClickOffset:
    """
    Calculate offset for tab elements.

    Strategy: Click center, slightly above.

    Args:
        bbox: Bounding box dimensions

    Returns:
        ClickOffset with calculated offsets

    Examples:
        >>> bbox = BoundingBox(x=50, y=10, width=100, height=40, center_x=100, center_y=30)
        >>> offset = calculate_tab_offset(bbox)
        >>> offset.offset_y
        -4
    """
    offset_x = 0
    offset_y = -int(bbox.height * 0.1)

    return ClickOffset(
        offset_x=offset_x,
        offset_y=offset_y,
        strategy="tab_above_center",
        reasoning=(
            f"Tab strategy: Click 10% above center. "
            f"Offset: ({offset_x}, {offset_y})"
        ),
    )


def calculate_generic_offset(bbox: BoundingBox) -> ClickOffset:
    """
    Calculate offset for generic/unknown elements.

    Strategy: Use center with no offset.

    Args:
        bbox: Bounding box dimensions

    Returns:
        ClickOffset with zero offsets

    Examples:
        >>> bbox = BoundingBox(x=0, y=0, width=100, height=50, center_x=50, center_y=25)
        >>> offset = calculate_generic_offset(bbox)
        >>> (offset.offset_x, offset.offset_y)
        (0, 0)
    """
    return ClickOffset(
        offset_x=0,
        offset_y=0,
        strategy="generic_center",
        reasoning="Generic element: Using bounding box center",
    )


# ============================================================================
# Multi-line Text Detection & Adjustment
# ============================================================================


def is_multiline_text(
    height: int, line_height: int = TYPICAL_LINE_HEIGHT
) -> bool:
    """
    Determine if bounding box likely contains multi-line text.

    Args:
        height: Bounding box height in pixels
        line_height: Expected single-line height (default: 20px)

    Returns:
        True if likely multi-line, False otherwise

    Examples:
        >>> is_multiline_text(25)
        False
        >>> is_multiline_text(45)
        True
    """
    return height > (line_height * 1.5)


def calculate_multiline_adjustment(
    bbox: BoundingBox, current_offset_y: int
) -> int:
    """
    Calculate Y-axis adjustment for multi-line text.

    For multi-line text, clicking center often hits between lines.
    This adjusts to click in the upper portion instead.

    Args:
        bbox: Bounding box dimensions
        current_offset_y: Current Y offset (may be negative)

    Returns:
        Adjusted Y offset (more negative = higher up)

    Examples:
        >>> bbox = BoundingBox(x=0, y=0, width=200, height=60, center_x=100, center_y=30)
        >>> calculate_multiline_adjustment(bbox, 0)
        -15
        >>> calculate_multiline_adjustment(bbox, -5)
        -15
    """
    multiline_offset_y = -int(bbox.height * 0.25)  # Move to upper 25%
    # Use more conservative (higher up) offset
    return min(current_offset_y, multiline_offset_y)


# ============================================================================
# Bounds Checking & Safety
# ============================================================================


def apply_bounds_check(
    target_x: int, target_y: int, bbox: BoundingBox
) -> tuple[int, int]:
    """
    Ensure click coordinates stay within bounding box.

    Args:
        target_x: Calculated X coordinate
        target_y: Calculated Y coordinate
        bbox: Bounding box to constrain within

    Returns:
        Tuple of (constrained_x, constrained_y)

    Examples:
        >>> bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        >>> apply_bounds_check(200, 100, bbox)  # Outside bounds
        (180, 80)
        >>> apply_bounds_check(120, 60, bbox)  # Inside bounds
        (120, 60)
    """
    constrained_x = max(bbox.x, min(target_x, bbox.x + bbox.width))
    constrained_y = max(bbox.y, min(target_y, bbox.y + bbox.height))
    return constrained_x, constrained_y


# ============================================================================
# Confidence Adjustment
# ============================================================================


def calculate_confidence_adjustment(
    base_confidence: float, element_type: ElementType
) -> float:
    """
    Adjust confidence score based on element type forgiveness.

    Some elements are more forgiving to click (buttons) while others
    require precise positioning (checkboxes).

    Args:
        base_confidence: OCR confidence score (0.0-1.0)
        element_type: Type of UI element

    Returns:
        Adjusted confidence (0.0-1.0)

    Examples:
        >>> calculate_confidence_adjustment(0.8, "button")
        0.9
        >>> calculate_confidence_adjustment(0.8, "checkbox")
        0.72
        >>> calculate_confidence_adjustment(0.8, "generic")
        0.8
    """
    if element_type in ("button", "link", "menu_item"):
        # Large, forgiving targets
        return min(base_confidence + 0.1, 1.0)
    elif element_type in ("checkbox", "radio_button"):
        # Require precise clicking
        return base_confidence * 0.9
    else:
        # No adjustment
        return base_confidence


# ============================================================================
# Retry Point Generation
# ============================================================================


def generate_retry_offsets(num_points: int = 5) -> list[tuple[int, int, str, str]]:
    """
    Generate retry offset patterns for fallback clicking.

    Returns predefined offset patterns to try when primary click fails.

    Args:
        num_points: Number of retry points to generate (excluding primary)

    Returns:
        List of (offset_x, offset_y, strategy_name, reasoning) tuples

    Examples:
        >>> offsets = generate_retry_offsets(3)
        >>> len(offsets)
        3
        >>> offsets[0]
        (0, -5, 'slightly_above', 'Fallback: 5px above center')
    """
    all_offsets = [
        (0, -5, "slightly_above", "Fallback: 5px above center"),
        (-5, 0, "slightly_left", "Fallback: 5px left of center"),
        (5, 0, "slightly_right", "Fallback: 5px right of center"),
        (0, 5, "slightly_below", "Fallback: 5px below center"),
        (-3, -3, "diagonal_up_left", "Fallback: Diagonal up-left"),
        (3, -3, "diagonal_up_right", "Fallback: Diagonal up-right"),
        (-3, 3, "diagonal_down_left", "Fallback: Diagonal down-left"),
        (3, 3, "diagonal_down_right", "Fallback: Diagonal down-right"),
    ]

    return all_offsets[:num_points]
