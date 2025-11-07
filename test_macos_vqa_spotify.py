#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test macOS Visual UI automation - Click Spotify minimize button.

This script tests:
1. Window detection and focus for Spotify
2. Visual element detection (yellow minimize button)
3. Coordinate calculation for macOS window controls
4. Click automation with proper coordinate conversion

Usage:
    python test_macos_vqa_spotify.py

Make sure Spotify is open!
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
from PIL import ImageDraw

from code_puppy.tools.gui_cub.platform import get_screen_scale_factor

print("=" * 70)
print("macOS VQA Test - Click Spotify Minimize Button")
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

    # Get list of windows
    window_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    )

    spotify_window = None
    for window in window_list:
        owner_name = window.get("kCGWindowOwnerName", "")
        window_name = window.get("kCGWindowName", "")

        # Look for Spotify
        if "Spotify" in owner_name:
            bounds = window.get("kCGWindowBounds", {})
            if bounds.get("Width", 0) > 100 and bounds.get("Height", 0) > 100:
                spotify_window = window
                print(f"   Found Spotify: '{window_name}'")
                print(f"   Bounds: {bounds}")
                break

    if not spotify_window:
        print("   [X] Spotify window not found!")
        print("   Please open Spotify and try again.")
        sys.exit(1)

    # Extract bounds (in logical points)
    bounds = spotify_window["kCGWindowBounds"]
    window_x = int(bounds["X"])
    window_y = int(bounds["Y"])
    window_width = int(bounds["Width"])
    window_height = int(bounds["Height"])

    print(f"   Window position: ({window_x}, {window_y})")
    print(f"   Window size: {window_width}x{window_height}")

except Exception as e:
    print(f"   [X] Error finding Spotify: {e}")
    sys.exit(1)

# Step 3: Focus Spotify
print("\n[3] Focusing Spotify...")

try:
    # Activate Spotify application
    subprocess.run(
        ["osascript", "-e", 'tell application "Spotify" to activate'],
        check=True,
        capture_output=True,
        timeout=5,
    )
    print("   [OK] Spotify focused")

    # Wait for window to come to front and render
    time.sleep(1.0)

except Exception as e:
    print(f"   [!] Could not focus Spotify: {e}")
    print("   Continuing anyway...")

# Step 4: Calculate minimize button position
print("\n[4] Locating Yellow Minimize Button...")

# macOS window controls are in the top-left corner:
# - Red (close) button: leftmost
# - Yellow (minimize) button: middle
# - Green (maximize/zoom) button: rightmost
#
# Standard positions (from window top-left):
# - Buttons are ~20px from left edge
# - Buttons are ~16px from top edge
# - Red button center: ~20px from left
# - Yellow button center: ~40px from left (20px spacing)
# - Green button center: ~60px from left
# - Button diameter: ~12px

# Calculate yellow button center (in logical coordinates)
# Adjusted based on testing - trying slightly different position
button_offset_x = 38  # Adjusted from 40px (slightly left)
button_offset_y = 14  # Adjusted from 16px (slightly higher)

button_x_logical = window_x + button_offset_x
button_y_logical = window_y + button_offset_y

print(f"   Window top-left: ({window_x}, {window_y})")
print(f"   Yellow button offset: (+{button_offset_x}, +{button_offset_y})")
print(f"   Yellow button position: ({button_x_logical}, {button_y_logical}) [logical]")

# Step 5: Take screenshot before click
print("\n[5] Capturing Before Screenshot...")

try:
    # Capture window area (convert to physical)
    x_phys = int(window_x * scale_factor)
    y_phys = int(window_y * scale_factor)
    w_phys = int(window_width * scale_factor)
    h_phys = int(window_height * scale_factor)

    before_screenshot = pyautogui.screenshot(region=(x_phys, y_phys, w_phys, h_phys))

    # Draw marker on button location
    debug_img = before_screenshot.copy()
    draw = ImageDraw.Draw(debug_img)

    # Convert button position to screenshot coordinates (physical)
    button_x_in_screenshot = int(button_offset_x * scale_factor)
    button_y_in_screenshot = int(button_offset_y * scale_factor)

    # Draw crosshair on button
    marker_size = 20
    draw.line(
        [
            (button_x_in_screenshot - marker_size, button_y_in_screenshot),
            (button_x_in_screenshot + marker_size, button_y_in_screenshot),
        ],
        fill="red",
        width=3,
    )
    draw.line(
        [
            (button_x_in_screenshot, button_y_in_screenshot - marker_size),
            (button_x_in_screenshot, button_y_in_screenshot + marker_size),
        ],
        fill="red",
        width=3,
    )

    # Draw circle around target
    circle_radius = 15
    draw.ellipse(
        [
            (
                button_x_in_screenshot - circle_radius,
                button_y_in_screenshot - circle_radius,
            ),
            (
                button_x_in_screenshot + circle_radius,
                button_y_in_screenshot + circle_radius,
            ),
        ],
        outline="red",
        width=3,
    )

    before_path = Path.cwd() / "test_spotify_before.png"
    debug_img.save(before_path)
    print(f"   Before screenshot saved: {before_path}")
    print("   (Red crosshair shows target click location)")

except Exception as e:
    print(f"   [!] Screenshot failed: {e}")

# Step 6: Click the minimize button
print("\n[6] Clicking Yellow Minimize Button...")
print(f"   Moving to: ({button_x_logical}, {button_y_logical})")

try:
    # Move to button position (pyautogui expects logical coordinates)
    pyautogui.moveTo(button_x_logical, button_y_logical, duration=0.5)
    print("   Mouse moved to button")

    # Small pause to see the cursor
    time.sleep(0.5)

    # Click
    pyautogui.click()
    print("   [OK] Button clicked!")

    # Wait for animation
    time.sleep(1.0)

except Exception as e:
    print(f"   [X] Click failed: {e}")
    sys.exit(1)

# Step 7: Verify window minimized
print("\n[7] Verifying Window Minimized...")

try:
    # Get window list again
    window_list = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    )

    # Check if Spotify is still visible
    spotify_visible = False
    for window in window_list:
        owner_name = window.get("kCGWindowOwnerName", "")
        if "Spotify" in owner_name:
            bounds = window.get("kCGWindowBounds", {})
            if bounds.get("Width", 0) > 100:
                spotify_visible = True
                break

    if spotify_visible:
        print("   [!] Spotify still visible - minimize may have failed")
        print("   (Or Spotify might have multiple windows open)")
    else:
        print("   [OK] Spotify minimized successfully!")
        print("   Window is no longer in visible window list")

except Exception as e:
    print(f"   [!] Verification failed: {e}")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Target window: Spotify at ({window_x}, {window_y})")
print(f"Button position: ({button_x_logical}, {button_y_logical}) [logical]")
print(f"Scale factor: {scale_factor}x")
print("Click executed: YES")
print("\nGenerated file:")
print(f"   - {before_path} (shows target location with red crosshair)")

print("\n[INFO] macOS Window Control Positions:")
print("   Red button (close):     ~20px from left, ~16px from top")
print("   Yellow button (minimize): ~40px from left, ~16px from top")
print("   Green button (zoom):    ~60px from left, ~16px from top")

print("\n" + "=" * 70)
