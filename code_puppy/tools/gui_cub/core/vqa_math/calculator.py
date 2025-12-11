"""Pure VQA coordinate transformation functions.

No I/O operations - just coordinate math and scaling calculations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CropRegion:
    """Logical screen region to crop (in screen points, not pixels)."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class DownscaleDimensions:
    """Calculated dimensions after downscaling."""

    width: int
    height: int
    ratio: float


def calculate_physical_crop_box(
    region: CropRegion,
    scale_factor: float,
) -> tuple[int, int, int, int]:
    """Convert logical screen region to physical pixel crop box.

    On HiDPI/Retina displays, screenshots are captured at higher resolution
    than the logical screen size. This converts logical coordinates to
    physical pixels for PIL crop operations.

    Args:
        region: Logical screen region (in points)
        scale_factor: Display scale factor (e.g., 2.0 for Retina)

    Returns:
        Tuple of (left, top, right, bottom) in physical pixels for PIL crop

    Example:
        >>> # On 2x Retina display
        >>> region = CropRegion(x=100, y=200, width=300, height=150)
        >>> box = calculate_physical_crop_box(region, scale_factor=2.0)
        >>> print(box)  # (200, 400, 800, 700)
        >>> # PIL crop: image.crop(box)
    """
    # Convert logical coordinates to physical pixels
    x_phys = int(region.x * scale_factor)
    y_phys = int(region.y * scale_factor)
    w_phys = int(region.width * scale_factor)
    h_phys = int(region.height * scale_factor)

    # PIL crop expects (left, top, right, bottom)
    left = x_phys
    top = y_phys
    right = x_phys + w_phys
    bottom = y_phys + h_phys

    return (left, top, right, bottom)


def calculate_downscale_ratio(
    width: int,
    height: int,
    max_dimension: int,
) -> float:
    """Calculate downscale ratio to fit image within max dimension.

    Used to reduce image size for vision model processing while
    maintaining aspect ratio.

    Args:
        width: Current image width in pixels
        height: Current image height in pixels
        max_dimension: Maximum allowed dimension (width or height)

    Returns:
        Scale ratio (1.0 = no scaling, 0.5 = half size, etc.)

    Example:
        >>> # 2048x1536 image, max 1024
        >>> ratio = calculate_downscale_ratio(2048, 1536, 1024)
        >>> print(ratio)  # 0.5 (will become 1024x768)

        >>> # 800x600 image, max 1024 (no downscaling needed)
        >>> ratio = calculate_downscale_ratio(800, 600, 1024)
        >>> print(ratio)  # 1.0
    """
    max_current = max(width, height)

    # No downscaling needed if already smaller
    if max_current <= max_dimension:
        return 1.0

    # Calculate ratio to fit within max_dimension
    return max_dimension / max_current


def calculate_downscaled_dimensions(
    width: int,
    height: int,
    ratio: float,
) -> DownscaleDimensions:
    """Calculate new dimensions after applying downscale ratio.

    Args:
        width: Original width in pixels
        height: Original height in pixels
        ratio: Downscale ratio (from calculate_downscale_ratio)

    Returns:
        DownscaleDimensions with new width, height, and ratio

    Example:
        >>> # 2048x1536 at 0.5 ratio
        >>> dims = calculate_downscaled_dimensions(2048, 1536, 0.5)
        >>> print(dims.width, dims.height)  # 1024 768
    """
    new_width = int(width * ratio)
    new_height = int(height * ratio)

    return DownscaleDimensions(
        width=new_width,
        height=new_height,
        ratio=ratio,
    )


def calculate_downscale_dimensions_auto(
    width: int,
    height: int,
    max_dimension: int,
) -> DownscaleDimensions:
    """Calculate downscaled dimensions in one step.

    Convenience function that combines calculate_downscale_ratio and
    calculate_downscaled_dimensions.

    Args:
        width: Original width in pixels
        height: Original height in pixels
        max_dimension: Maximum allowed dimension

    Returns:
        DownscaleDimensions with new width, height, and ratio

    Example:
        >>> dims = calculate_downscale_dimensions_auto(2048, 1536, 1024)
        >>> print(f"{dims.width}x{dims.height} at {dims.ratio}x")
        1024x768 at 0.5x
    """
    ratio = calculate_downscale_ratio(width, height, max_dimension)
    return calculate_downscaled_dimensions(width, height, ratio)
