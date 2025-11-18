# GUI-Cub Element Tree Test Prompt

This prompt exercises the element tree exploration capabilities of the GUI-Cub agent.

---

## Test Prompt (Copy & Paste)

```
I want to test your element tree exploration capabilities. Please help me explore and interact with the Calculator app using the accessibility element tree.

Here's what I'd like you to do:

1. **Launch & Focus Calculator**
   - Open the Calculator application (use macOS Spotlight or Windows Start Menu)
   - Make sure it's focused and visible
   - Take a screenshot to confirm it's ready

2. **Explore the Element Tree**
   - Use the accessibility API to list all elements in the Calculator window
   - Show me what types of elements are available (buttons, text fields, etc.)
   - Explain what you found - how many buttons, what their roles are, etc.

3. **Find Specific Elements**
   - Find the "7" button using the element tree
   - Find the "+" (plus/add) button
   - Find the "=" (equals) button
   - Show me the exact coordinates and properties for each

4. **Perform a Calculation Using Element Tree**
   - Click the "7" button using accessibility API
   - Click the "+" button
   - Click the "3" button  
   - Click the "=" button
   - Take a screenshot to verify the result shows "10"

5. **Compare Approaches**
   - Briefly explain why using the element tree (accessibility API) is better than OCR or VQA for this task
   - What are the advantages of pixel-perfect element coordinates?

**Important Requirements:**
- Use `desktop_list_accessible_elements()` (macOS) or `windows_list_elements_in_application()` (Windows) to explore the element tree
- Use `desktop_find_accessible_element()` (macOS) or `windows_click_element()` (Windows) for clicking
- Take screenshots to verify each major step
- Share your reasoning as you go

Let's see how well the element tree works! 🐻
```

---

## What This Tests

### Core Functionality
- ✅ **Window focusing** - Ensuring target app is active
- ✅ **Element tree exploration** - Listing all accessible elements
- ✅ **Element search** - Finding specific elements by role/title
- ✅ **Coordinate extraction** - Getting pixel-perfect click positions
- ✅ **Element interaction** - Clicking via accessibility API
- ✅ **Screenshot verification** - Confirming actions worked

### Platform Coverage
- **macOS:** `desktop_list_accessible_elements()`, `desktop_find_accessible_element()`, `desktop_click_accessible_element()`
- **Windows:** `windows_list_elements_in_application()`, `windows_click_element()`

### Skills Demonstrated
- Element tree traversal and filtering
- Fuzzy matching for element names
- Tool priority (accessibility API before OCR/VQA)
- Verification workflow (screenshot after actions)
- Reasoning about tool selection

---

## Expected Agent Behavior

### Good Response Pattern:

1. **Share reasoning** about approach
2. **Focus Calculator** using appropriate tool
3. **Take screenshot** to verify it's visible
4. **List elements** using element tree API
5. **Explain findings** ("Found 20 buttons, 1 text field, roles: AXButton, AXTextField...")
6. **Find specific elements** with fuzzy matching
7. **Show coordinates** for each found element
8. **Click elements** using accessibility API (NOT mouse coordinates)
9. **Screenshot verification** after calculation
10. **Explain advantages** of accessibility API over visual methods

### Red Flags (Agent Mistakes):

❌ Using OCR before trying element tree
❌ Using VQA for simple button clicks
❌ Not taking screenshots to verify actions
❌ Not focusing the window first
❌ Using mouse coordinates instead of accessibility API
❌ Not sharing reasoning along the way

---

## Advanced Variations

### Variation 1: Multi-Window App (More Complex)
```
Explore the element tree of a multi-window application like Outlook or Teams.
Show me how you'd find elements across multiple windows of the same app.
Use windows_list_elements_in_application() on Windows.
```

### Variation 2: Fuzzy Matching Test
```
Find the Calculator's "Clear" button using fuzzy matching.
Try searching with these variations:
- "clear"
- "C" (the actual button text)
- "reset"
Show me which fuzzy matches work and their confidence scores.
```

### Variation 3: Element Tree vs OCR Comparison
```
Compare two approaches to clicking the "5" button:
1. Use element tree (accessibility API)
2. Use OCR to find "5" text

Time both approaches and show me the accuracy/speed differences.
Explain when you'd use each method.
```

### Variation 4: Deep Element Tree (Nested UI)
```
Open System Preferences/Settings and explore a deeply nested UI.
Show me how the element tree represents hierarchical elements.
Find a specific toggle or checkbox 3+ levels deep in the tree.
```

---

## Success Criteria

### ✅ Agent successfully:
- Focuses Calculator without errors
- Lists accessible elements and explains structure
- Finds specific elements by role/title with fuzzy matching
- Extracts pixel-perfect coordinates
- Clicks elements using accessibility API (not mouse)
- Verifies calculation result (7+3=10) with screenshot
- Explains advantages of element tree over OCR/VQA
- Shares reasoning throughout the process

### ⚠️ Acceptable edge cases:
- Windows Calculator might have different element structure than macOS
- Element tree might show more elements than expected (include hidden/disabled)
- Fuzzy matching might find multiple candidates (agent should pick best match)

### ❌ Failure modes:
- Agent falls back to OCR without trying element tree first
- Agent can't list accessible elements (accessibility API broken)
- Agent uses VQA for simple button clicks
- Agent doesn't verify actions with screenshots
- Calculation result is wrong (clicking wrong elements)

---

## Platform-Specific Notes

### macOS
- Uses `atomacos` library (PyObjC wrapper)
- Element roles: `AXButton`, `AXTextField`, `AXStaticText`, etc.
- Tools: `desktop_list_accessible_elements()`, `desktop_find_accessible_element()`, `desktop_click_accessible_element()`
- Calculator app name: "Calculator"

### Windows  
- Uses UI Automation (UIA) via `pywinauto`/`comtypes`
- Element roles: `Button`, `Edit`, `Text`, `Window`, etc.
- Tools: `windows_list_elements_in_application()`, `windows_click_element()`, `ui_focus_window()`
- Calculator app pattern: ".*Calculator.*"

---

## Usage Instructions

1. **Switch to GUI-Cub agent:**
   ```
   /agent gui-cub
   ```

2. **Copy the test prompt above** (the section marked "Test Prompt")

3. **Paste and run**

4. **Observe agent behavior:**
   - Does it use element tree first?
   - Does it share reasoning?
   - Does it verify with screenshots?
   - Does it successfully complete the calculation?

5. **Try variations** to test edge cases and advanced features

---

## Debugging Tips

If the test fails:

### Agent can't list elements:
- Check if accessibility permissions are granted (macOS: System Preferences > Security & Privacy > Accessibility)
- Check if `atomacos` (macOS) or `pywinauto` (Windows) is installed
- Try with a different app (TextEdit, Notepad, etc.)

### Agent uses OCR instead of element tree:
- Remind agent: "Use the accessibility API element tree, not OCR"
- Check agent prompt - should prioritize Accessibility > OCR > VQA

### Element search finds nothing:
- Check exact button labels in Calculator (might be "C" not "Clear")
- Try fuzzy matching with lower threshold: `fuzzy_threshold=0.5`
- Use `_internal=True` to see ALL elements without compaction

### Clicks don't work:
- Verify Calculator is focused BEFORE clicking
- Check if coordinates are correct (use `desktop_highlight_click_target()`)
- Try different element (some might be non-clickable/disabled)

---

**Ready to test!** 🐻✨
