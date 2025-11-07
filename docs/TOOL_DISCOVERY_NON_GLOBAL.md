# Tool Discovery: Non-Global Implementation

## Changes Made

### Problem
Dakota requested we avoid registering global tools while keeping functionality discoverable from agent-builder.

### Solution
Removed global wrapper functions from `code_puppy/tools/__init__.py` that were re-exporting discovery functions.

---

## What Was Removed

**From `code_puppy/tools/__init__.py`:**

```python
# ❌ REMOVED - These were global exports
def get_tools_by_category(category: str) -> list[str]: ...
def get_tools_by_keyword(keyword: str) -> list[str]: ...
def get_tools_without_typing() -> list[str]: ...
def suggest_tools(user_intent: str) -> list[str]: ...
def generate_tool_docs() -> str: ...
```

---

## What Remains (Agent-Builder Can Use)

### 1. Tool Metadata Infrastructure ✅

- `code_puppy/tools/tool_metadata.py` - Schema and helpers
- `code_puppy/tools/tool_discovery.py` - Discovery functions
- `code_puppy/tools/__init__.py` - TOOL_REGISTRY with metadata

### 2. Discovery Functions (Non-Global) ✅

**Agent-builder imports directly from tool_discovery module:**

```python
# Import discovery functions from their module
from code_puppy.tools.tool_discovery import (
    suggest_tools,
    get_tools_by_category,
    get_tools_by_keyword,
    get_tools_without_typing,
    generate_tool_docs,
)

# Import TOOL_REGISTRY to pass to discovery functions
from code_puppy.tools import TOOL_REGISTRY

# Use them
suggestions = suggest_tools(TOOL_REGISTRY, "I want to click but not type")
desktop_tools = get_tools_by_category(TOOL_REGISTRY, "Desktop Automation")
```

---

## Benefits

### ✅ No Global Pollution
- Discovery functions are NOT exported from `code_puppy.tools`
- Clean global namespace
- Explicit imports required

### ✅ Functionality Preserved
- All discovery functions still exist
- Agent-builder can import them directly
- TOOL_REGISTRY still has metadata

### ✅ Clear API
- Agent-builder knows exactly where to import from
- Explicit dependency on tool_discovery module
- No hidden global functions

---

## Usage Pattern for Agent-Builder

```python
# agent_creator.py or similar

from code_puppy.tools.tool_discovery import suggest_tools
from code_puppy.tools import TOOL_REGISTRY

def create_agent_with_tools(user_intent: str):
    # Suggest tools based on user intent
    suggested_tools = suggest_tools(TOOL_REGISTRY, user_intent)
    
    # Use suggested tools to create agent
    return {
        "intent": user_intent,
        "tools": suggested_tools[:10],  # Top 10 suggestions
    }

# Example
result = create_agent_with_tools("I want to click but not type")
print(result)
# {
#   "intent": "I want to click but not type",
#   "tools": ["desktop_mouse", "desktop_vqa", "desktop_click_debugging", ...]
# }
```

---

## What Agent-Builder Gets

### From `code_puppy.tools.tool_discovery`:
```python
suggest_tools(registry, user_intent)          # Intent-based suggestions
get_tools_by_category(registry, category)     # Category filtering
get_tools_by_keyword(registry, keyword)       # Keyword search
get_tools_without_typing(registry)            # "Click but not type"
generate_tool_docs(registry)                  # Auto-generated docs
```

### From `code_puppy.tools`:
```python
TOOL_REGISTRY  # Dict with tool metadata
```

### From `code_puppy.tools.tool_metadata`:
```python
ToolMetadata          # TypedDict schema
CATEGORY_DESKTOP     # Category constants
CATEGORY_FILE_OPS    # ...
get_tool_metadata()   # Helper functions
```

---

## Testing

```bash
✅ All lint checks passing
✅ Discovery functions work from tool_discovery module
✅ Global exports removed (no pollution)
✅ "Click but not type" logic still works
✅ Backward compatible (TOOL_REGISTRY unchanged)
```

---

## Conclusion

**Dakota's request fulfilled:**
- ❌ No global tool functions exported from `code_puppy.tools`
- ✅ All functionality preserved in `code_puppy.tools.tool_discovery`
- ✅ Agent-builder can still discover tools by importing directly
- ✅ Clean, explicit API

**Status:** Ready for agent-builder integration with non-global imports.
