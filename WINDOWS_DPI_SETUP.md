# Windows DPI Awareness Setup

## Summary

We've configured code-puppy to be **Per-Monitor DPI Aware V2** on Windows, ensuring that window coordinates and screenshots use the same coordinate system.

## The Problem (Potential)

On Windows with DPI scaling (125%, 150%, 200%, etc.), there are **two** possible coordinate systems:

1. **Logical/Virtual coordinates** - DPI-virtualized, what non-DPI-aware apps see
2. **Physical pixels** - Actual screen pixels

If `GetWindowRect()` returns logical coordinates but `pyautogui.screenshot()` expects physical pixels (or vice versa), screenshots will capture the wrong region - similar to the bug we fixed on macOS Retina displays.

## The Solution

We set **Per-Monitor DPI Awareness V2** at module import time in `platform.py`:

```python
if IS_WINDOWS:
    import ctypes
    user32 = ctypes.windll.user32
    shcore = ctypes.windll.shcore
    
    # Set Per-Monitor-V2 (Windows 10 1703+)
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
```

### What This Does:

- ✅ `GetWindowRect()` returns **physical pixels**
- ✅ `pyautogui.screenshot()` uses **physical pixels**
- ✅ **No coordinate conversion needed** (unlike macOS)
- ✅ Works correctly across monitors with different DPI settings
- ✅ Handles DPI changes at runtime

### Fallback Modes:

1. **Per-Monitor-V2** (preferred) - Windows 10 1703+ 
2. **Per-Monitor** - Windows 8.1+
3. **System-Aware** - Legacy fallback (may have multi-monitor issues)

## Testing

Run `test_windows_coordinates.py` on a Windows machine:

```bash
python test_windows_coordinates.py
```

**Expected results if DPI awareness is working:**
- RED box on debug grid should be **exactly** around your window
- Window screenshot should capture **only** your window content
- OCR should read text from your window

**If results are wrong:**
- Check DPI awareness mode in test output
- Check for coordinate mismatches
- See if scaled coordinates (÷ or × DPI factor) work better

## Code Changes

### Files Modified:

1. **`code_puppy/tools/gui_cub/platform.py`**
   - Added Windows DPI awareness initialization at module import
   - Runs before any GUI operations
   - Added `get_windows_dpi_mode()` helper function

### Files Created:

1. **`test_windows_coordinates.py`**
   - Comprehensive Windows coordinate system test
   - Tests DPI awareness, window bounds, screenshots, OCR
   - Generates debug images to visually verify coordinates

2. **`research_prompt_windows.md`**
   - Research prompt for Windows DPI and coordinate systems

3. **`research_response_windows.md`**
   - Research results explaining Windows DPI behavior

## How It Works

### Before (Potential Issue):
```python
# Without DPI awareness
import win32gui
import pyautogui

# GetWindowRect might return logical coords (e.g., 800x600 at 150% = 533x400)
rect = win32gui.GetWindowRect(hwnd)

# pyautogui might expect physical coords (e.g., 1200x900)
screenshot = pyautogui.screenshot(region=rect)  # MISMATCH!
```

### After (Fixed):
```python
# With Per-Monitor-V2 awareness (set in platform.py)
import win32gui
import pyautogui

# GetWindowRect returns physical pixels (e.g., 1200x900)
rect = win32gui.GetWindowRect(hwnd)

# pyautogui uses physical pixels (e.g., 1200x900)
screenshot = pyautogui.screenshot(region=rect)  # MATCH! ✅
```

## Comparison to macOS

### macOS (Fixed):
- `CGWindowListCopyWindowInfo` returns **points (logical)**
- `pyautogui.screenshot()` expects **physical pixels**
- **Fix:** Multiply coordinates by `backingScaleFactor`

### Windows (Now Fixed):
- With Per-Monitor-V2: `GetWindowRect` returns **physical pixels**
- `pyautogui.screenshot()` expects **physical pixels**
- **Fix:** Set DPI awareness, no conversion needed!

## References

- [Microsoft: High DPI Desktop Application Development](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows)
- [Microsoft: GetWindowRect function](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect)
- [Microsoft: SetProcessDpiAwarenessContext](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocessdpiawarenesscontext)
- [Microsoft: GetDpiForWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow)

## Next Steps

1. **Test on Windows** - Run `test_windows_coordinates.py` to verify
2. **Test at different DPI** - Try 100%, 125%, 150%, 200% scaling
3. **Test multi-monitor** - Verify works across monitors with different DPI
4. **Test window automation** - Ensure clicks and screenshots work correctly

---

**Status:** Implemented (awaiting Windows testing)  
**Priority:** High - Must verify before releasing Windows desktop automation
