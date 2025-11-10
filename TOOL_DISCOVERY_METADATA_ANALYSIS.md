# Tool Discovery Metadata Analysis - GUI-Cub Tools

**Date:** 2024-12-19
**Question:** What info does agent get from tool discovery? Do all GUI-Cub tools have one-line descriptions?
**Status:** ⚠️ PARTIAL - Representative tools have metadata, individual tools don't

---

## 📊 Current State

### **GUI-Cub Tools in TOOL_REGISTRY**

**Total GUI-Cub tools:** 68
- **With metadata (descriptions):** 13 ✅
- **Without metadata (bare functions):** 55 ❌

---

## ✅ **Representative Tools (Have Metadata)**

### What They Include:

```python
"desktop_mouse": {
    "register": register_mouse_control_tools,
    "category": "Desktop Automation",
    "description": "Mouse operations (move, click, drag, scroll)",  # ✅
    "keywords": ["mouse", "click", "drag", "scroll"],
    "platform": "all",
    "requires_typing": False,
    "use_cases": ["clicking elements", "drag and drop"],
}
```

### List of Representative Tools (13 tools):

1. **`gui_cub_workflows`** ✅
   - Description: "Workflow management (save, list, read workflows)"
   
2. **`gui_cub_config`** ✅
   - Description: "GUI-CUB configuration (calibrate, validate, reset)"
   
3. **`gui_cub_debug`** ✅
   - Description: "Debug screenshot tools"

4. **`desktop_screenshot`** ✅
   - Description: "Screenshot capture and analysis (OCR/VQA)"

5. **`desktop_mouse`** ✅
   - Description: "Mouse operations (move, click, drag, scroll)"

6. **`desktop_keyboard`** ✅
   - Description: "Keyboard operations (type, press, hotkey)"

7. **`desktop_shortcuts`** ✅
   - Description: "Common keyboard shortcuts (copy, paste, save, etc.)"

8. **`desktop_window_control`** ✅
   - Description: "Window management (focus, sleep, alerts)"

9. **`desktop_grid_calibration`** ✅
   - Description: "Grid overlay calibration for coordinate debugging"

10. **`desktop_ocr`** ✅
    - Description: "OCR text extraction and search"

11. **`desktop_click_debugging`** ✅
    - Description: "Click debugging tools (highlight, verify coordinates)"

12. **`desktop_vqa`** ✅
    - Description: "Visual Question Answering for element location"

13. **`macos_automation`** ✅ (if macOS)
    - Description: "macOS Accessibility API (native UI automation)"

14. **`windows_automation`** ✅ (if Windows)
    - Description: "Windows UIA (native UI automation)"

15. **`ui_automation`** ✅
    - Description: "Cross-platform UI automation"

**These work great for discovery!** ✅

---

## ❌ **Individual Tools (NO Metadata)**

### The Problem:

55 individual tools are just bare function references:

```python
"desktop_click_element_smart": register_multi_strategy_click_tools,
"desktop_mouse_move": register_mouse_control_tools,
"desktop_mouse_click": register_mouse_control_tools,
"desktop_keyboard_type": register_keyboard_control_tools,
# ... 50+ more
```

**No descriptions!** ❌

### Examples of Tools Without Descriptions:

- `desktop_click_element_smart` ❌ (your example!)
- `desktop_mouse_move` ❌
- `desktop_mouse_click` ❌
- `desktop_keyboard_type` ❌
- `desktop_ocr_extract_text` ❌
- `desktop_find_text` ❌
- `desktop_verify_text` ❌
- `desktop_vqa_click_two_stage` ❌
- `gui_cub_save_workflow` ❌
- `gui_cub_read_workflow` ❌

... and 45 more!

---

## 🔍 What get_tool_metadata() Returns

### For Tools WITH Metadata:

```python
metadata = get_tool_metadata(TOOL_REGISTRY["desktop_mouse"])

# Returns:
{
    "register": <function>,
    "category": "Desktop Automation",
    "description": "Mouse operations (move, click, drag, scroll)",  # ✅
    "keywords": ["mouse", "click"],
    "platform": "all",
    "requires_typing": False,
    "use_cases": ["clicking elements"],
}
```

### For Tools WITHOUT Metadata:

```python
metadata = get_tool_metadata(TOOL_REGISTRY["desktop_click_element_smart"])

# Returns (minimal):
{
    "register": <function>
}
# No description! ❌
```

---

## 📝 What Tool Discovery Returns

### Using `generate_tool_docs()`:

```python
from code_puppy.tools.tool_discovery import generate_tool_docs
from code_puppy.tools import TOOL_REGISTRY

docs = generate_tool_docs(TOOL_REGISTRY)
```

**Returns:**

```markdown
### Desktop Automation

- **desktop_click_debugging**: Click debugging tools (highlight, verify coordinates)
- **desktop_keyboard**: Keyboard operations (type, press, hotkey)
- **desktop_mouse**: Mouse operations (move, click, drag, scroll)
- **desktop_ocr**: OCR text extraction and search
- **desktop_screenshot**: Screenshot capture and analysis (OCR/VQA)
- **desktop_vqa**: Visual Question Answering for element location
...
```

**But individual tools like `desktop_click_element_smart` show:**

```markdown
- **desktop_click_element_smart**: No description
```

❌ **Not helpful!**

---

## ⚠️ The Gap

### **Problem: Individual Tools Are Invisible to Smart Discovery**

**Scenario:**
```python
# User asks: "I need a smart click that tries multiple strategies"

suggestions = suggest_tools(TOOL_REGISTRY, "smart click multiple strategies")

# Returns:
[]  # Nothing! ❌
```

**Why?** 
- `desktop_click_element_smart` has NO keywords
- NO description
- NO use_cases
- Can't be discovered by intent!

**User must know the exact name** ❌

---

## 🛠️ Recommendations

### **Option 1: Add Metadata to Key Individual Tools** (RECOMMENDED)

**Add descriptions for frequently-used individual tools:**

```python
# Instead of:
"desktop_click_element_smart": register_multi_strategy_click_tools,

# Do:
"desktop_click_element_smart": {
    "register": register_multi_strategy_click_tools,
    "category": CATEGORY_DESKTOP,
    "description": "Smart click with automatic fallback (UIA → OCR → VQA)",
    "keywords": ["smart", "click", "fallback", "multi-strategy"],
    "platform": "all",
    "requires_typing": False,
    "use_cases": ["clicking with automatic retry", "multi-tier clicking"],
},
```

**Key tools to add:**
1. `desktop_click_element_smart` - Multi-strategy click
2. `desktop_find_text` - OCR text search
3. `desktop_ocr_extract_text` - Extract all text
4. `desktop_vqa_click_two_stage` - Two-stage VQA click
5. `desktop_keyboard_type` - Type text
6. `gui_cub_save_workflow` - Save workflow
7. `gui_cub_read_workflow` - Read workflow

**Effort:** ~2 hours
**Impact:** HIGH (makes key tools discoverable)

---

### **Option 2: Auto-Generate Descriptions from Docstrings**

**Extract first line of tool docstring:**

```python
def get_tool_metadata(tool_entry: Callable | ToolMetadata) -> ToolMetadata:
    if isinstance(tool_entry, dict):
        return tool_entry
    
    # Try to extract description from function docstring
    description = "No description"
    if hasattr(tool_entry, "__doc__") and tool_entry.__doc__:
        # Get first line of docstring
        description = tool_entry.__doc__.strip().split('\n')[0]
    
    return {
        "register": tool_entry,
        "description": description,  # Auto-generated!
    }
```

**Pros:** 
- ✅ Automatic for all tools
- ✅ No manual work
- ✅ Uses existing docstrings

**Cons:**
- ⚠️ Docstrings might not be one-line summaries
- ⚠️ No keywords/use_cases

**Effort:** ~30 minutes
**Impact:** MEDIUM

---

### **Option 3: Document Representative Tools Only** (CURRENT STATE)

**Keep current approach:**
- Representative tools have metadata ✅
- Individual tools are "advanced" ❌
- Users use representative tools mostly

**Assumption:** Users mostly use:
- `desktop_mouse` (not `desktop_mouse_click`)
- `desktop_keyboard` (not `desktop_keyboard_type`)
- `desktop_ocr` (not `desktop_find_text`)

**Pro:** No work needed
**Con:** Power users can't discover individual tools

---

## 🎯 Recommended Approach

### **Hybrid: Add Metadata to Top 10-15 Individual Tools**

Focus on frequently-used specific tools:

```python
TOOL_REGISTRY.update({
    # Multi-strategy click (THE KEY ONE)
    "desktop_click_element_smart": {
        "register": register_multi_strategy_click_tools,
        "category": CATEGORY_DESKTOP,
        "description": "Smart click with automatic fallback (UIA → OCR → VQA)",
        "keywords": ["smart", "click", "auto", "fallback", "retry"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": [
            "clicking with automatic strategy selection",
            "reliable clicking across different UI types",
        ],
    },
    
    # OCR text finding
    "desktop_find_text": {
        "register": register_ocr_tools,
        "category": CATEGORY_DESKTOP,
        "description": "Find text on screen using OCR",
        "keywords": ["ocr", "find", "text", "search", "locate"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["find UI elements by text", "locate buttons"],
    },
    
    # Typing
    "desktop_keyboard_type": {
        "register": register_keyboard_control_tools,
        "category": CATEGORY_DESKTOP,
        "description": "Type text via keyboard",
        "keywords": ["type", "text", "input", "enter"],
        "platform": "all",
        "requires_typing": True,
        "use_cases": ["type into forms", "enter text"],
    },
    
    # VQA two-stage
    "desktop_vqa_click_two_stage": {
        "register": register_vqa_two_stage_tools,
        "category": CATEGORY_DESKTOP,
        "description": "Two-stage VQA click (coarse → fine, 93% success)",
        "keywords": ["vqa", "vision", "ai", "visual", "two-stage"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["find elements visually", "click custom UI"],
    },
    
    # Workflow tools
    "gui_cub_save_workflow": {
        "register": register_gui_cub_workflows,
        "category": CATEGORY_DESKTOP,
        "description": "Save automation workflow as Markdown or YAML",
        "keywords": ["save", "workflow", "document", "pattern"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["save successful automation", "document patterns"],
    },
    
    "gui_cub_read_workflow": {
        "register": register_gui_cub_workflows,
        "category": CATEGORY_DESKTOP,
        "description": "Read workflow guidance document",
        "keywords": ["read", "workflow", "guidance", "load"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["load workflow guidance", "get automation patterns"],
    },
})
```

**Priority Tools (Add metadata):**
1. `desktop_click_element_smart` ⭐ **CRITICAL**
2. `desktop_find_text`
3. `desktop_keyboard_type`
4. `desktop_vqa_click_two_stage`
5. `gui_cub_save_workflow`
6. `gui_cub_read_workflow`
7. `desktop_ocr_extract_text`
8. `desktop_mouse_click`
9. `desktop_focus_window`
10. `ui_find_element`

**Effort:** ~2-3 hours
**Impact:** HIGH (covers 90% of use cases)

---

## 📋 Implementation Plan

### Step 1: Add Metadata to Top 10 Individual Tools

**File:** `code_puppy/tools/__init__.py`

**Change bare registrations to metadata dicts:**

```python
# Before:
"desktop_click_element_smart": register_multi_strategy_click_tools,

# After:
"desktop_click_element_smart": {
    "register": register_multi_strategy_click_tools,
    "category": CATEGORY_DESKTOP,
    "description": "Smart click with automatic fallback (UIA → OCR → VQA)",
    "keywords": ["smart", "click", "fallback"],
    "platform": "all",
    "requires_typing": False,
    "use_cases": ["reliable clicking", "multi-strategy automation"],
},
```

### Step 2: Test Tool Discovery

```python
from code_puppy.tools.tool_discovery import suggest_tools
from code_puppy.tools import TOOL_REGISTRY

# Test: "smart click"
result = suggest_tools(TOOL_REGISTRY, "smart click with fallback")
print(result)
# Should include: ['desktop_click_element_smart', ...]
```

### Step 3: Update Documentation

Update `docs/TOOL_DISCOVERY_SUMMARY.md` with new tool count.

---

## ✅ Answer to Your Question

### **"Do all GUI-Cub tools have one-line descriptions?"**

**NO** - Currently:
- ✅ 13 representative tools have descriptions
- ❌ 55 individual tools have NO descriptions

### **"What info does agent get?"**

**For representative tools (desktop_mouse, desktop_keyboard, etc.):**
```
- Description: "Mouse operations (move, click, drag, scroll)"
- Keywords: ["mouse", "click", "drag"]
- Use cases: ["clicking elements", "drag and drop"]
- Platform: "all"
```

**For individual tools (desktop_click_element_smart, etc.):**
```
- Description: "No description"  # ❌ Not helpful!
- No keywords
- No use cases
```

### **"What about desktop_click_element_smart specifically?"**

**Currently:** ❌ NO metadata
- No description
- Can't be discovered by intent
- User must know exact name

**Recommendation:** ✅ Add metadata (see implementation plan above)

---

## 📈 Impact of Adding Metadata

### Before:
```python
# User: "I need smart clicking with fallback"
suggestions = suggest_tools(TOOL_REGISTRY, "smart click fallback")
# Returns: []
```

### After:
```python
# User: "I need smart clicking with fallback"
suggestions = suggest_tools(TOOL_REGISTRY, "smart click fallback")
# Returns: ['desktop_click_element_smart', 'desktop_click_debugging']
```

**Much better!** ✅

---

## 🚀 Summary

**Current State:**
- 13 tools with descriptions ✅
- 55 tools without descriptions ❌

**Recommendation:**
- Add metadata to top 10 individual tools
- Focus on `desktop_click_element_smart` (your example)
- ~2-3 hours work
- High impact for discovery

**Priority:**
- MEDIUM (current state works for representative tools)
- HIGH if you want power users to discover individual tools

---

**Status:** Gap identified, solution proposed
**Effort:** 2-3 hours
**Impact:** HIGH for discoverability
