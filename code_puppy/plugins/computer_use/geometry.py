"""Coordinate spaces used by macOS computer use."""

from __future__ import annotations

from dataclasses import dataclass

from .backend_types import ComputerUseError


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def as_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class CaptureGeometry:
    """Mapping between screenshot pixels and global Quartz screen points.

    ScreenCaptureKit and CGWindow bounds use a top-left global coordinate
    system. AppKit uses bottom-left coordinates; callers that provide AppKit
    coordinates must opt into the explicit conversion helper below.
    """

    window_points: Rect
    image_width_pixels: int
    image_height_pixels: int
    backing_scale: float

    def __post_init__(self) -> None:
        if self.window_points.width <= 0 or self.window_points.height <= 0:
            raise ComputerUseError("Window bounds must have positive dimensions.")
        if self.image_width_pixels <= 0 or self.image_height_pixels <= 0:
            raise ComputerUseError("Screenshot dimensions must be positive.")
        if self.backing_scale <= 0:
            raise ComputerUseError("Backing scale must be positive.")

    def screenshot_to_quartz(self, x: float, y: float) -> tuple[float, float]:
        if not (0 <= x < self.image_width_pixels):
            raise ComputerUseError(
                f"Screenshot x={x} is outside 0..{self.image_width_pixels - 1}."
            )
        if not (0 <= y < self.image_height_pixels):
            raise ComputerUseError(
                f"Screenshot y={y} is outside 0..{self.image_height_pixels - 1}."
            )
        return (
            self.window_points.x
            + (float(x) / self.image_width_pixels) * self.window_points.width,
            self.window_points.y
            + (float(y) / self.image_height_pixels) * self.window_points.height,
        )

    @staticmethod
    def appkit_to_quartz(
        x: float, y: float, display_points: Rect
    ) -> tuple[float, float]:
        """Convert bottom-left AppKit coordinates to top-left Quartz points."""
        return x, display_points.y + display_points.height - (y - display_points.y)

    def as_dict(self) -> dict[str, object]:
        return {
            "window_bounds_points": self.window_points.as_dict(),
            "screenshot_size_pixels": {
                "width": self.image_width_pixels,
                "height": self.image_height_pixels,
            },
            "backing_scale": self.backing_scale,
            "screenshot_coordinate_system": "top-left, window-local pixels",
            "action_coordinate_system": "top-left, global Quartz points",
        }
