# GUI-CUB Integration Test Prompt
**Comprehensive Feature Testing After Refactoring**

This document provides manual integration tests to validate that all GUI-CUB features work correctly on both Windows and macOS after the file size reduction refactoring.

---

## Instructions for GUI-CUB Agent

Read through each test below and execute them on your current platform. Report PASS/FAIL for each test with brief explanation.

**Testing approach:**
- Use actual desktop applications on your system
- Make intelligent decisions about how to accomplish each task
- Report any import errors or missing functionality
- Skip tests that don't apply to your platform

---

## TEST 1: Platform Detection
**Module:** `platform.py`

### Task:
1. Tell me what operating system you're running on (Windows or macOS)
2. Tell me your screen's scale factor (Retina displays = 2.0, standard = 1.0, etc.)
3. List all connected displays and their resolutions

### Expected:
- Should correctly identify the OS
- Should return a valid scale factor (1.0, 1.5, 2.0, etc.)
- Should enumerate all monitors

---

## TEST 2: Screen Capture - Full Screen
**Module:** `screen_capture/`

### Task:
1. Take a full screenshot of your desktop
2. Save it to a temporary location
3. Report the file path and image dimensions
4. Confirm the file was created successfully

### Expected:
- Screenshot file should exist
- Dimensions should match screen resolution
- No import errors from screen_capture module

---

## TEST 3: Screen Capture - With Grid Overlay
**Module:** `screen_capture/`

### Task:
1. Take a screenshot with a coordinate grid overlay (100px spacing)
2. Confirm the grid lines are visible when you view the image
3. Report the file path

### Expected:
- Screenshot should have visible grid lines
- Grid should help with coordinate debugging

---

## TEST 4: Screen Capture - Specific Region
**Module:** `screen_capture/`

### Task:
1. Capture only the top-left quarter of your screen (approximately 500x400 pixels)
2. Confirm the resulting image is smaller than the full screen
3. Report the dimensions

### Expected:
- Smaller image than full screen
- Region capture works correctly

---

## TEST 5: OCR - Read Text from Screen
**Module:** `ocr/`

### Task:
1. Open any application with visible text (Notepad, TextEdit, browser, etc.)
2. Type or display the text: "Hello GUI-CUB Testing 12345"
3. Take a screenshot of that window
4. Use OCR to extract the text from the screenshot
5. Report what text was detected

### Expected:
- OCR should detect most of the text
- Should return "Hello", "GUI-CUB", "Testing", "12345" or similar
- Should provide bounding boxes for text elements

---

## TEST 6: Window Control - Get Active Window
**Module:** `window_control/`

### Task:
1. Focus any application window (browser, text editor, etc.)
2. Get the bounds (x, y, width, height) of the active window
3. Report the window title and dimensions

### Expected:
- Should return valid window bounds
- X, Y, width, height should all be positive numbers
- Window title should match the active application

---

## TEST 7: Window Control - Focus Window by Name
**Module:** `window_control/`

### Task (macOS):
1. Open Finder and Calculator (or any two apps)
2. Focus Calculator first
3. Use window control to focus Finder by app name
4. Confirm Finder came to the front

### Task (Windows):
1. Open File Explorer and Notepad
2. Focus Notepad first
3. Use window control to focus File Explorer by window title
4. Confirm Explorer came to the front

### Expected:
- Should successfully switch between windows
- Correct window should gain focus

---

## TEST 8: Fuzzy Matching - Find UI Element
**Module:** `fuzzy_matching.py`

### Task:
1. Create a list of fake UI elements:
   - {"title": "Submit Button", "id": "btn_submit"}
   - {"title": "Cancel", "id": "btn_cancel"}
   - {"title": "OK Button", "id": "btn_ok"}
2. Use fuzzy matching to search for "submit" with threshold 0.3
3. Report which element was the best match

### Expected:
- Should find "Submit Button" as the top match
- Fuzzy matching should work with partial text
- Should return match confidence score

---

## TEST 9: Accessibility - List UI Elements (macOS Only)
**Module:** `accessibility/`
**Platform:** macOS only (skip on Windows)

### Task:
1. Open Calculator app
2. Use accessibility API to list all buttons in the Calculator window
3. Report how many buttons were found
4. Show the labels of at least 5 buttons (e.g., "1", "2", "+", "=", etc.)

### Expected:
- Should find 20+ buttons in Calculator
- Button labels should be correct
- Should detect roles (AXButton)

---

## TEST 10: Accessibility - Find and Click (macOS Only)
**Module:** `accessibility/`
**Platform:** macOS only (skip on Windows)

### Task:
1. Open Calculator app and clear it
2. Use accessibility to find the "7" button
3. Click it using accessibility API
4. Find and click the "+" button
5. Find and click the "3" button  
6. Find and click the "=" button
7. Verify the result shows "10"

### Expected:
- Should successfully find each button by label
- Should click buttons programmatically
- Calculator should show correct result (7 + 3 = 10)

---

## TEST 11: Windows Automation - List Windows (Windows Only)
**Module:** `windows_automation/`
**Platform:** Windows only (skip on macOS)

### Task:
1. Open at least 3 different applications (Notepad, File Explorer, Calculator)
2. Use Windows automation to list all open windows
3. Report the window titles you found

### Expected:
- Should find all 3+ windows
- Window titles should be correct
- Should return window handles

---

## TEST 12: Windows Automation - Find Element (Windows Only)
**Module:** `windows_automation/`
**Platform:** Windows only (skip on macOS)

### Task:
1. Open Calculator app
2. Use Windows UIA to find the "7" button by name
3. Report the button's properties (name, control type, position)

### Expected:
- Should find the button element
- Should return control type "Button"
- Should have valid screen coordinates

---

## TEST 13: Calibration - Platform Report
**Module:** `calibration/`

### Task:
1. Run the platform calibration tool
2. Report the following:
   - OS name and version
   - Number of displays
   - Screen resolutions
   - Available capabilities (pyautogui, PIL, etc.)
   - Screen recording permission status

### Expected:
- Should return complete platform information
- Should detect all required dependencies
- Should check permissions appropriately

---

## TEST 14: Workflow Executor - Simple Workflow
**Module:** `executor/`

### Task:
1. Create a simple workflow YAML file that:
   - Sleeps for 0.5 seconds
   - Takes a screenshot
2. Execute the workflow
3. Confirm both steps completed successfully

### Expected:
- Workflow should parse correctly
- All steps should execute in order
- Screenshot should be created

---

## TEST 15: Window Button Detector - Find Close Button
**Module:** `window_button_detector/`

### Task:
1. Open any application window
2. Use the button detector to locate the Close button (red X or red dot)
3. Report the button's screen coordinates

### Expected:
- Should detect close button location
- Coordinates should be in the window's title bar
- Should work on macOS (top-left) or Windows (top-right)

---

## TEST 16: Click Debugging - Coordinate Grid
**Module:** `click_debugging/`

### Task:
1. Take a screenshot
2. Draw a pixel grid on the screenshot with:
   - Target click point at (400, 300)
   - Grid spacing of 50 pixels
   - Highlight radius of 30 pixels
3. Save and view the annotated image
4. Confirm the target point is highlighted

### Expected:
- Grid should be visible
- Target point should be clearly marked
- Helps debug coordinate issues

---

## TEST 17: VQA Vision Click - Image Processing
**Module:** `vqa_vision_click/`

### Task:
1. Take a screenshot of any window
2. Crop it to a 200x200 pixel region in the center
3. Downscale the cropped image if it's too large (max 1024px)
4. Convert the final image to base64 encoding
5. Report the base64 string length

### Expected:
- Image should be cropped correctly
- Downscaling should work if needed
- Base64 conversion should produce a valid string

---

## TEST 18: Integration - OCR + Click
**Modules:** `screen_capture/`, `ocr/`, `window_control/`

### Task:
1. Open Notepad/TextEdit
2. Type the text "CLICK HERE" in large font
3. Take a screenshot of the window
4. Use OCR to find the text "CLICK HERE"
5. Report the coordinates of that text
6. Optionally: move mouse to those coordinates (don't click)

### Expected:
- Should find the text with OCR
- Should return valid coordinates
- Coordinates should be within the window bounds

---

## TEST 19: Integration - Fuzzy Match + Accessibility (macOS)
**Modules:** `accessibility/`, `fuzzy_matching.py`
**Platform:** macOS only

### Task:
1. Open Calculator
2. List all buttons using accessibility
3. Use fuzzy matching to find a button with label similar to "equal" (should match "=")
4. Report the button you found

### Expected:
- Accessibility should list buttons
- Fuzzy matching should find "=" button when searching for "equal"
- Should demonstrate module integration

---

## TEST 20: Import Validation - All Modules
**All modules**

### Task:
Verify all refactored modules can be imported without errors:

```python
# Run these imports and report any failures:
from code_puppy.tools.gui_cub.platform import get_current_platform
from code_puppy.tools.gui_cub.screen_capture import screenshot
from code_puppy.tools.gui_cub.ocr import extract_text_from_image
from code_puppy.tools.gui_cub.window_control import get_active_window_bounds
from code_puppy.tools.gui_cub.fuzzy_matching import fuzzy_match
from code_puppy.tools.gui_cub.accessibility import ACCESSIBILITY_AVAILABLE
from code_puppy.tools.gui_cub.windows_automation import WINDOWS_AUTOMATION_AVAILABLE
from code_puppy.tools.gui_cub.calibration import calibrate_platform
from code_puppy.tools.gui_cub.executor import WorkflowExecutor
from code_puppy.tools.gui_cub.window_button_detector import WindowButton
from code_puppy.tools.gui_cub.click_debugging import draw_pixel_grid
from code_puppy.tools.gui_cub.vqa_vision_click import crop_to_region
```

### Expected:
- ALL imports should succeed
- NO ModuleNotFoundError
- NO ImportError
- NO AttributeError

---

## Test Results Summary

### Report Format:

```
Platform: [macOS/Windows]

=== RESULTS ===
✅ TEST 1: Platform Detection - PASSED
✅ TEST 2: Screen Capture Full - PASSED  
✅ TEST 3: Screen Capture Grid - PASSED
... (continue for all tests)

=== SUMMARY ===
Total Tests: 20
Passed: X
Failed: Y
Skipped: Z (platform-specific)

Overall Status: [PASS/FAIL]

=== ISSUES FOUND ===
(List any import errors, missing functions, or broken features)
```

---

## Success Criteria

### Must Pass:
1. ✅ TEST 20 - All imports work (CRITICAL)
2. ✅ Platform detection works
3. ✅ Screen capture works (full, grid, region)
4. ✅ OCR extracts text from screenshots
5. ✅ Window control gets active window
6. ✅ Fuzzy matching finds text matches
7. ✅ Calibration returns platform info

### Platform-Specific (Can Skip):
- Tests 9-10: macOS Accessibility (skip on Windows)
- Tests 11-12: Windows Automation (skip on macOS)

### Optional (May Fail Gracefully):
- Window button detection (needs active window)
- Focus window by name (needs specific apps)
- VQA features (may need vision model)

---

## Critical Failure Indicators

**STOP and report immediately if you see:**
- ❌ `ModuleNotFoundError` for any gui_cub submodule
- ❌ `ImportError` for refactored modules
- ❌ `AttributeError: module has no attribute 'X'`
- ❌ Missing functions that existed before refactoring
- ❌ Syntax errors in any module

**These indicate the refactoring broke something critical.**

---

**END OF INTEGRATION TEST PROMPT**
