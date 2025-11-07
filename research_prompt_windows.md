# Windows Desktop Automation Coordinate System Research

Please research Windows-specific coordinate systems and DPI scaling for desktop automation, screenshots, and OCR.

## Context

We recently discovered and fixed a **critical coordinate bug on macOS** where `CGWindowListCopyWindowInfo` returns coordinates in **points (logical)** but we were incorrectly treating them as **physical pixels**. This caused screenshots to capture wrong regions on Retina displays.

Now we need to verify Windows doesn't have similar issues.

## Windows Implementation Details

### Current Code:

```python
import win32gui
import pyautogui
from PIL import Image

# Get window handle and bounds
hwnd = win32gui.GetForegroundWindow()
rect = win32gui.GetWindowRect(hwnd)  # Returns (left, top, right, bottom)
x, y, right, bottom = rect
width = right - x
height = bottom - y

# Capture screenshot
region = (x, y, width, height)
screenshot = pyautogui.screenshot(region=region)
```

### Windows DPI Scaling Context:

- Windows supports various DPI scaling levels: 100%, 125%, 150%, 175%, 200%, etc.
- Users can set different DPI scaling per monitor
- Windows has "DPI awareness" modes: unaware, system-aware, per-monitor-aware
- Python applications may or may not be DPI-aware by default

## Research Questions

### 1. GetWindowRect Coordinate System

**Critical Question:** Does `win32gui.GetWindowRect()` return coordinates in:
- **Physical pixels** (actual screen resolution)?
- **Logical pixels/points** (DPI-scaled coordinates)?
- **Virtual screen coordinates** (something else)?

**Follow-up:** Does the answer change based on:
- The DPI awareness mode of the Python process?
- Whether the target window is on a high-DPI display?
- Windows version (Windows 10 vs 11)?

### 2. pyautogui Screenshot Coordinate System

**Critical Question:** What coordinate system does `pyautogui.screenshot(region=(x, y, w, h))` expect on Windows?
- Physical pixels?
- Logical pixels?
- Does it change based on DPI awareness?

**Test scenarios:**
- Windows at 100% DPI scaling (no scaling)
- Windows at 125% DPI scaling
- Windows at 150% DPI scaling
- Windows at 200% DPI scaling

### 3. DPI Awareness in Python

**Questions:**
- How can we check if a Python process is DPI-aware?
- How can we programmatically set DPI awareness?
- What's the default DPI awareness for Python 3.x?
- Do PyWin32 and pyautogui handle DPI differently?

**Relevant Windows APIs:**
```python
import ctypes

# Set DPI awareness (various methods)
ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware V2
ctypes.windll.user32.SetProcessDPIAware()  # System DPI aware

# Get DPI scaling
user32 = ctypes.windll.user32
dpi = user32.GetDpiForWindow(hwnd)
scaling = dpi / 96.0  # 96 DPI = 100% scaling
```

### 4. Coordinate Conversion

**If coordinates need conversion, what's the formula?**

Possible scenarios:

A) **GetWindowRect returns logical, pyautogui expects physical:**
```python
scaling = get_dpi_scaling()  # e.g., 1.25 for 125%
physical_x = int(logical_x * scaling)
physical_y = int(logical_y * scaling)
```

B) **GetWindowRect returns physical, pyautogui expects logical:**
```python
logical_x = int(physical_x / scaling)
logical_y = int(physical_y / scaling)
```

C) **No conversion needed (both use same system):**
```python
# Just pass coordinates directly
```

### 5. Known Issues & Quirks

**Are there documented issues with:**
- Window bounds detection on multi-monitor setups with different DPI scaling?
- Screenshot capture at non-100% DPI scaling?
- Coordinate mismatches between win32gui and pyautogui?
- OCR accuracy on high-DPI displays?

**Windows-specific API behaviors:**
- Does `GetWindowRect` include window decorations (title bar, borders)?
- Does `GetClientRect` behave differently?
- Are there differences between `GetWindowRect` and accessibility APIs?

### 6. Testing & Validation

**How to test if coordinates are correct:**

1. Get window bounds: `(x, y, width, height)`
2. Calculate center: `(x + width/2, y + height/2)`
3. Click at center with `pyautogui.click(center_x, center_y)`
4. Verify click lands in the correct window

**How to test screenshot accuracy:**

1. Get window bounds
2. Capture screenshot with those bounds
3. Check if screenshot shows the correct window content
4. Use OCR to verify captured text matches window content

### 7. Best Practices

**What's the recommended approach for Windows desktop automation?**

- Should we always set DPI awareness at startup?
- Which DPI awareness mode is best: system-aware or per-monitor-aware?
- Should we use `GetDpiForWindow()` for per-window scaling?
- Are there alternative APIs that handle DPI automatically?

**Alternative approaches:**

```python
# Option 1: Use Windows accessibility APIs
from pywinauto import Application
app = Application().connect(handle=hwnd)
rect = app.window().rectangle()

# Option 2: Use UIAutomation
from comtypes import client
uiAutomation = client.CreateObject("UIAutomation")
element = uiAutomation.ElementFromHandle(hwnd)
rect = element.CurrentBoundingRectangle

# Option 3: Direct Win32 with DPI awareness
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(2)
rect = win32gui.GetWindowRect(hwnd)
```

## What We Need

### Documentation:
- Official Microsoft docs on GetWindowRect coordinate system
- DPI scaling documentation for Win32 APIs
- Python-specific DPI handling guides
- pyautogui Windows DPI behavior

### Code Examples:
- Working examples of DPI-aware window capture
- Coordinate conversion formulas for different DPI settings
- Test scripts to validate coordinate accuracy

### Known Issues:
- Stack Overflow discussions about Windows DPI and pyautogui
- GitHub issues in pyautogui, PyWin32, or similar libraries
- Known bugs or workarounds for Windows 10/11 DPI scaling

### Recommendations:
- Best practices for DPI-aware desktop automation on Windows
- Whether to use logical or physical coordinates
- How to handle multi-monitor setups with different DPI

## Specific Test Case

We have a **native Windows login dialog** with:
- A login button with text label
- Username and password fields
- Standard Windows dialog appearance

**Goals:**
1. Detect the dialog window bounds
2. Capture a screenshot of just the dialog
3. Use OCR to find the "Login" button text
4. Click the button using detected coordinates

**Current concern:** Will coordinates be off by the DPI scaling factor (like they were on macOS)?

## Additional Context

### macOS Bug (for comparison):
- `CGWindowListCopyWindowInfo` returns **points** (logical)
- We incorrectly divided by scale factor
- Then multiplied back for screenshot
- Result: coordinates were **half** of what they should be on 2x displays

### Windows Question:
- Does `GetWindowRect` return logical or physical?
- Does `pyautogui.screenshot()` expect logical or physical?
- **If both use the same system, no conversion needed**
- **If they differ, we need conversion (like on macOS)**

## Expected Output

Please provide:

1. **Definitive answer:** What coordinate system does `GetWindowRect` use?
2. **Definitive answer:** What coordinate system does `pyautogui.screenshot()` expect?
3. **Conversion formula** if needed, with DPI scaling factor calculation
4. **Code example** showing correct DPI-aware window capture
5. **Links** to official documentation
6. **Known issues** or gotchas with Windows DPI scaling
7. **Testing approach** to validate coordinates are correct

---

**Priority:** High - We need to ensure Windows automation works correctly across all DPI scaling settings before releasing desktop VQA/OCR features.
