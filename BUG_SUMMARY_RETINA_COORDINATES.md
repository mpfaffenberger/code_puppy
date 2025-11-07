# macOS Retina Display Coordinate Bug - Fixed

## The Problem

We discovered a critical bug in our desktop automation VQA/OCR systems on macOS Retina displays where window coordinates were being reported at **half** their actual values, causing screenshots to capture the wrong regions of the screen.

### Symptoms
- Screenshots captured only **2-4x smaller regions** than intended
- Window screenshots captured **completely wrong screen areas** (e.g., terminal text instead of Calculator app)
- Coordinate offset of approximately **30-50%** in both X and Y directions on 2x Retina displays
- OCR finding text from unrelated windows instead of the target application

### Root Cause

The bug stemmed from a **fundamental misunderstanding of macOS coordinate systems**:

**What we thought:** `CGWindowListCopyWindowInfo` returns coordinates in **physical pixels**  
**Reality:** `CGWindowListCopyWindowInfo` returns coordinates in **points (logical coordinates)**

On Retina displays with 2x scaling:
- **Points/Logical coordinates**: What users see (e.g., 1728x1117 screen)
- **Physical pixels**: Actual display resolution (e.g., 3456x2234 for 2x Retina)
- **Conversion**: `physical_pixels = points × backingScaleFactor`

### The Incorrect Code

```python
# window_control.py - WRONG!
bounds = window.get("kCGWindowBounds")  # Returns (1016, 644) in POINTS

# We incorrectly divided by scale factor
logical_x = int(bounds["X"] / scale_factor)  # (1016 / 2.0) = 508 ❌
logical_y = int(bounds["Y"] / scale_factor)  # (644 / 2.0) = 322 ❌

# Then when capturing screenshots:
phys_x = int(logical_x * scale_factor)  # 508 * 2.0 = 1016
screenshot = pyautogui.screenshot(region=(phys_x, ...))  # Wrong location!
```

This **double conversion** cut coordinates in half:
1. CGWindow returns `(1016, 644)` points
2. We divided by 2.0 → `(508, 322)` (incorrect!)
3. We multiplied by 2.0 → `(1016, 644)` (back where we started, but should be `(2032, 1288)`!)

### The Fix

```python
# window_control.py - CORRECT!
bounds = window.get("kCGWindowBounds")  # Returns (1016, 644) in POINTS

# CGWindow already returns points/logical coordinates - use them directly!
logical_x = int(bounds["X"])  # 1016 ✅
logical_y = int(bounds["Y"])  # 644 ✅

# When capturing screenshots, convert to physical pixels:
phys_x = int(logical_x * scale_factor)  # 1016 * 2.0 = 2032 ✅
phys_y = int(logical_y * scale_factor)  # 644 * 2.0 = 1288 ✅
screenshot = pyautogui.screenshot(region=(phys_x, phys_y, ...))  # Correct!
```

## Files Fixed

1. **`code_puppy/tools/gui_cub/window_control.py`**
   - `_get_window_bounds_by_app_name()` - Removed incorrect division by scale factor
   - `_get_active_window_bounds_impl()` - Removed incorrect division by scale factor
   - Updated comments to correctly document that CGWindow returns **points**, not physical pixels

2. **`code_puppy/tools/gui_cub/screen_capture.py`**
   - `capture_screen()` - Added conversion from logical→physical before passing to `pyautogui.screenshot()`
   - Now correctly multiplies region coordinates by `backingScaleFactor`

3. **`code_puppy/tools/gui_cub/ocr_tools.py`**
   - `desktop_extract_text()` - Added logical→physical conversion before screenshot
   - `desktop_highlight_text()` - Added logical→physical conversion before screenshot

## Testing

Before fix:
- Calculator window reported at `(508, 322)` logical = `(1016, 644)` physical
- Actual position: `60%/60%` of screen = `~(2074, 1340)` physical
- Screenshots captured terminal text instead of Calculator

After fix:
- Calculator window correctly reported at `(1016, 644)` logical
- Converted to `(2032, 1288)` physical for screenshot
- Position: `58.8%/57.7%` = `~60%/60%` ✅
- Screenshots correctly capture Calculator window
- OCR successfully reads "1234567890" from Calculator display

## References

- [Apple Documentation: kCGWindowBounds](https://developer.apple.com/documentation/coregraphics/kcgwindowbounds) - Confirms coordinates are in **screen space** (points)
- [Apple Documentation: backingScaleFactor](https://developer.apple.com/documentation/appkit/nswindow/backingscalefactor) - Explains points vs physical pixels
- [CGWindowListCreateImage Documentation](https://developer.apple.com/documentation/coregraphics/cgwindowlistcreateimage%28_%3A_%3A_%3A_%3A%29) - Alternative API that handles scaling automatically

## Lessons Learned

1. **Always verify coordinate system assumptions** - Don't assume APIs return physical pixels on HiDPI displays
2. **Read Apple documentation carefully** - The distinction between points and pixels is well-documented
3. **Test on actual hardware** - This bug would have been caught immediately with visual verification on a Retina display
4. **Use correct terminology in comments** - Our incorrect comments propagated the misunderstanding

---

**Fixed:** January 2025  
**Affects:** macOS Retina/HiDPI displays only (Windows code was unaffected)  
**Impact:** All desktop VQA, OCR, and screenshot functionality now works correctly on Retina displays
