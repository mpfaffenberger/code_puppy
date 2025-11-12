# GUI Cub Windows Focus Detection Tools

## Overview

Two new tools have been added to `code_puppy/tools/rpa/windows_automation.py` to support field focus detection and element value verification on Windows.

## Tools Added

### 1. `windows_get_focused_element`

**Purpose:** Detect which UI element currently has keyboard focus

**Signature:**
```python
windows_get_focused_element(
    pid: int,
    window_title: str | None = None,
) -> dict[str, Any]
```

**Parameters:**
- `pid`: Process ID of the application
- `window_title`: (Optional) Specific window title within the process

**Returns:**
```python
{
    "success": True/False,
    "name": "Element name",
    "control_type": "Edit"|"Button"|etc,
    "automation_id": "AutomationId if available",
    "class_name": "WindowsFormsClassName",
    "value": "Current text/value",
    "focused": True,
    "error": "Error message if success=False"
}
```

**Usage Example:**
```python
# After typing into a field, check what's focused
result = windows_get_focused_element(pid=20928, window_title="Search")
if result["success"]:
    print(f"Focused field: {result['name']}")
    print(f"Current value: {result['value']}")
    print(f"Control type: {result['control_type']}")
```

**Use Cases:**
- Verify cursor is in correct field before typing
- Detect which field is focused after Tab navigation
- Validate tab order in forms
- Debug field focus issues

---

### 2. `windows_get_element_value`

**Purpose:** Get the current value/text of a specific UI element

**Signature:**
```python
windows_get_element_value(
    pid: int,
    window_title: str | None = None,
    control_type: str | None = None,
    name: str | None = None,
    automation_id: str | None = None,
) -> dict[str, Any]
```

**Parameters:**
- `pid`: Process ID of the application
- `window_title`: (Optional) Specific window title
- `control_type`: (Optional) Control type filter ("Edit", "Button", etc.)
- `name`: (Optional) Element name to find
- `automation_id`: (Optional) Automation ID to find

**Returns:**
```python
{
    "success": True/False,
    "value": "Current text/value",
    "name": "Element name",
    "control_type": "Edit"|"Button"|etc,
    "automation_id": "AutomationId if available",
    "class_name": "WindowsFormsClassName",
    "error": "Error message if success=False"
}
```

**Usage Example:**
```python
# After typing username, verify it was entered correctly
result = windows_get_element_value(
    pid=20928,
    window_title="Login",
    name="Username",
    control_type="Edit"
)
if result["success"]:
    assert result["value"] == "expected_username"
```

**Use Cases:**
- Verify typed text landed in correct field
- Check field values before submission
- Validate form data
- Debug why text appears in wrong field

---

## Integration Status

✅ **Code added** to `windows_automation.py`
✅ **Functions implemented**: `get_element_value_by_pid()`, `get_focused_element_by_pid()`
✅ **Tools registered**: `windows_get_element_value`, `windows_get_focused_element`
⏳ **Requires agent reload** to use in current session

---

## Workflow Pattern: Field Focus Detection

### Problem
When filling forms with Tab navigation, we need to know:
1. Is the cursor in the correct field?
2. Did our typed text land in the expected field?
3. What's the current tab order?

### Solution Pattern

```python
# 1. Type into field (assumes it's focused)
desktop_keyboard_type("Test Patient")
desktop_sleep(0.3)

# 2. Check what field is focused and its value
focused = windows_get_focused_element(pid=20928, window_title="Search")
if focused["success"]:
    print(f"Focused: {focused['name']}")
    print(f"Value: {focused['value']}")
    
    # Verify it's the expected field
    if focused["name"] != "Name":
        print(f"⚠️ WARNING: Expected 'Name' field, got '{focused['name']}'")
    
    # Verify value matches what we typed
    if focused["value"] != "Test Patient":
        print(f"⚠️ WARNING: Expected 'Test Patient', got '{focused['value']}'")

# 3. Tab to next field
desktop_keyboard_press("tab")
desktop_sleep(0.3)

# 4. Check new focused field
focused = windows_get_focused_element(pid=20928, window_title="Search")
print(f"After Tab, focused: {focused.get('name', 'unknown')}")

# 5. Type into new field
desktop_keyboard_type("01/01/1990")
desktop_sleep(0.3)

# 6. Verify again
focused = windows_get_focused_element(pid=20928, window_title="Search")
if focused["name"] == "Date of Birth" and focused["value"] == "01/01/1990":
    print("✅ DOB field verified")
```

---

## Workflow Pattern: Verify All Fields Before Submission

```python
# After filling all fields, verify each one before submitting
fields_to_verify = [
    {"name": "Name", "expected": "Test Patient"},
    {"name": "Date of Birth", "expected": "01/01/1990"},
    {"name": "Phone", "expected": "1234567890"},
    {"name": "Zip", "expected": "12345"},
]

all_correct = True
for field_spec in fields_to_verify:
    result = windows_get_element_value(
        pid=20928,
        window_title="Search",
        name=field_spec["name"],
        control_type="Edit"
    )
    
    if result["success"]:
        if result["value"] != field_spec["expected"]:
            print(f"❌ {field_spec['name']}: Expected '{field_spec['expected']}', got '{result['value']}'")
            all_correct = False
        else:
            print(f"✅ {field_spec['name']}: '{result['value']}'")
    else:
        print(f"⚠️ Could not verify {field_spec['name']}: {result.get('error')}")
        all_correct = False

if all_correct:
    print("✅ All fields verified, proceeding with submission")
    desktop_keyboard_press("enter")
else:
    print("❌ Field verification failed, stopping workflow")
```

---

## Alternative: OCR-Based Verification (Current Session)

Since these tools require agent reload, the current workaround is OCR-based verification:

```python
# Type into field
desktop_keyboard_type("Test Patient")
desktop_sleep(0.5)

# Use OCR to verify text appeared on screen
result = desktop_extract_text(use_active_window=True)
if "Test Patient" in result.full_text:
    print("✅ Text verified via OCR")
else:
    print(f"⚠️ Text not found. OCR result: {result.full_text[:100]}")
```

**Limitations:**
- OCR may not distinguish which field contains the text
- OCR accuracy varies with font rendering
- Cannot detect which field has focus

---

## Future Enhancement: Auto-Detect Tab Order

With these tools, we could build a tab order detection function:

```python
def detect_tab_order(pid: int, window_title: str, max_tabs: int = 20) -> list[str]:
    """Detect tab order by pressing Tab and recording focused elements."""
    tab_order = []
    seen_elements = set()
    
    for i in range(max_tabs):
        focused = windows_get_focused_element(pid=pid, window_title=window_title)
        if focused["success"]:
            elem_key = f"{focused['name']}_{focused['control_type']}"
            if elem_key in seen_elements:
                # Cycled back to start
                break
            tab_order.append({
                "index": i,
                "name": focused["name"],
                "type": focused["control_type"],
                "automation_id": focused.get("automation_id"),
            })
            seen_elements.add(elem_key)
        
        desktop_keyboard_press("tab")
        desktop_sleep(0.2)
    
    return tab_order
```

---

## Summary

These two new tools enable:
1. ✅ **Focus detection** - Know which field has keyboard focus
2. ✅ **Value verification** - Check field contents after typing
3. ✅ **Tab order discovery** - Map form navigation paths
4. ✅ **Robust form filling** - Verify at each step
5. ✅ **Debugging** - Diagnose why text lands in wrong fields

**Next Steps:**
1. Reload agent to use new tools
2. Test with Connexus Patient Search dialog
3. Build field focus detection logic into workflows
4. Document findings in knowledge base
