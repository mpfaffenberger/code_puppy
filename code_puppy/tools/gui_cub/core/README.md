# GUI-Cub Core Utilities

**Philosophy:** Functional Core, Imperative Shell

This directory contains pure utility functions and library adapters extracted from I/O-heavy wrapper functions. All code here follows these principles:

- ✅ **No side effects** (no file I/O, no network calls, no GUI operations)
- ✅ **Pure functions** (same input always produces same output)
- ✅ **Easily testable** (no mocking required for unit tests)
- ✅ **Type-safe** (comprehensive type hints)
- ✅ **Focused** (single responsibility per module)

---

## 🎯 Architecture

```
┌──────────────────────────────┐
│   I/O Wrapper Tools         │
│   (pyautogui, file I/O,     │
│    API calls, screenshots)  │
└──────────┬───────────────────┘
           │
           │ calls core utilities
           │
┌──────────┴───────────────────┐
│   Core Utilities            │
│   (algorithms, math,        │
│    decision trees, parsers, │
│    library adapters)        │
│                             │
│   THIS DIRECTORY            │
└─────────────────────────────┘
```

**Benefits:**
- 🧪 Easy to test (no I/O mocking)
- 🚀 Fast tests (pure functions are instant)
- 🛡️ Reliable (deterministic behavior)
- 📚 Reusable (no coupling to specific I/O)

---

## 📁 Module Directory

### 1. **`click_offsets/`** ✅
**Purpose:** Calculate optimal click coordinates for UI elements

**Key Functions:**
- `calculate_button_offset(bbox)` - Button click positioning
- `calculate_checkbox_offset(bbox)` - Checkbox precise clicking
- `calculate_link_offset(bbox)` - Link text offset correction
- `calculate_text_field_offset(bbox)` - Input field positioning
- `calculate_dropdown_offset(bbox)` - Dropdown menu targeting
- `is_multiline_text(bbox, text)` - Multiline detection
- `apply_bounds_check(x, y, bounds)` - Coordinate validation

**Used By:** `smart_click_calculator.py`

**Why Extracted:** OCR bounding boxes are approximate (±5-10px). Different element types need different offset strategies. This logic is complex and needs thorough testing.

---

### 2. **`matching/`** ✅
**Purpose:** Fuzzy text matching and scoring

**Key Functions:**
- `normalize_text_pure(text)` - Text normalization (lowercase, trim)
- `generate_identifier_variants(search)` - Generate fuzzy variants
- `calculate_match_score_pure(search, target)` - Similarity scoring
- `explain_match_pure(search, target, score)` - Match explanation

**Used By:** `fuzzy_matching.py` (adds caching layer)

**Why Extracted:** Matching algorithms are pure logic that benefit from extensive unit testing. Separating from caching makes testing easier.

---

### 3. **`element_scoring/`** ✅
**Purpose:** Prioritize UI elements by relevance

**Key Functions:**
- `calculate_element_relevance_score(type, fuzzy_score, depth, ...)` - Scoring
- `generate_score_explanation(...)` - Human-readable scoring rationale

**Used By:** `accessibility/element_list.py`

**Why Extracted:** Element prioritization logic is complex. Buttons should rank higher than text, enabled elements higher than disabled, etc. Pure function makes testing these rules easy.

---

### 4. **`scaling/`** ✅
**Purpose:** HiDPI/Retina coordinate scaling

**Key Functions:**
- `calculate_scale_factor(screen_w, screenshot_w)` - Determine pixel density
- `scale_coordinates(x, y, scale)` - Physical → Logical
- `inverse_scale_coordinates(x, y, scale)` - Logical → Physical
- `validate_scale_factor(scale)` - Sanity check

**Used By:** `platform.py`, OCR tools

**Why Extracted:** Scale factor math is critical for HiDPI displays. Bugs here cause click offsets. Pure math functions are easy to test thoroughly.

---

### 5. **`element_categorization/`** ✅
**Purpose:** Classify UI elements by text content

**Key Functions:**
- `classify_element_by_text(text)` - Categorize as button/field/link/menu/generic
- `categorize_text_list(texts)` - Batch categorization
- `generate_summary_from_categories(...)` - Human-readable summary
- `generate_natural_summary(texts)` - One-step categorize + summarize

**Used By:** `ocr/extraction.py`

**Why Extracted:** Element categorization is pure text processing with keyword matching. Separating from OCR I/O enables easy testing of classification rules.

---

### 6. **`vqa_math/`** ✅
**Purpose:** VQA coordinate transformations and scaling

**Key Functions:**
- `calculate_physical_crop_box(region, scale)` - Logical → Physical pixel conversion
- `calculate_downscale_ratio(w, h, max_dim)` - Determine downscale factor
- `calculate_downscaled_dimensions(w, h, ratio)` - Apply downscale
- `calculate_downscale_dimensions_auto(w, h, max_dim)` - Combined helper

**Used By:** `vqa_vision_click/utils.py`

**Why Extracted:** VQA coordinate math is critical for HiDPI displays and vision model input sizing. Pure math enables thorough testing without image I/O.

---

### 7. **`config_validation/`** ✅
**Purpose:** Configuration validation rules

**Key Functions:**
- `validate_screen_size(current, cached)` - Detect resolution changes
- `validate_platform(current, cached)` - Detect OS changes
- `validate_config_version(version)` - Version compatibility

**Used By:** `config_manager.py`

**Why Extracted:** Validation rules should be testable without file I/O. Pure functions make it easy to test edge cases.

---

### 8. **`browser_offsets/`** ✅
**Purpose:** Browser chrome offset calculation

**Key Functions:**
- `calculate_chrome_offset(browser, platform)` - Browser-specific offsets
- `get_title_bar_height(platform)` - OS title bar height

**Used By:** `browser_offset_detector.py`

**Why Extracted:** Browser chrome heights vary by browser and OS. Pure lookup functions make testing all combinations easy.

---

## 🔧 Usage Guidelines

### Adding New Core Utilities

When writing new GUI-Cub tools, extract pure functions and library adapters to this directory:

**❌ Don't do this:**
```python
# tool_file.py
def smart_click(element_name):
    element = find_element(element_name)  # I/O
    
    # Complex calculation logic mixed with I/O
    if element.width > 100:
        x = element.x + 50
    else:
        x = element.center_x
    
    pyautogui.click(x, element.center_y)  # I/O
```

**✅ Do this:**
```python
# core/click_calculation/calculator.py
def calculate_click_point(
    element_bounds: Bounds,
    strategy: str = "auto"
) -> tuple[int, int]:
    """Calculate optimal click point (PURE FUNCTION)."""
    if strategy == "auto":
        if element_bounds.width > 100:
            x = element_bounds.x + 50
        else:
            x = element_bounds.center_x
    return x, element_bounds.center_y

# tool_file.py  
def smart_click(element_name):
    element = find_element(element_name)  # I/O
    x, y = calculate_click_point(element.bounds)  # Pure logic
    pyautogui.click(x, y)  # I/O
```

### Testing Core Utilities

```python
# tests/test_click_calculation.py
from code_puppy.tools.gui_cub.core.click_calculation import calculate_click_point
from code_puppy.tools.gui_cub.core.click_calculation import Bounds

def test_click_point_wide_element():
    bounds = Bounds(x=100, y=200, width=150, height=40, ...)
    x, y = calculate_click_point(bounds, strategy="auto")
    assert x == 150  # 100 + 50 offset
    assert y == 220  # center_y

def test_click_point_narrow_element():
    bounds = Bounds(x=100, y=200, width=60, height=40, ...)
    x, y = calculate_click_point(bounds, strategy="auto")
    assert x == 130  # center_x
    assert y == 220
```

**No mocking needed! Just pass data and assert results.**

---

## 📊 Quality Standards

### Core Utility Standards

1. **Be pure**
   - No I/O operations
   - No global state mutations
   - Deterministic (same input → same output)

2. **Have type hints**
   ```python
   def calculate_score(text: str, confidence: float) -> float:
       ...
   ```

3. **Have docstrings**
   ```python
   def calculate_offset(bbox: BoundingBox) -> tuple[int, int]:
       """Calculate click offset from bounding box center.
       
       Args:
           bbox: Element bounding box
           
       Returns:
           (x_offset, y_offset) in pixels
       """
   ```

4. **Use dataclasses for structured data**
   ```python
   @dataclass(frozen=True)
   class BoundingBox:
       x: int
       y: int
       width: int
       height: int
   ```

5. **Be testable**
   - Easy to construct input data
   - Easy to verify output
   - No dependencies on external systems

---

## 🔍 Current Status

**Extraction Coverage:** ~75-80% of core business logic

**Modules:** 8 active directories

**Functions:** ~50+ pure functions

**Test Coverage:** Needs improvement (target: 80%+)

---

## 🐞 Known Issues

### Future Extraction Opportunities

Some utilities that could be extracted:

1. **VQA Response Parsing** - Coordinate parsing from text
2. **OCR Filtering** - Noise detection and confidence filtering
3. **Element Filtering** - Some rules scattered in main files

These are documented in `LOGIC_EXTRACTION_AUDIT.md`

---

## 📚 Resources

- **Design Document:** `docs/gui-cub/futureWork/TESTABLE_LOGIC_DESIGN.md`
- **Audit Report:** `LOGIC_EXTRACTION_AUDIT.md`
- **Philosophy:** [Functional Core, Imperative Shell](https://www.destroyallsoftware.com/screencasts/catalog/functional-core-imperative-shell)

---

## ❓ FAQ

**Q: When should I extract utilities to this directory?**

A: Extract when:
- Utility function is complex (>10 lines of calculations/decisions)
- Function needs thorough testing
- Function is reused across multiple files
- Function contains important algorithms or library adapters

**Q: What should NOT go in core/?**

A: Don't extract:
- Simple one-liners
- I/O operations (file reading, API calls, screenshot capture)
- Framework-specific code (pydantic models, tool decorators)
- Thin wrappers (just pass data through)

**Q: How do I test core utilities?**

A: Write standard unit tests:
```python
pytest tests/core/  # Run all core utility tests
```

No special setup needed - pure functions test instantly!

---

**Maintained by:** GUI-Cub Team
**Last Updated:** 2024-12-19