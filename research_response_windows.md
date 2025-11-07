Short version: on Windows, **coordinates and screenshots match only if your process is DPI-aware**.

* If your Python process is **DPI-unaware** or only **system-DPI-aware**, Windows applies **DPI virtualization**. Many APIs, including `GetWindowRect`, will hand you **scaled (logical) coords** while screenshot backends may capture **physical pixels**. Mismatch ensues. ([Microsoft Learn][1])
* If your process is **Per-Monitor-V2 aware**, `GetWindowRect` returns **actual screen-pixel coords** for the target monitor. Pass them directly to your screenshotter and mouse. ([Microsoft Learn][2])

# Answers to your questions

## 1) `GetWindowRect` coordinate system

* Returns a window’s bounding rectangle in **screen coordinates**. Origin is the **upper-left of the virtual screen**. ([Microsoft Learn][2])
* **DPI matters:**

  * **Per-Monitor-aware process:** values are **physical pixels**.
  * **DPI-unaware/system-aware:** Windows may return **DPI-virtualized (logical)** coords so your app sees a 96-DPI world. ([Microsoft Learn][1])
* Applies across Windows 10/11; behavior hinges on **your process awareness**, not OS version. ([Microsoft Learn][1])

## 2) `pyautogui.screenshot(region=...)` coordinate system

* PyAutoGUI on Windows uses **Pillow/ImageGrab** via **PyScreeze**. The region is interpreted in **the process’s coordinate space**. If you are DPI-unaware, expect scaling problems and partial captures. Set DPI awareness to align coords with pixels. ([pyautogui.readthedocs.io][3])
* Community reports confirm mismatches disappear after calling a DPI-awareness API or using a manifest. ([Stack Overflow][4])

## 3) DPI awareness in Python

* **Check/set awareness**

  * Preferred: **manifest** declares PMv2. ([Microsoft Learn][5])
  * Programmatic:

    * `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)`
    * or `SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)`
    * Legacy: `SetProcessDPIAware()` (system-DPI aware only). ([Microsoft Learn][6])
* **Get scale**

  * Per window: `GetDpiForWindow(hwnd)` → `scale = dpi / 96.0`. ([Microsoft Learn][7])
  * Per monitor: `GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI)`. ([Microsoft Learn][8])
* Beware: only **one** process-wide setting; the **first** library that calls one of these wins for the process. Import order matters. ([GitHub][9])

## 4) Coordinate conversion formulas

Let `s = dpi / 96.0`.

* If you detect you’re getting **logical** coords but need **physical**:

  ```
  x_px = round(x_logical * s)
  y_px = round(y_logical * s)
  w_px = round(w_logical * s)
  h_px = round(h_logical * s)
  ```
* If you have **physical** and need **logical**:

  ```
  x_logical = round(x_px / s)
  ...
  ```

Canonical rule is the same as macOS points↔pixels, just with Windows’ DIP=1/96″. ([Microsoft Learn][10])

## 5) Known issues and quirks

* **Mixed-DPI multi-monitor**: if you’re only **system-aware**, moving a window between monitors changes the *real* pixel size but your process keeps using a single system DPI, causing mismatches. Use **Per-Monitor-V2**. ([Microsoft Learn][11])
* **PyAutoGUI/Pillow**: historical issues when capturing beyond primary monitor or with scaling; these are symptoms of awareness mismatch. ([GitHub][12])
* **Window rect vs client rect**:

  * `GetWindowRect` includes borders/title bar.
  * `GetClientRect` is client area, and it’s **client-coords**, not screen-coords. Convert with `ClientToScreen` if needed. ([Stack Overflow][13])
* **UIAutomation**: `IUIAutomationElement.CurrentBoundingRectangle` returns a **screen-pixel `RECT`**. Still impacted if your process is not per-monitor aware. ([Microsoft Learn][14])

## 6) Testing & validation

* Minimal test: compute center of `GetWindowRect`, `pyautogui.click(center)`, verify hit. Then move the window across monitors and repeat at **100%, 125%, 150%, 200%** scaling.
* Screenshot test: capture using those rects and OCR text; any drift indicates awareness mismatch. Guidance on scaling and DIP in UIA docs. ([Microsoft Learn][15])

## 7) Best practices

* **Always set Per-Monitor-V2** awareness at startup, before importing GUI libs. Prefer manifest; API is acceptable if you control import order. ([Microsoft Learn][5])
* Use **`GetDpiForWindow`** for the target HWND to compute scale when converting external coords. ([Microsoft Learn][7])
* For automation stacks, consider **UIAutomation** or **pywinauto**; both expose window rectangles in screen pixels and track moves. ([Microsoft Learn][14])

---

# Drop-in DPI-aware example

```python
# Must run before importing Pillow/pyautogui
import ctypes, sys
user32 = ctypes.windll.user32
shcore = ctypes.windll.shcore

# Try Per-Monitor-V2 (Windows 10+). Fall back gracefully.
try:
    #  -4 == DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        # 2 == PROCESS_PER_MONITOR_DPI_AWARE
        shcore.SetProcessDpiAwareness(2)
    except Exception:
        # Legacy fallback: system DPI aware
        user32.SetProcessDPIAware()

import win32gui
import pyautogui

hwnd = win32gui.GetForegroundWindow()
left, top, right, bottom = win32gui.GetWindowRect(hwnd)  # screen pixels if PMv2
w = right - left
h = bottom - top

# Verify scale and compute if you need conversions for other APIs
dpi = user32.GetDpiForWindow(hwnd)  # pixels per logical inch
scale = dpi / 96.0  # e.g., 1.25 at 125%

# Screenshot the window in the same coordinate system
img = pyautogui.screenshot(region=(left, top, w, h))  # ok if process is PMv2 aware

# Optional: click center to validate
cx = left + w // 2
cy = top + h // 2
pyautogui.click(cx, cy)
```

**Multi-monitor note:** If you must convert logical↔physical yourself, get the monitor DPI for the window’s monitor and use the formulas above. `GetDpiForMonitor` is the per-monitor API. ([Microsoft Learn][8])

---

# Pointers to docs and issues

* **GetWindowRect**: screen coordinates. ([Microsoft Learn][2])
* **High-DPI, DPI virtualization, awareness modes**: overview and PMv2. ([Microsoft Learn][1])
* **Set process DPI awareness**: manifest vs API; `SetProcessDpiAwarenessContext`. ([Microsoft Learn][5])
* **GetDpiForWindow / GetDpiForMonitor**: obtain scale factor. ([Microsoft Learn][7])
* **UIAutomation bounding rectangle**: screen-pixel `RECT`. ([Microsoft Learn][14])
* **PyAutoGUI screenshot API** and DPI caveats via community issues. ([pyautogui.readthedocs.io][3])

---

## Bottom line

* Make your Python process **Per-Monitor-V2 aware**.
* Then `GetWindowRect` → **pixels**. `pyautogui.screenshot(region=...)` → same pixels.
* If you can’t set PMv2, compute `scale = GetDpiForWindow(hwnd)/96.0` and convert.

[1]: https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows?utm_source=chatgpt.com "High DPI Desktop Application Development on Windows"
[2]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect?utm_source=chatgpt.com "GetWindowRect function (winuser.h) - Win32 apps"
[3]: https://pyautogui.readthedocs.io/en/latest/screenshot.html?utm_source=chatgpt.com "Screenshot Functions - PyAutoGUI documentation"
[4]: https://stackoverflow.com/questions/69711836/pyautogui-changing-my-window-size-when-i-import-it?utm_source=chatgpt.com "Pyautogui changing my window size when I import it"
[5]: https://learn.microsoft.com/en-us/windows/win32/hidpi/setting-the-default-dpi-awareness-for-a-process?utm_source=chatgpt.com "Setting the default DPI awareness for a process (Windows)"
[6]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocessdpiawarenesscontext?utm_source=chatgpt.com "SetProcessDpiAwarenessContext function (winuser.h)"
[7]: https://learn.microsoft.com/ms-my/windows/win32/api/winuser/nf-winuser-getdpiforwindow?utm_source=chatgpt.com "GetDpiForWindow function (winuser.h) - Win32 apps"
[8]: https://learn.microsoft.com/en-us/windows/win32/api/shellscalingapi/nf-shellscalingapi-getdpiformonitor?utm_source=chatgpt.com "GetDpiForMonitor function (shellscalingapi.h) - Win32 apps"
[9]: https://github.com/BoboTiG/python-mss/issues/184?utm_source=chatgpt.com "SetProcessDpiAwareness Failed to fit High DPI in windows ..."
[10]: https://learn.microsoft.com/en-us/windows/win32/learnwin32/dpi-and-device-independent-pixels?utm_source=chatgpt.com "DPI and device-independent pixels - Win32 apps"
[11]: https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-improvements-for-desktop-applications?utm_source=chatgpt.com "Mixed-Mode DPI Scaling and DPI-aware APIs - Win32 apps"
[12]: https://github.com/python-pillow/Pillow/issues/1547?utm_source=chatgpt.com "ImageGrab fails with multiple monitors · Issue #1547"
[13]: https://stackoverflow.com/questions/7561049/what-is-the-difference-between-getclientrect-and-getwindowrect-in-winapi?utm_source=chatgpt.com "What is the difference between GetClientRect and ..."
[14]: https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nf-uiautomationclient-iuiautomationelement-get_currentboundingrectangle?utm_source=chatgpt.com "get_CurrentBoundingRectangle (uiautomationclient.h)"
[15]: https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-screenscaling?utm_source=chatgpt.com "Understanding Screen Scaling Issues - Win32 apps"
