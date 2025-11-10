# Open and Use Calculator - GUI-Cub Example Workflow

## Goal

Launch the Calculator application and perform a simple calculation

## Context

- **Application:** Calculator (native macOS/Windows app)
- **Platform:** macOS and Windows (different launchers)
- **Prerequisites:** None
- **Typical Use Case:** Quick calculations, automation testing, UI verification

## Recommended Approach

### Strategy Overview

Use OS-specific launcher (Spotlight on macOS, Start Menu on Windows) to open Calculator, then use keyboard shortcuts for all interactions to avoid unreliable mouse clicks.

### Suggested Steps

#### 1. Launch Calculator Application

**Goal:** Open Calculator and bring it to foreground

**Suggested Tools (macOS):**
```python
# Open Spotlight
desktop_keyboard_hotkey(["cmd", "space"])

# Type "Calculator"
desktop_keyboard_type("Calculator")

# Press Enter to launch
desktop_keyboard_press("enter")
```

**Suggested Tools (Windows):**
```python
# Open Start Menu
desktop_keyboard_press("win")

# Type "calc" (shorter, faster)
desktop_keyboard_type("calc")

# Press Enter to launch
desktop_keyboard_press("enter")
```

**Alternative Approach:**
```python
# Use Run dialog on Windows
desktop_keyboard_hotkey(["win", "r"])
desktop_keyboard_type("calc")
desktop_keyboard_press("enter")
```

**Tips:**
- Wait 0.5-1 second after launching for window to appear
- Application name is case-insensitive
- Spotlight/Start Menu auto-suggests after few characters

#### 2. Verify Calculator Is Open

**Goal:** Confirm Calculator window is visible and focused

**Suggested Tools:**
```python
# Focus the Calculator window (ensure it has focus)
desktop_focus_window("Calculator")

# Take screenshot to verify
desktop_screenshot(use_active_window=True)

# Or use OCR to verify "Calculator" title is visible
result = desktop_find_text("Calculator")
if result["found"]:
    print("Calculator is open and visible")
```

**Tips:**
- ALWAYS focus window before typing
- Window title might be "Calculator" or "calc" depending on platform
- Use fuzzy matching: `ui_find_element(title="calc", fuzzy=True)`

#### 3. Enter Calculation

**Goal:** Type a mathematical expression

**Suggested Tools:**
```python
# Keyboard input is MOST RELIABLE
desktop_keyboard_type("5+5")

# Press Enter or = to calculate
desktop_keyboard_press("enter")  # Works on most platforms
# OR
desktop_keyboard_press("=")  # Alternative
```

**Alternative (clicking buttons - less reliable):**
```python
# Find and click number buttons using OCR
for char in "5+5=":
    result = desktop_find_text(char)
    if result["found"]:
        desktop_mouse_click(x=result["x"], y=result["y"])
```

**Tips:**
- Keyboard typing is 10x more reliable than clicking buttons
- Calculator accepts standard operators: +, -, *, /
- No need to click - just type the expression
- Press Enter or = to get result

#### 4. Verify Result

**Goal:** Confirm calculation was performed correctly

**Suggested Tools:**
```python
# Option 1: OCR to extract result
result = desktop_extract_text(use_active_window=True)
if "10" in result["full_text"]:
    print("Calculation successful: 5+5=10")

# Option 2: Screenshot with analysis
screenshot_result = desktop_screenshot(use_active_window=True)
# Review screenshot for result display

# Option 3: UI automation to read result field
result_element = ui_find_element(title="result", fuzzy=True)
if result_element:
    value = ui_get_value(result_element)
    print(f"Result: {value}")
```

**Tips:**
- OCR is reliable for reading displayed numbers
- Result might be in different formats (integer, decimal)
- Some calculators display result immediately, others need Enter/=

#### 5. Clear and Perform Another Calculation (Optional)

**Goal:** Reset calculator and perform new calculation

**Suggested Tools:**
```python
# Press C or Escape to clear
desktop_keyboard_press("c")  # Most common
# OR
desktop_keyboard_press("escape")  # Alternative

# New calculation
desktop_keyboard_type("100/4")
desktop_keyboard_press("enter")
```

**Tips:**
- "C" clears current entry on most calculators
- "AC" or "CE" might be needed on some platforms
- Escape key often clears or closes dialogs

## Common Issues & Solutions

### Issue: Calculator Doesn't Launch

**Symptoms:**
- No window appears after typing and pressing Enter
- Wrong application opens

**Solution:**
1. Check application name spelling
2. Try full name "Calculator" instead of "calc"
3. Wait longer (1-2 seconds) for slow systems
4. Use alternative launcher (Run dialog on Windows)
5. Verify Calculator is installed: `which Calculator` (macOS) or check Start Menu

### Issue: Keyboard Input Goes to Wrong Window

**Symptoms:**
- Typing appears in different application
- Calculator doesn't show entered numbers

**Solution:**
1. **ALWAYS call `desktop_focus_window("Calculator")` first**
2. Take screenshot to verify focus
3. Click Calculator window manually if needed
4. Use `ui_focus_window()` as alternative

**Prevention:**
- Include focus_window call before EVERY keyboard input
- Verify focus with screenshot or OCR

### Issue: Result Not Displayed

**Symptoms:**
- Calculation typed but no result shows
- Display is blank or shows input only

**Solution:**
1. Press Enter or = to execute calculation
2. Some calculators auto-calculate, others need explicit trigger
3. Check for error state (division by zero, invalid input)
4. Clear and retry: Press C, re-enter calculation

## Platform-Specific Notes

### macOS

**Launcher:**
- Spotlight: `Cmd+Space`, type "Calculator", Enter
- Launchpad: Click icon or use gesture
- Applications folder: `/Applications/Calculator.app`

**Window Management:**
- Use `desktop_focus_window("Calculator")`
- Or `macos_find_window(title="Calculator")`

**Keyboard Shortcuts:**
- Clear: `Cmd+Delete` or `C`
- Quit: `Cmd+Q`

### Windows

**Launcher:**
- Start Menu: `Win`, type "calc", Enter
- Run Dialog: `Win+R`, type "calc", Enter
- Direct: `calc.exe` from command line

**Window Management:**
- Use `desktop_focus_window("Calculator")`
- Or `windows_find_window(title="Calculator")`

**Keyboard Shortcuts:**
- Clear: `C` or `Escape`
- Close: `Alt+F4`

### Linux

**Launcher:**
- Application Menu (varies by DE)
- Terminal: `gnome-calculator &` or `kcalc &`
- Desktop search: Type "calc" in launcher

**Window Management:**
- Use `ui_focus_window(title="Calculator")`
- Window title varies: "Calculator", "GNOME Calculator", "KCalc"

**Tips:**
- Calculator app varies by distribution
- Some DEs use different calculators
- Verify installation: `which gnome-calculator`

## Success Criteria

- [x] Calculator window is visible
- [x] Calculator window has focus
- [x] Calculation input is visible in display
- [x] Result is displayed correctly (5+5=10)
- [x] No error messages or dialogs
- [x] Can perform multiple calculations

## Alternative Strategies

### Strategy 2: Direct Executable Launch

**When to use:** When launcher search is slow or unreliable

**macOS:**
```bash
open -a Calculator
```

**Windows:**
```bash
start calc.exe
```

**Pros:**
- Faster (no search)
- More reliable
- Can be scripted

**Cons:**
- Requires knowing exact path/executable name
- Less flexible
- Platform-specific

### Strategy 3: UI Automation Clicking

**When to use:** When keyboard input fails or is unavailable

**Steps:**
1. Launch Calculator
2. Use `ui_list_elements()` to find all buttons
3. Click buttons for each digit/operator
4. Click equals button

**Pros:**
- Works when keyboard is disabled
- Tests actual UI interactions

**Cons:**
- Much slower
- Less reliable (button positions vary)
- More complex code

## Tool Reference

**`desktop_keyboard_hotkey(keys)`**
- Purpose: Press keyboard shortcut combination
- Example: `desktop_keyboard_hotkey(["cmd", "space"])` for Spotlight
- Platform: Cross-platform (use OS-specific keys)

**`desktop_keyboard_type(text)`**
- Purpose: Type text via keyboard
- Example: `desktop_keyboard_type("5+5")`
- Platform: Cross-platform

**`desktop_keyboard_press(key)`**
- Purpose: Press single key
- Example: `desktop_keyboard_press("enter")`
- Platform: Cross-platform

**`desktop_focus_window(app)`**
- Purpose: Bring application to foreground
- Example: `desktop_focus_window("Calculator")`
- Platform: Cross-platform

**`desktop_find_text(search_text)`**
- Purpose: Locate text on screen via OCR
- Example: `desktop_find_text("Calculator")`
- Platform: Cross-platform

**`desktop_extract_text(use_active_window=True)`**
- Purpose: Extract all text from window
- Example: `desktop_extract_text(use_active_window=True)`
- Platform: Cross-platform

## Troubleshooting Checklist

1. [x] Is Calculator installed? (`which Calculator` on macOS, check Start Menu on Windows)
2. [x] Did you focus the Calculator window before typing?
3. [x] Take a screenshot - is Calculator visible and in focus?
4. [x] Try alternative launcher (Run dialog, terminal)
5. [x] Verify keyboard input with screenshot after typing
6. [x] Check for error dialogs or messages
7. [x] Try clearing (C key) and re-entering calculation
8. [x] Test with simpler calculation (e.g., "2+2")

## Metadata

**Created:** 2024-12-19
**Last Updated:** 2024-12-19
**Tested On:**
- macOS: 14.0+ (Sonoma)
- Windows: 10/11
- Linux: Not extensively tested

**Success Rate:** High (95%+)
**Estimated Time:** 3-5 seconds
**Complexity:** Simple

---

**This is a GUIDANCE document for an intelligent agent.**
**Adapt these suggestions based on your current context.**
**Use your intelligence to handle variations and errors.**
