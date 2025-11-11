# GUI-Cub Tooling Recommendations

**Date:** 2025-01-10  
**Context:** Improvements based on Windows Element Tree testing and debugging with Python scripts  
**Priority:** High - Improves developer experience and testing workflow

---

## Executive Summary

During Windows Element Tree testing, we identified several gaps between the gui-cub library's agent-tool API and the needs of direct Python script testing. This document recommends improvements to make gui-cub more accessible for both agent-based automation AND standalone script testing.

### Key Issues Found

1. ❌ **Import path errors** - Fixed (window_control importing from wrong path)
2. ❌ **Window focus fails for minimized windows** - Fixed (now searches minimized windows)
3. ⚠️ **Parameter naming inconsistency** - `title` vs `name` confusion across functions
4. ⚠️ **No direct script-friendly API** - All functions require RunContext from pydantic-ai
5. ⚠️ **Missing testing utilities** - No built-in helpers for common test scenarios
6. ⚠️ **Incomplete error messages** - Errors swallowed, hard to debug failures

---

## 1. API Improvements

### 1.1 Dual API Pattern (Agent + Direct)

**Problem:**  
Current API requires pydantic-ai RunContext, making direct script usage awkward:

```python
# ❌ CURRENT - Doesn't work in scripts
from code_puppy.tools.gui_cub.windows_automation import list_elements_in_window

result = list_elements_in_window()  # ERROR: Missing 'context' parameter
```

**Recommendation:**  
Provide BOTH agent tools AND direct functions:

```python
# code_puppy/tools/gui_cub/windows_automation/api.py
"""
Direct API for standalone scripts (no agent required).
"""

def list_elements(
    window_title: str | None = None,
    pid: int | None = None,
    include_minimized: bool = True,
) -> ElementListResult:
    """
    List all elements in a window (direct API, no agent required).
    
    Args:
        window_title: Focus this window first (optional)
        pid: Target specific process (optional)
        include_minimized: Include minimized windows in search
    
    Returns:
        ElementListResult with element tree
    
    Example:
        >>> from code_puppy.tools.gui_cub.windows_automation.api import list_elements
        >>> result = list_elements(window_title="Calculator")
        >>> print(f"Found {result.total_elements} elements")
    """
    # Delegate to core.list_elements_in_window()
    ...


def find_element(
    name: str | None = None,
    control_type: str | None = None,
    automation_id: str | None = None,
    fuzzy: bool = False,
) -> ElementSearchResult:
    """Find element (direct API, no agent required)."""
    ...


def click_element(
    name: str | None = None,
    control_type: str | None = None,
    automation_id: str | None = None,
) -> ElementClickResult:
    """Click element (direct API, no agent required)."""
    ...
```

**Usage in scripts:**
```python
# ✅ NEW - Works in standalone scripts!
from code_puppy.tools.gui_cub.windows_automation.api import (
    list_elements,
    find_element,
    click_element,
)

result = list_elements(window_title="Calculator")
print(f"Found {result.total_elements} elements")
```

**File to create:**
- `code_puppy/tools/gui_cub/windows_automation/api.py` - Direct API
- `code_puppy/tools/gui_cub/windows_automation/__init__.py` - Export api functions

**Priority:** 🔥 HIGH - Enables standalone script testing

---

### 1.2 Parameter Naming Standardization

**Problem:**  
Inconsistent parameter names across functions:

```python
# windows_automation/core.py
find_element(title="Plus", ...)  # Uses 'title'

# windows_automation/tools.py
windows_find_element(title="Plus", ...)  # Also 'title'

# But elements have 'name' attribute!
elem.get('name')  # Returns element name
```

**Recommendation:**  
Standardize on `name` everywhere (matches Windows UI Automation API):

```python
# ✅ STANDARDIZED
def find_element(
    name: str | None = None,  # Was: title
    control_type: str | None = None,
    class_name: str | None = None,
    automation_id: str | None = None,  # Was: auto_id
    fuzzy: bool = False,
) -> ElementSearchResult:
    """
    Find element by name (Windows UI Automation 'Name' property).
    
    Args:
        name: Element name (e.g., "Plus", "Zero", "File")
        control_type: Control type (e.g., "Button", "MenuItem")
        automation_id: Unique automation identifier
    """
    ...
```

**Breaking Change:** Yes, but improves consistency  
**Migration Path:** Add deprecation warnings for `title` parameter

```python
def find_element(
    name: str | None = None,
    title: str | None = None,  # DEPRECATED
    ...
):
    if title is not None:
        import warnings
        warnings.warn(
            "Parameter 'title' is deprecated, use 'name' instead",
            DeprecationWarning,
            stacklevel=2,
        )
        name = title
    ...
```

**Files to update:**
- `code_puppy/tools/gui_cub/windows_automation/core.py`
- `code_puppy/tools/gui_cub/windows_automation/tools.py`
- Documentation and examples

**Priority:** 🟡 MEDIUM - Quality of life improvement

---

### 1.3 Window Focus Auto-Detection

**Problem:**  
Test scripts manually open apps and hope they're focused:

```python
# ❌ CURRENT - Fragile
import subprocess
import time

subprocess.Popen("calc.exe")
time.sleep(2)  # Hope it's ready?
result = list_elements_in_window()  # Might fail if wrong window focused!
```

**Recommendation:**  
Add automatic window focusing to element functions:

```python
# ✅ NEW - Robust
def list_elements(
    window_title: str | None = None,  # Auto-focus this window
    auto_focus: bool = True,  # Auto-focus if window_title provided
) -> ElementListResult:
    """
    List elements in a window.
    
    If window_title is provided and auto_focus=True, automatically
    focuses that window before listing elements.
    """
    if window_title and auto_focus:
        focus_result = focus_window(window_title=window_title)
        if not focus_result:
            return ElementListResult(
                success=False,
                error=f"Could not focus window: {window_title}"
            )
        time.sleep(0.5)  # Let focus settle
    
    # Proceed with listing
    ...
```

**Usage:**
```python
# Automatically focuses Calculator before listing
result = list_elements(window_title="Calculator")
```

**Priority:** 🔥 HIGH - Improves test reliability

---

## 2. Testing Utilities

### 2.1 Test Helper Module

**Problem:**  
Every test script reimplements the same utilities:

```python
# Duplicated in test_runner.py, test_windows_quick.py, etc.
def open_application(app_command, app_name, wait_time=2.0):
    subprocess.Popen(app_command, shell=True)
    time.sleep(wait_time)
    return True
```

**Recommendation:**  
Create `code_puppy/tools/gui_cub/testing_utils.py`:

```python
"""
Testing utilities for gui-cub automation scripts.
"""

import subprocess
import time
from typing import Literal

from .windows_automation.api import list_elements, find_element
from .result_types import ElementListResult, ElementSearchResult


def launch_and_focus(
    app_command: str,
    app_name: str,
    wait_time: float = 2.0,
    verify_launch: bool = True,
) -> bool:
    """
    Launch an application and wait for it to start.
    
    Args:
        app_command: Command to run (e.g., "calc.exe")
        app_name: Window title to verify (e.g., "Calculator")
        wait_time: Seconds to wait after launch
        verify_launch: Verify window exists after launch
    
    Returns:
        True if successfully launched and focused
    
    Example:
        >>> launch_and_focus("calc.exe", "Calculator")
        True
    """
    try:
        subprocess.Popen(app_command, shell=True)
        time.sleep(wait_time)
        
        if verify_launch:
            from .windows_automation.core import focus_window
            return focus_window(window_title=app_name)
        
        return True
    except Exception as e:
        print(f"Failed to launch {app_name}: {e}")
        return False


def verify_button_quality(
    buttons: list[dict],
    min_percentage_with_names: float = 80.0,
) -> dict:
    """
    Analyze button quality (labeling percentage).
    
    Args:
        buttons: List of button elements
        min_percentage_with_names: Minimum acceptable percentage
    
    Returns:
        Dict with quality metrics
    """
    total = len(buttons)
    with_names = sum(1 for b in buttons if b.get('name', '').strip())
    percentage = (with_names / total * 100) if total > 0 else 0
    
    return {
        'total': total,
        'with_names': with_names,
        'without_names': total - with_names,
        'percentage': percentage,
        'passes_threshold': percentage >= min_percentage_with_names,
    }


def verify_automation_id_coverage(
    elements: list[dict],
    min_percentage: float = 50.0,
) -> dict:
    """
    Analyze AutomationId coverage.
    """
    total = len(elements)
    with_auto_id = sum(1 for e in elements if e.get('automation_id'))
    percentage = (with_auto_id / total * 100) if total > 0 else 0
    
    return {
        'total': total,
        'with_automation_id': with_auto_id,
        'percentage': percentage,
        'passes_threshold': percentage >= min_percentage,
    }


def test_find_elements(
    element_names: list[str],
    control_type: str = "Button",
) -> dict:
    """
    Test finding multiple elements by name.
    
    Args:
        element_names: List of element names to find
        control_type: Control type to search for
    
    Returns:
        Dict with test results
    """
    results = []
    found_count = 0
    
    for name in element_names:
        result = find_element(name=name, control_type=control_type, fuzzy=True)
        found = result.get('found', False)
        if found:
            found_count += 1
        
        results.append({
            'name': name,
            'found': found,
            'position': (result.get('x'), result.get('y')) if found else None,
        })
    
    success_rate = (found_count / len(element_names) * 100) if element_names else 0
    
    return {
        'tested': len(element_names),
        'found': found_count,
        'not_found': len(element_names) - found_count,
        'success_rate': success_rate,
        'results': results,
    }


class TestCase:
    """
    Simple test case runner for gui-cub tests.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def test(
        self,
        description: str,
        condition: bool,
        error_msg: str = "",
    ):
        """Run a test assertion."""
        if condition:
            self.passed += 1
            status = "✅ PASS"
        else:
            self.failed += 1
            status = "❌ FAIL"
        
        result = f"{status}: {description}"
        if not condition and error_msg:
            result += f" - {error_msg}"
        
        print(result)
        self.results.append({'description': description, 'passed': condition})
    
    def summary(self):
        """Print test summary."""
        total = self.passed + self.failed
        print(f"\n{self.name} Summary:")
        print(f"  Passed: {self.passed}/{total}")
        print(f"  Failed: {self.failed}/{total}")
        print(f"  Success Rate: {self.passed/total*100:.1f}%" if total > 0 else "")
        return self.failed == 0
```

**Usage in test scripts:**
```python
#!/usr/bin/env python
from code_puppy.tools.gui_cub.testing_utils import (
    launch_and_focus,
    verify_button_quality,
    test_find_elements,
    TestCase,
)
from code_puppy.tools.gui_cub.windows_automation.api import list_elements

# Launch Calculator
launch_and_focus("calc.exe", "Calculator")

# Test element listing
test = TestCase("Calculator Button Test")
result = list_elements()

test.test(
    "Found elements",
    result.get('success') and result.get('total_elements', 0) > 0
)

buttons = [e for e in result.get('elements', []) if e.get('control_type') == 'Button']
quality = verify_button_quality(buttons, min_percentage_with_names=80.0)

test.test(
    f"Button quality ({quality['percentage']:.1f}% with names)",
    quality['passes_threshold']
)

test.summary()
```

**File to create:**
- `code_puppy/tools/gui_cub/testing_utils.py`

**Priority:** 🔥 HIGH - Reduces test script duplication

---

### 2.2 Element Tree Dumper

**Problem:**  
`test_notepad_deep_audit.py` manually implements element tree traversal.

**Recommendation:**  
Add built-in element tree dumping:

```python
# code_puppy/tools/gui_cub/windows_automation/api.py

def dump_element_tree(
    window_title: str | None = None,
    max_depth: int = 5,
    output_file: str | None = None,
    format: Literal["text", "json", "yaml"] = "text",
) -> str:
    """
    Dump complete element tree for debugging.
    
    Args:
        window_title: Target window (None for active)
        max_depth: Maximum traversal depth
        output_file: Save to file (optional)
        format: Output format (text, json, yaml)
    
    Returns:
        Formatted element tree as string
    """
    ...
```

**Usage:**
```python
# Dump Calculator element tree
from code_puppy.tools.gui_cub.windows_automation.api import dump_element_tree

tree = dump_element_tree(
    window_title="Calculator",
    output_file="calculator_tree.txt"
)
print(tree)
```

**Priority:** 🟡 MEDIUM - Helpful for debugging

---

## 3. Error Handling Improvements

### 3.1 Verbose Error Messages

**Problem:**  
Errors are silently swallowed:

```python
# windows_automation/core.py
try:
    # ... element finding logic ...
except Exception:  # ❌ Silent failure!
    pass

return ElementSearchResult(success=True, found=False)
```

**Recommendation:**  
Add detailed error messages:

```python
try:
    # ... element finding logic ...
except Exception as e:
    error_msg = f"Element search failed: {type(e).__name__}: {e}"
    return ElementSearchResult(
        success=False,
        found=False,
        error=error_msg,
    )
```

**Also add debug logging:**
```python
import logging

logger = logging.getLogger(__name__)

try:
    # ... element finding logic ...
except Exception as e:
    logger.debug(f"Element search error: {e}", exc_info=True)
    return ElementSearchResult(
        success=False,
        found=False,
        error=str(e),
    )
```

**Files to update:**
- `code_puppy/tools/gui_cub/windows_automation/core.py`
- All `try/except Exception: pass` blocks

**Priority:** 🔥 HIGH - Critical for debugging

---

### 3.2 Result Validation

**Problem:**  
Functions return success=True even when nothing found:

```python
# ❌ Confusing!
return ElementSearchResult(success=True, found=False)
# Success but not found? Which is it?
```

**Recommendation:**  
Clarify result semantics:

```python
return ElementSearchResult(
    success=True,   # API call succeeded (no crashes)
    found=False,    # Element was not found
    error=None,     # No errors occurred
)

# vs

return ElementSearchResult(
    success=False,  # API call failed (crashed/error)
    found=False,    # Can't be found if API failed
    error="pywinauto not installed",
)
```

**Add docstrings:**
```python
class ElementSearchResult:
    """
    Result from element search operation.
    
    Attributes:
        success: True if API call completed without errors
        found: True if element was located
        error: Error message if success=False
    
    Examples:
        # Successful search, element found
        ElementSearchResult(success=True, found=True, error=None)
        
        # Successful search, element NOT found (normal)
        ElementSearchResult(success=True, found=False, error=None)
        
        # Failed search (exception/crash)
        ElementSearchResult(success=False, found=False, error="...")
    """
```

**Priority:** 🟡 MEDIUM - Improves clarity

---

## 4. Documentation Improvements

### 4.1 Standalone Script Examples

**Problem:**  
No examples for using gui-cub outside of agent context.

**Recommendation:**  
Add `docs/gui-cub/examples/` directory:

```
docs/gui-cub/examples/
├── basic_windows_automation.py
├── calculator_test.py
├── element_tree_dump.py
└── README.md
```

**Example: basic_windows_automation.py**
```python
#!/usr/bin/env python
"""
Basic Windows automation without agent.

Demonstrates:
- Launching applications
- Finding elements
- Clicking elements
- Listing element trees
"""

from code_puppy.tools.gui_cub.testing_utils import launch_and_focus
from code_puppy.tools.gui_cub.windows_automation.api import (
    list_elements,
    find_element,
    click_element,
)

# Launch Calculator
if launch_and_focus("calc.exe", "Calculator"):
    print("✅ Calculator launched")

# List all elements
result = list_elements()
print(f"Found {result.total_elements} elements")

# Find specific button
plus_result = find_element(name="Plus", control_type="Button")
if plus_result.found:
    print(f"✅ Found Plus button at ({plus_result.x}, {plus_result.y})")

# Click the Plus button
click_result = click_element(name="Plus", control_type="Button")
if click_result.success:
    print("✅ Clicked Plus button")
```

**Priority:** 🟡 MEDIUM - Improves adoption

---

### 4.2 API Reference Documentation

**Recommendation:**  
Generate API docs with Sphinx:

```bash
cd docs
sphinx-apidoc -o api ../code_puppy/tools/gui_cub
sphinx-build -b html . _build
```

Add to `docs/gui-cub/API_REFERENCE.md`:

```markdown
# GUI-Cub API Reference

## Windows Automation

### Direct API (No Agent)

```python
from code_puppy.tools.gui_cub.windows_automation.api import (
    list_elements,
    find_element,
    click_element,
    focus_window,
)
```

#### list_elements()

List all elements in the active window.

**Parameters:**
- `window_title` (str, optional): Auto-focus this window first
- `auto_focus` (bool): Auto-focus if window_title provided (default: True)

**Returns:**
- `ElementListResult`: Element tree with metadata

**Example:**
```python
result = list_elements(window_title="Calculator")
for elem in result.elements:
    print(f"{elem['control_type']}: {elem['name']}")
```

...
```

**Priority:** 🟡 MEDIUM - Improves discoverability

---

## 5. Implementation Roadmap

### Phase 1: Critical Fixes (Week 1)

✅ **COMPLETED:**
- [x] Fix import path error in window_control/core.py
- [x] Fix window focus for minimized windows

🔥 **HIGH PRIORITY:**
- [ ] Create direct API module (`windows_automation/api.py`)
- [ ] Add testing_utils.py module
- [ ] Improve error messages (remove silent failures)
- [ ] Add auto-focus to element functions

### Phase 2: Quality Improvements (Week 2)

🟡 **MEDIUM PRIORITY:**
- [ ] Standardize parameter names (`title` → `name`)
- [ ] Add element tree dumper
- [ ] Improve result validation
- [ ] Add standalone script examples

### Phase 3: Documentation (Week 3)

🟡 **MEDIUM PRIORITY:**
- [ ] Generate API reference docs
- [ ] Update testing guide with new utilities
- [ ] Create migration guide for breaking changes

---

## 6. Breaking Changes Summary

### 6.1 Parameter Renames

| Old Parameter | New Parameter | Functions Affected |
|--------------|---------------|-------------------|
| `title` | `name` | find_element, click_element |
| `auto_id` | `automation_id` | find_element, click_element |

**Migration:** Add deprecation warnings, support both for 2 releases.

### 6.2 Error Return Changes

Before:
```python
try:
    ...
except Exception:
    pass
return ElementSearchResult(success=True, found=False)
```

After:
```python
try:
    ...
except Exception as e:
    return ElementSearchResult(success=False, found=False, error=str(e))
```

**Impact:** Scripts checking `success=True` may now see `success=False` on errors.

---

## 7. Testing Validation

### 7.1 Unit Tests to Add

```python
# tests/gui_cub/test_windows_automation_api.py

def test_direct_api_no_context():
    """Test direct API works without RunContext."""
    from code_puppy.tools.gui_cub.windows_automation.api import list_elements
    
    result = list_elements()  # Should not require context
    assert result is not None


def test_parameter_deprecation():
    """Test deprecated parameters show warnings."""
    import warnings
    from code_puppy.tools.gui_cub.windows_automation.api import find_element
    
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        find_element(title="Plus")  # Deprecated
        assert len(w) == 1
        assert "deprecated" in str(w[0].message).lower()
```

### 7.2 Integration Tests

```python
# tests/gui_cub/test_calculator_integration.py

def test_full_calculator_workflow():
    """Test complete workflow on Calculator."""
    from code_puppy.tools.gui_cub.testing_utils import launch_and_focus
    from code_puppy.tools.gui_cub.windows_automation.api import (
        list_elements,
        find_element,
    )
    
    # Launch
    assert launch_and_focus("calc.exe", "Calculator")
    
    # List
    result = list_elements()
    assert result.success
    assert result.total_elements > 0
    
    # Find
    plus = find_element(name="Plus", control_type="Button")
    assert plus.found
```

---

## 8. Success Metrics

### Adoption Metrics

- ✅ Test scripts can import and use api.py directly
- ✅ Test scripts use testing_utils instead of duplicating code
- ✅ No more silent exception swallowing
- ✅ Error messages are actionable

### Quality Metrics

- 📊 API coverage: >80% of agent tools have direct API equivalents
- 📊 Documentation: All public functions have docstrings with examples
- 📊 Error handling: <5% of exceptions silently caught
- 📊 Test coverage: >70% for windows_automation module

---

## 9. References

### Files Analyzed

- `test_runner.py` - Automated test suite
- `test_windows_quick.py` - Quick validation script
- `test_notepad_deep_audit.py` - Deep element tree analysis
- `code_puppy/tools/gui_cub/windows_automation/core.py` - Core implementation
- `code_puppy/tools/gui_cub/windows_automation/tools.py` - Agent tools
- `code_puppy/tools/gui_cub/window_control/core.py` - Window management
- `docs/gui-cub/testing/WINDOWS_ELEMENT_TREE_TESTING_GUIDE.md` - Testing guide

### Related Issues

- Import path error (FIXED)
- Window focus for minimized windows (FIXED)
- Compaction bug (separate issue)
- AutomationId attribute mapping (separate issue)

---

## Conclusion

These recommendations emerged from real-world testing and debugging scenarios. Implementing them will:

1. ✅ Make gui-cub usable in standalone scripts
2. ✅ Reduce test script duplication
3. ✅ Improve error visibility and debugging
4. ✅ Standardize API consistency
5. ✅ Enhance documentation and examples

Priority should be given to:
1. Direct API creation (api.py)
2. Testing utilities module
3. Error handling improvements

These changes maintain backward compatibility where possible and provide clear migration paths for breaking changes.

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-10  
**Author:** Code Puppy Testing Team 🐶
