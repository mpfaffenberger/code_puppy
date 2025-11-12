# 🤝 Agent Handoff: Connexus Debug Scripts

## For: Windows Code-Puppy Agent

Dakota - Give this to your Windows agent to run on the Connexus box!

---

## 🎯 Mission

Debug why gui-cub agent can't find elements with AutomationIds in Connexus.exe by analyzing the complete UI Automation element tree.

---

## 🚀 FASTEST PATH (Recommended)

### Single Command:

**PowerShell:**
```powershell
.\scripts\run_connexus_debug.ps1
```

**Command Prompt:**
```cmd
scripts\run_connexus_debug.bat
```

### What It Does:
1. Checks/installs `comtypes` dependency
2. Waits 3 seconds for Connexus to be focused
3. Runs full tree analysis → exports `connexus_tree_debug.json`
4. Lists all elements with AutomationId
5. Shows summary report

### Expected Result:
```
[SUCCESS] Found elements with AutomationId!
[FILE] connexus_tree_debug.json
```

---

## 📋 Files Created for You

### Core Scripts (Updated for Automation):

1. **debug_connexus_tree.py** - Deep tree walker
   - ✅ **Now supports `--auto` mode** (no prompts!)
   - Usage: `python scripts/debug_connexus_tree.py --auto --output connexus_tree_debug.json`
   - Exports: Full JSON with all properties
   - Lines: 548 (under 600 limit)

2. **debug_connexus_quick.py** - Fast element finder
   - ✅ **Now supports command-line args** (no interaction!)
   - Usage: `python scripts/debug_connexus_quick.py --list-all-ids --max-results 50`
   - Can output JSON: `--json` flag
   - Lines: 329

### Automation Scripts (NEW!):

3. **run_connexus_debug.bat** - One-command batch script
   - Auto-installs comtypes
   - Runs both scripts in sequence
   - Clear success/failure messages

4. **run_connexus_debug.ps1** - One-command PowerShell
   - Same as batch but with colors
   - Better error handling

### Documentation:

5. **AGENT_PROMPT_CONNEXUS.md** - Full agent instructions
   - Step-by-step workflow
   - Command reference
   - Success criteria
   - Troubleshooting

6. **AGENT_QUICK_START.txt** - Copy-paste ready commands
   - One-pagers for quick execution
   - Expected output examples
   - Exit codes

7. **CONNEXUS_DEBUG_COMMANDS.txt** - Human-readable guide
   - For manual execution
   - Examples and tips

8. **README_CONNEXUS_DEBUG.md** - Quick reference
   - TL;DR version
   - Key insights

---

## 📝 What the Agent Should Report Back

### Minimum Required:

```
1. Exit Code: 0 (success) or 1 (failure)

2. Statistics:
   Total elements: XXX
   With AutomationId: XX (XX%)
   With Name: XX (XX%)

3. File Created:
   connexus_tree_debug.json (XXX KB)

4. Key Finding:
   [SUCCESS] Found XX elements with AutomationId
   OR
   [WARNING] No elements with AutomationId found
```

### Bonus (If Available):

```
5. Sample AutomationIds:
   - SubmitButton
   - UsernameField
   - LoginButton
   ...

6. Control Type Breakdown:
   Button: XX
   Edit: XX
   Pane: XX
   ...
```

---

## ⚠️ Critical Prerequisites

**Before running ANY script:**

1. ✅ Connexus.exe is **RUNNING**
2. ✅ Connexus.exe is **LOGGED IN**
3. ✅ Connexus window is **IN FOREGROUND** (active window)
   - Agent should click on Connexus window or use Windows API to bring to front
   - Wait 1-2 seconds after focusing
   - Then run script

---

## 🛠️ Command Reference for Agent

### Option 1: Automated Script (Easiest)
```powershell
# PowerShell
.\scripts\run_connexus_debug.ps1

# Batch
scripts\run_connexus_debug.bat
```

### Option 2: Manual Steps
```powershell
# Step 1: Install dependency
pip install comtypes

# Step 2: Full tree analysis
python scripts/debug_connexus_tree.py --auto --output connexus_tree_debug.json

# Step 3: List AutomationIds
python scripts/debug_connexus_quick.py --list-all-ids --max-results 50
```

### Option 3: JSON Output (For Parsing)
```powershell
# Get JSON output for programmatic parsing
python scripts/debug_connexus_quick.py --list-all-ids --json > connexus_ids.json
```

---

## 📊 Interpreting Results

### Good News Indicators:
```
✅ statistics.with_automation_id > 10
   → gui-cub CAN find elements by AutomationId!

✅ Found elements: Button, Edit, ComboBox
   → Interactive elements are present

✅ is_enabled: true, is_offscreen: false
   → Elements are interactable
```

### Problem Indicators:
```
❌ statistics.with_automation_id = 0
   → Connexus doesn't use AutomationIds
   → Solution: Use Name or ClassName properties

❌ total_elements < 50
   → Wrong window captured
   → Solution: Ensure Connexus is foreground

⚠️ is_enabled: false OR is_offscreen: true
   → Element exists but can't be clicked
   → May need navigation/scrolling
```

---

## 🐞 Troubleshooting

### Error: "Could not get foreground window"
```powershell
# Solution: Focus Connexus window programmatically
# Example (PowerShell):
$wshell = New-Object -ComObject wscript.shell
$wshell.AppActivate("Connexus")
Start-Sleep -Seconds 2
python scripts/debug_connexus_tree.py --auto
```

### Error: "No module named 'comtypes'"
```powershell
pip install comtypes
```

### Warning: "Tree walker running for 2+ minutes"
```
# This is NORMAL for complex UIs
# Connexus might have 1000+ elements
# Let it complete - the data is worth it
```

### Error: "Total elements: 0"
```
# Problem: Wrong window focused
# Solution:
# 1. Click on Connexus window
# 2. Wait 2 seconds
# 3. Re-run script
```

---

## 💾 Files Generated

### Primary Output:
- **connexus_tree_debug.json** - Complete element tree
  - Full hierarchy
  - All properties (AutomationId, Name, ClassName, etc.)
  - Statistics
  - Bounding rectangles
  - Enable/offscreen state

### Optional Output:
- **connexus_ids.json** - JSON list of AutomationIds (if using `--json`)

---

## ✅ Success Criteria

### Script Execution:
- ✅ Exit code: 0
- ✅ No Python errors/exceptions
- ✅ File created: connexus_tree_debug.json

### Data Quality:
- ✅ statistics.total_elements > 100
- ✅ JSON file size > 10 KB
- ✅ Multiple control types found

### Findings:
- ✅ statistics.with_automation_id > 0 **OR**
- ✅ statistics.with_name > 0 **OR**
- ✅ statistics.with_class_name > 0

At least ONE identifier method must be available!

---

## 💬 Sample Agent Response

```
✅ CONNEXUS DEBUG COMPLETE

Execution:
- Script: run_connexus_debug.ps1
- Exit Code: 0 (success)
- Duration: 47 seconds

Statistics:
- Total elements: 482
- With AutomationId: 67 (13.9%)
- With Name: 234 (48.5%)
- Max depth: 12

Control Types:
- Button: 89
- Edit: 23
- Pane: 54
- Text: 67

Sample AutomationIds Found:
- SubmitButton
- UsernameField
- PasswordField
- LoginButton
- CancelButton

File Generated:
- connexus_tree_debug.json (156.3 KB)

Recommendation:
✅ gui-cub CAN use AutomationId to find 67 elements!
   Use AutomationId as primary identifier.
   Fallback to Name for remaining elements.

Next Steps:
- Use AutomationId-based element finding in gui-cub
- Example: "Click the button with AutomationId 'SubmitButton'"
```

---

## 📦 Deliverables

The agent should return:

1. **connexus_tree_debug.json** - Attach/upload this file
2. **Statistics summary** - Copy from console output
3. **Sample AutomationIds** - List first 10-20
4. **Success/failure status** - Based on exit code
5. **Recommendation** - Use AutomationId vs Name vs ClassName

---

## 🔗 Quick Links to Docs

- **Full Agent Instructions:** `AGENT_PROMPT_CONNEXUS.md`
- **Quick Start Commands:** `AGENT_QUICK_START.txt`
- **Copy-Paste Guide:** `CONNEXUS_DEBUG_COMMANDS.txt`
- **Human README:** `README_CONNEXUS_DEBUG.md`

---

## 💡 Pro Tips

1. **Use the automated scripts** (`run_connexus_debug.bat/ps1`) - they handle everything
2. **Always verify Connexus is foreground** before running
3. **Wait for tree walker to complete** - can take 30-120 seconds
4. **Attach the JSON file** in response - it's the most valuable output
5. **If no AutomationIds found** - check Name and ClassName properties in JSON

---

## 🐶 Created By

Doc the Puppy | May 2025 | code-puppy toolkit

**Files created in this session:**
- debug_connexus_tree.py (updated with --auto mode)
- debug_connexus_quick.py (updated with CLI args)
- run_connexus_debug.bat (new)
- run_connexus_debug.ps1 (new)
- AGENT_PROMPT_CONNEXUS.md (new)
- AGENT_QUICK_START.txt (new)
- CONNEXUS_DEBUG_COMMANDS.txt (new)
- README_CONNEXUS_DEBUG.md (existing, for reference)
- AGENT_HANDOFF.md (this file)

**Total:** 9 files ready for Windows agent

---

**🚀 Agent: Run `scripts\run_connexus_debug.ps1` and report back!**
