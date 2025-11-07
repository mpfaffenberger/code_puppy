# GUI-Cub Quick Wins - Simple Test Prompt

**Purpose:** Quick validation that Quick Wins improvements are working  
**Time:** 2-3 minutes  
**Platforms:** macOS, Windows  

---

## Simple Test (Copy-Paste into GUI-Cub)

### macOS Test

```python
# Quick Wins Validation Test (macOS)
import subprocess
import time

# Launch Calculator
print("\n=== GUI-Cub Quick Wins Test (macOS) ===")
print("\n1. Launching Calculator...")
subprocess.Popen(["open", "-a", "Calculator"])
time.sleep(2)

from code_puppy.tools.gui_cub.accessibility import find_accessible_element
from code_puppy.tools.gui_cub.performance_monitor import get_monitor, reset_monitor

# Reset performance monitor
reset_monitor()
monitor = get_monitor()

# Test 1: Find element with fuzzy matching
print("\n2. Testing fuzzy matching (searching for 'equals' button)...")
result = find_accessible_element(
    role="AXButton",
    title="equals",  # Will fuzzy match to "="
    fuzzy=True
)

if result.found:
    print(f"   ✅ Found: '{result.best_match.title}' at ({result.best_match.center_x}, {result.best_match.center_y})")
else:
    print("   ❌ Failed to find element")

# Test 2: Another search (tests early-stop)
print("\n3. Testing early-stop logic (searching for '1' button)...")
result = find_accessible_element(
    role="AXButton",
    title="1",  # Exact match - should trigger early-stop
    fuzzy=True
)

if result.found:
    print(f"   ✅ Found: '{result.best_match.title}'")
else:
    print("   ❌ Failed to find element")

# Test 3: Show performance metrics
print("\n4. Performance Metrics:")
monitor.report(show_details=True)

# Validate quick wins
summary = monitor.get_summary()
early_stop_rate = summary["search"]["early_stop_rate"]

print("\n=== Quick Wins Validation ===")
if early_stop_rate > 0:
    print(f"✅ Early-stop working: {early_stop_rate}% of searches stopped early")
else:
    print("❌ Early-stop not triggered (may need more confident matches)")

if "fuzzy_match" in summary["operations"]:
    avg_time = summary["operations"]["fuzzy_match"]["avg_ms"]
    print(f"✅ Fuzzy matching tracked: {avg_time:.1f}ms average")
    if avg_time < 50:
        print("   ✨ Excellent performance! (< 50ms)")
else:
    print("❌ Fuzzy matching not tracked")

print("\n✅ Quick Wins test complete!")
print("\nClose Calculator to clean up.")
```

### Windows Test

```python
# Quick Wins Validation Test (Windows)
import subprocess
import time

# Launch Calculator
print("\n=== GUI-Cub Quick Wins Test (Windows) ===")
print("\n1. Launching Calculator...")
subprocess.Popen(["calc.exe"])
time.sleep(2)

from code_puppy.tools.gui_cub.windows_automation import find_element
from code_puppy.tools.gui_cub.performance_monitor import get_monitor, reset_monitor

# Reset performance monitor
reset_monitor()
monitor = get_monitor()

# Test 1: Find element with fuzzy matching
print("\n2. Testing fuzzy matching (searching for 'equals' button)...")
result = find_element(
    title="equals",  # Will fuzzy match to "Equals"
    control_type="Button",
    fuzzy=True
)

if result.found:
    print(f"   ✅ Found: '{result.best_match.title}' at ({result.best_match.center_x}, {result.best_match.center_y})")
else:
    print("   ❌ Failed to find element")

# Test 2: Another search (tests early-stop)
print("\n3. Testing early-stop logic (searching for 'One' button)...")
result = find_element(
    title="One",  # Exact match - should trigger early-stop
    control_type="Button",
    fuzzy=True
)

if result.found:
    print(f"   ✅ Found: '{result.best_match.title}'")
else:
    print("   ❌ Failed to find element")

# Test 3: Show performance metrics
print("\n4. Performance Metrics:")
monitor.report(show_details=True)

# Validate quick wins
summary = monitor.get_summary()
early_stop_rate = summary["search"]["early_stop_rate"]

print("\n=== Quick Wins Validation ===")
if early_stop_rate > 0:
    print(f"✅ Early-stop working: {early_stop_rate}% of searches stopped early")
else:
    print("❌ Early-stop not triggered (may need more confident matches)")

if "fuzzy_match" in summary["operations"]:
    avg_time = summary["operations"]["fuzzy_match"]["avg_ms"]
    print(f"✅ Fuzzy matching tracked: {avg_time:.1f}ms average")
    if avg_time < 50:
        print("   ✨ Excellent performance! (< 50ms)")
else:
    print("❌ Fuzzy matching not tracked")

print("\n✅ Quick Wins test complete!")
print("\nClose Calculator to clean up.")
```

---

## Expected Output

```
=== GUI-Cub Quick Wins Test (macOS/Windows) ===

1. Launching Calculator...

2. Testing fuzzy matching (searching for 'equals' button)...
   ✅ Found: '=' at (x, y)

3. Testing early-stop logic (searching for '1' button)...
   ✅ Found: '1'

4. Performance Metrics:

=== Performance Report ===

Operation Timings:
  find_element_fuzzy_search    n=  2  avg= 25.3ms  min= 18.2ms  max= 32.4ms
  fuzzy_match                  n=  4  avg= 12.1ms  min=  8.5ms  max= 15.7ms

Search Optimization:
  Early Stops:   1
  Full Searches: 1
  Early Stop Rate: 50.0%

=========================

=== Quick Wins Validation ===
✅ Early-stop working: 50.0% of searches stopped early
✅ Fuzzy matching tracked: 12.1ms average
   ✨ Excellent performance! (< 50ms)

✅ Quick Wins test complete!
```

---

## Success Criteria

✅ **All of these should be true:**

1. Both elements found successfully
2. Early-stop rate > 0% (at least 1 confident match)
3. Fuzzy matching average < 50ms
4. Performance report displays timing data
5. No errors or exceptions

---

## Troubleshooting

### "Element not found"

**macOS:**
- Make sure Calculator is launched and visible
- Check Accessibility permissions in System Preferences
- Try different button names ("add", "multiply", "clear")

**Windows:**
- Make sure Calculator is launched and visible
- Try "Plus", "Minus", "Multiply" instead
- Calculator UI varies by Windows version

### "Early-stop rate: 0%"

**Cause:** No confident matches (all scores < 0.85)  
**Solution:** 
- Try exact matches like "1", "2", "3", "="
- Or use more specific search terms
- This is expected if searches are fuzzy/partial

### "Fuzzy matching not tracked"

**Cause:** No fuzzy searches performed  
**Solution:**
- Make sure `fuzzy=True` in function calls
- Check that searches are actually happening

---

## Quick Manual Test

If you prefer to test manually in gui-cub agent:

```
# Switch to gui-cub agent
/agent gui-cub

# macOS: Find Calculator button
desktop_find_accessible_element(role="AXButton", title="equals", fuzzy=True)

# Windows: Find Calculator button  
windows_find_element(title="equals", control_type="Button", fuzzy=True)

# View performance
from code_puppy.tools.gui_cub.performance_monitor import get_monitor
get_monitor().report()
```

---

**Last Updated:** 2025-01-XX  
**Status:** Ready for Testing  
**Platform:** macOS ✅ | Windows ⏳  
