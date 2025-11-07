# GUI-Cub Platform Support

**Status:** Windows and macOS Only  
**Last Updated:** 2025-01-15

---

## Supported Platforms

### ✅ Windows (10+)
- **Native OCR:** WinRT OCR (Windows.Media.Ocr)
- **Window Control:** pywinauto
- **Accessibility:** Win32 APIs
- **DPI Awareness:** Per-Monitor-V2
- **Screenshot:** mss (native)

### ✅ macOS (10.15+)
- **Native OCR:** Vision Framework (VNRecognizeTextRequest)
- **Window Control:** atomacos (Accessibility API)
- **Accessibility:** NSAccessibility
- **Retina Support:** Full HiDPI scaling
- **Screenshot:** mss (native)

---

## Unsupported Platforms

### ❌ Linux
**Status:** Not supported (may be added in future)

**Why removed:**
- No native OCR API (would require external dependencies)
- Complex multi-desktop-environment support (X11, Wayland, etc.)
- Inconsistent window management APIs across distros
- Limited testing resources
- Small user base for desktop automation tools

**If Linux support is needed in future:**
- OCR: Could add easyocr, paddleocr, or rapidocr
- Window Control: Could use python-xlib (X11) or wlroots (Wayland)
- Accessibility: AT-SPI2 (complex, varies by DE)

---

## Platform Detection

### Constants Available
```python
from code_puppy.tools.gui_cub.platform import IS_MACOS, IS_WINDOWS

if IS_MACOS:
    # macOS-specific code
    pass
elif IS_WINDOWS:
    # Windows-specific code
    pass
else:
    # Unsupported platform
    raise RuntimeError("GUI-Cub only supports Windows and macOS")
```

### Platform Enum
```python
from code_puppy.tools.gui_cub.platform import Platform

# Only two platforms defined:
Platform.MACOS   # "darwin"
Platform.WINDOWS # "win32"
```

### Display Name
```python
from code_puppy.tools.gui_cub.platform import get_platform_display_name

platform = get_platform_display_name()
# Returns: "macOS", "Windows", or "Unsupported"
```

---

## Feature Comparison

| Feature | Windows | macOS | Notes |
|---------|---------|-------|-------|
| **OCR (Native)** | ✅ WinRT | ✅ Vision | No external deps |
| **Window Control** | ✅ pywinauto | ✅ atomacos | Full API coverage |
| **Mouse/Keyboard** | ✅ pyautogui | ✅ pyautogui | Cross-platform |
| **Screenshots** | ✅ mss | ✅ mss | Native APIs |
| **Multi-Monitor** | ✅ Full | ✅ Full | DPI-aware |
| **Accessibility** | ✅ Win32 | ✅ NSAccessibility | Permission prompts on macOS |
| **HiDPI/Retina** | ✅ Per-Monitor-V2 | ✅ Native Scaling | Automatic |
| **Browser Automation** | ✅ Supported | ✅ Supported | Chrome, Firefox, Safari, Edge, Brave, Arc |
| **VQA Integration** | ✅ Supported | ✅ Supported | OpenAI GPT-4 Vision |

---

## OS-Specific Behaviors

### Windows
- **Keyboard Shortcuts:** Use `Ctrl` as modifier (Ctrl+C, Ctrl+V, etc.)
- **Window Close:** Alt+F4
- **DPI Scaling:** Automatic detection and conversion
- **Admin Rights:** Not required for GUI-Cub
- **Window Coordinates:** Physical pixels (converted to logical)

### macOS
- **Keyboard Shortcuts:** Use `Cmd` as modifier (Cmd+C, Cmd+V, etc.)
- **Window Close:** Cmd+Q
- **Retina Scaling:** Automatic 2x scaling detection
- **Permissions:** Requires Accessibility and Screen Recording permissions
- **Window Coordinates:** Logical points (already scaled)

---

## Default Platform for Logic

**When a default OS is needed:** Use macOS

Example:
```python
# Default to macOS for unknown platforms
platform_key = "macos" if IS_MACOS else "windows"

# Not:
platform_key = "macos" if IS_MACOS else "windows" if IS_WINDOWS else "linux"
```

**Rationale:**
- macOS development environment for code-puppy
- More conservative/safer defaults (requires permissions)
- Better error messages when unsupported platform detected

---

## Migration from Linux Support

**What was removed (2025-01-15):**
- `Platform.LINUX` enum value
- `IS_LINUX` constant
- `_detect_linux_monitors()` function
- Linux browser offset heights
- Linux-specific error messages
- All "Windows/Linux" references in docs/comments

**What remains:**
- Code will gracefully degrade on unsupported platforms
- Clear error messages indicate Windows/macOS only
- Platform detection returns "Unsupported" for unknown OS

---

## FAQ

**Q: Will Linux support be added in the future?**  
A: Maybe, if there's demand and resources. It's not a priority.

**Q: What happens if I run GUI-Cub on Linux?**  
A: Most features will fail gracefully with clear error messages. Some cross-platform tools (like pyautogui) might partially work, but OCR and window control won't.

**Q: Why not use portable OCR (easyocr, paddleocr) for cross-platform?**  
A: Native APIs are 2-5x faster and have zero dependencies. Portable OCR would add 500MB+ of dependencies and require GPU/CPU configuration.

**Q: Can I use GUI-Cub on WSL (Windows Subsystem for Linux)?**  
A: No. GUI-Cub requires native Windows or macOS. WSL doesn't have access to Windows GUI APIs from Linux environment.

---

**Platform Policy:** GUI-Cub is Windows/macOS only. Linux support is not planned but could be added if there's sufficient demand and contribution from the community.
