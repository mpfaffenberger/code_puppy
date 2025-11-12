# Connexus UI Automation Debug Guide

## 🐞 Problem

The `gui-cub` agent is having trouble finding elements in Connexus.exe even though you know AutomationIDs exist on the UI. These scripts help you debug the element tree structure to understand what's going on.

## 🛠️ Scripts Available

### 1. **debug_connexus_tree.py** - Deep Tree Walker

**Purpose:** Walk the ENTIRE UI Automation element tree and export comprehensive data.

**What it does:**
- Walks every single element in the tree
- Shows full hierarchy with parent-child relationships
- Exports detailed JSON file with ALL properties
- Highlights elements with AutomationId
- Shows statistics about element quality

**When to use:** 
- First-time debugging
- Understanding overall structure
- Finding all available AutomationIds
- Analyzing element properties in detail

**Usage:**
```powershell
# 1. Open Connexus.exe and log in
# 2. Make sure Connexus window is in the foreground (click on it)
# 3. Run:
python scripts/debug_connexus_tree.py

# Output:
#   - Visual tree in console
#   - connexus_tree_YYYYMMDD_HHMMSS.json (detailed export)
```

**Expected output:**
```
📊 ELEMENT TREE STATISTICS

Total elements: 482
Max depth: 12

Elements WITH AutomationId: 67 (13.9%)
Elements WITH Name: 234 (48.5%)

By Control Type:
  Button                    89
  Text                      67
  Pane                      54
  ...
```

---

### 2. **debug_connexus_quick.py** - Interactive Finder

**Purpose:** Quickly search and test specific elements without walking the entire tree.

**What it does:**
- Search by AutomationId, Name, or Control Type
- Show matching elements immediately
- List all elements with AutomationIds
- Fast and lightweight (no tree walking)

**When to use:**
- You know what you're looking for
- Testing if a specific AutomationId exists
- Quick iteration during development
- Verifying element properties

**Usage:**
```powershell
# 1. Open Connexus.exe and log in
# 2. Make sure Connexus window is in the foreground
# 3. Run:
python scripts/debug_connexus_quick.py

# Interactive menu:
#   1. Find by AutomationId
#   2. Find by Name (partial match)
#   3. Find by Control Type
#   4. List ALL elements with AutomationId
#   5. Exit
```

**Example search:**
```
Choice: 1
Enter AutomationId: SubmitButton

🔎 Searching for AutomationId='SubmitButton'...

✅ Found 1 match(es):

[0] 🎯 Button
   Name: Submit
   AutomationId: SubmitButton
   ClassName: Button
   Bounds: (450,320) 120x35
   Status: ✅ Enabled, ⌨️ Focusable
```

---

## 🚀 Quick Start Workflow

### Step 1: Run Full Tree Analysis

```powershell
# Open Connexus and log in
python scripts/debug_connexus_tree.py
```

This gives you:
- `connexus_tree_YYYYMMDD_HHMMSS.json` - Full tree export
- Console output with statistics
- List of all elements WITH AutomationId

### Step 2: Analyze the JSON

Open the JSON file and look for:

```json
{
  "statistics": {
    "total_elements": 482,
    "with_automation_id": 67,
    "by_control_type": { ... }
  },
  "flat_elements": [
    {
      "depth": 3,
      "path": "root/Pane/Pane/Button[SubmitButton]",
      "properties": {
        "name": "Submit",
        "automation_id": "SubmitButton",  // 🎯 BINGO!
        "control_type": "Button",
        "class_name": "Button",
        "is_enabled": true,
        "bounding_rect": { ... }
      }
    }
  ]
}
```

**Search the JSON for:**
- `"automation_id"` to find all AutomationIds
- Specific button/field names you're looking for
- Control types (Button, Edit, ComboBox, etc.)

### Step 3: Test Specific Elements

```powershell
# Use quick finder to test
python scripts/debug_connexus_quick.py

# Option 4: List ALL elements with AutomationId
# This shows you exactly what's findable
```

### Step 4: Use Findings in gui-cub Agent

Once you know the AutomationId, you can use it in the agent:

```python
# In your gui-cub agent prompts:
"Click the button with AutomationId 'SubmitButton'"
"Type 'hello' in the field with AutomationId 'UsernameField'"
```

---

## 🔍 Common Issues & Solutions

### Issue: "No elements with AutomationId found!"

**Possible causes:**
1. **Wrong window focused** - Make sure Connexus is the active window
2. **UI framework doesn't set AutomationIds** - Some apps don't use them
3. **Elements are in a different tree** - Try child windows/dialogs

**Solution:**
```powershell
# Check what window you're capturing:
python scripts/debug_connexus_tree.py
# Look at the first line: "Found window: <name>"
# Make sure it says "Connexus" or similar
```

### Issue: "AutomationId exists but agent can't find it"

**Possible causes:**
1. **Element is offscreen** - Check `is_offscreen` property
2. **Element is disabled** - Check `is_enabled` property  
3. **Element is in a child window** - Check window hierarchy
4. **Timing issue** - Element loads after search

**Solution:**
```powershell
# Use quick finder to verify element state:
python scripts/debug_connexus_quick.py
# Search by AutomationId and check Status line
```

### Issue: "Found element but it's not interactable"

**Check these properties in the JSON:**
- `is_enabled: false` - Element is disabled
- `is_offscreen: true` - Element is not visible
- `is_keyboard_focusable: false` - Can't receive keyboard input
- `bounding_rect: null` - Element has no position

---

## 💡 Tips & Tricks

### 1. **Search the JSON efficiently**

```powershell
# On Windows (PowerShell):
Select-String -Path "connexus_tree_*.json" -Pattern '"automation_id": ".*"' | Select-Object -First 20

# On Linux/Mac:
grep -o '"automation_id": "[^"]*"' connexus_tree_*.json | head -20
```

### 2. **Find buttons specifically**

In the JSON, search for:
```json
"control_type": "Button"
```

Then look at the `automation_id` field for those elements.

### 3. **Understand the hierarchy**

Look at the `path` field:
```
root/Pane/Pane/Group/Button[SubmitButton]
       ^^^^ ^^^^ ^^^^^ ^^^^^^^^^^^^^^^^^^^
       Window -> Container -> Button
```

This shows:
- Element is 4 levels deep
- Inside nested Panes and a Group
- Has AutomationId "SubmitButton"

### 4. **Export filtered results**

The tree walker has interactive search at the end. Use it!

```
Want to search for specific elements? (y/n): y

Search by:
  1. Name contains
  2. AutomationId contains  ← Use this!
  3. Control type
  4. Done searching

Choice: 2
AutomationId contains: Submit

Found 3 matches:
  Button          AutomationId: 'SubmitButton'
  Button          AutomationId: 'SubmitDialogButton'
  Button          AutomationId: 'QuickSubmitButton'
```

---

## 📝 Reporting Issues to gui-cub Team

If you find that elements exist but the agent still can't find them, include:

1. **The JSON export** - Attach the `connexus_tree_*.json` file
2. **Element details** - Copy/paste the specific element from JSON:
   ```json
   {
     "path": "root/Pane/Button[TargetButton]",
     "properties": {
       "name": "Click Me",
       "automation_id": "TargetButton",
       "control_type": "Button",
       "is_enabled": true,
       "is_offscreen": false
     }
   }
   ```
3. **What you tried** - The exact command/prompt you gave the agent
4. **Error message** - What the agent returned

---

## 🧑‍💻 Developer Notes

### Script Dependencies

Both scripts require:
```powershell
pip install comtypes
```

The `comtypes` package provides Windows UI Automation bindings.

### Property IDs

For reference, these are the UI Automation property IDs used:
- `30005` - Name
- `30011` - AutomationId  
- `30003` - ControlType
- See full list: https://docs.microsoft.com/en-us/windows/win32/winauto/uiauto-automation-element-propids

### Control Type IDs

Mapped in `CONTROL_TYPE_MAP` dictionary:
- `50000` - Button
- `50004` - Edit
- `50003` - ComboBox
- etc.

See full list: https://docs.microsoft.com/en-us/windows/win32/winauto/uiauto-controltype-ids

---

## ✅ Success Criteria

You've successfully debugged the tree when:

1. **You can see elements** - Tree walker shows >0 elements
2. **You found AutomationIds** - Statistics show >0 with_automation_id
3. **You can search by AutomationId** - Quick finder returns matches
4. **Properties look correct** - Elements are enabled, not offscreen
5. **You have the JSON export** - For sharing/analysis

---

## 🐶 Need Help?

Ping Doc the Puppy in the code-puppy repo!

**Common questions:**
- "Tree walker found 0 elements" → Wrong window focused
- "No AutomationIds" → App might not use them (check ClassName/Name instead)  
- "Found element but can't click" → Check is_enabled and is_offscreen
- "JSON too large" → Normal! Connexus might have 1000+ elements

---

**Created by Doc 🐶 | May 2025**
