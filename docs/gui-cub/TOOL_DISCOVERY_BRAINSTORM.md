# GUI-CUB Tool Discovery Brainstorm

## Problem Statement

Agent-creator currently has NO knowledge of GUI-CUB tools. Users can't discover:
- "I want to click elements but NOT type" → Which tools?
- "I want to extract text from screenshots" → Which tools?
- "I want macOS-only automation" → Which tools?

**Current state:** GUI-CUB tools are completely invisible to agent-creator.

**Constraint:** We CANNOT modify agent-creator directly (it's out of scope for GUI-CUB).

---

## Solution Approaches

### Approach 1: Tool Registry Metadata Enhancement ⭐ **RECOMMENDED**

**Concept:** Enhance `TOOL_REGISTRY` in `code_puppy/tools/__init__.py` with rich metadata.

#### Implementation

```python
# code_puppy/tools/__init__.py

TOOL_REGISTRY = {
    # Current (just function reference)
    "desktop_mouse": register_mouse_control_tools,
    
    # Enhanced (with metadata)
    "desktop_mouse": {
        "register": register_mouse_control_tools,
        "category": "Desktop Automation",
        "subcategory": "Mouse Control",
        "description": "Mouse operations (move, click, drag, scroll)",
        "use_cases": ["clicking elements", "drag and drop", "scrolling"],
        "keywords": ["click", "mouse", "drag", "scroll", "pointer"],
        "platform": "all",  # or "macos", "windows", "linux"
        "requires_typing": False,  # Important for "click but not type" use case
    },
    
    "desktop_keyboard": {
        "register": register_keyboard_control_tools,
        "category": "Desktop Automation",
        "subcategory": "Keyboard Control",
        "description": "Keyboard operations (type, press, hotkey)",
        "use_cases": ["typing text", "keyboard shortcuts", "form input"],
        "keywords": ["type", "keyboard", "text", "input", "hotkey"],
        "platform": "all",
        "requires_typing": True,
    },
    
    "macos_automation": {
        "register": register_macos_automation_tools,
        "category": "Desktop Automation",
        "subcategory": "Platform-Specific",
        "description": "macOS Accessibility API (find, click elements)",
        "use_cases": ["macOS UI automation", "native element clicking"],
        "keywords": ["macos", "accessibility", "native"],
        "platform": "macos",
        "requires_typing": False,
    },
}
```

#### Usage in Agent-Creator

```python
# agent_creator_agent.py

from code_puppy.tools import TOOL_REGISTRY

def get_tool_metadata(tool_name: str) -> dict:
    """Get rich metadata for a tool."""
    tool_info = TOOL_REGISTRY.get(tool_name)
    if isinstance(tool_info, dict):
        return tool_info
    else:
        # Legacy format (just function reference)
        return {"register": tool_info, "category": "Unknown"}

def suggest_tools_for_intent(user_intent: str) -> list[str]:
    """Suggest tools based on user intent."""
    intent_lower = user_intent.lower()
    suggestions = []
    
    for tool_name, tool_info in TOOL_REGISTRY.items():
        if isinstance(tool_info, dict):
            # Check keywords
            if any(keyword in intent_lower for keyword in tool_info.get("keywords", [])):
                suggestions.append(tool_name)
            
            # Special case: "click but not type"
            if "click" in intent_lower and "not type" in intent_lower:
                if not tool_info.get("requires_typing", False):
                    suggestions.append(tool_name)
    
    return suggestions
```

#### System Prompt Enhancement

```python
# Auto-generate tool documentation from metadata
def generate_tool_docs() -> str:
    """Generate tool documentation from registry metadata."""
    categories = {}
    
    for tool_name, tool_info in TOOL_REGISTRY.items():
        if isinstance(tool_info, dict):
            category = tool_info.get("category", "Other")
            if category not in categories:
                categories[category] = []
            categories[category].append((tool_name, tool_info))
    
    docs = []
    for category, tools in categories.items():
        docs.append(f"\n### {category}\n")
        for tool_name, tool_info in tools:
            docs.append(f"- `{tool_name}`: {tool_info['description']}")
            if tool_info.get("platform") != "all":
                docs.append(f" ⚠️ {tool_info['platform'].upper()} ONLY")
    
    return "\n".join(docs)

# In agent-creator system prompt
system_prompt = f"""
You are the Agent Creator! 🏗️

## Available Tools:
{generate_tool_docs()}
"""
```

**Pros:**
- ✅ Single source of truth (TOOL_REGISTRY)
- ✅ Auto-generates documentation
- ✅ Easy to maintain (add metadata once)
- ✅ Works for any agent, not just agent-creator
- ✅ Enables smart tool suggestions

**Cons:**
- ⚠️ Requires updating TOOL_REGISTRY structure
- ⚠️ Need to add metadata for all 40+ tools
- ⚠️ Breaking change (need migration)

---

### Approach 2: Separate Tool Metadata File

**Concept:** Create a `tools_metadata.json` file with tool descriptions.

#### Implementation

```json
// code_puppy/tools/tools_metadata.json
{
  "desktop_mouse": {
    "category": "Desktop Automation",
    "description": "Mouse operations (move, click, drag, scroll)",
    "use_cases": ["clicking elements", "drag and drop"],
    "keywords": ["click", "mouse", "drag"],
    "platform": "all",
    "requires_typing": false
  },
  "desktop_keyboard": {
    "category": "Desktop Automation",
    "description": "Keyboard operations (type, press, hotkey)",
    "use_cases": ["typing text", "keyboard shortcuts"],
    "keywords": ["type", "keyboard", "text"],
    "platform": "all",
    "requires_typing": true
  },
  "macos_automation": {
    "category": "Desktop Automation",
    "description": "macOS Accessibility API",
    "use_cases": ["macOS UI automation"],
    "keywords": ["macos", "accessibility"],
    "platform": "macos",
    "requires_typing": false
  }
}
```

```python
# code_puppy/tools/metadata.py

import json
from pathlib import Path

def load_tool_metadata() -> dict:
    """Load tool metadata from JSON."""
    metadata_file = Path(__file__).parent / "tools_metadata.json"
    with open(metadata_file) as f:
        return json.load(f)

def get_tools_by_category() -> dict:
    """Get tools organized by category."""
    metadata = load_tool_metadata()
    categories = {}
    
    for tool_name, tool_info in metadata.items():
        category = tool_info.get("category", "Other")
        if category not in categories:
            categories[category] = []
        categories[category].append((tool_name, tool_info))
    
    return categories

def suggest_tools(user_intent: str) -> list[str]:
    """Suggest tools based on user intent."""
    metadata = load_tool_metadata()
    intent_lower = user_intent.lower()
    suggestions = []
    
    for tool_name, tool_info in metadata.items():
        # Keyword matching
        if any(keyword in intent_lower for keyword in tool_info.get("keywords", [])):
            suggestions.append(tool_name)
        
        # Special cases
        if "click" in intent_lower and "not type" in intent_lower:
            if not tool_info.get("requires_typing", False):
                suggestions.append(tool_name)
    
    return list(set(suggestions))  # Remove duplicates
```

**Pros:**
- ✅ Non-breaking (doesn't change TOOL_REGISTRY)
- ✅ Easy to edit (JSON format)
- ✅ Can be version controlled separately
- ✅ No code changes to existing tools

**Cons:**
- ⚠️ Separate from tool definitions (can get out of sync)
- ⚠️ Need to manually maintain JSON file
- ⚠️ Duplication (metadata separate from code)

---

### Approach 3: Docstring Parsing

**Concept:** Extract metadata from tool function docstrings.

#### Implementation

```python
# code_puppy/tools/introspection.py

import inspect
from typing import Callable

def extract_tool_metadata(register_func: Callable) -> dict:
    """Extract metadata from tool registration function docstring."""
    # Get the actual tool functions from the register function
    # This is tricky because register_func creates closures
    
    doc = inspect.getdoc(register_func)
    if not doc:
        return {"description": "No description"}
    
    # Parse docstring for metadata
    # Example docstring:
    # """Register mouse control tools.
    # 
    # Category: Desktop Automation
    # Use cases: clicking, dragging, scrolling
    # Keywords: click, mouse, drag
    # Platform: all
    # """
    
    metadata = {"description": doc.split("\n")[0]}
    
    for line in doc.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            
            if key == "keywords":
                metadata[key] = [k.strip() for k in value.split(",")]
            else:
                metadata[key] = value
    
    return metadata

def get_all_tool_metadata() -> dict:
    """Get metadata for all registered tools."""
    from code_puppy.tools import TOOL_REGISTRY
    
    metadata = {}
    for tool_name, register_func in TOOL_REGISTRY.items():
        metadata[tool_name] = extract_tool_metadata(register_func)
    
    return metadata
```

**Example Tool Registration with Metadata Docstring:**

```python
# code_puppy/tools/gui_cub/mouse_control.py

def register_mouse_control_tools(agent):
    """Register mouse control tools.
    
    Category: Desktop Automation
    Subcategory: Mouse Control
    Use cases: clicking elements, drag and drop, scrolling
    Keywords: click, mouse, drag, scroll, pointer
    Platform: all
    Requires typing: false
    """
    # ... tool definitions
```

**Pros:**
- ✅ Metadata lives with code (single source of truth)
- ✅ Non-breaking (just enhanced docstrings)
- ✅ Auto-discoverable via introspection

**Cons:**
- ⚠️ Docstring parsing is fragile
- ⚠️ Need consistent docstring format
- ⚠️ Parsing can fail silently
- ⚠️ Not as structured as JSON/dict

---

### Approach 4: LLM-Based Tool Discovery

**Concept:** Let agent-creator use an LLM to analyze tool names/descriptions.

#### Implementation

```python
# agent_creator_agent.py

from code_puppy.tools import get_available_tool_names

class AgentCreatorAgent(BaseAgent):
    def get_system_prompt(self) -> str:
        all_tools = get_available_tool_names()
        
        return f"""
You are the Agent Creator! 🏗️

## Available Tools:
{', '.join(all_tools)}

## Tool Suggestion Guidelines:

When users describe what they want their agent to do, analyze the tool names
and suggest appropriate tools:

**Examples:**
- "I want to click but not type" → Suggest: desktop_mouse, ui_automation, desktop_click_element_smart
  (Avoid: desktop_keyboard, desktop_shortcuts)

- "I want OCR text extraction" → Suggest: desktop_ocr, desktop_screenshot

- "I want macOS automation" → Suggest: macos_automation (warn: macOS only)

- "I want Windows automation" → Suggest: windows_automation (warn: Windows only)

Use your understanding of tool names to infer their purpose:
- `desktop_mouse` = mouse control
- `desktop_keyboard` = typing/keyboard
- `desktop_ocr` = text extraction
- `macos_automation` = macOS-specific
- `windows_automation` = Windows-specific
"""
```

**Pros:**
- ✅ No metadata needed
- ✅ LLM can infer from tool names
- ✅ Minimal implementation
- ✅ Works immediately

**Cons:**
- ⚠️ Less accurate than structured metadata
- ⚠️ Depends on LLM reasoning
- ⚠️ Can't handle complex relationships
- ⚠️ No programmatic filtering (e.g., platform-specific)

---

## Comparison Matrix

| Approach | Accuracy | Maintenance | Implementation | Breaking Changes |
|----------|----------|-------------|----------------|------------------|
| 1. Registry Metadata | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⚠️ Yes |
| 2. Metadata File | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ No |
| 3. Docstring Parsing | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ✅ No |
| 4. LLM-Based | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ No |

---

## Recommendation

### Phase 1: Quick Win (1 hour)
**Use Approach 4 (LLM-Based) immediately**

```python
# agent_creator_agent.py - Add to system prompt
"""
## GUI-CUB Desktop Automation Tools:

When users want desktop automation, suggest these tools based on their needs:

**Mouse Control (clicking without typing):**
- desktop_mouse - Direct mouse control (move, click, drag, scroll)
- desktop_click_element_smart - Multi-strategy click with auto-fallback
- ui_automation - Cross-platform UI element clicking

**Keyboard Control (typing into fields):**
- desktop_keyboard - Keyboard operations (type, press, hotkey)
- desktop_shortcuts - Common shortcuts (copy, paste, save)

**Text Recognition:**
- desktop_ocr - Extract and search for text using OCR
- desktop_screenshot - Capture and analyze screenshots

**Platform-Specific:**
- macos_automation - macOS Accessibility API ⚠️ macOS ONLY
- windows_automation - Windows UIA ⚠️ Windows ONLY

**Workflows:**
- gui_cub_workflows - Save/load/execute workflows
- gui_cub_read_workflow - Read workflow guidance
"""
```

**Benefits:**
- ✅ Works immediately
- ✅ No code changes
- ✅ Good enough for most use cases

---

### Phase 2: Long-Term Solution (1 week)
**Implement Approach 2 (Metadata File)**

1. Create `code_puppy/tools/tools_metadata.json`
2. Add metadata for all 40+ tools
3. Create `code_puppy/tools/metadata.py` with helper functions
4. Update agent-creator to use `suggest_tools(user_intent)`
5. Auto-generate tool documentation in system prompt

**Benefits:**
- ✅ Structured and accurate
- ✅ Easy to maintain
- ✅ Non-breaking
- ✅ Enables smart filtering

---

### Phase 3: Future Enhancement (3 months)
**Migrate to Approach 1 (Registry Metadata)**

1. Update TOOL_REGISTRY structure to support metadata
2. Migrate metadata from JSON to registry
3. Add migration guide for custom tools
4. Deprecate tools_metadata.json

**Benefits:**
- ✅ Single source of truth
- ✅ Auto-discoverable
- ✅ Type-safe (if using TypedDict)

---

## Example: "Click but not type" Use Case

### Current State (Broken)
```
User: "I want to create an agent that clicks elements but does NOT type text"

Agent-Creator: "I suggest: read_file, edit_file, agent_share_your_reasoning"
❌ Completely wrong - suggested file tools instead of GUI-CUB
```

### Phase 1 (LLM-Based)
```
User: "I want to create an agent that clicks elements but does NOT type text"

Agent-Creator: "Great! For clicking without typing, I suggest:
- desktop_mouse: Direct mouse control for clicking
- desktop_click_element_smart: Multi-strategy click with fallback
- ui_automation: Cross-platform UI element clicking

I did NOT include desktop_keyboard or desktop_shortcuts since you don't want typing."
✅ Works! LLM infers from tool names and guidelines
```

### Phase 2 (Metadata File)
```
User: "I want to create an agent that clicks elements but does NOT type text"

# Code:
suggest_tools("click but not type")
# Returns: ["desktop_mouse", "desktop_click_element_smart", "ui_automation"]
# (filtered by requires_typing=false)

Agent-Creator: "Based on your needs, I suggest:
- desktop_mouse: Mouse operations (move, click, drag, scroll)
  Use case: Clicking elements without typing
- desktop_click_element_smart: Multi-strategy click (UIA → OCR → VQA)
  Use case: Reliable clicking with auto-fallback
- ui_automation: Cross-platform UI automation
  Use case: Find and click UI elements

These tools do NOT require typing, as requested."
✅ Perfect! Programmatic filtering + rich descriptions
```

---

## Implementation Priority

### Immediate (This Sprint)
1. ✅ Add GUI-CUB tools to agent-creator system prompt (Approach 4)
2. ✅ Add usage examples for common scenarios
3. ✅ Test with real users

### Next Sprint
1. Create `tools_metadata.json` (Approach 2)
2. Implement `suggest_tools()` function
3. Auto-generate tool docs from metadata
4. Update agent-creator to use metadata

### Future (Q3 2025)
1. Migrate to TOOL_REGISTRY metadata (Approach 1)
2. Add metadata to all tools
3. Deprecate JSON file

---

## Conclusion

**Recommended Path:**
1. **Now:** Use LLM-based approach (quick win, no code changes)
2. **Soon:** Implement metadata file (structured, maintainable)
3. **Later:** Migrate to registry metadata (single source of truth)

This gives us immediate value while building toward a robust long-term solution.
