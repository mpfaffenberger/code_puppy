# OCR Coordinate Debugging - Comprehensive Logging Added

**Date:** 2025-01-11  
**Issue:** Window targeting coordinates not working correctly in OCR flow  
**Solution:** Added extensive debug logging throughout the entire OCR coordinate transformation pipeline

---

## 🐛 The Problem

Window coordinates for OCR targeting are still not working correctly. The OCR is capturing the wrong window or returning incorrect screen coordinates even after fixing the window focus bug.

## 🔍 Debug Logs Added

Added comprehensive debug logging to track:
1. **Coordinates** through the entire transformation pipeline
2. **Agent state** and context at each tool invocation
3. **Call counters** to detect if functions are being called fresh or cached

This will help identify if the agent is:
- ❌ Caching window bounds between calls
- ❌ Reusing stale coordinates from previous tool invocations  
- ❌ Not calling window detection fresh each time

---

### 0. **Agent Context Inspection** (NEW! 🧠)

**Location:** `ocr/tools.py` - `desktop_extract_text()`, `window_control/tools.py` - `desktop_focus_window()`, `desktop_get_active_window()`

**Logs Added:**
- **Call counter** for each tool (tracks invocation number since agent started)
- **RunContext inspection** (checks for deps, cached state, model info)
- **Fresh vs Cached detection** (shows if this is a new call or repeat)

**Example Output:**
```
🔢 DEBUG [CALL #1]: desktop_extract_text invoked
   This is invocation #1 since agent started

🧠 DEBUG [AGENT CONTEXT]: RunContext inspection
   has_deps=False, has_retry=True, has_model=True
   context_type=RunContext

🔢 DEBUG [CALL #2]: desktop_focus_window(app_name='TextEdit')

🔢 DEBUG [CALL #3]: desktop_extract_text invoked
   This is invocation #3 since agent started
```

**What to Watch For:**
- ⚠️ If call counter doesn't increment, something is wrong
- ⚠️ If context.deps contains window bounds, they might be cached
- ✅ Each tool call should have a unique call number

---

### 1. **Window Bounds Detection** (`window_control/core.py`)

**Location:** `_get_active_window_bounds_impl()`

**Logs Added:**
- **Call counter** (tracks invocation number - should increment on EVERY call!)
- **"FRESH DETECTION STARTING"** message (proves function is being called, not cached)
- **Frontmost app detection** from macOS
- Number of candidate windows found
- Window details (title, size, position, area)
- Selected window information
- **Final bounds being returned (LOGICAL coordinates from macOS)**

**Example Output:**
```
🔍 DEBUG [CALL #1]: _get_active_window_bounds_impl() - FRESH DETECTION STARTING

🔍 DEBUG: macOS reports frontmost app:
   app_name='Calculator', pid=12345

🔍 DEBUG [_get_active_window_bounds_impl]: Found 1 candidate windows
🔍 DEBUG [_get_active_window_bounds_impl]: Returning window bounds
   app_name=Calculator
   window_title=Calculator
   LOGICAL coords (points): x=22, y=57, w=198, h=350
   These are macOS CGWindowBounds in POINTS (will be multiplied by scale_factor for physical pixels)

[Later...]

🔍 DEBUG [CALL #2]: _get_active_window_bounds_impl() - FRESH DETECTION STARTING

🔍 DEBUG: macOS reports frontmost app:
   app_name='TextEdit', pid=67890

🔍 DEBUG [_get_active_window_bounds_impl]: Found 1 candidate windows
```

**KEY INDICATOR:** If the call counter doesn't increment between different window captures, the function isn't being called fresh!

---

### 2. **OCR Tool Entry** (`ocr/tools.py` - `desktop_extract_text()`) ✨ ENHANCED

**Logs Added:**
- **Call counter** (invocation number since agent started)
- **RunContext inspection** (checks for cached state in agent context)
- **Input parameters** (x, y, width, height, use_active_window, use_full_screen)
- Window bounds detection trigger and results
- Scale factor detection
- Logical → Physical coordinate conversion
- Screenshot capture confirmation
- OCR call parameters

**Example Output:**
```
🔢 DEBUG [CALL #1]: desktop_extract_text invoked
   This is invocation #1 since agent started

🧠 DEBUG [AGENT CONTEXT]: RunContext inspection
   has_deps=False, has_retry=True, has_model=True
   context_type=RunContext

🔍 DEBUG [INPUT PARAMS]: Tool parameters
   x=None, y=None, width=None, height=None
   use_active_window=True, use_full_screen=False

🔍 DEBUG: Detecting active window bounds...

🪟 DEBUG: Window bounds detection - success=True
   app_name=TextEdit, window_title=Untitled
   bounds=(x=185, y=90, w=601, h=491)

✓ DEBUG: Using window bounds (LOGICAL coords): (185, 90, 601, 491)

🔍 DEBUG: Screen scale factor detected: 2.0x

🔍 DEBUG: Converting region coordinates (logical → physical)
   Region (logical): (185, 90, 601, 491)
   Scale factor: 2.0x

📍 Region (logical): (185, 90, 601, 491)
📍 Region (physical): (370, 180, 1202, 982) - for screenshot capture

🔍 DEBUG: Physical region calculated:
   x=370, y=180, w=1202, h=982

📸 DEBUG: Capturing screenshot with region=(370, 180, 1202, 982)

✓ DEBUG: Screenshot captured - size=(1202, 982) (width=1202, height=982)

🔍 DEBUG: Calling OCR with:
   scale_factor=2.0
   region_offset=(370, 180) (physical pixels)
   language=eng

✓ DEBUG: OCR completed - found 3 elements
```

---

### 3. **OCR Coordinate Conversion** (`ocr/extraction.py` - `extract_text_from_image()`)

**Logs Added:**
- Extraction parameters (image size, scale factor, region offset)
- Total words found by OCR provider
- **Per-word coordinate transformation** (first 3 words):
  - Raw OCR bbox (screenshot space, physical pixels)
  - After scale division (logical pixels)
  - Region offset application (physical → logical)
  - Before/after offset addition
  - **Final screen coordinates**

**Example Output:**
```
🔍 DEBUG [extract_text_from_image]: Starting OCR extraction
   image_size=(1202, 982)
   scale_factor=2.0
   region_offset=(370, 180)
   language=eng

🔍 DEBUG [extract_text_from_image]: Processing 3 OCR words

   Word #1 'untitled':
     OCR bbox (screenshot space, physical): (10, 5, 120, 30)
     After scale division (logical): (5, 2, 60, 15)
     Region offset (physical): (370, 180)
     Region offset (logical): (185, 90)
     Before offset: (5, 2)
     After offset: (190, 92) ← FINAL SCREEN COORDS

   Word #2 'Edit':
     OCR bbox (screenshot space, physical): (150, 5, 60, 30)
     After scale division (logical): (75, 2, 30, 15)
     Region offset (physical): (370, 180)
     Region offset (logical): (185, 90)
     Before offset: (75, 2)
     After offset: (260, 92) ← FINAL SCREEN COORDS

✓ DEBUG [extract_text_from_image]: Converted 3 elements to screen coordinates
```

---

## 🎯 What to Look For

When you run OCR now, examine the debug logs for:

### 🔍 **Agent Caching Issues** (NEW!):
1. **Call counters should increment sequentially:**
   - desktop_extract_text: #1, #2, #3...
   - _get_active_window_bounds_impl: #1, #2, #3...
   - desktop_focus_window: #1, #2, #3...

2. **Each tool call should show "FRESH DETECTION STARTING"**
   - If missing, the function isn't being called at all!

3. **"macOS reports frontmost app" should change** between window switches
   - If it shows same app after focus change, focus bug is back
   - If it shows different app but same coords, caching bug!

4. **RunContext should NOT have window bounds in deps**
   - If context.deps contains coordinates, agent is caching them

---

### ✅ **Correct Flow:**
1. Window bounds should match the actual window position (check with mouse hover)
2. Logical coords should be multiplied by scale_factor (2.0x on Retina)
3. Region offset (physical) = Logical coords × scale_factor
4. OCR bbox coordinates start at (0, 0) relative to screenshot
5. Final screen coords = (OCR coords / scale_factor) + (region_offset / scale_factor)

### ❌ **Common Bugs to Spot:**
- **Wrong window detected** → Check "Window bounds detection" section
- **Scale factor not applied** → Check "Scale factor detected" log
- **Region offset missing/wrong** → Check "Region offset (logical)" values
- **Coordinates doubled/halved** → Check scale_factor division/multiplication
- **Coordinates don't match window** → Compare "FINAL SCREEN COORDS" to actual positions

---

## 🧪 How to Test

1. **Enable debug screenshots** (if not already):
   ```
   /debug_screenshots on
   ```

2. **Switch to gui-cub agent**:
   ```
   /agent gui-cub
   ```

3. **Run OCR test** (this will trigger all the debug logs):
   ```
   Focus Calculator, extract text, and copy the screenshot to my cwd.
   Then focus TextEdit, extract text, and copy that screenshot to my cwd.
   ```

4. **Watch for these patterns in the logs:**
   - ✅ Call counters incrementing: #1, #2, #3...
   - ✅ "FRESH DETECTION STARTING" appearing before each window detection
   - ✅ "macOS reports frontmost app" changing from Calculator to TextEdit
   - ❌ Same call number appearing twice (caching!)
   - ❌ Same window bounds for different windows (stale coords!)
   - ❌ Missing "FRESH DETECTION" messages (function not called!)

5. **Collect the logs** and paste them back to Doc for analysis

6. **Check the screenshots** in your cwd to verify they captured the right windows

---

## 📋 Files Modified

1. **`code_puppy/tools/gui_cub/window_control/core.py`**
   - Added debug logs in `_get_active_window_bounds_impl()`
   - Shows window detection results and final bounds being returned

2. **`code_puppy/tools/gui_cub/ocr/tools.py`**
   - Added debug logs in `desktop_extract_text()`
   - Shows input params, window detection, coordinate conversions, screenshot capture

3. **`code_puppy/tools/gui_cub/ocr/extraction.py`**
   - Added debug logs in `extract_text_from_image()`
   - Shows detailed coordinate transformation for each OCR word (first 3)

---

## 🐕 Next Steps

1. Run the test with debug logging enabled
2. Paste the full debug output back to Doc
3. I'll analyze the coordinate transformations and identify the bug
4. Fix the coordinate math
5. Verify OCR targets the correct windows!

**The debug logs will tell us exactly where the coordinates are going wrong!** 🎯
