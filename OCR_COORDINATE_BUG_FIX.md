# OCR Coordinate Bug Fix - November 11, 2025

## Problem

OCR coordinates were offset and not grabbing the right window on macOS Retina displays. When OCR detected text and returned coordinates, clicking on those coordinates would miss the actual target.

## Root Cause

**Bug introduced in commit `e20a80f` ("screenshot safety")**

The commit switched from `pyautogui.screenshot()` to `ImageGrab.grab()` on macOS for thread safety (pyautogui uses tkinter which crashes on background threads). However, there was a critical coordinate system mismatch:

- **pyautogui.screenshot(region=(x, y, w, h))**: Expects PHYSICAL pixels on Retina displays
- **ImageGrab.grab(bbox=(left, top, right, bottom))**: Expects LOGICAL coordinates (points) on macOS

The code was passing physical pixel coordinates to `ImageGrab.grab()`, causing it to capture from the wrong screen location.

### Example of the Bug

On a 2x Retina display:
1. Window at logical position (100, 100)
2. Code converts to physical: (200, 200) 
3. Passes (200, 200) to ImageGrab.grab()
4. ImageGrab interprets this as logical (200, 200), which is actually physical (400, 400)
5. Result: Screenshot captured from **wrong location** → OCR coordinates completely offset!

## The Fix

**File:** `code_puppy/tools/gui_cub/screen_capture/capture.py`

**Function:** `_safe_screenshot()`

Added logic to convert physical pixels to logical coordinates before passing to `ImageGrab.grab()` on macOS:

```python
if region:
    x, y, w, h = region
    # CRITICAL BUG FIX: ImageGrab.grab() on macOS expects LOGICAL coordinates (points),
    # not physical pixels! The region parameter passed to this function is in physical pixels,
    # so we must divide by the scale factor to convert to logical coordinates.
    from ..platform import get_screen_scale_factor
    scale_factor = get_screen_scale_factor()
    
    # Convert physical pixels to logical points for ImageGrab
    logical_x = int(x / scale_factor)
    logical_y = int(y / scale_factor)
    logical_w = int(w / scale_factor)
    logical_h = int(h / scale_factor)
    
    # ImageGrab.grab expects (left, top, right, bottom) in LOGICAL coordinates
    return ImageGrab.grab(bbox=(logical_x, logical_y, logical_x + logical_w, logical_y + logical_h))
```

## Coordinate Flow After Fix

1. **Window bounds detection** (`window_control/core.py`)
   - Returns LOGICAL coordinates (e.g., x=100, y=100 on 2x Retina)

2. **OCR tools** (`ocr/tools.py`)
   - Converts to PHYSICAL: (200, 200) for screenshot capture
   - Passes PHYSICAL coords to `_safe_screenshot()`

3. **Screenshot capture** (`screen_capture/capture.py`) **[FIXED]**
   - Converts PHYSICAL back to LOGICAL: (100, 100)
   - Passes LOGICAL coords to ImageGrab.grab()
   - ImageGrab captures from correct location! ✅

4. **OCR extraction** (`ocr/extraction.py`)
   - OCR returns coordinates in screenshot space (physical pixels)
   - Converts to logical screen coordinates
   - Adds region offset (also converted to logical)
   - Returns correct screen coordinates! ✅

## Impact

- **Before fix**: OCR coordinates were wrong, clicks missed targets
- **After fix**: OCR coordinates are accurate, clicks hit targets
- **Affected platforms**: macOS with Retina displays (scale_factor > 1.0)
- **Windows/Linux**: Unaffected (still uses pyautogui)

## Testing Recommendations

1. Test OCR on macOS Retina display (2x or higher)
2. Verify `desktop_extract_text()` returns accurate coordinates
3. Verify `desktop_find_text_on_screen()` finds text at correct position
4. Verify `desktop_click_text()` clicks on the correct location
5. Test with different window positions and sizes

## Related Commits

- `e20a80f` - "screenshot safety" (introduced the bug)
- `1f94adf` - "threaded vqa issue" 
- `7e1bd7d` - "OCR bug" (attempted partial fix)
