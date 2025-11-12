# Agent Instructions: Connexus UI Automation Debug

## 🤖 For: Windows Code-Puppy Agent

**Objective:** Debug the UI Automation element tree for Connexus.exe to identify why gui-cub agent cannot find elements with AutomationIds.

---

## 📍 Prerequisites Check

Before running scripts, verify:

1. **Connexus.exe is running and logged in**
2. **Connexus window is in foreground** (bring to front)
3. **comtypes is installed:**
   ```powershell
   pip install comtypes
   ```

---

## 🚀 Step 1: Full Tree Analysis (AUTOMATIC MODE)

### Command:
```powershell
python scripts/debug_connexus_tree.py --auto --output connexus_tree_debug.json
```

### What This Does:
- Walks ENTIRE UI Automation element tree
- Exports detailed JSON: `connexus_tree_debug.json`
- Shows statistics about elements
- Lists all elements with AutomationId
- NO interactive prompts (fully automatic)

### Expected Output:
```
🐶 Doc the Puppy - Connexus UI Automation Element Tree Debugger
🤖 AUTOMATIC MODE - Running immediately...
🔍 Initializing UI Automation...
📡 Getting foreground window...
✅ Found window: Connexus
🚶 Walking element tree (this may take a minute)...

📊 ELEMENT TREE STATISTICS
Total elements: XXX
Max depth: XX

Elements WITH AutomationId: XX (XX%)
Elements WITH Name: XX (XX%)
Elements WITH ClassName: XX (XX%)

By Control Type:
  Button                    XX
  Edit                      XX
  ...

🎯 Elements WITH AutomationId (XX):
  Button          AutomationId: 'SubmitButton'
                  Name: 'Submit'
  ...

💾 Exported to: connexus_tree_debug.json

✅ COMPLETE!
```

### Success Criteria:
- Exit code: `0` (success)
- File created: `connexus_tree_debug.json`
- Statistics show `total_elements > 0`

### If Failed:
- Exit code: `1` (error)
- Check error message in output
- Verify Connexus is in foreground
- Verify comtypes is installed

---

## 🚀 Step 2: List All AutomationIds (QUICK CHECK)

### Command:
```powershell
python scripts/debug_connexus_quick.py --list-all-ids --max-results 100
```

### What This Does:
- Lists ALL elements that have AutomationId property
- Shows up to 100 results
- NO interactive prompts
- Fast execution (no tree walking)

### Expected Output:
```
🤖 NON-INTERACTIVE MODE - Running immediately...
✅ Connected to UI Automation

🔎 Listing ALL elements with AutomationId...

✅ Found XX elements with AutomationId (showing max 100):

[0] 🎯 Button
   Name: Submit
   AutomationId: SubmitButton
   ClassName: Button
   Bounds: (450,320) 120x35
   Status: ✅ Enabled, ⌨️ Focusable

[1] 🎯 Edit
   Name: Username
   AutomationId: UsernameField
   ...

📋 By Control Type:
   Button                 XX
   Edit                   XX
   ...
```

### Success Criteria:
- Exit code: `0` (found elements)
- Shows list of elements with AutomationId

### If No Elements Found:
- Exit code: `1`
- Output: "❌ No elements with AutomationId found!"
- **This indicates:** Connexus UI does NOT use AutomationIds
- **Action:** Check JSON for `name` and `class_name` properties instead

---

## 🚀 Step 3: Search Specific Element (OPTIONAL)

### Find by AutomationId:
```powershell
python scripts/debug_connexus_quick.py --auto-id "SubmitButton"
```

### Find by Name:
```powershell
python scripts/debug_connexus_quick.py --name "Submit" --max-results 20
```

### Find by Control Type:
```powershell
python scripts/debug_connexus_quick.py --control-type "Button" --max-results 30
```

### JSON Output (for parsing):
```powershell
python scripts/debug_connexus_quick.py --list-all-ids --json
```

Outputs:
```json
{
  "success": true,
  "count": 67,
  "results": [
    {
      "name": "Submit",
      "automation_id": "SubmitButton",
      "control_type": "Button",
      "is_enabled": true,
      "is_offscreen": false,
      "is_keyboard_focusable": true,
      "bounds": "(450,320) 120x35"
    }
  ],
  "total_found": 67
}
```

---

## 📊 Analyzing Results

### Parse the JSON Export:

The `connexus_tree_debug.json` file contains:

```json
{
  "timestamp": "2025-05-XX...",
  "statistics": {
    "total_elements": 482,
    "with_automation_id": 67,
    "with_name": 234,
    "by_control_type": { ... }
  },
  "flat_elements": [
    {
      "depth": 3,
      "path": "root/Pane/Pane/Button[SubmitButton]",
      "properties": {
        "name": "Submit",
        "automation_id": "SubmitButton",
        "control_type": "Button",
        "class_name": "Button",
        "is_enabled": true,
        "is_offscreen": false,
        "is_keyboard_focusable": true,
        "bounding_rect": {
          "left": 450,
          "top": 320,
          "width": 120,
          "height": 35
        }
      }
    }
  ]
}
```

### Key Fields to Check:

1. **`statistics.with_automation_id`**
   - If `> 0`: Elements have AutomationIds ✅
   - If `= 0`: No AutomationIds ❌ (use Name/ClassName instead)

2. **`flat_elements[].properties.automation_id`**
   - Non-empty = This element is findable by AutomationId

3. **`flat_elements[].properties.is_enabled`**
   - `true` = Element can be interacted with
   - `false` = Element is disabled (can't click)

4. **`flat_elements[].properties.is_offscreen`**
   - `false` = Element is visible
   - `true` = Element is not visible (can't click)

5. **`flat_elements[].properties.control_type`**
   - Button, Edit, ComboBox = Interactive elements
   - Text, Pane, Group = Container/static elements

---

## ✅ Success Indicators

### Good Signs:
```
✅ statistics.total_elements > 100
✅ statistics.with_automation_id > 10
✅ Found elements with control_type: "Button", "Edit"
✅ Elements have is_enabled: true
✅ Elements have is_offscreen: false
```

### Problem Signs:
```
❌ statistics.with_automation_id = 0
   → Use Name or ClassName properties instead

❌ Elements have is_enabled: false
   → Element is disabled, can't interact

❌ Elements have is_offscreen: true
   → Element not visible, need to scroll/navigate

❌ statistics.total_elements < 50
   → Wrong window captured (not Connexus)
```

---

## 📝 Report Back

### Include in Your Response:

1. **Statistics from tree walker:**
   ```
   Total elements: XXX
   With AutomationId: XX (XX%)
   With Name: XX (XX%)
   ```

2. **Sample elements with AutomationId:**
   ```
   Button | AutomationId: 'SubmitButton' | Name: 'Submit'
   Edit   | AutomationId: 'UsernameField' | Name: 'Username'
   ...
   ```

3. **File location:**
   ```
   JSON export: connexus_tree_debug.json (XX KB)
   ```

4. **Exit code:**
   ```
   Tree walker: exit code 0 (success)
   Quick finder: exit code 0 (found XX elements)
   ```

5. **Key finding:**
   ```
   ✅ Found XX elements with AutomationId - gui-cub can use these!
   OR
   ❌ No elements with AutomationId - gui-cub should use Name/ClassName
   ```

---

## 🐞 Troubleshooting

### Error: "Could not get foreground window"
```powershell
# Solution: Bring Connexus to foreground
# Use Windows API or manually click on Connexus window
# Then re-run script
```

### Error: "No module named 'comtypes'"
```powershell
pip install comtypes
```

### Error: "No elements found (total_elements = 0)"
```powershell
# Check: Is Connexus actually in foreground?
# Try: Click on Connexus window, wait 2 seconds, then run script
```

### Warning: "Tree walker takes >2 minutes"
```
# This is normal for complex UIs with 1000+ elements
# Let it complete - the JSON export is worth the wait
```

---

## 🚀 Quick Command Reference

```powershell
# Full tree analysis (MAIN COMMAND)
python scripts/debug_connexus_tree.py --auto --output connexus_tree_debug.json

# List all AutomationIds
python scripts/debug_connexus_quick.py --list-all-ids --max-results 100

# Search specific element
python scripts/debug_connexus_quick.py --auto-id "SubmitButton"
python scripts/debug_connexus_quick.py --name "Submit"
python scripts/debug_connexus_quick.py --control-type "Button"

# JSON output (for parsing)
python scripts/debug_connexus_quick.py --list-all-ids --json
```

---

## 💡 Expected Timeline

- **Step 1 (Tree walker):** 30-120 seconds (depends on UI complexity)
- **Step 2 (Quick finder):** 5-15 seconds
- **Step 3 (Specific search):** 2-5 seconds

---

**Created by Doc 🐶 | For Windows Code-Puppy Agent**
