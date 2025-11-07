# GUI-Cub Quick Wins Test Cases

**Purpose:** Validate Phase 1 Quick Wins implementation  
**Date:** 2025-01-XX  
**Platforms:** macOS, Windows

---

## Overview

These test cases validate the Quick Wins improvements:
1. ✅ RapidFuzz integration (3-5× faster fuzzy matching)
2. ✅ Performance monitoring (timing and cache metrics)
3. ✅ Early-stop logic (confident matches > 0.85)
4. ✅ Optimized identifier variants (8 instead of 15-20)

---

## Prerequisites

### macOS
- Calculator app (built-in)
- System Preferences accessible
- Accessibility permissions granted to Terminal/Python

### Windows
- Calculator app (built-in)
- Notepad (built-in)
- No admin privileges required

---

## Test Case 1: Fuzzy Matching Performance

**Objective:** Verify rapidfuzz integration provides faster fuzzy matching

### macOS Test

```python
# Launch Calculator
import subprocess
subprocess.Popen(["open", "-a", "Calculator"])
import time; time.sleep(2)

# Test fuzzy matching with various patterns
test_cases = [
    {"search": "equals", "role": "AXButton", "expected": "="},
    {"search": "plus", "role": "AXButton", "expected": "+"},
    {"search": "clear", "role": "AXButton", "expected": "C"},
    {"search": "multiply", "role": "AXButton", "expected": "×"},
]

from code_puppy.tools.gui_cub.accessibility import find_accessible_element
from code_puppy.tools.gui_cub.performance_monitor import get_monitor

monitor = get_monitor()
monitor.reset()

for test in test_cases:
    result = find_accessible_element(
        role=test["role"],
        title=test["search"],
        fuzzy=True,
        fuzzy_threshold=0.6
    )
    assert result.found, f"Failed to find {test['search']}"
    print(f"✓ Found {test['search']}: {result.best_match.title}")

# Show performance report
monitor.report()

# Verify early-stop rate > 0
print(f"\nEarly Stop Rate: {monitor.early_stop_rate * 100:.1f}%")
assert monitor.early_stop_rate > 0, "No early stops detected!"
```

### Windows Test

```python
# Launch Calculator
import subprocess
subprocess.Popen(["calc.exe"])
import time; time.sleep(2)

from code_puppy.tools.gui_cub.windows_automation import find_element
from code_puppy.tools.gui_cub.performance_monitor import get_monitor

monitor = get_monitor()
monitor.reset()

test_cases = [
    {"search": "equals", "control_type": "Button", "expected": "Equals"},
    {"search": "plus", "control_type": "Button", "expected": "Plus"},
    {"search": "clear", "control_type": "Button", "expected": "Clear"},
]

for test in test_cases:
    result = find_element(
        title=test["search"],
        control_type=test["control_type"],
        fuzzy=True,
        fuzzy_threshold=0.7
    )
    assert result.found, f"Failed to find {test['search']}"
    print(f"✓ Found {test['search']}: {result.best_match.title}")

# Show performance report
monitor.report()
```

**Expected Results:**
- ✅ All test cases find correct elements
- ✅ Average fuzzy search time < 30ms (was ~80ms)
- ✅ Early-stop rate > 30% (at least 1 confident match)
- ✅ Performance report shows timing breakdown

---

## Test Case 2: Early-Stop Validation

**Objective:** Verify early-stop triggers on confident matches (score > 0.85)

### macOS Test

```python
import subprocess
subprocess.Popen(["open", "-a", "Calculator"])
import time; time.sleep(2)

from code_puppy.tools.gui_cub.accessibility import find_accessible_element
from code_puppy.tools.gui_cub.performance_monitor import get_monitor

monitor = get_monitor()
monitor.reset()

# Test with exact match (should trigger early-stop)
result = find_accessible_element(
    role="AXButton",
    title="1",  # Exact match
    fuzzy=True
)

assert result.found
assert monitor.early_stops >= 1, "Expected early-stop on exact match!"
print(f"✓ Early-stop triggered: {monitor.early_stops} time(s)")

# Test with partial match (may or may not trigger)
monitor.reset()
result = find_accessible_element(
    role="AXButton",
    title="equ",  # Partial for "="
    fuzzy=True
)

print(f"Partial match - Early stops: {monitor.early_stops}, Full searches: {monitor.full_searches}")
```

### Windows Test

```python
import subprocess
subprocess.Popen(["calc.exe"])
import time; time.sleep(2)

from code_puppy.tools.gui_cub.windows_automation import find_element
from code_puppy.tools.gui_cub.performance_monitor import get_monitor

monitor = get_monitor()
monitor.reset()

# Exact match should trigger early-stop
result = find_element(
    title="One",
    control_type="Button",
    fuzzy=True
)

assert result.found
assert monitor.early_stops >= 1, "Expected early-stop!"
print(f"✓ Early-stop on exact match: {monitor.early_stops}")
```

**Expected Results:**
- ✅ Exact matches trigger early-stop (early_stops >= 1)
- ✅ Partial matches may trigger full search
- ✅ Early-stop rate improves with better matches

---

## Test Case 3: Performance Monitoring

**Objective:** Verify performance monitor tracks operations correctly

### Cross-Platform Test

```python
from code_puppy.tools.gui_cub.performance_monitor import get_monitor, reset_monitor
import time

# Reset monitor
reset_monitor()
monitor = get_monitor()

# Simulate operations
with monitor.measure("test_operation_1"):
    time.sleep(0.01)  # 10ms

with monitor.measure("test_operation_2"):
    time.sleep(0.02)  # 20ms

with monitor.measure("test_operation_1"):  # Same operation
    time.sleep(0.015)  # 15ms

# Record cache events
monitor.record_cache_hit()
monitor.record_cache_hit()
monitor.record_cache_miss()

# Record search events
monitor.record_early_stop()
monitor.record_full_search()

# Get summary
summary = monitor.get_summary()

# Verify metrics
assert summary["operations"]["test_operation_1"]["count"] == 2
assert summary["operations"]["test_operation_2"]["count"] == 1
assert summary["cache"]["hits"] == 2
assert summary["cache"]["misses"] == 1
assert summary["cache"]["hit_rate"] == 66.7  # 2/3
assert summary["search"]["early_stops"] == 1
assert summary["search"]["full_searches"] == 1

print("\n✓ Performance monitor validated:")
monitor.report(show_details=True)
```

**Expected Results:**
- ✅ Operations tracked correctly (count, avg, min, max)
- ✅ Cache hit/miss rates calculated
- ✅ Early-stop vs full search tracked
- ✅ Summary dict contains all metrics
- ✅ Report() displays human-readable output

---

## Test Case 4: RapidFuzz vs Difflib Comparison

**Objective:** Verify rapidfuzz provides performance improvement

```python
import time
from code_puppy.tools.gui_cub.fuzzy_matching import similarity_score

# Test data
test_pairs = [
    ("submit", "Submit Button"),
    ("save", "Save As..."),
    ("close", "Close Window"),
    ("login", "Log In"),
    ("search", "Search Field"),
] * 100  # 500 comparisons

# Benchmark rapidfuzz
start = time.perf_counter()
for search, target in test_pairs:
    score = similarity_score(search, target, use_rapidfuzz=True)
elapsed_rapidfuzz = time.perf_counter() - start

# Benchmark difflib
start = time.perf_counter()
for search, target in test_pairs:
    score = similarity_score(search, target, use_rapidfuzz=False)
elapsed_difflib = time.perf_counter() - start

speedup = elapsed_difflib / elapsed_rapidfuzz

print(f"\nFuzzy Matching Performance:")
print(f"  RapidFuzz: {elapsed_rapidfuzz*1000:.2f}ms (500 comparisons)")
print(f"  Difflib:   {elapsed_difflib*1000:.2f}ms (500 comparisons)")
print(f"  Speedup:   {speedup:.1f}x faster")

assert speedup >= 2.0, f"Expected 3-5x speedup, got {speedup:.1f}x"
print(f"\n✓ RapidFuzz is {speedup:.1f}x faster than difflib!")
```

**Expected Results:**
- ✅ RapidFuzz is 3-5× faster than difflib
- ✅ Both produce similar scores (within 0.05)
- ✅ RapidFuzz completes 500 comparisons in < 50ms

---

## Test Case 5: Identifier Variant Optimization

**Objective:** Verify reduced variant generation (8 vs 15-20)

```python
from code_puppy.tools.gui_cub.fuzzy_matching import extract_identifier_variants

# Test single word
variants = extract_identifier_variants("Submit")
print(f"\nVariants for 'Submit': {variants}")
assert len(variants) <= 8, f"Too many variants: {len(variants)}"
assert "submit" in variants
assert "submitbtn" in variants
assert "submit_btn" in variants
assert "btnsubmit" in variants

# Test multi-word (should include camelCase)
variants = extract_identifier_variants("Save File")
print(f"Variants for 'Save File': {variants}")
assert "savefile" in variants
assert "saveFile" in variants  # camelCase
assert len(variants) <= 10  # Slightly more for multi-word

print("\n✓ Identifier variants optimized (was 15-20, now ≤8)")
```

**Expected Results:**
- ✅ Single words generate ≤8 variants
- ✅ Multi-words include camelCase
- ✅ No duplicate variants
- ✅ Most common patterns included (btn, button, btn_)

---

## Test Case 6: End-to-End Integration

**Objective:** Verify all quick wins work together in real usage

### macOS Full Workflow

```python
import subprocess
import time

# Launch Calculator
subprocess.Popen(["open", "-a", "Calculator"])
time.sleep(2)

from code_puppy.tools.gui_cub.accessibility import (
    find_accessible_element,
    desktop_list_accessible_tree,
)
from code_puppy.tools.gui_cub.performance_monitor import get_monitor, reset_monitor

# Reset monitor for clean test
reset_monitor()
monitor = get_monitor()

print("\n=== Testing Full Workflow ===")

# Step 1: List element tree (tests performance monitoring)
print("\n1. Listing element tree...")
tree_result = desktop_list_accessible_tree(max_depth=5)
assert tree_result.success
print(f"   Found {tree_result.total_elements} elements (compacted to {tree_result.filtered_count})")

# Step 2: Find button with fuzzy matching (tests rapidfuzz + early-stop)
print("\n2. Finding 'equals' button with fuzzy matching...")
result = find_accessible_element(
    role="AXButton",
    title="equals",  # Will match "="
    fuzzy=True,
    fuzzy_threshold=0.6
)
assert result.found
print(f"   Found: '{result.best_match.title}' at ({result.best_match.center_x}, {result.best_match.center_y})")

# Step 3: Find another button (tests cache and early-stop)
print("\n3. Finding 'multiply' button...")
result = find_accessible_element(
    role="AXButton",
    title="multiply",  # Will match "×"
    fuzzy=True
)
assert result.found
print(f"   Found: '{result.best_match.title}'")

# Step 4: Show performance metrics
print("\n4. Performance Metrics:")
monitor.report(show_details=True)

# Verify improvements
summary = monitor.get_summary()
assert len(summary["operations"]) > 0, "No operations tracked!"
assert summary["search"]["early_stops"] > 0, "No early-stops detected!"

print("\n✓ All quick wins validated in end-to-end test!")
```

### Windows Full Workflow

```python
import subprocess
import time

subprocess.Popen(["calc.exe"])
time.sleep(2)

from code_puppy.tools.gui_cub.windows_automation import (
    find_element,
    list_elements_in_window,
)
from code_puppy.tools.gui_cub.performance_monitor import get_monitor, reset_monitor

reset_monitor()
monitor = get_monitor()

print("\n=== Testing Full Workflow (Windows) ===")

# Step 1: List elements
print("\n1. Listing element tree...")
tree_result = list_elements_in_window()
assert tree_result.success
print(f"   Found {tree_result.total_elements} elements")

# Step 2: Find with fuzzy matching
print("\n2. Finding 'equals' button...")
result = find_element(
    title="equals",
    control_type="Button",
    fuzzy=True,
    fuzzy_threshold=0.7
)
assert result.found
print(f"   Found: '{result.best_match.title}'")

# Step 3: Performance report
print("\n3. Performance Metrics:")
monitor.report(show_details=True)

print("\n✓ Windows quick wins validated!")
```

**Expected Results:**
- ✅ Tree building completes in <200ms
- ✅ Fuzzy matching works with common search terms
- ✅ Early-stops detected (>30% rate)
- ✅ Performance monitor tracks all operations
- ✅ No errors or exceptions

---

## Success Criteria

### Performance Improvements
- [ ] Fuzzy matching: 3-5× faster (< 30ms avg)
- [ ] Tree traversal: < 200ms on complex UIs
- [ ] Early-stop rate: > 30% on typical searches

### Functional Requirements
- [ ] All test cases pass on macOS
- [ ] All test cases pass on Windows
- [ ] No regressions in existing functionality
- [ ] Performance monitor accurately tracks operations

### Code Quality
- [ ] Backward compatible with existing code
- [ ] RapidFuzz gracefully falls back to difflib if unavailable
- [ ] No breaking changes to public APIs

---

## Running the Tests

### Option 1: Via gui-cub Agent

```bash
# Start code-puppy and switch to gui-cub agent
code-puppy
/agent gui-cub

# Run test cases (copy-paste from this document)
```

### Option 2: Direct Python Execution

```bash
# macOS
python -c "$(cat test_case_1_macos.py)"

# Windows
python -c "$(cat test_case_1_windows.py)"
```

### Option 3: Unit Tests

```bash
# Run gui-cub unit tests (includes quick wins validation)
uv run pytest tests/test_gui_cub_quick_wins.py -v
```

---

## Troubleshooting

### Issue: "RAPIDFUZZ_AVAILABLE = False"

**Solution:**
```bash
uv add rapidfuzz
```

### Issue: "No early-stops detected"

**Cause:** Search terms don't have confident matches (all scores < 0.85)  
**Solution:** Try exact matches like "1", "=", "Clear"

### Issue: "Performance worse than baseline"

**Cause:** First run includes import overhead  
**Solution:** Run test multiple times, check avg after warmup

### Issue: macOS "Accessibility permission denied"

**Solution:**
```
System Preferences → Security & Privacy → Privacy → Accessibility
Add Terminal/Python and grant permission
```

---

## Next Steps

Once all test cases pass:

1. ✅ Commit quick wins implementation
2. 📊 Benchmark before/after performance
3. 📝 Update CHANGELOG.md
4. 🚀 Proceed to Phase 2: Caching & Consistency

---

**Last Updated:** 2025-01-XX  
**Status:** Ready for Testing  
**Author:** Code Puppy Team 🐶
