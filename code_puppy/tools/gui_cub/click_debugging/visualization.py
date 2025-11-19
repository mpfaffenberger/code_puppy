"""Visualization helpers for click debugging."""

from __future__ import annotations


def draw_pixel_grid(
    draw,
    center_x: int,
    center_y: int,
    grid_size: int = 50,
    spacing: int = 10,
    scale_factor: float = 1.0,
):
    """
    Draw a pixel grid overlay around a point for precise coordinate debugging.

    Args:
        draw: PIL ImageDraw object
        center_x: Center X coordinate in screenshot pixels
        center_y: Center Y coordinate in screenshot pixels
        grid_size: Size of grid area in pixels
        spacing: Spacing between grid lines in pixels
        scale_factor: HiDPI scale factor
    """
    half_size = grid_size // 2
    start_x = center_x - half_size
    start_y = center_y - half_size
    end_x = center_x + half_size
    end_y = center_y + half_size

    # Draw vertical lines
    for x in range(start_x, end_x + 1, spacing):
        draw.line(
            [(x, start_y), (x, end_y)],
            fill=(128, 128, 128, 128),  # Semi-transparent gray
            width=1,
        )

    # Draw horizontal lines
    for y in range(start_y, end_y + 1, spacing):
        draw.line(
            [(start_x, y), (end_x, y)],
            fill=(128, 128, 128, 128),
            width=1,
        )

    # Draw center lines in brighter color
    draw.line([(center_x, start_y), (center_x, end_y)], fill=(255, 255, 0), width=1)
    draw.line([(start_x, center_y), (end_x, center_y)], fill=(255, 255, 0), width=1)
