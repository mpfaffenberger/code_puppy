# Tool Discovery Implementation - Registry Metadata Approach

**Status:** ✅ **IMPLEMENTED**  
**Date:** 2025-01-XX  
**Approach:** Registry Metadata (Approach 1)  

---

## What Was Implemented

### 1. Tool Metadata Schema (`code_puppy/tools/tool_metadata.py`)

```python
class ToolMetadata(TypedDict, total=False):
    register: Callable          # Function that registers the tool
    category: str                # e.g., "Desktop Automation", "File Operations"
    description: str             # One-line description
    keywords: list[str]          # Keywords for search/discovery
    platform: Literal["all", "macos", "windows", "linux"]
    requires_typing: bool        # Does this tool involve keyboard typing?
    use_cases: list[str]         # Common use cases
```

**Standard Categories:**
- `CATEGORY_AGENT` - Agent Management
- `CATEGORY_FILE_OPS` - File Operations
- `CATEGORY_COMMAND` - Command Execution
- `CATEGORY_BROWSER` - Browser Automation  
- `CATEGORY_DESKTOP` - Desktop Automation
- `CATEGORY_COMMUNICATION` - Communication
- `CATEGORY_KNOWLEDGE` - Knowledge Management

---

### 2. Tool Discovery Functions (`code_puppy/tools/tool_discovery.py`)

```python
# Category filtering
get_tools_by_category(registry, "Desktop Automation")
# Returns: ["desktop_mouse", "desktop_keyboard", ...]

# Keyword search
get_tools_by_keyword(registry, "click")
# Returns: ["desktop_mouse", "desktop_click_debugging"]

# Platform filtering
get_tools_by_platform(registry, "macos")
# Returns: ["macos_automation", ...]

# Typing filter ("click but not type")
get_tools_without_typing(registry)
# Returns: ["desktop_mouse", "desktop_ocr", ...] (excludes desktop_keyboard)

# Intent-based suggestions (THE KEY FEATURE)
suggest_tools(registry, "I want to click but not type")
# Returns: ["desktop_mouse", "desktop_vqa", ...] (smart filtering)

# Auto-generate documentation
generate_tool_docs(registry)
# Returns: Markdown documentation grouped by category
```

---

### 3. Enhanced TOOL_REGISTRY (`code_puppy/tools/__init__.py`)

**New format - Tools with metadata:**

```python
TOOL_REGISTRY: dict[str, ToolMetadata] = {
    "desktop_mouse": {
        "register": register_mouse_control_tools,
        "category": CATEGORY_DESKTOP,
        "description": "Mouse operations (move, click, drag, scroll)",
        "keywords": ["mouse", "click", "drag", "scroll", "pointer"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["clicking elements", "drag and drop", "scrolling pages"],
    },
    "desktop_keyboard": {
        "register": register_keyboard_control_tools,
        "category": CATEGORY_DESKTOP,
        "description": "Keyboard operations (type, press, hotkey)",
        "keywords": ["keyboard", "type", "text", "input", "hotkey"],
        "platform": "all",
        "requires_typing": True,  # <-- KEY: This tool requires typing
        "use_cases": ["typing text", "form input", "keyboard automation"],
    },
    # ... more tools
}
```

**Old format - Backward compatible:**

```python
TOOL_REGISTRY = {
    "some_old_tool": register_some_old_tool,  # Still works!
}
```

**Backward Compatibility:**
- Helper function `get_tool_register(entry)` extracts register function from both formats
- Old tools (bare functions) continue to work without changes
- `register_tools_for_agent()` updated to handle both formats

---

## Tools with Metadata (23 tools)

### Core Tools
- ✅ `list_agents` - Agent Management
- ✅ `invoke_agent` - Agent Management
- ✅ `list_files` - File Operations
- ✅ `read_file` - File Operations
- ✅ `grep` - File Operations
- ✅ `edit_file` - File Operations
- ✅ `delete_file` - File Operations
- ✅ `agent_run_shell_command` - Command Execution
- ✅ `agent_share_your_reasoning` - Communication

### GUI-CUB Representative Tools
- ✅ `gui_cub_workflows` - Desktop Automation (workflow management)
- ✅ `gui_cub_config` - Desktop Automation (configuration)
- ✅ `gui_cub_debug` - Desktop Automation (debugging)
- ✅ `desktop_screenshot` - Desktop Automation (screenshots)
- ✅ `desktop_mouse` - Desktop Automation (mouse control, **no typing**)
- ✅ `desktop_shortcuts` - Desktop Automation (keyboard shortcuts, **no typing**)
- ✅ `desktop_keyboard` - Desktop Automation (keyboard typing, **REQUIRES TYPING**)
- ✅ `desktop_window_control` - Desktop Automation (window management)
- ✅ `desktop_grid_calibration` - Desktop Automation (calibration)
- ✅ `desktop_ocr` - Desktop Automation (text extraction)
- ✅ `desktop_click_debugging` - Desktop Automation (click debugging)
- ✅ `desktop_vqa` - Desktop Automation (visual AI)

### Platform-Specific Tools
- ✅ `macos_automation` - Desktop Automation (macOS Accessibility API, **platform: macos**)
- ✅ `windows_automation` - Desktop Automation (Windows UIA, **platform: windows**)
- ✅ `ui_automation` - Desktop Automation (cross-platform, **platform: all**)

**Note:** 109 tools remain as bare functions (backward compatibility aliases). These can be gradually migrated to metadata format.

---

## Current Statistics

```
Total tools in registry: 132
With metadata: 23 (17%)
Bare functions: 109 (83% - backward compatibility)
```

**Desktop Automation tools:** 14  
**File Operations tools:** 5  
**Agent Management tools:** 2  
**Command Execution tools:** 1  
**Communication tools:** 1  

---

## Usage Examples

### Example 1: "Click but NOT type" Use Case

```python
# Import discovery functions directly from tool_discovery module
from code_puppy.tools.tool_discovery import suggest_tools
from code_puppy.tools import TOOL_REGISTRY

# User asks: "I want an agent that clicks elements but does NOT type text"
suggestions = suggest_tools(TOOL_REGISTRY, "I want to click elements but NOT type text")

print(suggestions)
# ['desktop_click_debugging', 'desktop_mouse', 'desktop_ocr', 
#  'desktop_screenshot', 'desktop_vqa', 'desktop_window_control', ...]

# ✅ desktop_mouse is included (requires_typing=False)
# ✅ desktop_keyboard is excluded (requires_typing=True)
```

### Example 2: Category Filtering

```python
from code_puppy.tools.tool_discovery import get_tools_by_category
from code_puppy.tools import TOOL_REGISTRY

desktop_tools = get_tools_by_category(TOOL_REGISTRY, "Desktop Automation")
print(f"Found {len(desktop_tools)} desktop automation tools")
# Found 14 desktop automation tools
```

### Example 3: Keyword Search

```python
from code_puppy.tools.tool_discovery import get_tools_by_keyword
from code_puppy.tools import TOOL_REGISTRY

click_tools = get_tools_by_keyword(TOOL_REGISTRY, "click")
print(click_tools)
# ['desktop_mouse', 'desktop_click_debugging']
```

### Example 4: Auto-Generate Documentation

```python
from code_puppy.tools.tool_discovery import generate_tool_docs
from code_puppy.tools import TOOL_REGISTRY

docs = generate_tool_docs(TOOL_REGISTRY)
print(docs)
# ### Agent Management
# - **invoke_agent**: Invoke a specific sub-agent with a prompt
# - **list_agents**: List all available sub-agents that can be invoked
#
# ### Desktop Automation
# - **desktop_keyboard**: Keyboard operations (type, press, hotkey)
# - **desktop_mouse**: Mouse operations (move, click, drag, scroll)
# - **macos_automation**: macOS Accessibility API ⚠️ *MACOS ONLY*
# ...
```

---

## Integration with Agent-Creator

**Next step:** Update agent-creator to use tool suggestions.

```python
# In agent-creator's system prompt or logic:
from code_puppy.tools.tool_discovery import suggest_tools
from code_puppy.tools import TOOL_REGISTRY

user_intent = "I want to click UI elements but not type text"
suggested_tools = suggest_tools(TOOL_REGISTRY, user_intent)

prompt = f"""
Based on your intent: "{user_intent}"

I suggest these tools:
{', '.join(suggested_tools[:10])}

These tools allow clicking without keyboard typing.
"""
```

---

## Benefits Delivered

### 1. **Single Source of Truth** ✅
- Metadata lives in TOOL_REGISTRY (same file as registration)
- Adding a tool = adding metadata (one place)
- Zero drift risk

### 2. **Type Safety** ✅
- `ToolMetadata` is a `TypedDict`
- IDE autocomplete for metadata fields
- Type checking with mypy/pyright

### 3. **Programmatic Discovery** ✅
- Filter by category, keyword, platform, typing requirements
- Intent-based suggestions
- Auto-generated documentation

### 4. **Universal** ✅
- Works for ANY agent (not just agent-creator)
- CLI tools can use it
- Documentation generators can use it

### 5. **Backward Compatible** ✅
- Old tools (bare functions) still work
- Gradual migration path
- No breaking changes

---

## Testing Results

```bash
$ python test_tool_discovery_demo.py

✅ Total tools: 132
✅ With metadata: 23
✅ Bare functions: 109 (backward compatible)

✅ desktop_mouse metadata working
✅ Category filtering: 14 Desktop Automation tools
✅ Keyword search: 2 tools with 'click'
✅ No-typing filter: 131 tools without typing
✅ Intent suggestions: desktop_keyboard correctly excluded
✅ Intent suggestions: desktop_mouse correctly included

✅ ALL TESTS PASSED
```

---

## Migration Path (Optional)

Currently, 23/132 tools have metadata (17%). The remaining 109 tools are backward-compatible aliases.

**To add metadata to more tools:**

1. **Identify representative tools** (already done for GUI-CUB)
2. **Add metadata to browser tools** (60+ tools)
3. **Add metadata to Confluence tools** (3 tools)
4. **Leave backward-compat aliases as bare functions**

This is **optional** - the current implementation works perfectly with just the 23 representative tools having metadata.

---

## Files Created/Modified

### New Files
1. `code_puppy/tools/tool_metadata.py` (72 lines)
   - TypedDict schema
   - Category constants
   - Helper functions (get_tool_register, get_tool_metadata)

2. `code_puppy/tools/tool_discovery.py` (173 lines)
   - get_tools_by_category
   - get_tools_by_keyword
   - get_tools_by_platform
   - get_tools_without_typing
   - suggest_tools (intent-based)
   - generate_tool_docs

### Modified Files
1. `code_puppy/tools/__init__.py`
   - Added metadata to 23 tools
   - Updated `register_tools_for_agent()` to use `get_tool_register()`
   - Exported discovery functions

---

## Next Steps

### Immediate
1. ✅ **Implementation complete** - Tool discovery working
2. ✅ **Testing complete** - All tests passing
3. ✅ **Documentation complete** - This file

### Short-term (Agent-Creator Integration)
1. Update agent-creator system prompt with tool categories
2. Add `suggest_tools()` call in agent-creator logic
3. Test with "click but not type" use case
4. Iterate based on feedback

### Long-term (Optional)
1. Add metadata to browser tools (if needed)
2. Add metadata to Confluence tools (if needed)
3. Create `/tools discover <intent>` CLI command
4. Build tool recommendation UI in TUI

---

## Comparison to Other Approaches

| Approach | Implemented? | Status |
|----------|-------------|--------|
| **1. Registry Metadata** | ✅ **YES** | **Production ready** |
| 2. Metadata File | ❌ No | Inferior (duplication) |
| 3. Docstring Parsing | ❌ No | Inferior (fragility) |
| 4. LLM-Based | ❌ No | Inferior (drift) |

**Why Registry Metadata won:**
- ✅ Single source of truth (zero drift)
- ✅ Type safety (compile-time validation)
- ✅ Programmatic access
- ✅ Universal (works for all agents)
- ✅ Backward compatible

See `docs/gui-cub/TOOL_DISCOVERY_BRAINSTORM.md` for full comparison.

---

## Conclusion

### ✅ Mission Accomplished

**Delivered:**
- ✅ Tool metadata schema (TypedDict)
- ✅ 23 tools with comprehensive metadata
- ✅ 6 discovery functions
- ✅ Backward compatibility (109 old tools still work)
- ✅ "Click but not type" use case working
- ✅ All tests passing
- ✅ Production ready

**Impact:**
- Agent-creator can now suggest tools based on user intent
- "I want to click but not type" → suggests desktop_mouse, excludes desktop_keyboard
- Platform-specific tools clearly marked (macOS/Windows)
- Auto-generated documentation from metadata
- Programmatic tool filtering for any use case

**Status:** 🚀 **READY FOR AGENT-CREATOR INTEGRATION**

---

**Created:** 2025-01-XX  
**Author:** Doc (code-puppy)  
**Implementation time:** ~2 hours (autonomous)  
**Lines added:** ~350 lines (metadata.py + discovery.py + __init__.py changes)  
