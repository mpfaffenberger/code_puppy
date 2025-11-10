# GUI-Cub Test Cleanup Plan

**Goal:** Remove over-mocked tests and establish a clean, maintainable test suite

## Phase 1: Delete Over-Mocked Tests

### Files to Delete Completely (15 files)

```bash
# 1. Keyboard control tests (all mocked pyautogui calls)
rm tests/gui_cub/test_keyboard_control.py           # 10.4 KB
rm tests/gui_cub/test_keyboard_shortcuts.py         # 3.6 KB

# 2. Mouse control tests (all mocked pyautogui calls)
rm tests/gui_cub/test_mouse_control.py              # 2.8 KB
rm tests/gui_cub/test_mouse_control_comprehensive.py  # 13.8 KB

# 3. Platform/calibration tests (all mocked OS APIs)
rm tests/gui_cub/test_calibration.py                # 3.8 KB
rm tests/gui_cub/test_platform.py                   # 7.8 KB
rm tests/gui_cub/test_platform_detection.py         # 1.0 KB
rm tests/gui_cub/test_platform_utils.py             # 3.2 KB

# 4. OCR/VQA tests (all mocked external APIs)
rm tests/gui_cub/test_ocr_tools.py                  # 4.3 KB
rm tests/gui_cub/test_vqa_desktop.py                # 11.1 KB

# 5. Unified OS tools (just wrapper tests)
rm tests/gui_cub/test_os_unified_tools.py           # 8.9 KB

# 6. Screen capture tests (mocked screenshot APIs)
rm tests/gui_cub/test_screen_capture.py             # 7.8 KB

# 7. Misc wrapper tests
rm tests/gui_cub/test_scale_api.py                  # 0.5 KB
rm tests/gui_cub/test_windows_click_fuzzy_signature.py  # 1.6 KB
rm tests/gui_cub/test_hover_defaults.py             # 1.2 KB
```

**Total deletion:** ~81.8 KB of test code

---

### Files to Partially Refactor (5 files)

#### 1. `test_pixel_color_detection.py` (13.9 KB → ~2 KB)

**Delete:** All mocked screenshot tests
```python
# DELETE: These test PIL/pyautogui, not our logic
class TestPixelColorDetection:
    def test_sample_single_pixel_1x_display(self):  # Mocked pyautogui
        ...
    
    def test_sample_single_pixel_2x_display(self):  # Mocked pyautogui
        ...
```

**Keep:** Pure scaling calculation tests (if we extract the logic)
```python
# KEEP: Tests pure math
def test_calculate_hidpi_scaling_2x():
    scale_x, scale_y = calculate_hidpi_scaling(
        logical_width=1920,
        logical_height=1080,
        physical_width=3840,
        physical_height=2160
    )
    assert scale_x == 2.0
    assert scale_y == 2.0
```

**Action:**
```bash
# Extract the scaling logic first
cp code_puppy/tools/gui_cub/pixel_utils.py code_puppy/tools/gui_cub/logic/screenshot_processing.py

# Then simplify test to only test pure functions
vim tests/gui_cub/test_pixel_color_detection.py
# Delete classes: TestPixelColorDetection, TestSampleNeighborhood, etc.
# Keep: TestHiDPIScaling (if logic extracted)
```

---

#### 2. `test_result_types.py` (5.7 KB → ~2 KB)

**Delete:** Simple object creation tests
```python
# DELETE: Just tests Pydantic, no value
def test_mouse_action_result_creation():
    result = MouseActionResult(success=True, x=100, y=200)
    assert result.x == 100  # Duh!
```

**Keep:** Validation edge cases
```python
# KEEP: Tests our validation logic
def test_mouse_action_requires_coordinates():
    with pytest.raises(ValidationError):
        MouseActionResult(success=True, x=None, y=200)

def test_click_count_must_be_positive():
    with pytest.raises(ValidationError):
        MouseActionResult(success=True, x=100, y=200, clicks=-1)
```

**Action:**
```bash
vim tests/gui_cub/test_result_types.py
# Delete ~60% of trivial creation tests
# Keep validation tests, edge cases, serialization tests
```

---

#### 3. `test_tool_wrapper.py` (9.4 KB → evaluate)

**Decision:** Read the file and check if there's actual wrapping logic.

**If it's just registration:**
```python
# DELETE
def test_tool_registered():
    assert "click" in agent.tools  # No value
```

**If there's error handling logic:**
```python
# KEEP
def test_wraps_exceptions_with_context():
    # Tests our error transformation
    ...
```

**Action:**
```bash
vim tests/gui_cub/test_tool_wrapper.py
# Read and decide
# If mostly registration tests: DELETE
# If has error handling logic: Refactor to test pure error transformation
```

---

#### 4. `test_locking.py` (6.2 KB → evaluate)

**Decision:** Is it using standard library locks or custom logic?

**If using threading.Lock:**
```python
# DELETE - testing standard library
import threading

lock = threading.Lock()
lock.acquire()  # We don't need to test this!
```

**If custom lock implementation:**
```python
# KEEP - testing our logic
class SmartLock:
    def acquire_with_timeout(self, timeout: float) -> bool:
        # Custom logic - test this!
        ...
```

**Action:**
```bash
vim tests/gui_cub/test_locking.py
# If trivial wrapper: DELETE
# If custom logic: KEEP
```

---

#### 5. `test_debug_screenshot_manager.py` (8.5 KB → ~4 KB)

**Delete:** File I/O tests
```python
# DELETE: Tests filesystem, not logic
def test_saves_screenshot_to_disk(tmp_path):
    manager.save_screenshot(image, tmp_path / "test.png")
    assert (tmp_path / "test.png").exists()
```

**Keep:** Filename generation logic
```python
# KEEP: Tests our naming convention
def test_generates_unique_filenames():
    name1 = generate_screenshot_filename("test", timestamp=1000)
    name2 = generate_screenshot_filename("test", timestamp=1001)
    assert name1 != name2
    assert name1.startswith("test_")

def test_sanitizes_invalid_filename_characters():
    name = generate_screenshot_filename("test/with/slashes")
    assert "/" not in name
```

**Keep:** Cleanup logic
```python
# KEEP: Tests our cleanup algorithm
def test_cleanup_deletes_oldest_files_first():
    files = [
        ("old.png", timestamp=1000),
        ("new.png", timestamp=2000),
    ]
    to_delete = select_files_for_cleanup(files, max_files=1)
    assert to_delete == ["old.png"]
```

**Action:**
```bash
vim tests/gui_cub/test_debug_screenshot_manager.py
# Delete I/O tests
# Keep filename generation and cleanup logic tests
```

---

## Phase 2: Keep High-Value Tests

### Files to Keep (6 files, no changes needed)

```bash
# Already pure logic - no changes needed
tests/gui_cub/test_fuzzy_matching.py          # 6.4 KB ✅
tests/gui_cub/test_coordinates.py             # 7.3 KB ✅
tests/gui_cub/test_pixel_utils.py             # 1.9 KB ✅
tests/gui_cub/test_workflows.py               # 13.3 KB ✅
tests/gui_cub/test_config_manager.py          # 5.4 KB ✅ (or refactor if heavy I/O)
tests/gui_cub/test_performance_monitor_comprehensive.py  # 11.0 KB ✅ (or refactor)
```

These test pure logic and are already well-written.

---

## Phase 3: Add New Tests for Extracted Logic

After extracting business logic (see `TESTABLE_LOGIC_DESIGN.md`), add tests:

### New Test Files to Create

```bash
# 1. Click strategy logic
tests/gui_cub/logic/test_click_strategy.py

# 2. Screenshot processing math
tests/gui_cub/logic/test_screenshot_processing.py

# 3. Element matching algorithms
tests/gui_cub/logic/test_element_matching.py

# 4. Workflow validation
tests/gui_cub/logic/test_workflow_validation.py

# 5. Movement calculations
tests/gui_cub/logic/test_movement_calculation.py
```

---

## Execution Plan

### Step 1: Backup Current Tests
```bash
cd tests/gui_cub
tar -czf ../gui_cub_tests_backup_$(date +%Y%m%d).tar.gz .
```

### Step 2: Delete Over-Mocked Tests
```bash
#!/bin/bash
# delete_overmocked_tests.sh

cd tests/gui_cub

# Keyboard/mouse control
rm test_keyboard_control.py
rm test_keyboard_shortcuts.py
rm test_mouse_control.py
rm test_mouse_control_comprehensive.py

# Platform/calibration
rm test_calibration.py
rm test_platform.py
rm test_platform_detection.py
rm test_platform_utils.py

# OCR/VQA
rm test_ocr_tools.py
rm test_vqa_desktop.py

# Wrappers
rm test_os_unified_tools.py
rm test_screen_capture.py
rm test_scale_api.py
rm test_windows_click_fuzzy_signature.py
rm test_hover_defaults.py

echo "Deleted 15 over-mocked test files"
```

### Step 3: Refactor Partial Files
```bash
# Manually edit these 5 files:
vim test_pixel_color_detection.py  # Reduce 13.9 KB → ~2 KB
vim test_result_types.py           # Reduce 5.7 KB → ~2 KB
vim test_tool_wrapper.py           # Evaluate & reduce
vim test_locking.py                # Evaluate & reduce
vim test_debug_screenshot_manager.py  # Reduce 8.5 KB → ~4 KB
```

### Step 4: Run Remaining Tests
```bash
uv run pytest tests/gui_cub/ -v

# Expected result:
# ~80-100 tests passing (down from 341)
# All failures should be from deleted dependencies
```

### Step 5: Update Test Count
```bash
# Update this doc with actual numbers
vim docs/gui-cub/TEST_CLEANUP_PLAN.md
```

---

## Before & After Comparison

### Before Cleanup
```
Tests:        341 passed, 24 skipped
Test files:   29 files
Total size:   ~175 KB
Coverage:     13% (mostly I/O wrappers)
Test speed:   ~30 seconds (lots of mocking overhead)
```

### After Cleanup (Projected)
```
Tests:        ~80-100 passed, 10 skipped
Test files:   ~10-12 files
Total size:   ~50 KB
Coverage:     ~60% (pure logic only)
Test speed:   ~3-5 seconds (no mocking)
```

### After Phase 3 (Add New Tests)
```
Tests:        ~150-200 passed, 10 skipped
Test files:   ~15 files
Total size:   ~70 KB
Coverage:     ~85% (all business logic)
Test speed:   ~5-8 seconds
```

---

## Validation Checklist

Before merging cleanup:

- [ ] All remaining tests pass
- [ ] No broken imports from deleted test files
- [ ] Coverage report shows we're testing **logic**, not wrappers
- [ ] Test suite runs in <10 seconds
- [ ] Documentation updated (this file, TEST_AUDIT.md)
- [ ] Team reviewed and approved the changes

---

## Communication Plan

### Announcement (Before Cleanup)

```markdown
**Subject:** Cleaning up gui-cub test suite - removing over-mocked tests

**Context:**
Our current test suite has 341 tests, but ~60% are testing library contracts
(pyautogui, PIL, etc.) rather than our business logic. This creates:
- Slow test runs (~30s)
- False confidence (mocks don't catch real issues)
- Maintenance burden (update mocks when libraries change)

**Plan:**
We're deleting ~15 files of over-mocked tests and keeping only tests that
validate our algorithms and business logic.

**Impact:**
- Test count drops: 341 → ~80-100
- Test speed improves: 30s → ~5s
- Coverage quality improves: 13% wrappers → 60%+ pure logic

**Next Steps:**
Phase 3 will add new tests for extracted business logic, bringing us to
~150-200 tests with much higher value.

**Questions?** See docs/gui-cub/TEST_AUDIT.md
```

---

## Rollback Plan

If cleanup causes issues:

```bash
# Restore from backup
cd tests/gui_cub
rm -rf *
tar -xzf ../gui_cub_tests_backup_YYYYMMDD.tar.gz

# Restore git history
git checkout HEAD~1 tests/gui_cub/
```

---

## Success Criteria

1. ✅ Test suite runs in <10 seconds
2. ✅ All remaining tests are valuable (test logic, not libraries)
3. ✅ Coverage focuses on business logic, not I/O wrappers
4. ✅ No flaky tests from complex mocking
5. ✅ Easy to add new tests (pure functions)
6. ✅ Team understands and approves the changes

---

See also:
- `TEST_AUDIT.md` - Complete audit of current tests
- `TESTABLE_LOGIC_DESIGN.md` - Architecture for separating logic from I/O
- `NEW_TEST_STRATEGY.md` - Testing philosophy going forward
