#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test macOS minimize button with grid search - finds exact position.

This version tries multiple positions in a grid pattern to find
the exact minimize button location.
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

from code_puppy.tools.gui_cub.platform import get_screen_scale_factor

print("=" * 70)
print("macOS VQA Test - Grid Search for Minimize Button")
print("=" * 70)

# Step 1: Get screen info
print("\n[1] Screen Information...")
scale_factor = get_screen_scale_factor()
screen_size = pyautogui.size()
print(f"   Screen size: {screen_size.width}x{screen_size.height} (logical)")
print(f"   Scale factor: {scale_factor}x")

# Step 2: Find Spotify window
print("\n[2] Finding Spotify...")

try:
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
    )

    window_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    )

    spotify_window = None
    for window in window_list:
        owner_name = window.get("kCGWindowOwnerName", "")
        window_name = window.get("kCGWindowName", "")

        if "Spotify" in owner_name:
            bounds = window.get("kCGWindowBounds", {})
            if bounds.get("Width", 0) > 100 and bounds.get("Height", 0) > 100:
                spotify_window = window
                print(f"   Found Spotify: '{window_name}'")
                break

    if not spotify_window:
        print("   [X] Spotify window not found!")
        sys.exit(1)

    bounds = spotify_window["kCGWindowBounds"]
    window_x = int(bounds["X"])
    window_y = int(bounds["Y"])
    window_width = int(bounds["Width"])
    window_height = int(bounds["Height"])

    print(f"   Window: {window_width}x{window_height} at ({window_x}, {window_y})")

except Exception as e:
    print(f"   [X] Error: {e}")
    sys.exit(1)

# Step 3: Focus Spotify
print("\n[3] Focusing Spotify...")

try:
    subprocess.run(
        ["osascript", "-e", 'tell application "Spotify" to activate'],
        check=True,
        capture_output=True,
        timeout=5,
    )
    time.sleep(1.0)
    print("   [OK] Spotify focused")
except Exception as e:
    print(f"   [!] Focus failed: {e}")

# Step 4: Capture screenshot with grid overlay
print("\n[4] Capturing Screenshot with Grid...")

try:
    x_phys = int(window_x * scale_factor)
    y_phys = int(window_y * scale_factor)
    w_phys = int(window_width * scale_factor)
    h_phys = int(window_height * scale_factor)

    screenshot = pyautogui.screenshot(region=(x_phys, y_phys, w_phys, h_phys))

    # Create grid overlay
    debug_img = screenshot.copy()
    draw = ImageDraw.Draw(debug_img)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except Exception:
        font = None

    # Grid of positions to try (X offset from left, Y offset from top)
    grid_positions = [
        (35, 12),
        (38, 12),
        (41, 12),
        (44, 12),
        (35, 14),
        (38, 14),
        (41, 14),
        (44, 14),
        (35, 16),
        (38, 16),
        (41, 16),
        (44, 16),
        (35, 18),
        (38, 18),
        (41, 18),
        (44, 18),
    ]

    colors = ["red", "orange", "yellow", "green", "blue", "purple", "pink", "cyan"]

    for i, (offset_x, offset_y) in enumerate(grid_positions):
        # Convert to screenshot coordinates (physical)
        x_in_screenshot = int(offset_x * scale_factor)
        y_in_screenshot = int(offset_y * scale_factor)

        color = colors[i % len(colors)]

        # Draw small crosshair
        size = 8
        draw.line(
            [
                (x_in_screenshot - size, y_in_screenshot),
                (x_in_screenshot + size, y_in_screenshot),
            ],
            fill=color,
            width=2,
        )
        draw.line(
            [
                (x_in_screenshot, y_in_screenshot - size),
                (x_in_screenshot, y_in_screenshot + size),
            ],
            fill=color,
            width=2,
        )

        # Draw label
        label = f"{i + 1}"
        draw.text(
            (x_in_screenshot + 10, y_in_screenshot - 5), label, fill=color, font=font
        )

    grid_path = Path.cwd() / "test_spotify_grid.png"
    debug_img.save(grid_path)
    print(f"   Grid screenshot saved: {grid_path}")
    print(f"   {len(grid_positions)} positions marked")

except Exception as e:
    print(f"   [!] Screenshot failed: {e}")
    sys.exit(1)

# Step 5: Show grid positions
print("\n[5] Grid Positions (offset from window top-left):")
for i, (offset_x, offset_y) in enumerate(grid_positions):
    print(f"   {i + 1:2d}. ({offset_x}, {offset_y}) px")

print("\n" + "=" * 70)
print("INSTRUCTIONS")
print("=" * 70)
print(f"1. Open: {grid_path}")
print("2. Find which numbered crosshair is ON the yellow minimize button")
print("3. Note the number (1-16)")
print("4. Tell me the number and I'll update the script!")
print("\nThe colored crosshairs show different positions to try.")
print("=" * 70)
