#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test Windows coordinate system for desktop automation.

This script tests window bounds detection, screenshot capture, and OCR
on Windows to verify there are no DPI scaling coordinate bugs (like we
found on macOS).

Requirements:
- Run on Windows
- Have a native Windows dialog open (e.g., login dialog, notepad, calculator)
- The dialog should have visible text we can OCR

Usage:
    python test_windows_coordinates.py
"""

import sys
import io
import platform

# Windows console encoding fix:
# Windows terminals default to CP1252/CP437 encoding which cannot handle Unicode.
# This causes UnicodeEncodeError when printing Unicode characters (✓ ✅ ❌ ⚠ etc).
# We wrap stdout/stderr to force UTF-8 encoding with error replacement instead of crashing.
if platform.system() == "Windows":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

if platform.system() != "Windows":
    print("[X] This script must be run on Windows!")
    sys.exit(1)

# CRITICAL: Set DPI awareness BEFORE importing any GUI libraries!
# This ensures GetWindowRect and pyautogui use the same coordinate system.
import ctypes

print("Setting DPI awareness...")
user32 = ctypes.windll.user32
shcore = ctypes.windll.shcore

# Try Per-Monitor-V2 (Windows 10 1703+)
try:
    # -4 == DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    print("[OK] Set DPI awareness: Per-Monitor-V2")
    dpi_mode = "Per-Monitor-V2"
except Exception:
    try:
        # 2 == PROCESS_PER_MONITOR_DPI_AWARE
        shcore.SetProcessDpiAwareness(2)
        print("[OK] Set DPI awareness: Per-Monitor")
        dpi_mode = "Per-Monitor"
    except Exception:
        try:
            # Legacy fallback: system DPI aware
            user32.SetProcessDPIAware()
            print("[OK] Set DPI awareness: System DPI Aware")
            dpi_mode = "System-Aware"
        except Exception as e:
            print(f"[!] Could not set DPI awareness: {e}")
            dpi_mode = "Unknown"

try:
    import win32gui
    import win32con
    import win32api
except ImportError:
    print("[X] PyWin32 not installed!")
    print("Install with: pip install pywin32")
    sys.exit(1)

try:
    import pyautogui
except ImportError:
    print("[X] pyautogui not installed!")
    print("Install with: pip install pyautogui")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("[X] Pillow not installed!")
    print("Install with: pip install Pillow")
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("[X] pytesseract not installed!")
    print("Install with: pip install pytesseract")
    print("Also install Tesseract-OCR from: https://github.com/UB-Mannheim/tesseract/wiki")
    sys.exit(1)


print("="*70)
print("Windows Desktop Automation Coordinate System Test")
print("="*70)

# Step 1: Confirm DPI awareness and get scaling
print("\n[1] DPI Configuration...")
print(f"   Mode: {dpi_mode}")

# Get system DPI
try:
    
    # Get DPI for primary monitor
    hdc = user32.GetDC(0)
    dpi_x = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
    dpi_y = ctypes.windll.gdi32.GetDeviceCaps(hdc, 90)  # LOGPIXELSY
    user32.ReleaseDC(0, hdc)
    
    scaling_x = dpi_x / 96.0
    scaling_y = dpi_y / 96.0
    
    print(f"   System DPI: {dpi_x}x{dpi_y} (Scaling: {scaling_x*100:.0f}% x {scaling_y*100:.0f}%)")
except Exception as e:
    print(f"   Error getting DPI: {e}")
    scaling_x = 1.0
    scaling_y = 1.0

# Step 2: Get active window
print("\n[2] Getting Active Window...")
print("   Capturing currently focused window...")

hwnd = win32gui.GetForegroundWindow()
if not hwnd:
    print("   [X] No foreground window found!")
    sys.exit(1)

window_text = win32gui.GetWindowText(hwnd)
print(f"   Active window: '{window_text}' (HWND: {hwnd})")

# Step 3: Get window bounds using Win32 API
print("\n[3] Getting Window Bounds (Win32 API)...")

try:
    rect = win32gui.GetWindowRect(hwnd)
    x, y, right, bottom = rect
    width = right - x
    height = bottom - y
    
    print("   GetWindowRect returned:")
    print(f"      Position: ({x}, {y})")
    print(f"      Size: {width}x{height}")
    print(f"      (left={x}, top={y}, right={right}, bottom={bottom})")
    
    # Get client rect for comparison
    client_rect = win32gui.GetClientRect(hwnd)
    client_width = client_rect[2]
    client_height = client_rect[3]
    print(f"   GetClientRect size: {client_width}x{client_height} (excludes decorations)")
    
    # Try to get DPI for this specific window (Windows 10+)
    try:
        window_dpi = user32.GetDpiForWindow(hwnd)
        window_scaling = window_dpi / 96.0
        print(f"   Window-specific DPI: {window_dpi} (Scaling: {window_scaling*100:.0f}%)")
    except:
        window_dpi = dpi_x
        window_scaling = scaling_x
        print("   Using system DPI (GetDpiForWindow not available)")

except Exception as e:
    print(f"   [X] Error: {e}")
    sys.exit(1)

# Step 4: Get screen dimensions
print("\n[4] Screen Dimensions...")
screen_width = win32api.GetSystemMetrics(0)  # SM_CXSCREEN
screen_height = win32api.GetSystemMetrics(1)  # SM_CYSCREEN
print(f"   GetSystemMetrics: {screen_width}x{screen_height}")

pyautogui_size = pyautogui.size()
print(f"   pyautogui.size(): {pyautogui_size.width}x{pyautogui_size.height}")

if screen_width != pyautogui_size.width or screen_height != pyautogui_size.height:
    print("   [!] MISMATCH! Win32 and pyautogui report different screen sizes!")
    print("   This suggests coordinate system differences!")

# Step 5: Capture full screen for reference
print("\n[5] Capturing Full Screen...")
full_screen = pyautogui.screenshot()
full_screen.save("windows_fullscreen.png")
print(f"   Saved: windows_fullscreen.png ({full_screen.width}x{full_screen.height})")

if full_screen.width != pyautogui_size.width or full_screen.height != pyautogui_size.height:
    print("   [!] Screenshot size doesn't match pyautogui.size()!")
    print(f"   Screenshot: {full_screen.width}x{full_screen.height}")
    print(f"   pyautogui.size(): {pyautogui_size.width}x{pyautogui_size.height}")

# Step 6: Draw debug grid on full screen
print("\n[6] Creating Debug Grid...")
debug_img = full_screen.copy()
draw = ImageDraw.Draw(debug_img)

# Draw 10% grid lines
for i in range(0, 11):
    grid_x = int(debug_img.width * i / 10)
    grid_y = int(debug_img.height * i / 10)
    
    # Vertical lines
    draw.line([(grid_x, 0), (grid_x, debug_img.height)], fill="cyan", width=2)
    # Horizontal lines
    draw.line([(0, grid_y), (debug_img.width, grid_y)], fill="cyan", width=2)
    
    # Labels
    label = f"{i*10}%"
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = None
    
    draw.text((grid_x + 5, 5), label, fill="yellow", font=font)
    draw.text((5, grid_y + 5), label, fill="yellow", font=font)

# Draw RED box at Win32 reported coordinates
print("\n[7] Drawing Window Bounds on Grid...")
print(f"   Drawing RED box at Win32 coords: ({x}, {y}) {width}x{height}")

draw.rectangle(
    [(x, y), (x + width, y + height)],
    outline="red",
    width=4
)
draw.text((x + 5, y + 5), "Win32 Coords", fill="red", font=font)

# Calculate window position as percentage
win_pct_x = (x / debug_img.width) * 100
win_pct_y = (y / debug_img.height) * 100
print(f"   Window position: {win_pct_x:.1f}% horizontal, {win_pct_y:.1f}% vertical")

debug_img.save("windows_debug_grid.png")
print("   Saved: windows_debug_grid.png")
print("   -> Check this image - is the RED box around your window?")

# Step 8: Capture just the window
print("\n[8] Capturing Window Region...")
print(f"   Using coordinates: ({x}, {y}, {width}, {height})")

try:
    # Try direct coordinates first
    window_screenshot = pyautogui.screenshot(region=(x, y, width, height))
    window_screenshot.save("windows_window_direct.png")
    print(f"   Saved: windows_window_direct.png ({window_screenshot.width}x{window_screenshot.height})")
except Exception as e:
    print(f"   [X] Direct capture failed: {e}")
    window_screenshot = None

# Try with DPI scaling if available
if window_scaling != 1.0:
    print(f"\n   Trying with DPI scaling ({window_scaling}x)...")
    
    # Test 1: Divide by scaling (logical -> physical)
    try:
        logical_x = int(x / window_scaling)
        logical_y = int(y / window_scaling)
        logical_w = int(width / window_scaling)
        logical_h = int(height / window_scaling)
        
        print(f"   Scaled coords (/{window_scaling}): ({logical_x}, {logical_y}, {logical_w}, {logical_h})")
        window_scaled_down = pyautogui.screenshot(region=(logical_x, logical_y, logical_w, logical_h))
        window_scaled_down.save("windows_window_scaled_down.png")
        print(f"   Saved: windows_window_scaled_down.png ({window_scaled_down.width}x{window_scaled_down.height})")
    except Exception as e:
        print(f"   Scaled down capture failed: {e}")
    
    # Test 2: Multiply by scaling (physical -> logical)
    try:
        physical_x = int(x * window_scaling)
        physical_y = int(y * window_scaling)
        physical_w = int(width * window_scaling)
        physical_h = int(height * window_scaling)
        
        print(f"   Scaled coords (x{window_scaling}): ({physical_x}, {physical_y}, {physical_w}, {physical_h})")
        window_scaled_up = pyautogui.screenshot(region=(physical_x, physical_y, physical_w, physical_h))
        window_scaled_up.save("windows_window_scaled_up.png")
        print(f"   Saved: windows_window_scaled_up.png ({window_scaled_up.width}x{window_scaled_up.height})")
    except Exception as e:
        print(f"   Scaled up capture failed: {e}")

# Step 9: OCR Test
print("\n[9] Testing OCR...")

if window_screenshot:
    print("   Running OCR on window screenshot...")
    try:
        # Upscale for better OCR
        upscaled = window_screenshot.resize(
            (window_screenshot.width * 2, window_screenshot.height * 2),
            Image.Resampling.LANCZOS
        )
        
        text = pytesseract.image_to_string(upscaled)
        print("\n   OCR Result:")
        print("   " + "-"*60)
        for line in text.strip().split('\n'):
            if line.strip():
                print(f"   {line}")
        print("   " + "-"*60)
        
        if text.strip():
            print("\n   [OK] OCR found text!")
        else:
            print("\n   [!] OCR found no text (window might be blank or OCR failed)")
    except Exception as e:
        print(f"   [X] OCR failed: {e}")
else:
    print("   [!] Skipping OCR (no window screenshot captured)")

# Step 10: Click the "CE" button
print("\n[10] Testing Click Coordination...")
print("   Attempting to find and click the 'CE' button on Calculator...")

if window_screenshot:
    try:
        # Upscale more aggressively for better button OCR
        print("   Upscaling screenshot for better button detection...")
        upscaled_for_buttons = window_screenshot.resize(
            (window_screenshot.width * 4, window_screenshot.height * 4),
            Image.Resampling.LANCZOS
        )
        
        # Get detailed OCR data with bounding boxes
        print("   Running OCR to find button positions...")
        ocr_data = pytesseract.image_to_data(upscaled_for_buttons, output_type=pytesseract.Output.DICT)
        
        # Find the "CE" button
        button_found = False
        for i, text in enumerate(ocr_data['text']):
            if text.strip() == 'CE':
                # Get bounding box relative to upscaled screenshot (4x)
                box_x = ocr_data['left'][i]
                box_y = ocr_data['top'][i]
                box_w = ocr_data['width'][i]
                box_h = ocr_data['height'][i]
                
                # Scale back down to original window coordinates
                box_x = box_x // 4
                box_y = box_y // 4
                box_w = box_w // 4
                box_h = box_h // 4
                
                # Calculate center of the "8" button (relative to window)
                button_center_x = box_x + box_w // 2
                button_center_y = box_y + box_h // 2
                
                # Convert to screen coordinates
                screen_click_x = x + button_center_x
                screen_click_y = y + button_center_y
                
                print("   Found 'CE' button in window screenshot:")
                print(f"      Window-relative position: ({box_x}, {box_y}) size {box_w}x{box_h}")
                print(f"      Button center (window): ({button_center_x}, {button_center_y})")
                print(f"      Button center (screen): ({screen_click_x}, {screen_click_y})")
                
                # Draw the OCR-found button position on debug grid
                print("   Drawing BLUE box on debug grid at OCR-found 'CE' button position...")
                
                # Reload debug grid image to add the button marker
                debug_with_button = Image.open("windows_debug_grid.png")
                draw_button = ImageDraw.Draw(debug_with_button)
                
                # Draw box at the OCR-found position (screen coordinates)
                draw_button.rectangle(
                    [(screen_click_x - box_w//2, screen_click_y - box_h//2),
                     (screen_click_x + box_w//2, screen_click_y + box_h//2)],
                    outline="blue",
                    width=3
                )
                
                # Draw crosshair at click point
                crosshair_size = 15
                draw_button.line(
                    [(screen_click_x - crosshair_size, screen_click_y), 
                     (screen_click_x + crosshair_size, screen_click_y)],
                    fill="blue",
                    width=2
                )
                draw_button.line(
                    [(screen_click_x, screen_click_y - crosshair_size), 
                     (screen_click_x, screen_click_y + crosshair_size)],
                    fill="blue",
                    width=2
                )
                
                # Add label
                try:
                    font = ImageFont.truetype("arial.ttf", 20)
                except:
                    font = None
                draw_button.text(
                    (screen_click_x + 5, screen_click_y - 25),
                    "OCR 'CE' click",
                    fill="blue",
                    font=font
                )
                
                debug_with_button.save("windows_debug_with_click.png")
                print("   Saved: windows_debug_with_click.png (BLUE = OCR-found 'CE' position)")
                
                # Bring Calculator to foreground
                import win32gui
                win32gui.SetForegroundWindow(hwnd)
                
                # Small delay to ensure window is focused
                import time
                time.sleep(0.2)
                
                # Click the button!
                print(f"\n   Clicking at screen coordinates ({screen_click_x}, {screen_click_y})...")
                pyautogui.click(screen_click_x, screen_click_y)
                
                print("   [OK] Click executed! Check if Calculator display was cleared (CE button).")
                button_found = True
                break
        
        if not button_found:
            print("   [!] Could not find 'CE' button via OCR")
            print(f"   Available text elements: {[t for t in ocr_data['text'] if t.strip()]}")
            
            # Fallback: Estimate button position based on typical calculator layout
            print("\n   Trying fallback: Estimating 'CE' button position based on layout...")
            
            # Windows Calculator Standard mode has buttons in lower ~60% of window
            # Button grid is roughly centered horizontally
            # "8" is in row 2 (from bottom), column 2 (center)
            
            # CE button is in the top row of the number pad area
            # Typically at around 40% down from top, second column
            button_grid_top = int(window_screenshot.height * 0.35)
            
            # CE is in the top row of calculator buttons
            # Row is at about 35-40% down the window
            ce_y = button_grid_top
            
            # CE is typically in column 2 (of 4 columns: %, CE, C, backspace)
            col_width = window_screenshot.width // 4
            ce_x = col_width * 1.5  # Column 2
            
            # Calculate estimated button center
            est_button_x = int(ce_x)
            est_button_y = int(ce_y)
            
            # Convert to screen coordinates
            est_screen_x = x + est_button_x
            est_screen_y = y + est_button_y
            
            print(f"   Estimated 'CE' button position (window): ({est_button_x}, {est_button_y})")
            print(f"   Estimated 'CE' button position (screen): ({est_screen_x}, {est_screen_y})")
            
            # Draw the estimated button position on debug grid for visualization
            print("   Drawing GREEN crosshair on debug grid at estimated 'CE' button position...")
            
            # Reload debug grid image to add the button marker
            debug_with_button = Image.open("windows_debug_grid.png")
            draw_button = ImageDraw.Draw(debug_with_button)
            
            # Draw a crosshair at the estimated click position
            crosshair_size = 20
            # Horizontal line
            draw_button.line(
                [(est_screen_x - crosshair_size, est_screen_y), 
                 (est_screen_x + crosshair_size, est_screen_y)],
                fill="lime",
                width=3
            )
            # Vertical line
            draw_button.line(
                [(est_screen_x, est_screen_y - crosshair_size), 
                 (est_screen_x, est_screen_y + crosshair_size)],
                fill="lime",
                width=3
            )
            
            # Draw a small box around the estimated button area
            button_box_size = 30
            draw_button.rectangle(
                [(est_screen_x - button_box_size, est_screen_y - button_box_size),
                 (est_screen_x + button_box_size, est_screen_y + button_box_size)],
                outline="lime",
                width=3
            )
            
            # Add label
            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except:
                font = None
            draw_button.text(
                (est_screen_x + 5, est_screen_y - 25),
                "Est. 'CE' click",
                fill="lime",
                font=font
            )
            
            debug_with_button.save("windows_debug_with_click.png")
            print("   Saved: windows_debug_with_click.png (GREEN = estimated click position)")
            
            # Bring Calculator to foreground
            import win32gui
            win32gui.SetForegroundWindow(hwnd)
            
            # Small delay
            import time
            time.sleep(0.2)
            
            # Click!
            print(f"\n   Clicking at screen coordinates ({est_screen_x}, {est_screen_y})...")
            pyautogui.click(est_screen_x, est_screen_y)
            
            print("   [OK] Click executed! Check if Calculator display was cleared (CE button).")
            button_found = True
            
    except Exception as e:
        print(f"   [X] Click test failed: {e}")
        import traceback
        traceback.print_exc()
else:
    print("   [!] No window screenshot available for click test")

# Step 11: Summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70)
print(f"Window: '{window_text}'")
print(f"Win32 bounds: ({x}, {y}) {width}x{height}")
print(f"System DPI scaling: {scaling_x*100:.0f}%")
print(f"Screen size (Win32): {screen_width}x{screen_height}")
print(f"Screen size (pyautogui): {pyautogui_size.width}x{pyautogui_size.height}")
print(f"Screenshot size: {full_screen.width}x{full_screen.height}")

print("\nGenerated Files:")
print("   - windows_fullscreen.png (full screen capture)")
print("   - windows_debug_grid.png (grid with RED box showing Win32 coords)")
print("   - windows_debug_with_click.png (RED=window, GREEN/BLUE=click target)")
print("   - windows_window_direct.png (window capture using Win32 coords directly)")
if window_scaling != 1.0:
    print("   - windows_window_scaled_down.png (window capture / DPI scaling)")
    print("   - windows_window_scaled_up.png (window capture x DPI scaling)")

print("\nVALIDATION:")
if dpi_mode == "Per-Monitor-V2":
    print("   [OK] DPI awareness is Per-Monitor-V2")
    print("   [OK] GetWindowRect should return PHYSICAL pixels")
    print("   [OK] pyautogui.screenshot() should use PHYSICAL pixels")
    print("   [OK] NO coordinate conversion needed!")
    print("")
    print("   Expected result:")
    print("   - RED box should be EXACTLY on your window")
    print("   - windows_window_direct.png should show ONLY your window")
elif dpi_mode == "System-Aware":
    print("   [!] DPI awareness is System-Aware")
    print("   [!] This may cause issues on multi-monitor setups")
    print("   [!] GetWindowRect returns DPI-virtualized coordinates")
    print("   [!] pyautogui may use different coordinate system")
    print("")
    print("   If screenshots are wrong, you may need coordinate conversion!")
else:
    print("   [!] DPI awareness is unknown or not set properly")
    print("   [!] Coordinate mismatches are likely!")

print("\nNEXT STEPS:")
print("   1. Open windows_debug_grid.png")
print("   2. Check if the RED box is around your window")
print("   3. Open windows_window_direct.png")
print("   4. Check if it shows your window correctly")
print("")
print("   [OK] If both are correct -> Windows coordinate handling is WORKING!")
print("   [X] If RED box is wrong -> GetWindowRect coordinate issue")
print("   [X] If screenshot is wrong -> pyautogui coordinate issue")
print("")
print("="*70)