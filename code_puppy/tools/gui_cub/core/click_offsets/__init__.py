"""Click offset calculation logic.

This module provides pure functions for calculating optimal click coordinates
based on UI element types and bounding box characteristics.
"""

from .calculator import (
    BoundingBox,
    ClickOffset,
    calculate_button_offset,
    calculate_checkbox_offset,
    calculate_dropdown_offset,
    calculate_generic_offset,
    calculate_icon_offset,
    calculate_link_offset,
    calculate_menu_item_offset,
    calculate_tab_offset,
    calculate_text_field_offset,
    calculate_multiline_adjustment,
    is_multiline_text,
    apply_bounds_check,
    calculate_confidence_adjustment,
    generate_retry_offsets,
)

__all__ = [
    "BoundingBox",
    "ClickOffset",
    "calculate_button_offset",
    "calculate_link_offset",
    "calculate_checkbox_offset",
    "calculate_text_field_offset",
    "calculate_dropdown_offset",
    "calculate_icon_offset",
    "calculate_menu_item_offset",
    "calculate_tab_offset",
    "calculate_generic_offset",
    "calculate_multiline_adjustment",
    "is_multiline_text",
    "apply_bounds_check",
    "calculate_confidence_adjustment",
    "generate_retry_offsets",
]
