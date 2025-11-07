#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test macOS OCR on Chrome browser window.

This script tests:
1. Window detection and focus for Chrome
2. Screenshot capture with Retina/HiDPI handling
3. OCR text extraction using provider chain (Vision -> Tesseract)
4. Coordinate accuracy on macOS Retina displays

Usage:
    python test_macos_ocr_chrome.py

Make sure Chrome is open with some text visible!
"""

import subprocess
import sys
import platform
import time
from pathlib import Path

if platform.system() != "Darwin":
    print("[X] This script must be run on macOS!")
    sys.exit(1)

import pyautogui
from PIL import ImageDraw, ImageFont

from code_puppy.tools.gui_cub.ocr_providers import get_ocr_provider
from code_puppy.tools.gui_cub.platform import get_screen_scale_factor

print("=" * 70)
print("macOS Chrome OCR Test")
print("=" * 70)

# Step 1: Get screen info
print("\n[1] Screen Information...")
scale_factor = get_screen_scale_factor()
screen_size = pyautogui.size()
print(f"   Screen size: {screen_size.width}x{screen_size.height} (logical)")
print(f"   Scale factor: {scale_factor}x")
print(
    f"   Physical pixels: {int(screen_size.width * scale_factor)}x{int(screen_size.height * scale_factor)}"
)

# Step 2: Find and focus Chrome
print("\n[2] Finding Chrome Browser...")

try:
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
    )

    # Get list of windows
    window_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    )

    chrome_window = None
    for window in window_list:
        owner_name = window.get("kCGWindowOwnerName", "")
        window_name = window.get("kCGWindowName", "")

        # Look for Chrome
        if "Chrome" in owner_name or "Google Chrome" in owner_name:
            bounds = window.get("kCGWindowBounds", {})
            if bounds.get("Width", 0) > 100 and bounds.get("Height", 0) > 100:
                chrome_window = window
                print(f"   Found Chrome window: '{window_name}'")
                print(f"   Bounds: {bounds}")
                break

    if not chrome_window:
        print("   [X] Chrome window not found!")
        print("   Please open Chrome with some text visible and try again.")
        sys.exit(1)

    # Extract bounds
    bounds = chrome_window["kCGWindowBounds"]
    x = int(bounds["X"])
    y = int(bounds["Y"])
    width = int(bounds["Width"])
    height = int(bounds["Height"])

    print(f"   Window position (points): ({x}, {y})")
    print(f"   Window size (points): {width}x{height}")

    # Convert to physical pixels for screenshot
    x_physical = int(x * scale_factor)
    y_physical = int(y * scale_factor)
    width_physical = int(width * scale_factor)
    height_physical = int(height * scale_factor)

    print(f"   Window position (pixels): ({x_physical}, {y_physical})")
    print(f"   Window size (pixels): {width_physical}x{height_physical}")

except Exception as e:
    print(f"   [X] Error finding Chrome: {e}")
    sys.exit(1)

# Step 3: Focus Chrome (using AppleScript)
print("\n[3] Focusing Chrome Window...")

try:
    # Activate Chrome application
    subprocess.run(
        ["osascript", "-e", 'tell application "Google Chrome" to activate'],
        check=True,
        capture_output=True,
        timeout=5,
    )
    print("   [OK] Chrome focused")

    # Wait a moment for window to come to front
    time.sleep(0.5)

except Exception as e:
    print(f"   [!] Could not focus Chrome: {e}")
    print("   Continuing anyway...")

# Step 4: Capture screenshot
print("\n[4] Capturing Screenshot...")

try:
    # Capture using physical pixel coordinates
    screenshot = pyautogui.screenshot(
        region=(x_physical, y_physical, width_physical, height_physical)
    )

    print(f"   Screenshot captured: {screenshot.width}x{screenshot.height} pixels")

    # Save screenshot
    screenshot_path = Path.cwd() / "test_chrome_screenshot.png"
    screenshot.save(screenshot_path)
    print(f"   Saved to: {screenshot_path}")

except Exception as e:
    print(f"   [X] Screenshot failed: {e}")
    sys.exit(1)

# Step 5: Run OCR
print("\n[5] Running OCR...")

try:
    # Get OCR provider chain
    ocr_chain = get_ocr_provider()
    available_providers = ocr_chain.get_available_providers()
    print(f"   Available OCR providers: {available_providers}")

    # Run OCR
    print("   Extracting text...")
    result = ocr_chain.extract_text(screenshot, language="en")

    print("\n   Results:")
    print(f"      Success: {result.success}")
    print(f"      Provider used: {result.provider}")
    print(f"      Words found: {len(result.words)}")

    if result.error:
        print(f"      Error: {result.error}")

    if result.full_text:
        print("\n   Full text (first 500 chars):")
        print("   " + "=" * 60)
        text_preview = result.full_text[:500]
        for line in text_preview.split("\n"):
            print(f"   {line}")
        if len(result.full_text) > 500:
            print("   [... truncated ...]")
        print("   " + "=" * 60)

    if result.words:
        print("\n   Sample words (first 10):")
        for i, word in enumerate(result.words[:10]):
            print(f"      {i + 1}. '{word.text}' (confidence: {word.confidence:.2f})")
            print(f"         bbox: {word.bbox}")

except Exception as e:
    print(f"   [X] OCR failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Step 6: Create debug visualization
print("\n[6] Creating Debug Visualization...")

try:
    debug_img = screenshot.copy()
    draw = ImageDraw.Draw(debug_img)

    # Try to load a font
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except Exception:
        font = None
        small_font = None

    # Draw bounding boxes for each word
    colors = ["red", "green", "blue", "yellow", "orange", "purple"]
    for i, word in enumerate(result.words):
        color = colors[i % len(colors)]
        x, y, w, h = word.bbox

        # Draw rectangle
        draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=2)

        # Draw text label
        label = f"{word.text[:20]}"
        draw.text((x, y - 15), label, fill=color, font=small_font)

    # Add summary text at top
    summary = f"OCR: {len(result.words)} words found using {result.provider}"
    draw.text((10, 10), summary, fill="white", font=font)

    # Save debug image
    debug_path = Path.cwd() / "test_chrome_ocr_debug.png"
    debug_img.save(debug_path)
    print(f"   Debug visualization saved to: {debug_path}")

except Exception as e:
    print(f"   [!] Debug visualization failed: {e}")

# Step 7: Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Chrome window: {width}x{height} at ({x}, {y}) [logical points]")
print(f"Screenshot: {screenshot.width}x{screenshot.height} pixels")
print(f"Scale factor: {scale_factor}x")
print(f"OCR provider: {result.provider}")
print(f"Words found: {len(result.words)}")
print(f"Text preview: {result.full_text[:100] if result.full_text else '(no text)'}...")

print("\n[FILES] Generated Files:")
print(f"   - {screenshot_path} (screenshot)")
print(f"   - {debug_path} (debug visualization with bounding boxes)")

print("\n[NEXT STEPS]:")
print("   1. Open test_chrome_ocr_debug.png to see bounding boxes")
print("   2. Verify text was correctly extracted")
print("   3. Check if coordinates are accurate")

if len(result.words) == 0:
    print("\n[!] WARNING: No text found!")
    print("   Possible reasons:")
    print("   - Chrome window might be showing images/graphics only")
    print("   - Text might be in a canvas/video element (not readable by OCR)")
    print("   - Screenshot might be blank (check test_chrome_screenshot.png)")
    print("   - Try opening a text-heavy webpage (e.g., Wikipedia, GitHub)")

print("\n" + "=" * 70)
