# Windows Element Tree Refactoring - Code Puppy Prompt

## Problem Statement

Currently, `windows_list_elements()` automatically applies compaction when there are >20 elements, returning only the "top 20 actionable elements" (buttons, fields, menus). This causes critical issues:

1. **Calculator Display Bug:** The result display value "30" stored in Text element `value` properties gets filtered out because Text elements have low relevance scores (0.15)
2. **No Control Over Compaction:** Agent cannot request full element tree when debugging or searching for non-button elements
3. **Search Function Fails:** `windows_search_text_in_elements()` calls the compacted tree, so it can't find text in filtered-out elements

## Desired Solution

Create **three distinct functions** with clear purposes:

### 1. `windows_list_interactive_elements()` - Actionable Elements Only
**Purpose:** Find buttons, fields, menus, and other interactive controls  
**Use Case:** When agent needs to click/interact with UI elements  
**Behavior:** Returns compacted list prioritizing interactive elements (current behavior)  
**Max Results:** 20 elements by default, configurable via `max_elements` parameter

**Function Signature:**
```python
def windows_list_interactive_elements(
    context: RunContext,
    max_elements: int = 20,
) -> ElementListResult:
    """
    List interactive UI elements (buttons, fields, menus) in the active window.
    
    Optimized for finding clickable/typeable elements. Automatically filters
    out static text, labels, and other non-interactive elements.
    
    Args:
        max_elements: Maximum elements to return (default: 20)
    
    Returns:
        ElementListResult with interactive elements sorted by relevance
    
    Examples:
        - windows_list_interactive_elements()  # Get top 20 buttons/fields
        - windows_list_interactive_elements(max_elements=50)  # More results
    """
```

### 2. `windows_search_elements()` - Smart Fuzzy Search
**Purpose:** Find elements matching a search query using intelligent ranking  
**Use Case:** When agent is looking for specific text, values, or element names  
**Behavior:** Searches ALL elements (no compaction), ranks by relevance to query, returns top matches  
**Max Results:** 10 by default, configurable via `max_results` parameter

**Function Signature:**
```python
def windows_search_elements(
    context: RunContext,
    search_query: str,
    fuzzy: bool = True,
    fuzzy_threshold: float = 0.6,
    max_results: int = 10,
    element_types: list[str] | None = None,  # Optional filter: ["Button", "Text", "Edit"]
) -> ElementSearchResult:
    """
    Search for elements matching a query across ALL elements in the window.
    
    Uses intelligent ranking that considers:
    - Fuzzy text matching against title, auto_id, value, class_name
    - Element type relevance to query
    - Visual prominence (size, position)
    - Accessibility properties
    
    Args:
        search_query: Text to search for (e.g., "Submit", "30", "Display")
        fuzzy: Enable fuzzy matching (default: True)
        fuzzy_threshold: Minimum similarity score 0.0-1.0 (default: 0.6)
        max_results: Maximum matches to return (default: 10)
        element_types: Optional filter by control types (e.g., ["Button", "Text"])
    
    Returns:
        ElementSearchResult with matches sorted by relevance score
    
    Examples:
        - windows_search_elements(search_query="Submit")  # Find Submit button
        - windows_search_elements(search_query="30", element_types=["Text", "Edit"])  # Find Calculator result
        - windows_search_elements(search_query="OK", fuzzy=False)  # Exact match only
    
    Use Cases:
        - Finding Calculator display value: search_query="30"
        - Finding button by label: search_query="Submit"
        - Finding text field by name: search_query="Username"
        - Debugging: search_query="Display", max_results=50
    """
```

**Ranking Algorithm Should Consider:**
1. **Text Match Score** (highest weight):
   - Exact match in value/title/auto_id = 1.0
   - Fuzzy match score from rapidfuzz
   - Substring match = 0.8
2. **Element Type Relevance** (medium weight):
   - Text/Edit controls when searching numeric values
   - Button controls when searching action words
   - Boost if matches `element_types` filter
3. **Visual Prominence** (low weight):
   - Larger elements slightly boosted
   - Elements near top-left slightly boosted
4. **Property Completeness** (tiebreaker):
   - Elements with values/text preferred over empty ones

### 3. `windows_list_all_elements()` - Complete Element Tree
**Purpose:** Get the entire unfiltered element tree for debugging  
**Use Case:** When agent needs to see everything or debug why search failed  
**Behavior:** Returns ALL elements with NO compaction or filtering  
**Max Results:** Unlimited (all elements in tree)

**Function Signature:**
```python
def windows_list_all_elements(
    context: RunContext,
    max_depth: int = 10,
    include_invisible: bool = False,
) -> ElementListResult:
    """
    List ALL UI elements in the active window without filtering.
    
    ⚠️ WARNING: Can return 100+ elements. Use for debugging only.
    For normal automation, use windows_list_interactive_elements() or
    windows_search_elements() instead.
    
    Args:
        max_depth: Maximum tree traversal depth (default: 10)
        include_invisible: Include hidden/disabled elements (default: False)
    
    Returns:
        ElementListResult with complete unfiltered element tree
    
    Examples:
        - windows_list_all_elements()  # Get everything
        - windows_list_all_elements(max_depth=5)  # Shallower traversal
        - windows_list_all_elements(include_invisible=True)  # Include hidden
    
    Use Cases:
        - Debugging why search failed
        - Understanding application structure
        - Finding obscure UI elements
    """
```

## Implementation Requirements

### Files to Modify

1. **`code_puppy/tools/gui_cub/windows_automation/tools.py`**
   - Add three new `@agent.tool` functions as specified above
   - Keep existing `windows_list_elements()` for backward compatibility but mark as deprecated
   - Update `windows_search_text_in_elements()` to use `windows_search_elements()` internally

2. **`code_puppy/tools/gui_cub/windows_automation/core.py`**
   - Refactor `list_elements_in_window()` to accept `compact` parameter (default: True for backward compatibility)
   - Create new `search_elements_smart()` function with ranking algorithm
   - Create new `rank_element_by_query()` helper function for scoring

3. **`code_puppy/agents/agent_gui_cub.py`**
   - Update agent prompt to recommend new functions:
     - Use `windows_search_elements()` when looking for specific text/values
     - Use `windows_list_interactive_elements()` when exploring clickable elements
     - Use `windows_list_all_elements()` only for debugging
   - Update the "🚨 CRITICAL RULE" section about element tree searching

### Core Implementation Details

#### Enhanced Element Data Collection
Update `list_elements_in_window()` to capture more properties for better ranking:

```python
elem_data = {
    "control_type": info.control_type,
    "title": info.name,
    "class_name": info.class_name,
    "auto_id": info.automation_id,
    "value": value,  # Already captured
    "depth": depth,
    "x": x,
    "y": y,
    "width": width,
    "height": height,
    "center_x": center_x,
    "center_y": center_y,
    # NEW PROPERTIES FOR RANKING:
    "visible": element.is_visible() if hasattr(element, 'is_visible') else True,
    "enabled": element.is_enabled() if hasattr(element, 'is_enabled') else True,
    "area": width * height if width and height else 0,  # For prominence ranking
}
```

#### Smart Ranking Algorithm
Implement in `rank_element_by_query(element, query, fuzzy, threshold)`:

```python
def rank_element_by_query(
    element: dict,
    query: str,
    fuzzy: bool = True,
    threshold: float = 0.6,
) -> float:
    """
    Calculate relevance score for an element given a search query.
    
    Returns:
        Score from 0.0 to 1.0 (higher = more relevant)
    """
    query_lower = query.lower().strip()
    
    # 1. TEXT MATCH SCORE (70% weight)
    text_score = 0.0
    
    # Check value property (highest priority for Calculator, text fields)
    value = (element.get("value") or "").lower().strip()
    if query_lower == value:  # Exact match
        text_score = 1.0
    elif query_lower in value:  # Substring match
        text_score = 0.8
    elif fuzzy and value:  # Fuzzy match
        from rapidfuzz import fuzz
        text_score = max(text_score, fuzz.ratio(query_lower, value) / 100.0)
    
    # Check title/name
    title = (element.get("title") or "").lower().strip()
    if not text_score:  # Only check if value didn't match
        if query_lower == title:
            text_score = 1.0
        elif query_lower in title:
            text_score = 0.8
        elif fuzzy and title:
            from rapidfuzz import fuzz
            text_score = max(text_score, fuzz.ratio(query_lower, title) / 100.0)
    
    # Check auto_id
    auto_id = (element.get("auto_id") or "").lower().strip()
    if text_score < 0.8:  # Only check if we don't have a good match yet
        if query_lower in auto_id:
            text_score = max(text_score, 0.6)
        elif fuzzy and auto_id:
            from rapidfuzz import fuzz
            text_score = max(text_score, fuzz.ratio(query_lower, auto_id) / 100.0 * 0.7)
    
    # If no match, return 0
    if text_score < threshold:
        return 0.0
    
    # 2. ELEMENT TYPE RELEVANCE (20% weight)
    type_score = 0.5  # Baseline
    control_type = element.get("control_type", "")
    
    # Boost Text/Edit for numeric/value queries
    if query.strip().replace('.', '').replace('-', '').isdigit():
        if control_type in ["Text", "Edit"]:
            type_score = 1.0
    # Boost Button for action words
    elif any(word in query_lower for word in ["submit", "ok", "cancel", "close", "save", "delete"]):
        if control_type == "Button":
            type_score = 1.0
    
    # 3. VISUAL PROMINENCE (10% weight)
    prominence_score = 0.5  # Baseline
    area = element.get("area", 0)
    if area > 10000:  # Large element
        prominence_score = 0.8
    elif area > 5000:  # Medium element
        prominence_score = 0.6
    
    # Near top-left is slightly more prominent
    x = element.get("x", 1000)
    y = element.get("y", 1000)
    if x < 200 and y < 200:
        prominence_score = min(1.0, prominence_score + 0.2)
    
    # COMBINED SCORE
    final_score = (
        text_score * 0.7 +
        type_score * 0.2 +
        prominence_score * 0.1
    )
    
    return final_score
```

## Expected Behavior After Changes

### Example 1: Finding Calculator Result
```python
# OLD (fails):
result = windows_search_text_in_elements(search_text="30")
# Returns: found=False because Text elements were filtered out

# NEW (succeeds):
result = windows_search_elements(search_query="30")
# Returns: found=True, best_match with value="30", control_type="Text"
```

### Example 2: Exploring Interactive Elements
```python
# Get buttons/fields for clicking:
result = windows_list_interactive_elements()
# Returns: 20 buttons/fields sorted by relevance (current behavior)
```

### Example 3: Debugging
```python
# See everything in Calculator:
result = windows_list_all_elements()
# Returns: All 54+ elements including display, buttons, labels, etc.
```

### Example 4: Smart Search with Filtering
```python
# Find only Text elements containing "30":
result = windows_search_elements(
    search_query="30",
    element_types=["Text", "Edit"],
    max_results=5
)
# Returns: Top 5 Text/Edit elements matching "30"
```

## Backward Compatibility

- Keep `windows_list_elements()` functioning as-is but add deprecation warning:
  ```python
  emit_info(
      "[yellow]⚠️ windows_list_elements() is deprecated. "
      "Use windows_list_interactive_elements(), windows_search_elements(), "
      "or windows_list_all_elements() instead.[/yellow]"
  )
  ```

- Update `windows_search_text_in_elements()` to use new `windows_search_elements()` internally:
  ```python
  def windows_search_text_in_elements(
      context: RunContext,
      search_text: str,
      fuzzy: bool = False,
      fuzzy_threshold: float = 0.7,
  ) -> ElementSearchResult:
      # Delegate to new smart search
      return windows_search_elements(
          context=context,
          search_query=search_text,
          fuzzy=fuzzy,
          fuzzy_threshold=fuzzy_threshold,
          max_results=10,
      )
  ```

## Testing Requirements

Create test cases in `tests/test_windows_element_search.py`:

1. **Test Calculator Display Value Search**
   - Open Calculator, calculate 5+10+15=30
   - Call `windows_search_elements(search_query="30")`
   - Assert: found=True, value="30", control_type="Text"

2. **Test Interactive Elements Filtering**
   - Call `windows_list_interactive_elements(max_elements=10)`
   - Assert: All returned elements are Button/Edit/ComboBox/etc.
   - Assert: No static Text/Label elements

3. **Test All Elements Unfiltered**
   - Call `windows_list_all_elements()`
   - Assert: Returns >50 elements for Calculator
   - Assert: Includes Text, Button, Label, etc.

4. **Test Ranking Algorithm**
   - Verify exact matches score higher than fuzzy matches
   - Verify value property matches score higher than title matches
   - Verify element type relevance boosts scores appropriately

## Documentation Updates

Update `docs/gui-cub/WINDOWS_ELEMENT_TREE.md` (create if doesn't exist):

```markdown
# Windows Element Tree Functions

## Overview

Three functions for different use cases:

1. **windows_list_interactive_elements()** - Get clickable elements (buttons, fields)
2. **windows_search_elements()** - Smart search across all elements
3. **windows_list_all_elements()** - Complete unfiltered tree (debugging)

## When to Use Each Function

### Use `windows_search_elements()` when:
- Looking for specific text/values ("30", "Submit", "Display")
- Verifying Calculator results
- Finding elements by name or label
- You know what you're looking for

### Use `windows_list_interactive_elements()` when:
- Exploring available buttons/fields
- Building automation workflows
- You want to see what's clickable

### Use `windows_list_all_elements()` when:
- Debugging why search failed
- Understanding application structure
- Need to see everything (warning: verbose)

## Examples

[Include the examples from "Expected Behavior" section above]
```

## Success Criteria

✅ Calculator display value "30" is found by `windows_search_elements(search_query="30")`  
✅ All three functions work independently and return correct data structures  
✅ Ranking algorithm prioritizes exact matches over fuzzy matches  
✅ Backward compatibility maintained for existing workflows  
✅ Agent prompt updated to recommend appropriate function for each use case  
✅ Tests pass for all three functions  
✅ Documentation is clear and includes examples  

## Implementation Checklist

- [ ] Refactor `list_elements_in_window()` to accept `compact` parameter
- [ ] Implement `rank_element_by_query()` helper function
- [ ] Implement `search_elements_smart()` core function
- [ ] Add `windows_list_interactive_elements()` tool
- [ ] Add `windows_search_elements()` tool
- [ ] Add `windows_list_all_elements()` tool
- [ ] Update `windows_search_text_in_elements()` to delegate to new search
- [ ] Deprecate `windows_list_elements()` with warning
- [ ] Update agent prompt with new function recommendations
- [ ] Write test cases
- [ ] Create documentation
- [ ] Verify Calculator "30" search works
- [ ] Test backward compatibility

## Notes for Code Puppy Agent

- Follow existing code style in `windows_automation/` module
- Use type hints on all new functions
- Add comprehensive docstrings with examples
- Emit informative messages using `emit_info()` for debugging
- Handle exceptions gracefully with try/except
- Use `get_monitor()` for performance tracking on core functions
- Keep functions under 100 lines each (extract helpers if needed)
- Add inline comments explaining ranking algorithm logic
- Test with Calculator app before considering complete
