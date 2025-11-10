# Windows Element Tree Testing Guide

**Purpose:** Test accessibility/element tree functionality on Windows to compare with macOS results.

**Time Required:** 15-20 minutes

---

## Prerequisites

1. **Windows Machine** (Windows 10/11)
2. **Code-Puppy Installed:**
   ```powershell
   pip install code-puppy
   # OR from source
   git clone https://github.com/your-org/code-puppy
   cd code-puppy
   uv sync
   ```

3. **Test Applications:**
   - Calculator (built-in)
   - Notepad (built-in)
   - File Explorer (built-in)

---

## Quick Start

### 1. Navigate to Code-Puppy Directory
```powershell
cd path\to\code-puppy
```

### 2. Run Test Script
```powershell
# Make sure Calculator is open and focused
calculator

# Run the test
python scripts\test_element_tree.py
```

---

## Test 1: Calculator App

### Step 1: Open Calculator
```powershell
calculator
```

### Step 2: Run Element Tree Tests
```powershell
python scripts\test_element_tree.py
```

### Expected Results:

#### TEST 1: List All Buttons
```
Success: True
Total buttons: 20-30 (number buttons, operations, etc.)

Button details:
  [0] type='Button', name='Zero'
  [1] type='Button', name='One'
  [2] type='Button', name='Two'
  ...
```

**✅ GOOD:** Buttons have clear names ("Zero", "One", "Plus", etc.)  
**❌ BAD:** Most buttons have empty names

#### TEST 2: Element Compaction
```
Compact result:
  Elements returned: 20
  Filtered count: 20

Compacted elements:
  [0] Button: 'Plus' (relevance=0.7)
  [1] Button: 'Minus' (relevance=0.7)
  [2] Button: 'Equals' (relevance=0.7)
  ...
```

**✅ GOOD:** Returns 20 relevant elements  
**❌ BAD:** Returns 0 elements (compaction broken!)

#### TEST 3: Find Element 'Plus'
```
Success: True
Found: True

Match details:
  Role: Button
  Title: Plus
  X: 150
  Y: 300
```

**✅ GOOD:** Finds the Plus button  
**❌ BAD:** Not found

#### TEST 4: Description Fallback
```
Searching for 'equals' button...
✅ SUCCESS! Found button
   Role: Button
   Title: 'Equals'
   Coords: (200, 400)
```

**✅ GOOD:** All buttons found  
**❌ BAD:** Buttons not found (fallback not working)

---

## Test 2: Notepad App

### Step 1: Open Notepad
```powershell
notepad
```

### Step 2: Focus Notepad Window
Click on the Notepad window to make it active.

### Step 3: Run Tests
```powershell
python scripts\test_element_tree.py
```

### Expected Results:

#### Buttons Found:
```
Button details:
  [0] type='Button', name='Close'
  [1] type='Button', name='Minimize'
  [2] type='Button', name='Maximize'
  [3] type='MenuItem', name='File'
  [4] type='MenuItem', name='Edit'
  ...
```

#### Text Field:
```
[N] type='Edit', name='Text Editor'
    automation_id: '15'  ← Unique identifier!
```

**Key Points:**
- Menu items (File, Edit, Format, View, Help)
- Window control buttons (Close, Minimize, Maximize)
- Text editor field with automation_id

---

## Test 3: File Explorer

### Step 1: Open File Explorer
```powershell
explorer
```

### Step 2: Navigate to C:\
```powershell
explorer C:\
```

### Step 3: Run Tests
```powershell
python scripts\test_element_tree.py
```

### Expected Results:

#### Buttons Found:
```
Button details:
  [0] type='Button', name='Back', description='back'
  [1] type='Button', name='Forward', description='forward'
  [2] type='Button', name='Up one level'
  [3] type='Button', name='Search'
  ...
```

**Compare with macOS Finder:**
- macOS: title=None, description="back"  
- Windows: name="Back", description="back"

**Windows should have BETTER labels!**

---

## Test 4: Automation ID Testing (Windows-Specific)

### Test Exact Match by AutomationId

```python
# Create test script: test_automation_id.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from code_puppy.tools.gui_cub.windows_automation import find_element

# Open Calculator first!
print("Testing AutomationId exact match...")

# Try to find element by automation_id
result = find_element(
    name="Zero",  # Number 0 button
    # automation_id might be something like "num0Button"
)

if result.get("found"):
    print(f"✅ Found: {result['name']}")
    print(f"   AutomationId: {result.get('automation_id')}")
    print(f"   Position: ({result['x']}, {result['y']})")
else:
    print(f"❌ Not found: {result.get('error')}")
```

Run:
```powershell
python test_automation_id.py
```

---

## Comparison: macOS vs Windows

### Calculator Buttons:

| Platform | Attribute | Value |
|----------|-----------|-------|
| macOS | AXTitle | "Plus" |
| macOS | AXDescription | None |
| macOS | AXIdentifier | None (rarely set) |
| **Windows** | **Name** | **"Plus"** |
| **Windows** | **HelpText** | **"Add"** |
| **Windows** | **AutomationId** | **"plusButton"** |

**Winner:** 🏆 Windows (more attributes, better labels)

### Text Fields:

| Platform | Attribute | Value |
|----------|-----------|-------|
| macOS | AXTitle | None |
| macOS | AXPlaceholderValue | "Search" |
| macOS | AXIdentifier | "_SC_SEARCH_FIELD" |
| **Windows** | **Name** | **"Search"** |
| **Windows** | **PlaceholderText** | **"Search"** |
| **Windows** | **AutomationId** | **"searchBox"** |

**Winner:** 🏆 Tie (both good)

---

## Debugging Tips

### If No Elements Found:

1. **Check if window is focused:**
   ```python
   # The test script assumes frontmost app
   # Make sure the target app is in focus!
   ```

2. **Try different element types:**
   ```python
   # Instead of AXButton, Windows uses:
   # Button, MenuItem, Edit, ComboBox, etc.
   ```

3. **Check UIAutomation support:**
   ```python
   # Some apps don't expose accessibility tree
   # Modern apps (UWP) > Legacy apps (Win32)
   ```

### If Compaction Returns 0:

```python
# This was a bug we found on macOS!
# Check if Windows has same issue:

from code_puppy.tools.gui_cub.windows_automation import list_elements

result = list_elements()
print(f"Elements in result: {result.get('elements')}")
print(f"By role in result: {result.get('by_role')}")

# If elements=None but by_role has data,
# compaction bug exists on Windows too!
```

---

## Expected Differences: macOS vs Windows

### Attribute Names:
| macOS | Windows |
|-------|--------|
| AXTitle | Name |
| AXDescription | HelpText |
| AXRole | ControlType |
| AXValue | Value |
| AXIdentifier | AutomationId |
| AXPlaceholderValue | PlaceholderText |

### Element Quality:
- **macOS:** Title often empty, use description fallback
- **Windows:** Name usually populated, better labeling

### Identifier Support:
- **macOS:** AXIdentifier rarely set by apps
- **Windows:** AutomationId commonly used (especially UWP apps)

---

## Report Results

### Create a summary report:

```markdown
# Windows Element Tree Test Results

**Date:** 2025-01-10  
**OS:** Windows 11  
**Code-Puppy Version:** 1.0.0

## Calculator Test
- Total buttons found: 28
- Buttons with good names: 28 (100%)
- Compaction working: ✅ YES
- Find element working: ✅ YES
- Description fallback working: ✅ YES

## Notepad Test
- Total buttons found: 15
- Menu items found: 5
- Text editor found: ✅ YES (automation_id: "15")
- Compaction working: ✅ YES

## File Explorer Test
- Back/Forward buttons: ✅ FOUND (name="Back")
- Compared to macOS Finder: 🏆 BETTER (has name field)
- Search field: ✅ FOUND (placeholder working)

## Bugs Found:
- None! Windows accessibility working well.

## Comparison to macOS:
- Windows has BETTER default labeling
- AutomationId more commonly used than AXIdentifier
- Compaction working on Windows (was broken on macOS!)
```

---

## Advanced Testing

### Test Comprehensive Attribute Extraction:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from code_puppy.tools.gui_cub.windows_automation import find_element

# Open Calculator
result = find_element(name="Plus")

if result.get("found"):
    print("\nComprehensive Attributes:")
    print(f"  Name: {result.get('name')}")
    print(f"  ControlType: {result.get('control_type')}")
    print(f"  AutomationId: {result.get('automation_id')}")
    print(f"  HelpText: {result.get('help_text')}")
    print(f"  ClassName: {result.get('class_name')}")
    print(f"  LocalizedControlType: {result.get('localized_control_type')}")
    print(f"  Value: {result.get('value')}")
    
    # Check which attributes are populated
    populated = [k for k, v in result.items() if v]
    print(f"\nPopulated attributes: {len(populated)}")
    print(f"  {', '.join(populated)}")
```

---

## Success Criteria

### ✅ Tests Pass If:

1. **Calculator:**
   - Finds 20+ buttons
   - All buttons have names
   - Compaction returns 20 elements
   - Can find "Plus" button

2. **Notepad:**
   - Finds menu items
   - Finds text editor with automation_id
   - Compaction working

3. **File Explorer:**
   - Finds Back/Forward buttons
   - Buttons have name field (not just description)
   - Search field findable

4. **Comprehensive Attributes:**
   - AutomationId populated on most elements
   - HelpText available on many elements
   - LocalizedControlType available

### ❌ Tests Fail If:

1. Compaction returns 0 elements (BUG!)
2. Most buttons have empty names
3. Cannot find common elements (Plus, Back, etc.)
4. AutomationId never populated

---

## Troubleshooting

### "Module not found" Error:
```powershell
# Make sure you're in code-puppy directory
cd path\to\code-puppy

# Install dependencies
uv sync
```

### "No elements found" Error:
```python
# Check if app is running and focused
# Try clicking on the app window before running test
```

### "Compaction returns 0" Error:
```python
# This is the BUG we found on macOS!
# If this happens on Windows too, we need to fix it
# Report in issue tracker
```

---

## Next Steps After Testing

1. **Document results** in summary format above
2. **Compare with macOS results** from testing guide
3. **Report bugs** if compaction broken or attributes missing
4. **Update weights** if Windows has different attribute priorities

---

## Questions to Answer:

1. Is compaction working on Windows? (Was broken on macOS)
2. Are Windows labels better than macOS? (Expected: YES)
3. Is AutomationId commonly populated? (Expected: YES for modern apps)
4. Do we need Windows-specific attribute weights?
5. Are there Windows-specific issues we haven't seen on macOS?

---

## Contact

If you find bugs or have questions, create an issue with:
- Windows version
- Code-Puppy version
- Test results summary
- Any error messages
