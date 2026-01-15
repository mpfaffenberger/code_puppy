"""Advanced grid calibration and adaptive grid density for desktop automation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Literal

from pydantic_ai import RunContext

from .dependencies import PIL_AVAILABLE, PYAUTOGUI_AVAILABLE

if PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui = None

if PIL_AVAILABLE:
    from PIL import Image, ImageDraw, ImageFont
else:
    Image = None
    ImageDraw = None
    ImageFont = None

from rich.text import Text

from code_puppy.messaging import emit_error
from .rich_emit import emit_rich
from code_puppy.tools.common import generate_group_id

from .constants import ERROR_PILLOW_MISSING, ERROR_PYAUTOGUI_MISSING
from .result_types import BaseAutomationResult

# Grid density presets
GRID_DENSITIES = {
    "coarse": 200,  # Fast, low detail
    "normal": 100,  # Default, balanced
    "fine": 50,  # Slow, high detail
    "ultra": 25,  # Very slow, pixel-perfect
}

# Calibration marker configuration
CALIBRATION_MARKER_SIZE = 40
CALIBRATION_MARKER_COLOR = (0, 255, 0, 255)  # Green, opaque
CALIBRATION_TEXT_SIZE = 24
CALIBRATION_GRID_POINTS = [
    (100, 100),
    (500, 100),
    (900, 100),
    (100, 400),
    (500, 400),
    (900, 400),
    (100, 700),
    (500, 700),
    (900, 700),
]


class GridDensityResult(BaseAutomationResult):
    """Result from grid density operations."""

    density: str = "normal"
    spacing: int = 100
    estimated_vqa_time: float = 3.0  # seconds


class GridCalibrationResult(BaseAutomationResult):
    """Result from grid calibration operations."""

    calibration_screenshot: str | None = None
    markers_placed: int = 0
    grid_spacing: int = 100
    instructions: str = ""


class GridConfidenceResult(BaseAutomationResult):
    """Result with confidence score."""

    answer: str = ""
    confidence: float = 0.0
    grid_spacing: int = 100
    recommended_action: str = ""


def get_grid_spacing(density: Literal["coarse", "normal", "fine", "ultra"]) -> int:
    """
    Get grid spacing for a given density level.

    Args:
        density: One of "coarse", "normal", "fine", "ultra"

    Returns:
        Grid spacing in pixels
    """
    return GRID_DENSITIES.get(density, 100)


def estimate_vqa_time(grid_spacing: int) -> float:
    """
    Estimate VQA processing time based on grid density.

    Args:
        grid_spacing: Grid spacing in pixels

    Returns:
        Estimated time in seconds

    Note:
        Finer grids mean more visual complexity, which slows down VQA.
        These are rough estimates based on typical VQA performance.
    """
    # Base VQA time
    base_time = 2.5

    # Additional time penalty for finer grids
    if grid_spacing <= 25:
        return base_time + 2.0  # Ultra grid: ~4.5s
    elif grid_spacing <= 50:
        return base_time + 1.0  # Fine grid: ~3.5s
    elif grid_spacing <= 100:
        return base_time + 0.5  # Normal grid: ~3.0s
    else:
        return base_time  # Coarse grid: ~2.5s


def create_calibration_test_pattern(
    width: int = 1920,
    height: int = 1080,
    grid_spacing: int = 100,
) -> "Image.Image":
    """
    Create a test pattern image with numbered calibration markers.

    This creates a white background with:
    - Red coordinate grid (like normal grid overlay)
    - Green numbered circles at specific grid intersections
    - Large coordinate labels for easy verification

    Args:
        width: Image width in pixels
        height: Image height in pixels
        grid_spacing: Distance between grid lines

    Returns:
        PIL Image with test pattern
    """
    if not PYAUTOGUI_AVAILABLE:
        raise ImportError(f"{ERROR_PYAUTOGUI_MISSING} and {ERROR_PILLOW_MISSING}")

    # Create white background
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    # Load font
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        large_font = ImageFont.truetype(
            "/System/Library/Fonts/Helvetica.ttc", CALIBRATION_TEXT_SIZE
        )
    except (OSError, AttributeError):
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16
            )
            large_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                CALIBRATION_TEXT_SIZE,
            )
        except (OSError, AttributeError):
            font = ImageFont.load_default()
            large_font = font

    # Draw red coordinate grid
    for x in range(0, width, grid_spacing):
        draw.line([(x, 0), (x, height)], fill=(255, 0, 0, 128), width=1)
        label = str(x)
        draw.text((x + 2, 2), label, fill=(255, 0, 0), font=font)

    for y in range(0, height, grid_spacing):
        draw.line([(0, y), (width, y)], fill=(255, 0, 0, 128), width=1)
        label = str(y)
        draw.text((2, y + 2), label, fill=(255, 0, 0), font=font)

    # Draw green calibration markers at specific points
    marker_radius = CALIBRATION_MARKER_SIZE // 2
    for idx, (cx, cy) in enumerate(CALIBRATION_GRID_POINTS, start=1):
        # Skip points outside image bounds
        if cx >= width or cy >= height:
            continue

        # Draw circle
        draw.ellipse(
            [
                (cx - marker_radius, cy - marker_radius),
                (cx + marker_radius, cy + marker_radius),
            ],
            outline=CALIBRATION_MARKER_COLOR,
            fill=None,
            width=3,
        )

        # Draw crosshair at exact center
        cross_size = 10
        draw.line(
            [(cx - cross_size, cy), (cx + cross_size, cy)],
            fill=CALIBRATION_MARKER_COLOR,
            width=2,
        )
        draw.line(
            [(cx, cy - cross_size), (cx, cy + cross_size)],
            fill=CALIBRATION_MARKER_COLOR,
            width=2,
        )

        # Draw marker number
        marker_text = str(idx)
        # Get text bounding box for centering
        bbox = draw.textbbox((0, 0), marker_text, font=large_font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = cx - text_width // 2
        text_y = cy + marker_radius + 5

        # White background for text
        text_bg_bbox = (
            text_x - 2,
            text_y - 2,
            text_x + text_width + 2,
            text_y + text_height + 2,
        )
        draw.rectangle(text_bg_bbox, fill=(255, 255, 255, 200))
        draw.text((text_x, text_y), marker_text, fill=(0, 128, 0), font=large_font)

        # Draw coordinate label
        coord_text = f"({cx}, {cy})"
        coord_y = text_y + text_height + 5
        bbox = draw.textbbox((0, 0), coord_text, font=font)
        coord_width = bbox[2] - bbox[0]
        coord_x = cx - coord_width // 2

        draw.rectangle(
            (
                coord_x - 2,
                coord_y - 2,
                coord_x + coord_width + 2,
                coord_y + bbox[3] - bbox[1] + 2,
            ),
            fill=(255, 255, 255, 200),
        )
        draw.text((coord_x, coord_y), coord_text, fill=(0, 0, 0), font=font)

    return img


def register_grid_calibration_tools(agent):
    """Register advanced grid calibration and density tools."""

    @agent.tool
    def desktop_set_grid_density(
        context: RunContext,
        density: Literal["coarse", "normal", "fine", "ultra"] = "normal",
    ) -> GridDensityResult:
        """
        Set the grid density for future screenshot analysis operations.

        This doesn't take a screenshot - it just returns recommended settings.
        Use the spacing value with desktop_screenshot_analyze(grid_spacing=X).

        Args:
            density: Grid density level:
                - "coarse" (200px): Fastest, lowest detail - use for general questions
                - "normal" (100px): Default, balanced speed/accuracy
                - "fine" (50px): Slower, high detail - use for precise element location
                - "ultra" (25px): Slowest, pixel-perfect - use for sub-element precision

        Returns:
            GridDensityResult with spacing and estimated VQA time

        Examples:
            - desktop_set_grid_density(density="fine") -> Use 50px grid for precision
            - desktop_set_grid_density(density="coarse") -> Use 200px grid for speed
        """
        spacing = get_grid_spacing(density)
        estimated_time = estimate_vqa_time(spacing)

        emit_rich(
            f"[bold cyan]Grid density set to '{density}' ({spacing}px spacing)[/bold cyan]"
        )
        emit_rich(
            f"[dim]Estimated VQA time: {estimated_time:.1f}s (use with grid_spacing={spacing})[/dim]"
        )

        return GridDensityResult(
            success=True,
            density=density,
            spacing=spacing,
            estimated_vqa_time=estimated_time,
        )

    @agent.tool
    def desktop_show_grid_test_pattern(
        context: RunContext,
        grid_spacing: int = 100,
    ) -> GridCalibrationResult:
        """
        Create and save a grid calibration test pattern for visual verification.

        This generates an image with:
        - Red coordinate grid overlay (like VQA screenshots)
        - Green numbered circles at known coordinates
        - Coordinate labels at each marker

        Use this to verify that VQA is reading grid coordinates correctly:
        1. Generate test pattern
        2. Ask VQA "Where is marker #5?"
        3. Compare VQA's answer with the actual coordinates

        Args:
            grid_spacing: Distance between grid lines (default 100)

        Returns:
            GridCalibrationResult with test pattern path and instructions

        Example:
            1. desktop_show_grid_test_pattern(grid_spacing=100)
            2. VQA should identify marker #5 at approximately (500, 400)
        """
        if not PYAUTOGUI_AVAILABLE:
            return GridCalibrationResult(
                success=False,
                error=f"{ERROR_PYAUTOGUI_MISSING} and {ERROR_PILLOW_MISSING}",
            )

        group_id = generate_group_id("grid_test_pattern", f"spacing_{grid_spacing}")
        emit_rich(
            "[bold white on blue] GRID TEST PATTERN [/bold white on blue] 🎯 Creating calibration test pattern...",
            message_group=group_id,
        )

        try:
            # Get screen size
            screen_width, screen_height = pyautogui.size()

            # Create test pattern
            img = create_calibration_test_pattern(
                width=screen_width,
                height=screen_height,
                grid_spacing=grid_spacing,
            )

            # Save test pattern
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"grid_test_pattern_{grid_spacing}px_{timestamp}.png"
            save_path = Path(gettempdir()) / "code_puppy_rpa_calibration" / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(save_path)

            # Count valid markers
            markers_placed = sum(
                1
                for x, y in CALIBRATION_GRID_POINTS
                if x < screen_width and y < screen_height
            )

            instructions = f"""
Grid calibration test pattern created!

Test Pattern: {save_path}
Grid Spacing: {grid_spacing}px
Markers Placed: {markers_placed}

How to verify grid accuracy:
1. Open the test pattern image
2. Use desktop_screenshot_analyze() to ask about marker locations
3. Example: "Where is marker #5?"
4. VQA should report coordinates close to the labeled values

Marker reference:
"""
            for idx, (x, y) in enumerate(CALIBRATION_GRID_POINTS[:markers_placed], 1):
                instructions += f"  Marker #{idx}: ({x}, {y})\n"

            emit_rich(
                Text.from_markup(f"[green]Test pattern saved: {save_path}[/green]"),
                message_group=group_id,
            )
            emit_rich(
                Text.from_markup(f"[dim]{instructions.strip()}[/dim]"),
                message_group=group_id,
            )

            return GridCalibrationResult(
                success=True,
                calibration_screenshot=str(save_path),
                markers_placed=markers_placed,
                grid_spacing=grid_spacing,
                instructions=instructions,
            )

        except Exception as e:
            emit_error(
                Text.from_markup(f"[red]Failed to create test pattern: {e}[/red]"),
                message_group=group_id,
            )
            return GridCalibrationResult(
                success=False,
                error=str(e),
                grid_spacing=grid_spacing,
            )

    @agent.tool
    async def desktop_screenshot_with_confidence(
        context: RunContext,
        question: str,
        confidence_threshold: float = 0.7,
        initial_density: Literal["coarse", "normal", "fine", "ultra"] = "normal",
        auto_refine: bool = True,
    ) -> GridConfidenceResult:
        """
        Take screenshot and analyze with automatic grid refinement based on confidence.

        This is an intelligent wrapper around desktop_screenshot_analyze that:
        1. Starts with initial_density grid
        2. If confidence < threshold and auto_refine=True, retries with finer grid
        3. Returns result with confidence score and recommendations

        Args:
            question: Question to ask about the screenshot
            confidence_threshold: Minimum acceptable confidence (0.0-1.0)
            initial_density: Starting grid density ("coarse", "normal", "fine", "ultra")
            auto_refine: Automatically retry with finer grid if confidence is low

        Returns:
            GridConfidenceResult with answer, confidence, and recommendations

        Example:
            - desktop_screenshot_with_confidence(
                question="Where is the Submit button?",
                confidence_threshold=0.8,
                auto_refine=True
              )
              -> Tries normal grid first, refines to fine grid if needed
        """
        from .screen_capture import screenshot_analyze  # noqa: TCH001

        group_id = generate_group_id("screenshot_with_confidence", question[:50])
        emit_rich(
            f"[bold white on blue] CONFIDENCE-BASED SCREENSHOT [/bold white on blue] question='{question[:80]}...' threshold={confidence_threshold}",
            message_group=group_id,
        )

        if not PYAUTOGUI_AVAILABLE:
            return GridConfidenceResult(
                success=False,
                error=f"{ERROR_PYAUTOGUI_MISSING} and {ERROR_PILLOW_MISSING}",
            )

        # Map density to grid spacing
        initial_spacing = get_grid_spacing(initial_density)

        # Use unified screenshot_analyze() with auto_refine enabled
        result = await screenshot_analyze(
            question=question,
            add_grid=True,
            grid_spacing=initial_spacing,
            confidence_threshold=confidence_threshold,
            auto_refine=auto_refine,
        )

        if not result.get("success"):
            return GridConfidenceResult(
                success=False,
                error=result.get("error", "Screenshot analysis failed"),
            )

        confidence = result.get("confidence", 0.0)
        answer = result.get("answer", "")

        # Determine which grid density was used (if refined)
        final_density = initial_density
        if result.get("grid_refined"):
            final_density = result.get("grid_density", initial_density)

        final_spacing = get_grid_spacing(final_density)

        # Generate recommendations
        density_order = ["coarse", "normal", "fine", "ultra"]
        if confidence < confidence_threshold:
            try:
                current_idx = density_order.index(final_density)
                if current_idx < len(density_order) - 1:
                    next_density = density_order[current_idx + 1]
                    recommended_action = (
                        f"Confidence still low ({confidence:.2f}). "
                        f"Try: screenshot_analyze(question='{question}', grid_spacing={get_grid_spacing(next_density)}) "
                        f"or use accessibility API for better precision."
                    )
                else:
                    recommended_action = (
                        "Already at finest grid (ultra). "
                        "Consider using accessibility API (desktop_find_accessible_element) "
                        "or VQA without grid for general questions."
                    )
            except ValueError:
                recommended_action = (
                    "Consider using accessibility API for better precision."
                )
        else:
            recommended_action = "Confidence acceptable. Proceed with action."

        return GridConfidenceResult(
            success=True,
            question=question,
            answer=answer,
            confidence=confidence,
            grid_density=final_density,
            grid_spacing=final_spacing,
            confidence_threshold=confidence_threshold,
            recommended_action=recommended_action,
        )
