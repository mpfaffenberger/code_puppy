"""Image manipulation utilities for screen capture."""

from __future__ import annotations

from io import BytesIO

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None

from ..constants import (
    DEFAULT_GRID_SPACING,
    GRID_LINE_COLOR,
    GRID_LINE_WIDTH,
    GRID_TEXT_COLOR,
)

# VQA image size limit (Claude API has 5MB max, use 4.5MB for safety margin)
VQA_MAX_IMAGE_SIZE_BYTES = 4_500_000  # 4.5 MB
VQA_MAX_RESOLUTION = (1920, 1200)  # Max resolution for downscaling


def resize_image_if_needed(
    image_bytes: bytes,
    max_size_bytes: int = VQA_MAX_IMAGE_SIZE_BYTES,
    max_resolution: tuple[int, int] = VQA_MAX_RESOLUTION,
) -> tuple[bytes, float, str]:
    """
    Resize image if it exceeds size limit, maintaining aspect ratio.

    This function uses a progressive compression strategy:
    1. First tries PNG optimization
    2. Then tries JPEG with progressively lower quality
    3. Finally resizes if needed with iterative quality reduction

    Args:
        image_bytes: Original PNG image bytes
        max_size_bytes: Maximum allowed file size in bytes
        max_resolution: Maximum (width, height) for downscaling

    Returns:
        Tuple of (resized_image_bytes, scale_factor, format)
        scale_factor is 1.0 if no resize needed, < 1.0 if downscaled
        format is 'PNG' or 'JPEG' indicating the output format
    """
    if not PIL_AVAILABLE:
        return image_bytes, 1.0, "PNG"

    # Check if resize needed
    if len(image_bytes) <= max_size_bytes:
        return image_bytes, 1.0, "PNG"

    # Load image
    img = Image.open(BytesIO(image_bytes))
    original_size = img.size

    # Convert RGBA to RGB if needed (JPEG doesn't support transparency)
    if img.mode == "RGBA":
        rgb_img = Image.new("RGB", img.size, (255, 255, 255))
        rgb_img.paste(img, mask=img.split()[3])  # Use alpha channel as mask
        img = rgb_img
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Strategy 1: Try PNG optimization first
    output = BytesIO()
    img.save(output, format="PNG", optimize=True)
    output.seek(0)
    compressed_bytes = output.getvalue()
    if len(compressed_bytes) <= max_size_bytes:
        return compressed_bytes, 1.0, "PNG"

    # Strategy 2: Try JPEG compression with progressively lower quality
    for quality in [95, 85, 75, 65, 55]:
        output = BytesIO()
        img.save(output, format="JPEG", quality=quality, optimize=True)
        output.seek(0)
        jpeg_bytes = output.getvalue()
        if len(jpeg_bytes) <= max_size_bytes:
            return jpeg_bytes, 1.0, "JPEG"

    # Strategy 3: Calculate scaling to fit within max_resolution
    width_scale = max_resolution[0] / original_size[0]
    height_scale = max_resolution[1] / original_size[1]
    scale_factor = min(width_scale, height_scale, 1.0)  # Don't upscale

    # If scale_factor is still 1.0 (image is within resolution limits),
    # we need to force downscaling since compression alone didn't work
    if scale_factor >= 1.0:
        # Calculate required scale based on file size ratio (with some buffer)
        size_ratio = max_size_bytes / len(image_bytes)
        # Use square root since area scales quadratically with linear dimensions
        scale_factor = min(0.8, (size_ratio * 0.9) ** 0.5)  # 90% of target for safety

    # Resize image with calculated scale factor
    new_size = (
        max(1, int(original_size[0] * scale_factor)),
        max(1, int(original_size[1] * scale_factor)),
    )
    resized_img = img.resize(new_size, Image.Resampling.LANCZOS)

    # Try JPEG compression on resized image with progressive quality reduction
    for quality in [95, 85, 75, 65, 55, 45]:
        output = BytesIO()
        resized_img.save(output, format="JPEG", quality=quality, optimize=True)
        output.seek(0)
        resized_bytes = output.getvalue()
        if len(resized_bytes) <= max_size_bytes:
            return resized_bytes, scale_factor, "JPEG"

    # Last resort: aggressive downscaling
    # If we're still too large, scale down further
    while len(resized_bytes) > max_size_bytes and scale_factor > 0.1:
        scale_factor *= 0.8
        new_size = (
            max(1, int(original_size[0] * scale_factor)),
            max(1, int(original_size[1] * scale_factor)),
        )
        resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
        output = BytesIO()
        resized_img.save(output, format="JPEG", quality=55, optimize=True)
        output.seek(0)
        resized_bytes = output.getvalue()

    return resized_bytes, scale_factor, "JPEG"


def add_coordinate_grid(
    image: "Image.Image",
    grid_spacing: int = DEFAULT_GRID_SPACING,
    line_color: tuple[int, int, int, int] = GRID_LINE_COLOR,
    text_color: tuple[int, int, int] = GRID_TEXT_COLOR,
    line_width: int = GRID_LINE_WIDTH,
) -> "Image.Image":
    """
    Add a coordinate grid overlay to an image for VQA reference.

    Args:
        image: PIL Image to add grid to
        grid_spacing: Distance between grid lines in pixels
        line_color: RGBA color for grid lines
        text_color: RGB color for coordinate labels
        line_width: Width of grid lines in pixels

    Returns:
        New PIL Image with grid overlay
    """
    if not PIL_AVAILABLE:
        return image

    from PIL import ImageDraw, ImageFont

    # Create a copy to avoid modifying original
    img_with_grid = image.copy()
    draw = ImageDraw.Draw(img_with_grid, "RGBA")

    width, height = image.size

    # Try to load a font, fall back to default if not available
    try:
        # Try to use a system font
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except (OSError, AttributeError):
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16
            )
        except (OSError, AttributeError):
            # Fall back to default PIL font
            font = ImageFont.load_default()

    # Draw vertical grid lines
    for x in range(0, width, grid_spacing):
        draw.line([(x, 0), (x, height)], fill=line_color, width=line_width)
        # Add x-coordinate label at top
        label = str(x)
        # Draw text with background for visibility
        bbox = draw.textbbox((x + 2, 2), label, font=font)
        draw.rectangle(bbox, fill=(255, 255, 255, 200))  # White background
        draw.text((x + 2, 2), label, fill=text_color, font=font)

    # Draw horizontal grid lines
    for y in range(0, height, grid_spacing):
        draw.line([(0, y), (width, y)], fill=line_color, width=line_width)
        # Add y-coordinate label on left
        label = str(y)
        bbox = draw.textbbox((2, y + 2), label, font=font)
        draw.rectangle(bbox, fill=(255, 255, 255, 200))  # White background
        draw.text((2, y + 2), label, fill=text_color, font=font)

    return img_with_grid
