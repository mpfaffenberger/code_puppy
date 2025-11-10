# Comprehensive Accessibility Attribute Support

## Current State

### What We Extract:
- ✅ `title` / `AXTitle` / `Name` - Main label
- ✅ `description` / `AXDescription` - Secondary label  
- ✅ `value` / `AXValue` / `Value` - Current value
- ✅ `role` / `AXRole` / `ControlType` - Element type

### What We Search in Fuzzy Matching:
- ✅ `title`
- ✅ `description`
- ✅ `value`

### Current Weights:
```python
"title": 0.6,
"description": 0.3,
"value": 0.1,
```

---

## Available Attributes Not Being Used

### macOS (atomacos):

#### Text Content (should be searchable):
- ❌ `AXPlaceholderValue` - Placeholder text in text fields
  - Example: Search field shows "Search"
  - **Use Case:** Find text field by placeholder
  - **Weight:** 0.4 (similar to description)

- ❌ `AXHelp` - Tooltip/help text
  - Example: Button hover shows "Click to submit"
  - **Use Case:** Find element by help text
  - **Weight:** 0.2 (lower priority)

- ❌ `AXRoleDescription` - Human-readable role
  - Example: "search text field", "increment arrow button"
  - **Use Case:** Find by descriptive role
  - **Weight:** 0.2 (lower priority)

#### Identifiers (exact match only):
- ❌ `AXIdentifier` - Unique automation ID
  - Example: `_SC_SEARCH_FIELD`, `xSidebarHeader`
  - **Use Case:** Reliable element targeting (like automation_id on Windows)
  - **Should:** Support exact match AND be returned in results

- ❌ `AXSubrole` - Sub-role classification
  - Example: `AXIncrementArrow`, `AXSearchField`
  - **Use Case:** More specific filtering
  - **Should:** Include in search for role filtering

---

### Windows (UIAutomation):

#### Text Content:
- ✅ `Name` - Main label (equivalent to AXTitle) ✅
- ❌ `HelpText` - Help/tooltip text **NOT USING!**
- ❌ `LocalizedControlType` - Human-readable type **NOT USING!**
- ❌ `ClassName` - CSS-like class name **NOT USING!**
- ❌ `AcceleratorKey` - Keyboard shortcut **NOT USING!**
- ❌ `AccessKey` - Access key (Alt+X) **NOT USING!**

#### Identifiers:
- ✅ `AutomationId` - Unique ID ✅ (already supported on Windows!)
  - **macOS equivalent:** `AXIdentifier`
  - **Already works on Windows!**

---

## Proposed Comprehensive Attribute List

### Searchable Text Attributes (fuzzy matching):

```python
SEARCHABLE_ATTRIBUTES = {
    # Core attributes (high weight)
    "title": 0.6,              # Main label
    "name": 0.6,               # Windows equivalent
    
    # Secondary attributes (medium weight)
    "description": 0.3,        # macOS AXDescription
    "placeholder": 0.4,        # AXPlaceholderValue / Placeholder
    
    # Context attributes (low weight)
    "value": 0.1,              # Current value
    "help": 0.2,               # AXHelp / HelpText
    "role_description": 0.2,   # AXRoleDescription / LocalizedControlType
    "class_name": 0.1,         # Windows ClassName
}
```

### Exact Match Identifiers (no fuzzy):

```python
IDENTIFIER_ATTRIBUTES = [
    "identifier",        # AXIdentifier (macOS)
    "automation_id",     # AutomationId (Windows)
    "auto_id",          # Alias
]
```

### Additional Metadata (include in results):

```python
METADATA_ATTRIBUTES = [
    "subrole",          # AXSubrole
    "accelerator_key",  # Keyboard shortcut
    "access_key",       # Alt+X key
]
```

---

## Implementation Plan

### Phase 1: Extract All Attributes ✅

**macOS:**
```python
elem_dict = {
    "element": elem,
    "title": getattr(elem, "AXTitle", None) or "",
    "description": getattr(elem, "AXDescription", None) or "",
    "value": getattr(elem, "AXValue", None) or "",
    "placeholder": getattr(elem, "AXPlaceholderValue", None) or "",  # NEW
    "help": getattr(elem, "AXHelp", None) or "",                      # NEW
    "role_description": getattr(elem, "AXRoleDescription", None) or "", # NEW
    "identifier": getattr(elem, "AXIdentifier", None) or "",          # NEW
    "subrole": getattr(elem, "AXSubrole", None) or "",                # NEW
}
```

**Windows:**
```python
elem_dict = {
    "element": elem,
    "title": info.name or "",
    "value": info.value or "",
    "help": info.help_text or "",                          # NEW
    "role_description": info.localized_control_type or "", # NEW
    "class_name": info.class_name or "",                   # NEW
    "automation_id": info.automation_id or "",            # EXISTS
    "accelerator_key": info.accelerator_key or "",         # NEW
}
```

---

### Phase 2: Update Fuzzy Matching ✅

**Add new attributes to search:**
```python
fuzzy_matches = fuzzy_match(
    search_text=title,
    candidates=element_dicts,
    attribute_names=[
        "title", "name",           # Core
        "description", "placeholder", # Secondary
        "value", "help", "role_description", "class_name"  # Context
    ],
    threshold=fuzzy_threshold,
    attribute_weights={
        "title": 0.6,
        "name": 0.6,
        "description": 0.3,
        "placeholder": 0.4,
        "value": 0.1,
        "help": 0.2,
        "role_description": 0.2,
        "class_name": 0.1,
    }
)
```

---

### Phase 3: Support Identifier Exact Match ✅

**Add identifier parameter to find_accessible_element:**
```python
def find_accessible_element(
    role: str | None = None,
    title: str | None = None,
    identifier: str | None = None,  # NEW: AXIdentifier or AutomationId
    ...
) -> ElementSearchResult:
    """
    Find element by title (fuzzy) OR identifier (exact).
    
    Args:
        identifier: Exact match on AXIdentifier (macOS) or AutomationId (Windows)
                    Takes precedence over fuzzy title search
    """
    # Strategy 0: Try identifier exact match first (highest priority)
    if identifier:
        if platform == "darwin":
            matches = app.findAllR(AXIdentifier=identifier)
        elif platform == "win32":
            # Windows already supports automation_id
            matches = find_by_automation_id(identifier)
        
        if matches:
            return matches[0]  # Exact match!
    
    # Strategy 1: Try exact title match
    # Strategy 2: Try fuzzy match on all text attributes
    ...
```

---

### Phase 4: Return Identifiers in Results ✅

**Include in ElementInfo:**
```python
class ElementInfo(BaseModel):
    role: str | None = None
    title: str | None = None
    description: str | None = None
    value: str | None = None
    
    # NEW: Additional searchable attributes
    placeholder: str | None = None
    help: str | None = None
    role_description: str | None = None
    
    # NEW: Identifiers
    identifier: str | None = None  # AXIdentifier or AutomationId
    subrole: str | None = None
    
    # Coordinates
    x: int | None = None
    y: int | None = None
    ...
```

---

## Benefits

### 1. **More Reliable Element Finding** ✅
Finding search field:
```python
# Before: Only searches title (often empty)
find_accessible_element(title="search")  # ❌ Not found (title=None)

# After: Searches placeholder too!
find_accessible_element(title="search")  # ✅ Found via placeholder="Search"
```

### 2. **Exact Match via Identifiers** ✅
```python
# Reliable automation
find_accessible_element(identifier="_SC_SEARCH_FIELD")  # ✅ Exact match!
find_accessible_element(identifier="xSidebarHeader")   # ✅ Exact match!

# No fuzzy matching ambiguity
```

### 3. **Better Role Filtering** ✅
```python
# Find by human-readable role
find_accessible_element(
    title="search",
    role_description="search text field"  # More intuitive than AXSearchField
)
```

### 4. **Help Text Discovery** ✅
```python
# Find by tooltip
find_accessible_element(title="click to submit")  # Matches AXHelp text
```

### 5. **Windows Parity** ✅
- macOS `AXIdentifier` → Windows `AutomationId`
- macOS `AXHelp` → Windows `HelpText`
- macOS `AXRoleDescription` → Windows `LocalizedControlType`

---

## Testing Strategy

### Test 1: Placeholder Matching
```python
# macOS: Search field with placeholder="Search"
result = find_accessible_element(title="search")
assert result.found
assert result.best_match.placeholder == "Search"
```

### Test 2: Identifier Exact Match
```python
# macOS: Element with AXIdentifier="_SC_SEARCH_FIELD"
result = find_accessible_element(identifier="_SC_SEARCH_FIELD")
assert result.found
assert result.best_match.identifier == "_SC_SEARCH_FIELD"
```

### Test 3: Help Text Matching
```python
# Element with AXHelp="Click to submit form"
result = find_accessible_element(title="submit form")
assert result.found  # Matched via help text
```

### Test 4: Comprehensive Search
```python
# Search across ALL attributes
result = find_accessible_element(title="increment")
# Could match:
# - title="Increment"
# - description="increment value"
# - role_description="increment arrow button"
# - help="Increment the counter"
```

---

## Migration Path

### Backward Compatible ✅
- Existing code continues to work
- New attributes are additive
- `identifier` parameter is optional

### Gradual Rollout:
1. **Phase 1:** Extract new attributes ✅
2. **Phase 2:** Add to fuzzy matching ✅
3. **Phase 3:** Add identifier parameter ✅
4. **Phase 4:** Update documentation ✅
5. **Phase 5:** Add tests ✅

---

## Risk Analysis

### Low Risk:
- ✅ Backward compatible
- ✅ Additive changes only
- ✅ Optional parameters

### Medium Risk:
- ⚠️ More attributes = slower fuzzy matching
  - **Mitigation:** Use early-stop optimization
  - **Mitigation:** Only search non-empty attributes

### Performance Impact:
- **Before:** Search 3 attributes (title, description, value)
- **After:** Search up to 8 attributes
- **Impact:** ~2-3x slower fuzzy search
- **Mitigation:** Early-stop threshold (0.6) prevents full search

---

## Recommendation

### ✅ **Implement All Phases**

**Priority 1 (HIGH):**
- Add `placeholder`, `help`, `identifier` extraction
- Add to fuzzy matching search
- Support `identifier` exact match parameter

**Priority 2 (MEDIUM):**
- Add `role_description`, `subrole`, `class_name`
- Update weights based on testing

**Priority 3 (LOW):**
- Add `accelerator_key`, `access_key`
- Advanced keyboard shortcut support

**Estimated Effort:** 4-6 hours
**Estimated Impact:** 50-70% improvement in element finding reliability

---

## Example: Before vs After

### Finder Search Field

**Before:**
```python
buttons = app.findAllR(AXRole='AXTextField')
field = buttons[0]

Extracted:
  title: None           ❌ Empty
  description: None     ❌ Empty  
  value: None           ❌ Empty

find_accessible_element(title="search")  ❌ NOT FOUND
```

**After:**
```python
buttons = app.findAllR(AXRole='AXTextField')
field = buttons[0]

Extracted:
  title: None
  description: None
  value: None
  placeholder: "Search"           ✅ Has value!
  identifier: "_SC_SEARCH_FIELD"  ✅ Has identifier!
  role_description: "search text field"

find_accessible_element(title="search")              ✅ FOUND (via placeholder)
find_accessible_element(identifier="_SC_SEARCH_FIELD") ✅ FOUND (exact match)
```

---

## Dakota's Question: "Can we search entire element?"

**YES!** ✅

With this comprehensive approach:
- Fuzzy matching searches **all text attributes**
- Exact matching searches **identifiers**
- Weighted scoring prioritizes important attributes
- Early-stop prevents performance issues

The element becomes **fully searchable** across all its text content!
