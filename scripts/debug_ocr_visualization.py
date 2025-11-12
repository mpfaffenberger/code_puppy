#!/usr/bin/env python3
"""
OCR Debugging Visualization Script

Captures screenshots, runs OCR, and outputs annotated images with bounding boxes.
Use this to debug OCR detection, coordinate accuracy, and confidence scores.

Usage:
    python debug_ocr_visualization.py

    OR with window name:
    python debug_ocr_visualization.py --window "Calculator"

Outputs:
    - debug_ocr_original_2x.png - Original Retina screenshot
    - debug_ocr_normalized_1x.png - Normalized image fed to OCR
    - debug_ocr_annotated.png - Original with bounding boxes + confidence
    - debug_ocr_results.txt - Detailed text results
"""

import argparse
import sys
from pathlib import Path

# Add code_puppy to path
sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image, ImageDraw, ImageFont
from code_puppy.tools.gui_cub.screen_capture.capture import _safe_screenshot
from code_puppy.tools.gui_cub.ocr.extraction import (
    prepare_ocr_image,
    extract_text_from_image,
)
from code_puppy.tools.gui_cub.platform import get_screen_scale_factor
from code_puppy.tools.gui_cub.window_control import (
    _get_active_window_bounds_impl,
    _focus_window_impl,
)


def draw_ocr_boxes(image: Image.Image, ocr_result, scale_factor: float) -> Image.Image:
    """
    Draw bounding boxes on image with confidence scores.

    Args:
        image: PIL Image to annotate
        ocr_result: OCRExtractResult with text_elements
        scale_factor: HiDPI scale factor

    Returns:
        Annotated PIL Image with boxes and labels
    """
    # Create a copy to draw on
    annotated = image.copy()

    # Convert to RGB if needed (can't draw colors on grayscale/L mode)
    if annotated.mode != "RGB" and annotated.mode != "RGBA":
        annotated = annotated.convert("RGB")

    draw = ImageDraw.Draw(annotated)

    # Try to load a font, fall back to default
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14
            )
        except (OSError, IOError):
            font = ImageFont.load_default()

    # Color scheme
    HIGH_CONF_COLOR = (0, 255, 0)  # Green for >70%
    MED_CONF_COLOR = (255, 165, 0)  # Orange for 50-70%
    LOW_CONF_COLOR = (255, 0, 0)  # Red for <50%

    print(f"\n{'=' * 80}")
    print(f"OCR RESULTS: {len(ocr_result.text_elements)} text elements found")
    print(f"{'=' * 80}\n")

    for idx, elem in enumerate(ocr_result.text_elements, 1):
        # Choose color based on confidence
        if elem.confidence > 0.7:
            color = HIGH_CONF_COLOR
            conf_label = "HIGH"
        elif elem.confidence > 0.5:
            color = MED_CONF_COLOR
            conf_label = "MED"
        else:
            color = LOW_CONF_COLOR
            conf_label = "LOW"

        # Coordinates are already in the same space as the image (logical)
        # ImageGrab returns logical resolution, so no conversion needed
        x = int(elem.x)
        y = int(elem.y)
        w = int(elem.width)
        h = int(elem.height)

        # Draw bounding box
        box = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
        draw.line(box, fill=color, width=3)

        # Draw label with confidence
        label = f"{elem.confidence:.0%}"
        label_bg = draw.textbbox((x, y - 20), label, font=font)
        draw.rectangle(label_bg, fill=color)
        draw.text((x, y - 20), label, fill=(0, 0, 0), font=font)

        # Print details
        print(f"[{idx:2d}] '{elem.text}'")
        print(f"     Confidence: {elem.confidence:.2%} ({conf_label})")
        print(f"     Position: ({x}, {y})")
        print(f"     Size: {w}x{h}")
        print(f"     Box: ({x}, {y}, {w}, {h})")
        print()

    return annotated


def save_debug_images(original_2x, normalized_1x, annotated, ocr_result):
    """
    Save all debug images and text results.
    """
    output_dir = Path.cwd()

    # Save original 2x image
    original_path = output_dir / "debug_ocr_original_2x.png"
    original_2x.save(original_path)
    print(f"✅ Saved original 2x image: {original_path}")
    print(f"   Dimensions: {original_2x.width}x{original_2x.height}")

    # Save normalized 1x image (what OCR sees)
    normalized_path = output_dir / "debug_ocr_normalized_1x.png"
    normalized_1x.save(normalized_path)
    print(f"✅ Saved normalized 1x image: {normalized_path}")
    print(f"   Dimensions: {normalized_1x.width}x{normalized_1x.height}")

    # Save annotated image
    annotated_path = output_dir / "debug_ocr_annotated.png"
    annotated.save(annotated_path)
    print(f"✅ Saved annotated image: {annotated_path}")

    # Save text results
    results_path = output_dir / "debug_ocr_results.txt"
    with open(results_path, "w") as f:
        f.write("OCR DEBUG RESULTS\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total elements found: {len(ocr_result.text_elements)}\n")
        f.write(f"Average confidence: {ocr_result.average_confidence:.2%}\n\n")
        f.write("Full text extracted:\n")
        f.write("-" * 80 + "\n")
        f.write(ocr_result.full_text + "\n")
        f.write("-" * 80 + "\n\n")
        f.write("Individual text elements:\n\n")

        for idx, elem in enumerate(ocr_result.text_elements, 1):
            f.write(f"[{idx:2d}] Text: '{elem.text}'\n")
            f.write(f"     Confidence: {elem.confidence:.2%}\n")
            f.write(f"     Position: ({elem.x}, {elem.y})\n")
            f.write(f"     Size: {elem.width}x{elem.height}\n")
            f.write(f"     Center: ({elem.center_x}, {elem.center_y})\n")
            f.write("\n")

    print(f"✅ Saved text results: {results_path}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Debug OCR by capturing screenshots and visualizing detection boxes"
    )
    parser.add_argument(
        "--window",
        "-w",
        type=str,
        help="Window title to capture (e.g., 'Calculator', 'TextEdit')",
    )
    parser.add_argument(
        "--fullscreen",
        "-f",
        action="store_true",
        help="Capture full screen instead of window",
    )

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("OCR DEBUGGING VISUALIZATION TOOL")
    print("=" * 80 + "\n")

    # Get scale factor
    scale_factor = get_screen_scale_factor()
    print(f"Screen scale factor: {scale_factor}x")
    if scale_factor > 1.0:
        print(
            f"Retina display detected - images will be normalized {scale_factor}x → 1x for OCR\n"
        )
    else:
        print("Standard DPI display - no normalization needed\n")

    # Determine capture region
    region = None
    if not args.fullscreen:
        # Try to get window bounds
        if args.window:
            print(f"Focusing window: '{args.window}'...")
            focus_result = _focus_window_impl(args.window)
            if not focus_result.success:
                print(f"❌ Failed to focus window: {focus_result.error}")
                print("Falling back to active window...\n")
            else:
                print("✅ Focused window\n")
                import time

                time.sleep(0.3)  # Wait for focus

        print("Getting active window bounds...")
        bounds = _get_active_window_bounds_impl()
        if bounds.success and bounds.x is not None:
            region = (bounds.x, bounds.y, bounds.width, bounds.height)
            print(
                f"✅ Window bounds (logical): ({bounds.x}, {bounds.y}, {bounds.width}, {bounds.height})"
            )
            print(f"   Window title: {bounds.window_title or 'Unknown'}\n")

            # Convert to physical for screenshot
            region_phys = tuple(int(v * scale_factor) for v in region)
            print(f"Capture region (physical): {region_phys}\n")
        else:
            print(f"❌ Failed to get window bounds: {bounds.error}")
            print("Capturing full screen instead...\n")
            region = None
            region_phys = None
    else:
        print("Capturing full screen...\n")
        region_phys = None

    # Capture screenshot
    print("📸 Capturing screenshot...")
    screenshot_2x = _safe_screenshot(region=region_phys)
    print(f"✅ Captured: {screenshot_2x.width}x{screenshot_2x.height} pixels\n")

    # Prepare normalized image for OCR (NO downscaling - ImageGrab already returns logical resolution)
    print("🔬 Preparing image for OCR (grayscale, contrast - NO downscaling)...")
    normalized_1x = prepare_ocr_image(
        screenshot_2x, 1.0
    )  # Force scale_factor=1.0 (no downscaling)
    print(
        f"✅ Normalized: {normalized_1x.width}x{normalized_1x.height} pixels ({normalized_1x.mode})\n"
    )

    # Run OCR (pass original screenshot, extraction.py will handle normalization)
    print("🔍 Running OCR...")
    ocr_result = extract_text_from_image(
        screenshot_2x,
        language="eng",
        scale_factor=scale_factor,  # This is used for coordinate conversion only now
        region_offset=(region_phys[0], region_phys[1]) if region_phys else None,
    )

    if not ocr_result.success:
        print(f"❌ OCR failed: {ocr_result.error}")
        return 1

    print("✅ OCR complete!\n")
    print(f"Found {len(ocr_result.text_elements)} text elements")
    print(f"Average confidence: {ocr_result.average_confidence:.2%}\n")

    # Draw bounding boxes
    print("🎨 Drawing bounding boxes...")
    annotated = draw_ocr_boxes(screenshot_2x, ocr_result, scale_factor)

    # Save all debug outputs
    print(f"\n{'=' * 80}")
    print("SAVING DEBUG OUTPUT")
    print(f"{'=' * 80}\n")
    save_debug_images(screenshot_2x, normalized_1x, annotated, ocr_result)

    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}\n")
    print(f"Total text elements: {len(ocr_result.text_elements)}")
    print(f"Average confidence: {ocr_result.average_confidence:.2%}")
    print("\nConfidence breakdown:")

    high_conf = sum(1 for e in ocr_result.text_elements if e.confidence > 0.7)
    med_conf = sum(1 for e in ocr_result.text_elements if 0.5 < e.confidence <= 0.7)
    low_conf = sum(1 for e in ocr_result.text_elements if e.confidence <= 0.5)

    print(f"  HIGH (>70%): {high_conf} elements")
    print(f"  MED (50-70%): {med_conf} elements")
    print(f"  LOW (<50%): {low_conf} elements")

    print(f"\n{'=' * 80}")
    print("Check the output images to verify:")
    print("  1. Are text regions detected correctly? (annotated image)")
    print("  2. Are bounding boxes in the right place? (annotated image)")
    print("  3. What does the normalized image look like? (1x image)")
    print("  4. What are the actual confidence scores? (results.txt)")
    print(f"{'=' * 80}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
