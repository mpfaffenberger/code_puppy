"""VQA coordinate math utilities.

Pure functions for VQA-related coordinate transformations and scaling.
No I/O operations, just math.
"""

from .calculator import (
    CropRegion,
    DownscaleDimensions,
    calculate_physical_crop_box,
    calculate_downscale_ratio,
    calculate_downscaled_dimensions,
    calculate_downscale_dimensions_auto,
)

__all__ = [
    "CropRegion",
    "DownscaleDimensions",
    "calculate_physical_crop_box",
    "calculate_downscale_ratio",
    "calculate_downscaled_dimensions",
    "calculate_downscale_dimensions_auto",
]
