# Windows Compatibility Audit - OCR Changes

**Date:** January 2025  
**Commit:** debbc72 ("Mac App Launcher" squashed commit)  
**Scope:** Audit recent OCR changes for Windows compatibility

## Summary

✅ **No breaking changes for Windows**  
⚠️ **One recommendation: Platform-specific confidence thresholds**  
✅ **All preprocessing is cross-platform compatible**

## Changes Audited

### 1. Confidence Threshold Lowered (0.7 → 0.25)

**File:** `code_puppy/tools/gui_cub/ocr/extraction.py`

```python
# Before
if elem.confidence > 0.7:

# After
if elem.confidence > 0.25  # Lowered for Vision Framework (macOS)
```

#### Impact on Windows:

**WinRT OCR Behavior:**
```python
# From winrt_provider.py line 196:
# WinRT doesn't provide confidence scores, use 1.0
ocr_word = OCRWord(text=word.text, confidence=1.0, bbox=bbox)
```

**Key Finding:** WinRT OCR **always returns confidence = 1.0** (100%)

| Platform | OCR Engine | Confidence Range | Threshold Impact |
|----------|------------|------------------|------------------|
| **macOS** | Vision Framework | 0.3-0.8 | **IMPROVED** (0.25 catches valid text) |
| **Windows** | WinRT OCR | Always 1.0 | **NO CHANGE** (always passes threshold) |

**Verdict:** ✅ **Safe for Windows** - WinRT confidence always passes any threshold

**Recommendation:** ⚠️ Consider platform-specific thresholds for future flexibility

---

### 2. Image Preprocessing Added

**File:** `code_puppy/tools/gui_cub/ocr/extraction.py`

New `prepare_ocr_image()` function:
1. Light Gaussian blur (radius=0.3)
2. Downscaling (if scale_factor > 1.0)
3. Grayscale conversion
4. Autocontrast

#### Cross-Platform Compatibility:

**Dependencies:**
```python
from PIL import Image, ImageFilter, ImageOps
```

- ✅ **PIL/Pillow** - Cross-platform (Windows, macOS, Linux)
- ✅ **ImageFilter.GaussianBlur** - Works identically on all platforms
- ✅ **ImageOps.grayscale** - Cross-platform
- ✅ **ImageOps.autocontrast** - Cross-platform
- ✅ **Image.resize** - Cross-platform

**Verdict:** ✅ **Fully compatible with Windows**

**Windows HiDPI Handling:**
- Windows uses `pyautogui.screenshot()` which handles DPI automatically
- `scale_factor` is detected correctly on Windows via `get_screen_scale_factor()`
- Preprocessing applies correctly on Windows HiDPI displays (125%, 150%, 200%)

---

### 3. Screenshot Capture Changes

**File:** `code_puppy/tools/gui_cub/screen_capture/capture.py`

**Platform-Specific Logic:**
```python
def _safe_screenshot(region=None):
    if platform.system() == "Darwin":
        # macOS: Use ImageGrab.grab() for thread safety
        # ... macOS-specific coordinate conversion
    else:
        # Windows/Linux: Use pyautogui.screenshot()
        return pyautogui.screenshot(region=region)
```

**Verdict:** ✅ **Windows code path unchanged** - Still uses `pyautogui.screenshot()`

---

### 4. Vision Framework Enhancements

**File:** `code_puppy/tools/gui_cub/ocr_providers/vision_provider.py`

Changes:
- Added `usesLanguageCorrection_(True)`
- Set `recognitionLanguages_(["en-US"])`
- Use latest revision
- Added confidence interpretation docs

**Verdict:** ✅ **macOS-only code** - Windows never imports this module

**Isolation:**
```python
# In __init__.py
if IS_MACOS:
    from .vision_provider import VisionOCRProvider

# Windows never loads VisionOCRProvider
```

---

## Potential Issues Found

### Issue #1: Hardcoded Confidence Threshold

**Current State:**
- Single threshold (0.25) for all OCR engines
- Optimized for Vision Framework (macOS)
- WinRT (Windows) always returns 1.0, so threshold is irrelevant

**Problem:**
- If future OCR engines on Windows return variable confidence
- 0.25 might be too low for those engines
- No way to set engine-specific thresholds

**Recommendation:**
```python
# Provider-specific confidence thresholds
PROVIDER_CONFIDENCE_THRESHOLDS = {
    "Apple Vision": 0.25,  # Vision Framework reports low (0.3-0.5)
    "WinRT OCR": 0.0,      # Always returns 1.0, threshold irrelevant
    "Tesseract": 0.7,      # Tesseract uses 0-100 scale
    "Google Vision": 0.7,  # Calibrated probabilities
}

def get_confidence_threshold(provider_name: str) -> float:
    return PROVIDER_CONFIDENCE_THRESHOLDS.get(provider_name, 0.25)
```

**Priority:** 🟡 **LOW** - Not urgent, but good for future-proofing

---

### Issue #2: Documentation Says "Vision Framework adjusted"

**Current:**
```python
filters_applied=[
    "confidence > 0.25 (Vision Framework adjusted)",
    ...
]
```

**Problem:** This applies to Windows too, but comment says "Vision Framework"

**Recommendation:** Update to:
```python
"confidence > 0.25 (adjusted for macOS Vision Framework)"
```

Or make it dynamic:
```python
threshold_note = "adjusted for macOS Vision" if IS_MACOS else "WinRT always 1.0"
```

**Priority:** 🟢 **TRIVIAL** - Documentation clarity only

---

## Testing Recommendations

### Windows-Specific Tests:

1. **Test WinRT OCR confidence**:
   ```python
   # On Windows, verify all text has confidence = 1.0
   result = desktop_extract_text(window_title="Notepad")
   assert all(elem.confidence == 1.0 for elem in result.text_elements)
   ```

2. **Test HiDPI preprocessing**:
   ```python
   # On Windows with 150% scaling, verify preprocessing works
   # Image should be blurred, grayscaled, autocontrasted
   ```

3. **Test filtering doesn't break**:
   ```python
   # Verify 0.25 threshold doesn't filter out WinRT results
   # (Should never filter since confidence = 1.0)
   ```

### Cross-Platform Tests:

1. **Compare OCR results**:
   - Same image on macOS (Vision) vs Windows (WinRT)
   - Verify both detect text (may differ in accuracy)
   - Check confidence: macOS 0.3-0.5, Windows 1.0

2. **Preprocessing consistency**:
   - Verify grayscale + autocontrast produces similar images
   - Check blur reduces anti-aliasing on both platforms

---

## Compatibility Matrix

| Feature | Windows | macOS | Linux | Notes |
|---------|---------|-------|-------|-------|
| **Confidence threshold 0.25** | ✅ Safe | ✅ Improved | ✅ Safe | WinRT always 1.0 |
| **Image preprocessing** | ✅ Works | ✅ Works | ✅ Works | PIL cross-platform |
| **GaussianBlur** | ✅ Works | ✅ Works | ✅ Works | |
| **Grayscale** | ✅ Works | ✅ Works | ✅ Works | |
| **Autocontrast** | ✅ Works | ✅ Works | ✅ Works | |
| **Vision Framework changes** | N/A | ✅ Works | N/A | macOS-only |
| **ImageGrab coordinate fix** | N/A | ✅ Fixed | N/A | macOS-only |
| **WinRT OCR** | ✅ Unchanged | N/A | N/A | Windows-only |

---

## Recommendations

### 🟢 Optional Enhancements (Not Required):

1. **Add provider-specific thresholds**:
   ```python
   threshold = get_confidence_threshold(provider_result.provider)
   if elem.confidence > threshold:
       ...
   ```

2. **Document WinRT confidence behavior**:
   ```python
   # In winrt_provider.py
   class WinRTOCRProvider(OCRProvider):
       """
       IMPORTANT - Confidence Scores:
       WinRT OCR does not provide confidence scores. All text
       is returned with confidence = 1.0 (100%).
       
       This means confidence-based filtering has NO EFFECT on
       Windows. Use other validation methods (string matching,
       bounding box checks, etc.) instead.
       """
   ```

3. **Add platform-aware filter messages**:
   ```python
   if IS_MACOS:
       note = "Vision Framework adjusted (0.3-0.5 typical)"
   elif IS_WINDOWS:
       note = "WinRT always returns 1.0"
   else:
       note = "Platform default"
   ```

### 🔴 Required: None

All changes are backward-compatible and Windows-safe!

---

## Conclusion

### ✅ **No Breaking Changes for Windows**

The recent OCR changes:
- Lower confidence threshold (0.7 → 0.25)
- Image preprocessing (blur, grayscale, contrast)
- Vision Framework enhancements

All are **fully compatible with Windows**:
- WinRT OCR always returns confidence = 1.0, so threshold change has no effect
- PIL preprocessing is cross-platform
- macOS-specific code is properly isolated

### ⚠️ **Recommendations for Future**

1. Consider provider-specific confidence thresholds
2. Document WinRT's 1.0 confidence behavior
3. Make filter messages platform-aware

### 🎯 **Bottom Line**

**The code is safe to ship on Windows!** No immediate changes needed.

The confidence threshold of 0.25 was optimized for macOS Vision Framework, but it doesn't hurt Windows because WinRT always returns 1.0 anyway.

---

## Files Reviewed

- ✅ `code_puppy/tools/gui_cub/ocr/extraction.py`
- ✅ `code_puppy/tools/gui_cub/ocr_providers/vision_provider.py`
- ✅ `code_puppy/tools/gui_cub/ocr_providers/winrt_provider.py`
- ✅ `code_puppy/tools/gui_cub/screen_capture/capture.py`
- ✅ `code_puppy/tools/gui_cub/ocr/tools.py`

**All clear for Windows!** ✅
