# Connexus Element Tree Debugging Scripts

## 🎯 Quick Start

### Step 1: Open Connexus
```powershell
# 1. Launch Connexus.exe
# 2. Log in completely
# 3. Click on the Connexus window to make it active (foreground)
```

### Step 2: Run Full Tree Analysis
```powershell
python scripts/debug_connexus_tree.py
```

**This will:**
- Walk the entire UI tree
- Show statistics about elements
- Export `connexus_tree_YYYYMMDD_HHMMSS.json`
- Display visual tree in console
- List all elements with AutomationId

### Step 3: Analyze Results

Look for this in the output:
```
🎯 Elements WITH AutomationId (67):
  Button          AutomationId: 'SubmitButton'
                  Name: 'Submit'
  Edit            AutomationId: 'UsernameField'
                  Name: 'Username'
  ...
```

These are the elements your gui-cub agent CAN find!

### Step 4: Quick Testing
```powershell
python scripts/debug_connexus_quick.py

# Then choose option 4: "List ALL elements with AutomationId"
```

---

## 📚 Scripts Included

| Script | Purpose | Use When |
|--------|---------|----------|
| **debug_connexus_tree.py** | Deep tree walker with JSON export | First-time debugging, understanding structure |
| **debug_connexus_quick.py** | Fast interactive element finder | Testing specific elements, quick iteration |
| **CONNEXUS_DEBUG_PROMPT.md** | Complete guide with troubleshooting | Reference, common issues |

---

## 🔍 What You'll Learn

### From debug_connexus_tree.py:
- Total elements in the UI tree
- How many have AutomationId (these are findable!)
- Complete hierarchy (parent-child relationships)
- All properties (Name, ClassName, ControlType, etc.)
- Where elements are located (BoundingRectangle)

### From debug_connexus_quick.py:
- Search by AutomationId, Name, or Control Type
- Test if specific elements exist
- Verify element state (enabled, focusable, offscreen)
- Quick validation during development

---

## 💡 Key Insights

### AutomationId is King 👑

Elements WITH AutomationId are the most reliable to find:
```python
# In gui-cub agent:
"Click the button with AutomationId 'SubmitButton'"
```

### Name is Second Best 🥈

If no AutomationId, use Name:
```python
"Click the button named 'Submit'"
```

### ClassName + ControlType is Last Resort 🥉

Least reliable but sometimes works:
```python
"Click the Button with ClassName 'StandardButton'"
```

---

## ⚠️ Troubleshooting

### "No elements found!"
→ Make sure Connexus window is in foreground (click on it)

### "Found 0 elements with AutomationId"
→ The app might not use AutomationIds (check Name/ClassName instead)

### "Element exists but agent can't find it"
→ Check if `is_offscreen: true` or `is_enabled: false` in the JSON

### "JSON file is huge!"
→ Normal! Complex UIs have 1000+ elements

---

## 📦 Dependencies

Both scripts require:
```powershell
pip install comtypes
```

---

## 📝 Example Output

### Tree Walker Statistics
```
📊 ELEMENT TREE STATISTICS

Total elements: 482
Max depth: 12

Elements WITH AutomationId: 67 (13.9%)
Elements WITH Name: 234 (48.5%)
Elements WITH ClassName: 412 (85.5%)

By Control Type:
  Button                    89 (18.5%)
  Text                      67 (13.9%)
  Pane                      54 (11.2%)
  Edit                      23 ( 4.8%)
  ...
```

### Quick Finder Search
```
Choice: 1
Enter AutomationId: SubmitButton

✅ Found 1 match(es):

[0] 🎯 Button
   Name: Submit
   AutomationId: SubmitButton
   ClassName: Button
   Bounds: (450,320) 120x35
   Status: ✅ Enabled, ⌨️ Focusable
```

---

## 🎯 Success Checklist

- [ ] Run tree walker successfully
- [ ] Got JSON export file
- [ ] Statistics show >0 elements
- [ ] Found elements with AutomationId
- [ ] Can search by AutomationId in quick finder
- [ ] Verified element properties (enabled, not offscreen)

---

**Created by Doc 🐶 | Part of code-puppy toolkit**

For full details, see: **CONNEXUS_DEBUG_PROMPT.md**
