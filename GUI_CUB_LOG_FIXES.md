# GUI-Cub Log Analysis & Fixes

## Issues Found in log.log

### 1. ✅ FIXED: JSON Serialization Error in Window Listing

**Error:**
```
MAC LIST WINDOWS  🪟
Unexpected error: Object of type __NSDictionaryI is not JSON serializable
```

**Root Cause:**
- macOS `CGWindowListCopyWindowInfo` returns CoreFoundation dictionaries
- `kCGWindowBounds` is `__NSDictionaryI` (Objective-C dictionary)
- Cannot be directly JSON serialized

**Fix Applied:**
- `code_puppy/tools/gui_cub/accessibility.py` - `_list_macos_windows()`
- Convert bounds from `__NSDictionaryI` to plain Python dict
- Extract X, Y, Width, Height fields explicitly
- Cast to int for consistency

**Code Change:**
```python
# Before:
bounds = win.get("kCGWindowBounds", {})
out.append({"owner": owner, "title": title, "bounds": bounds})

# After:
bounds = win.get("kCGWindowBounds", {})
bounds_dict = {
    "x": int(bounds.get("X", 0)),
    "y": int(bounds.get("Y", 0)),
    "width": int(bounds.get("Width", 0)),
    "height": int(bounds.get("Height", 0)),
}
out.append({"owner": owner, "title": title, "bounds": bounds_dict})
```

**Status:** ✅ Fixed in commit 204a844

---

### 2. ⚠️ PARTIAL: OCR Capturing Wrong Window

**Symptoms:**
```
OCR EXTRACT TEXT  📖 region=active window (Calculator)
📍 Region offset applied: (996, 337)
✅ OCR COMPLETE
   Words found: 6
   Full text preview: eS. nsitivity guid py) >>> /agent
```

**Issue:**
- OCR is capturing terminal/IDE window instead of Calculator
- Region offset (996, 337) points to wrong window
- Text captured: "eS. nsitivity guid py) >>> /agent" (clearly terminal)

**Root Cause:**
- Calculator may not be the active window when OCR runs
- Window focus/activation timing issue
- Possible race condition between focus and OCR

**HiDPI Fix Already Applied:**
- Window bounds conversion from physical to logical pixels ✅
- Scale factor detection working ✅
- Coordinate conversion working ✅

**Remaining Issue:**
- Window focus/activation needs investigation
- May need explicit window activation before OCR
- May need wait/retry logic for window focus

**Status:** ⚠️ Partial - HiDPI fixed, window focus needs investigation

**Next Steps:**
1. Add explicit window activation with retry
2. Add verification that target window is frontmost
3. Add small delay after activation before OCR
4. Consider using VQA instead of OCR for verification

---

## Test Results

```bash
✅ All 306 tests passing
✅ JSON serialization fixed
✅ HiDPI scaling working
⚠️ Window focus issue remains (needs runtime testing)
```

---

## Files Modified

1. **code_puppy/tools/gui_cub/accessibility.py**
   - Fixed `_list_macos_windows()` JSON serialization
   - Convert CoreFoundation dicts to Python dicts

2. **code_puppy/tools/gui_cub/window_control.py** (previous fix)
   - HiDPI scaling for window bounds ✅
   - Physical to logical pixel conversion ✅

---

## Summary

| Issue | Status | Commit |
|-------|--------|--------|
| JSON serialization error | ✅ Fixed | 204a844 |
| HiDPI window bounds | ✅ Fixed | fa1014d |
| OCR wrong window | ⚠️ Partial | Needs runtime testing |

**Overall:** 2/3 issues fully resolved, 1 needs runtime investigation
