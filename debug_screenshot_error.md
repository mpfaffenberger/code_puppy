# Screenshot Error Debug Information

## Error Summary
**Error Message:** `'ScreenshotResult' object has no attribute 'file_path'`

## Context
This error occurred during the Drop-Off workflow execution when attempting to use OCR to find the "Patient Not Present" button after VQA successfully identified it in the validation dialog.

## Timeline of Events

### 1. VQA Success
- Called `desktop_screenshot_analyze` with question: "What buttons are visible at the bottom of the Validate Patient Information dialog?"
- **VQA Response:**
  - Answer: "The visible buttons at the bottom of the Validate Patient Information dialog are: 'Update Patient Profile', 'Wrong Patient Initiate New Search', and 'Patient Not Present'."
  - Confidence: 0.95
  - Screenshot path: `C:\Users\AUTOMA~1\AppData\Local\Temp\code_puppy_rpa_screenshots_y4acxdwy\desktop_screenshot_20251102_104419.png`

### 2. OCR Attempt
- Called `desktop_find_text` with:
  - `search_text`: "Patient Not Present"
  - `use_full_screen`: True
  - `fuzzy`: True
  - `fuzzy_threshold`: 0.6
- **Result:** Found=False, matches=[], total_matches=0

### 3. Error Occurrence
- After the OCR call returned no matches
- Error suggests there was an attempt to access `.file_path` attribute on a `ScreenshotResult` object
- The attribute should be `.screenshot_path` instead (based on VQA result)

## ScreenshotResult Object Structure (from VQA)

```python
{
  "screenshot_info": {
    "path": "C:\\Users\\AUTOMA~1\\AppData\\Local\\Temp\\code_puppy_rpa_screenshots_y4acxdwy\\desktop_screenshot_20251102_104419.png",
    "size": 103113,
    "timestamp": "20251102_104419",
    "width": 1680,
    "height": 1050,
    "logical_width": 1680,
    "logical_height": 1050,
    "scale_x": 1.0,
    "scale_y": 1.0,
    "original_width": 1680,
    "original_height": 1050,
    "vqa_width": 1680,
    "vqa_height": 1050,
    "vqa_scale_x": 1.0,
    "vqa_scale_y": 1.0,
    "region": null
  }
}
```

## Hypothesis

### Likely Cause
The `desktop_find_text` function internally takes a screenshot and returns an OCR result. Somewhere in the code, there's an attempt to access `screenshot_result.file_path` when it should be accessing `screenshot_result.screenshot_path` or `screenshot_result.path`.

### Evidence
1. Earlier in the workflow, `desktop_screenshot()` returned:
   ```python
   {
     "screenshot_path": "C:\\Users\\AUTOMA~1\\AppData\\Local\\Temp\\...",
     "timestamp": "...",
     "width": 1680,
     "height": 1050
   }
   ```
   - Note: Uses `screenshot_path`, NOT `file_path`

2. VQA result uses nested structure: `screenshot_info.path`

3. The error suggests internal code is trying to access `.file_path` which doesn't exist

## Related Function Calls

### Working Screenshot Calls
```python
desktop_screenshot(save_screenshot=True)
# Returns: {"screenshot_path": "...", "timestamp": "...", ...}

desktop_screenshot_analyze(question="...", use_grid=False, capture_mode="full_screen")
# Returns: {"screenshot_info": {"path": "..."}, ...}

desktop_extract_text(use_active_window=True)
# Returns: {"full_text": "...", "text_elements": [...], ...}
```

### Problematic Call
```python
desktop_find_text(
  search_text="Patient Not Present",
  use_full_screen=True,
  fuzzy=True,
  fuzzy_threshold=0.6
)
# Returns: {"found": False, "matches": [], ...}
# ERROR: Internal code tries to access .file_path on ScreenshotResult
```

## Potential Fix Locations

Check the following in `desktop_find_text` implementation:

1. **Screenshot capture step:**
   ```python
   # WRONG:
   screenshot = take_screenshot(...)
   path = screenshot.file_path  # AttributeError!
   
   # CORRECT:
   screenshot = take_screenshot(...)
   path = screenshot.screenshot_path  # or screenshot.path
   ```

2. **OCR result construction:**
   - Ensure the result object structure matches expected attributes

3. **Error handling:**
   - Check if error occurs during exception handling when OCR fails to find text

## Recommended Actions

1. **Search codebase** for:
   - `.file_path` references (should be `.screenshot_path` or `.path`)
   - `ScreenshotResult` class definition to verify correct attribute names
   - `desktop_find_text` implementation

2. **Verify attribute names** across all screenshot-related tools:
   - `desktop_screenshot` → `screenshot_path`
   - `desktop_screenshot_analyze` → `screenshot_info.path`
   - `desktop_extract_text` → (no screenshot path in return)
   - `desktop_find_text` → (error occurs here)

3. **Add defensive coding:**
   ```python
   # Check for multiple possible attribute names
   path = getattr(screenshot, 'screenshot_path', None) or \
          getattr(screenshot, 'file_path', None) or \
          getattr(screenshot, 'path', None)
   ```

## Workaround for Current Workflow

Since OCR cannot find "Patient Not Present" but VQA can see it, use VQA coordinates:

### Option 1: VQA + Click
```python
vqa_result = desktop_screenshot_analyze(
    question="What are the exact coordinates of the 'Patient Not Present' button?",
    use_grid=True,  # Enable grid for coordinates
    capture_mode="full_screen"
)
# Then parse coordinates from answer and click
```

### Option 2: UI Automation
```python
ui_click_element(title="Patient Not Present")
# or
windows_click_element(title="Patient Not Present")
```

### Option 3: Keyboard Navigation
```python
# Tab through buttons and press Enter
for i in range(10):
    desktop_keyboard_press("tab")
    desktop_sleep(0.1)
    # Check if "Patient Not Present" is focused
    desktop_keyboard_press("enter")
```

## Additional Debug Info

### Full Error Traceback
```
Unexpected error: 'ScreenshotResult' object has no attribute 'file_path'
("'ScreenshotResult' object has no attribute 'file_path'",)
```

### Workflow State at Error
- **Screen:** Validate Patient Information dialog visible
- **Last successful action:** VQA identified three buttons
- **Failed action:** OCR text search for "Patient Not Present"
- **Next planned action:** Click "Patient Not Present" button

### Session Details
- **Timestamp:** 2025-11-02 10:44:19
- **Application:** Connexus (Drop-Off screen)
- **Workflow step:** Patient validation dialog handling
- **Mode:** Workflow Building Mode (interactive)

---

**Generated:** 2025-11-02  
**Workflow:** connexus_locator_library/workflows/DropOff.yaml  
**Reference:** connexus_locator_library/reference/OrderIntake.yaml
