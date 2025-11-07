# GUI-CUB Type Stubs & Tool Discoverability Implementation Plan

## Executive Summary

**Problem:** 
1. No type stubs for GUI-CUB tools → Poor IDE experience for developers building custom agents
2. GUI-CUB tools are NOT documented in agent-creator → Users can't discover "click but don't type" tools
3. Platform-specific tools (macOS vs Windows) have no IDE hints

**Solution:**
1. Add 6 minimal type stub files (~230 lines total, 2-3 hours work)
2. Add GUI-CUB tool catalog to agent-creator's system prompt
3. Add tool discovery method for interactive tool selection

**Timeline:** 1-2 days
**ROI:** High - Enables organizational publishing with excellent DX

---

## Part 1: Type Stubs Implementation Plan

### Goal
Create minimal `.pyi` stub files for high-value GUI-CUB modules to provide:
- Instant IDE autocomplete
- Platform-specific tool hints (macOS/Windows)
- Type checking for custom agents
- Clear public API documentation

### Scope: 9 Core Stub Files (Expanded for Casual Users)

```
code_puppy/tools/gui_cub/
├── __init__.pyi                    # Main exports (40 lines)
├── screen_capture/__init__.pyi     # Screenshot tools (50 lines)
├── ocr/__init__.pyi                # OCR/text tools (40 lines)
├── mouse_control/__init__.pyi      # Mouse operations (40 lines) ← NEW
├── keyboard_control/__init__.pyi   # Keyboard/typing (40 lines) ← NEW
├── window_control/__init__.pyi     # Window management (35 lines) ← NEW
├── accessibility/__init__.pyi      # macOS-only tools (40 lines)
├── windows_automation/__init__.pyi # Windows-only tools (40 lines)
└── workflows.pyi                   # Workflow management (30 lines)
```

**Total:** ~355 lines of stubs (3-4 hours work)

**Rationale:** Casual users want to click elements and type into fields, so mouse/keyboard/window control stubs are essential.

---

### Step 1: Auto-Generate Initial Stubs (30 min)

```bash
# Install stubgen if needed
uv pip install mypy

# Auto-generate initial stubs
stubgen -p code_puppy.tools.gui_cub -o stubs/
stubgen -p code_puppy.tools.gui_cub.screen_capture -o stubs/
stubgen -p code_puppy.tools.gui_cub.ocr -o stubs/
stubgen -p code_puppy.tools.gui_cub.accessibility -o stubs/
stubgen -p code_puppy.tools.gui_cub.windows_automation -o stubs/
stubgen -p code_puppy.tools.gui_cub.workflows -o stubs/

# Move to correct locations
mv stubs/code_puppy/tools/gui_cub/__init__.pyi code_puppy/tools/gui_cub/
mv stubs/code_puppy/tools/gui_cub/screen_capture/__init__.pyi code_puppy/tools/gui_cub/screen_capture/
mv stubs/code_puppy/tools/gui_cub/ocr/__init__.pyi code_puppy/tools/gui_cub/ocr/
mv stubs/code_puppy/tools/gui_cub/accessibility/__init__.pyi code_puppy/tools/gui_cub/accessibility/
mv stubs/code_puppy/tools/gui_cub/windows_automation/__init__.pyi code_puppy/tools/gui_cub/windows_automation/
mv stubs/code_puppy/tools/gui_cub/workflows.pyi code_puppy/tools/gui_cub/

# Clean up
rm -rf stubs/
```

---

### Step 2: Create High-Quality Stubs (1-2 hours)

#### 2.1: `code_puppy/tools/gui_cub/screen_capture/__init__.pyi`

```python
"""Type stubs for screen_capture module.

Provides screenshot capture and analysis tools.
"""

from typing import Any, Literal
from .result_types import ScreenshotResult

def screenshot(
    save_path: str | None = ...,
    mode: Literal["full_screen", "active_window", "region"] = ...,
    x: int | None = ...,
    y: int | None = ...,
    width: int | None = ...,
    height: int | None = ...,
) -> ScreenshotResult:
    """Take a screenshot of screen or region.
    
    Args:
        save_path: Optional path to save screenshot
        mode: Capture mode (default: "full_screen")
        x: Left coordinate for region mode
        y: Top coordinate for region mode
        width: Width for region mode
        height: Height for region mode
    
    Returns:
        ScreenshotResult with success status and path
    """
    ...

async def screenshot_analyze(
    question: str | None = ...,
    mode: Literal["full_screen", "active_window", "region"] = ...,
    x: int | None = ...,
    y: int | None = ...,
    width: int | None = ...,
    height: int | None = ...,
) -> dict[str, Any]:
    """Take screenshot and analyze with VQA or OCR.
    
    Args:
        question: Optional question for VQA analysis. If None, uses OCR.
        mode: Capture mode
        x: Left coordinate for region mode
        y: Top coordinate for region mode
        width: Width for region mode
        height: Height for region mode
    
    Returns:
        Analysis results with extracted text or VQA answer
    """
    ...

def get_screen_size() -> tuple[int, int]:
    """Get screen dimensions.
    
    Returns:
        Tuple of (width, height) in pixels
    """
    ...
```

---

#### 2.2: `code_puppy/tools/gui_cub/ocr/__init__.pyi`

```python
"""Type stubs for OCR text extraction tools."""

from typing import Any

def extract_text(
    use_active_window: bool = ...,
    use_full_screen: bool = ...,
    x: int | None = ...,
    y: int | None = ...,
    width: int | None = ...,
    height: int | None = ...,
) -> dict[str, Any]:
    """Extract text from screen region using OCR.
    
    Args:
        use_active_window: Extract from active window only
        use_full_screen: Extract from entire screen
        x: Left coordinate for region
        y: Top coordinate for region
        width: Region width
        height: Region height
    
    Returns:
        Dict with full_text, words, confidence scores
    """
    ...

def find_text(
    search_text: str,
    use_active_window: bool = ...,
    fuzzy: bool = ...,
) -> dict[str, Any]:
    """Find text on screen using OCR.
    
    Args:
        search_text: Text to search for
        use_active_window: Search in active window only
        fuzzy: Enable fuzzy matching
    
    Returns:
        Dict with found status, matches, coordinates
    """
    ...

def verify_text(
    expected_text: str,
    use_active_window: bool = ...,
) -> dict[str, Any]:
    """Verify expected text appears on screen.
    
    Args:
        expected_text: Text that should be visible
        use_active_window: Check active window only
    
    Returns:
        Dict with verification status
    """
    ...
```

---

#### 2.3: `code_puppy/tools/gui_cub/accessibility/__init__.pyi`

```python
"""Type stubs for macOS Accessibility API tools.

⚠️ **macOS ONLY** - Not available on Windows or Linux.
Use windows_automation on Windows instead.
"""

import sys
from typing import Any

if sys.platform == "darwin":
    # Full macOS Accessibility API
    
    def find_accessible_element(
        role: str | None = ...,
        title: str | None = ...,
        description: str | None = ...,
        fuzzy: bool = ...,
    ) -> dict[str, Any]:
        """Find UI element using macOS Accessibility API.
        
        Args:
            role: Element role (e.g., 'AXButton', 'AXTextField')
            title: Element title/label
            description: Element description
            fuzzy: Enable fuzzy matching
        
        Returns:
            Dict with element info and coordinates
        """
        ...
    
    def list_accessible_elements(
        role: str | None = ...,
    ) -> list[dict[str, Any]]:
        """List all accessible elements in active window.
        
        Args:
            role: Filter by role (optional)
        
        Returns:
            List of element dictionaries
        """
        ...
    
    def click_accessible_element(
        role: str | None = ...,
        title: str | None = ...,
        fuzzy: bool = ...,
    ) -> dict[str, Any]:
        """Click UI element using Accessibility API.
        
        Args:
            role: Element role
            title: Element title/label
            fuzzy: Enable fuzzy matching
        
        Returns:
            Dict with click result
        """
        ...

else:
    # Stub for non-macOS platforms
    
    def find_accessible_element(
        role: str | None = ...,
        title: str | None = ...,
        description: str | None = ...,
        fuzzy: bool = ...,
    ) -> None:
        """❌ **macOS ONLY** - Not available on this platform.
        
        Use windows_automation.find_element() on Windows instead.
        """
        ...
    
    def list_accessible_elements(
        role: str | None = ...,
    ) -> None:
        """❌ **macOS ONLY** - Not available on this platform."""
        ...
    
    def click_accessible_element(
        role: str | None = ...,
        title: str | None = ...,
        fuzzy: bool = ...,
    ) -> None:
        """❌ **macOS ONLY** - Not available on this platform."""
        ...
```

---

#### 2.4: `code_puppy/tools/gui_cub/windows_automation/__init__.pyi`

```python
"""Type stubs for Windows UI Automation tools.

⚠️ **Windows ONLY** - Not available on macOS or Linux.
Use accessibility tools on macOS instead.
"""

import sys
from typing import Any

if sys.platform == "win32":
    # Full Windows UIA API
    
    def list_windows() -> dict[str, Any]:
        """List all open Windows windows using UIA.
        
        Returns:
            Dict with window titles and automation info
        """
        ...
    
    def focus_window(title: str) -> bool:
        """Focus a Windows window by title.
        
        Args:
            title: Window title to focus
        
        Returns:
            True if successful
        """
        ...
    
    def find_element(
        automation_id: str | None = ...,
        name: str | None = ...,
        control_type: str | None = ...,
        fuzzy: bool = ...,
    ) -> dict[str, Any]:
        """Find UI element using Windows UIA.
        
        Args:
            automation_id: Element automation ID
            name: Element name/label
            control_type: Control type (e.g., 'Button', 'Edit')
            fuzzy: Enable fuzzy matching
        
        Returns:
            Dict with element info and coordinates
        """
        ...
    
    def click_element(
        automation_id: str | None = ...,
        name: str | None = ...,
        control_type: str | None = ...,
        fuzzy: bool = ...,
    ) -> dict[str, Any]:
        """Click UI element using Windows UIA.
        
        Args:
            automation_id: Element automation ID
            name: Element name/label
            control_type: Control type
            fuzzy: Enable fuzzy matching
        
        Returns:
            Dict with click result
        """
        ...

else:
    # Stub for non-Windows platforms
    
    def list_windows() -> None:
        """❌ **Windows ONLY** - Not available on this platform.
        
        Use window_control.list_windows() on macOS instead.
        """
        ...
    
    def focus_window(title: str) -> None:
        """❌ **Windows ONLY** - Not available on this platform."""
        ...
    
    def find_element(
        automation_id: str | None = ...,
        name: str | None = ...,
        control_type: str | None = ...,
        fuzzy: bool = ...,
    ) -> None:
        """❌ **Windows ONLY** - Not available on this platform."""
        ...
    
    def click_element(
        automation_id: str | None = ...,
        name: str | None = ...,
        control_type: str | None = ...,
        fuzzy: bool = ...,
    ) -> None:
        """❌ **Windows ONLY** - Not available on this platform."""
        ...
```

---

#### 2.5: `code_puppy/tools/gui_cub/workflows.pyi`

```python
"""Type stubs for workflow management tools."""

from typing import Any

async def save_workflow(
    name: str,
    content: str,
    format: str = ...,
) -> dict[str, Any]:
    """Save a GUI-Cub workflow for reuse.
    
    Args:
        name: Workflow name (e.g., 'login_flow')
        content: YAML workflow content
        format: 'yaml' or 'markdown'
    
    Returns:
        Dict with success status and path
    """
    ...

async def list_workflows() -> dict[str, Any]:
    """List all saved workflows.
    
    Returns:
        Dict with workflow names and metadata
    """
    ...

async def read_workflow(name: str) -> dict[str, Any]:
    """Read a saved workflow.
    
    Args:
        name: Workflow name
    
    Returns:
        Dict with workflow content
    """
    ...
```

---

#### 2.6: `code_puppy/tools/gui_cub/__init__.pyi`

```python
"""Type stubs for GUI-CUB desktop automation tools.

Main entry point for all GUI-CUB functionality.
"""

# Re-export from submodules
from .screen_capture import screenshot, screenshot_analyze, get_screen_size
from .ocr import extract_text, find_text, verify_text
from .workflows import save_workflow, list_workflows, read_workflow

# Platform-specific exports
import sys

if sys.platform == "darwin":
    from .accessibility import (
        find_accessible_element,
        list_accessible_elements,
        click_accessible_element,
    )

if sys.platform == "win32":
    from .windows_automation import (
        list_windows,
        focus_window,
        find_element,
        click_element,
    )

__all__ = [
    # Screenshot
    "screenshot",
    "screenshot_analyze",
    "get_screen_size",
    # OCR
    "extract_text",
    "find_text",
    "verify_text",
    # Workflows
    "save_workflow",
    "list_workflows",
    "read_workflow",
    # Platform-specific (conditionally available)
    "find_accessible_element",
    "list_accessible_elements",
    "click_accessible_element",
    "list_windows",
    "focus_window",
    "find_element",
    "click_element",
]
```

---

### Step 3: Test Stubs (30 min)

```bash
# Verify stubs work with mypy
uv run mypy code_puppy/tools/gui_cub/ --check-untyped-defs

# Test IDE autocomplete (manual)
# Open VSCode, type:
# from code_puppy.tools.gui_cub import screenshot
# screenshot(  # ← Should show instant autocomplete

# Verify platform-specific hints
# On macOS: import accessibility should work
# On macOS: import windows_automation should show "Windows only" error
```

---

### Step 4: Document Stubs (15 min)

Add to `docs/gui-cub/README.md`:

```markdown
## Type Stubs

GUI-CUB provides type stubs (`.pyi` files) for better IDE support:

✅ **Instant autocomplete** for all public APIs
✅ **Platform-specific hints** (Windows vs macOS)
✅ **Type checking** with mypy/pyright

### Available Stubs

- `screen_capture/__init__.pyi` - Screenshot and analysis tools
- `ocr/__init__.pyi` - OCR text extraction
- `accessibility/__init__.pyi` - macOS Accessibility API (macOS only)
- `windows_automation/__init__.pyi` - Windows UIA (Windows only)
- `workflows.pyi` - Workflow management

### Type Checking

```bash
# Check types in your custom agent
mypy my_custom_agent.py --check-untyped-defs
```

### Platform-Specific Hints

Stubs provide clear platform availability:

```python
# On macOS - full API
from code_puppy.tools.gui_cub.accessibility import find_accessible_element
result = find_accessible_element(role="AXButton", title="Submit")

# On Windows - IDE shows "macOS only" error before runtime
from code_puppy.tools.gui_cub.accessibility import find_accessible_element
# ❌ IDE warning: "macOS ONLY - Not available on this platform"
```
```

---

## Part 2: Tool Discoverability Brainstorm (Separate Implementation)

**NOTE:** Agent-creator modifications are OUT OF SCOPE for this implementation.
Tool discovery solutions will be brainstormed in a separate document for future implementation.

See: `docs/gui-cub/TOOL_DISCOVERY_BRAINSTORM.md`

---

## Part 2 (ARCHIVED): Agent-Creator Tool Discoverability

### Goal
Enable users to discover GUI-CUB tools when creating agents.
Example: "I want to click elements but NOT type" → Agent-creator suggests mouse/UI automation tools.

### Current Problem

**Agent-creator's system prompt has NO GUI-CUB documentation.**

It only documents:
- File operations (list_files, read_file, edit_file, delete_file, grep)
- Command execution (agent_run_shell_command)
- Agent management (list_agents, invoke_agent)
- Browser automation (browser_*)

**GUI-CUB tools are completely invisible to agent-creator.**

---

### Solution: Add GUI-CUB Tool Catalog

#### Step 1: Add Tool Categorization (30 min)

Add to `agent_creator_agent.py` system prompt after line 115:

```python
### 🖱️ **Desktop Automation (GUI-CUB)** (for agents interacting with desktop apps):

**Setup & Configuration:**
- `gui_cub_config` - Get/set GUI-CUB configuration (calibration, settings)
- `gui_cub_calibrate` - Calibrate screen coordinates for accuracy
- `gui_cub_validate_config` - Validate current configuration

**Screenshots & Visual Analysis:**
- `desktop_screenshot` - Take screenshots with optional analysis
- `desktop_grid_calibration` - Calibrate grid overlay for coordinate debugging
- `save_debug_screenshot` - Save debug screenshots with annotations

**Text Recognition (OCR):**
- `desktop_ocr` - Extract text from screen (extract_text, find_text, verify_text)
- `desktop_find_text` - Find specific text on screen using OCR
- `desktop_verify_text` - Verify expected text appears

**Mouse Control:**
- `desktop_mouse` - Mouse operations (move, click, drag, scroll, get_position)
- `desktop_click_debugging` - Debug click operations (highlight, verify coordinates)
- `desktop_click_element_smart` - Multi-strategy click with auto-fallback (UIA → OCR → VQA)

**Keyboard Control:**
- `desktop_keyboard` - Keyboard operations (type, press, hotkey, hold, release)
- `desktop_shortcuts` - Common shortcuts (copy, paste, cut, save, undo, etc.)

**UI Element Interaction (Cross-Platform):**
- `ui_automation` - Cross-platform UI automation (list_windows, find_element, click_element)

**macOS-Specific (Accessibility API):**
- `macos_automation` - macOS Accessibility API (find, list, click elements)
  ⚠️ **macOS ONLY** - Not available on Windows/Linux

**Windows-Specific (UI Automation):**
- `windows_automation` - Windows UIA (focus_window, find, click, list_elements)
  ⚠️ **Windows ONLY** - Not available on macOS/Linux

**Visual Question Answering (VQA):**
- `desktop_vqa` - AI-powered visual element location (two-stage coarse-to-fine)

**Workflow Management:**
- `gui_cub_workflows` - Workflow management (save, list, read workflows)
- `gui_cub_execute_workflow` - Execute saved YAML workflows
- `gui_cub_append_to_knowledge_base` - Save knowledge for reuse

**Window Control:**
- `desktop_window_control` - Window operations (sleep, alert, confirm, focus_window)
```

---

#### Step 2: Add Tool Suggestion Examples (15 min)

Add to tool suggestion examples section:

```python
**For "Desktop automation agent":** → Suggest `desktop_screenshot`, `ui_automation`, `desktop_keyboard`, `desktop_mouse`, `gui_cub_workflows`, `agent_share_your_reasoning`
**For "Click-only agent (no typing)":** → Suggest `desktop_mouse`, `desktop_click_element_smart`, `ui_automation`, `desktop_screenshot`, `agent_share_your_reasoning`
**For "OCR text extractor":** → Suggest `desktop_ocr`, `desktop_screenshot`, `read_file`, `edit_file`, `agent_share_your_reasoning`
**For "Workflow executor":** → Suggest `gui_cub_execute_workflow`, `gui_cub_workflows`, `desktop_screenshot`, `agent_share_your_reasoning`
**For "macOS automation":** → Suggest `macos_automation`, `desktop_screenshot`, `desktop_keyboard`, `agent_share_your_reasoning`
**For "Windows automation":** → Suggest `windows_automation`, `desktop_screenshot`, `desktop_keyboard`, `agent_share_your_reasoning`
```

---

#### Step 3: Add Interactive Tool Discovery Method (1 hour)

Add new agent method to `agent_creator_agent.py`:

```python
class AgentCreatorAgent(BaseAgent):
    # ... existing code ...
    
    def get_tool_suggestions(self, user_intent: str) -> list[str]:
        """Suggest tools based on user's stated intent.
        
        Args:
            user_intent: What the user wants the agent to do
        
        Returns:
            List of suggested tool names
        """
        intent_lower = user_intent.lower()
        suggestions = []
        
        # Always include reasoning
        suggestions.append("agent_share_your_reasoning")
        
        # Desktop automation keywords
        if any(word in intent_lower for word in ["desktop", "gui", "window", "click", "type", "mouse", "keyboard"]):
            suggestions.append("desktop_screenshot")
            
            if any(word in intent_lower for word in ["click", "mouse"]):
                suggestions.extend(["desktop_mouse", "desktop_click_element_smart", "ui_automation"])
            
            if any(word in intent_lower for word in ["type", "keyboard", "text input"]):
                suggestions.extend(["desktop_keyboard", "desktop_shortcuts"])
            
            if "ocr" in intent_lower or "text" in intent_lower or "read" in intent_lower:
                suggestions.append("desktop_ocr")
            
            if "workflow" in intent_lower:
                suggestions.extend(["gui_cub_workflows", "gui_cub_execute_workflow"])
            
            if "macos" in intent_lower or "mac" in intent_lower:
                suggestions.append("macos_automation")
            
            if "windows" in intent_lower or "win" in intent_lower:
                suggestions.append("windows_automation")
        
        # File operations keywords
        if any(word in intent_lower for word in ["file", "read", "write", "edit", "code"]):
            suggestions.extend(["read_file", "list_files", "edit_file"])
        
        # Command execution keywords
        if any(word in intent_lower for word in ["command", "shell", "terminal", "script", "run"]):
            suggestions.append("agent_run_shell_command")
        
        # Browser keywords
        if any(word in intent_lower for word in ["browser", "web", "url", "page"]):
            suggestions.extend(["browser_initialize", "browser_navigate", "browser_click"])
        
        # Agent orchestration keywords
        if any(word in intent_lower for word in ["agent", "delegate", "invoke"]):
            suggestions.extend(["list_agents", "invoke_agent"])
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(suggestions))
```

Then update system prompt to use this method:

```python
2. **🔧 ALWAYS ASK: "What should this agent be able to do?"**
3. **🎯 SUGGEST TOOLS** based on their answer:
   - Use get_tool_suggestions() to generate initial recommendations
   - Explain WHY each tool is relevant
   - Example: "Since you want to click elements, I suggest desktop_click_element_smart for reliable clicking with auto-fallback"
```

---

## Testing Plan

### Test 1: Type Stubs Work (15 min)

```bash
# Create test agent file
cat > test_gui_cub_agent.py << 'EOF'
from code_puppy.tools.gui_cub import screenshot, find_text
from code_puppy.tools.gui_cub.accessibility import find_accessible_element

# Should show type errors on wrong types
result = screenshot(mode="invalid")  # Error: invalid literal
result = screenshot(x="not a number")  # Error: expected int

# Should autocomplete correctly
result = screenshot(  # ← IDE should show all parameters
EOF

# Run type checker
mypy test_gui_cub_agent.py
```

### Test 2: Agent-Creator Suggests GUI-CUB Tools (30 min)

```bash
# Start agent-creator
/agent agent-creator

# Test 1: Click-only agent
> I want to create an agent that clicks UI elements but does NOT type text

# Expected: Should suggest desktop_mouse, desktop_click_element_smart, ui_automation
# Should NOT suggest desktop_keyboard

# Test 2: OCR agent
> I want to create an agent that extracts text from screenshots

# Expected: Should suggest desktop_ocr, desktop_screenshot

# Test 3: macOS automation
> I want to create a macOS automation agent

# Expected: Should suggest macos_automation, desktop_screenshot
# Should warn about macOS-only tools
```

---

## Timeline

### Day 1: Type Stubs (4 hours)

- ✅ 0.5h: Auto-generate initial stubs
- ✅ 2.0h: Manually refine stubs (platform-specific, better docs)
- ✅ 0.5h: Test stubs with mypy/IDE
- ✅ 1.0h: Document stubs in README

### Day 2: Tool Discoverability (4 hours)

- ✅ 0.5h: Add GUI-CUB tool catalog to agent-creator
- ✅ 0.25h: Add tool suggestion examples
- ✅ 1.0h: Implement get_tool_suggestions() method
- ✅ 0.5h: Test agent-creator suggestions
- ✅ 1.0h: Update documentation
- ✅ 0.75h: Buffer for fixes

**Total:** 8 hours (1-2 days)

---

## Success Criteria

### Type Stubs
✅ IDE autocomplete shows all parameters instantly
✅ Platform-specific tools show "macOS/Windows only" warnings
✅ mypy type checking catches type errors
✅ All 6 stub files pass mypy validation

### Tool Discoverability
✅ Agent-creator mentions GUI-CUB tools in available tools list
✅ Agent-creator suggests correct tools based on user intent
✅ User asking for "click but not type" gets mouse/UI automation tools
✅ User asking for "OCR" gets desktop_ocr tools
✅ Platform-specific tools are clearly marked

---

## Next Steps

1. Review and approve this plan
2. Execute Day 1 (type stubs)
3. Test stubs with real IDE
4. Execute Day 2 (tool discoverability)
5. Test agent-creator with real scenarios
6. Document for organizational publishing
7. Publish to internal registry

---

## ROI Summary

**Investment:** 8 hours over 1-2 days

**Returns:**
- ✅ Better IDE experience for all org developers
- ✅ Faster agent development (instant autocomplete)
- ✅ Fewer platform-specific bugs (IDE warns before runtime)
- ✅ Easier tool discovery (agent-creator suggests tools)
- ✅ Type-safe agent code (mypy catches errors)
- ✅ Professional organizational publishing

**Recommendation:** HIGH ROI - Do it before org publishing.
