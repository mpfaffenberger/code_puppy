# Testable Logic Architecture Design

**Purpose:** Extract business logic from I/O-heavy wrappers into pure, testable functions

## Design Principles

### 1. **Functional Core, Imperative Shell** 🌰

```
┌────────────────────────────┐
│  Imperative Shell (I/O)   │ ← Thin wrappers, no tests needed
│  - pyautogui calls        │
│  - File I/O               │
│  - API requests           │
└────────┬───────────────────┘
         │
         │ calls
         │
         ↓
┌────────┴───────────────────┐
│  Functional Core (Logic)   │ ← Pure functions, 100% tested
│  - Algorithms             │
│  - Calculations           │
│  - Decision trees         │
│  - Data transformations   │
└────────────────────────────┘
```

**Key idea:** Push all I/O to the edges. Pure logic in the center.

---

### 2. **Dependency Injection for External Services** 💉

Instead of:
```python
# Hard to test - tightly coupled to pyautogui
def click_button(x: int, y: int):
    import pyautogui
    pyautogui.click(x, y)
    return MouseActionResult(success=True, x=x, y=y)
```

Do this:
```python
# Easy to test - injected dependency
class MouseController:
    def __init__(self, clicker: Callable[[int, int], None] = None):
        self.clicker = clicker or pyautogui.click
    
    def click_button(self, x: int, y: int) -> MouseActionResult:
        self.clicker(x, y)
        return MouseActionResult(success=True, x=x, y=y)

# Test without pyautogui
def test_click_button():
    clicks = []
    controller = MouseController(clicker=lambda x, y: clicks.append((x, y)))
    result = controller.click_button(100, 200)
    assert clicks == [(100, 200)]
```

**But wait!** This still doesn't test much logic. Only use DI when there's **actual business logic** to test.

---

### 3. **Separate Calculation from Execution** 🧮

**Bad:** Mixed logic and I/O
```python
def smart_click(element_name: str):
    # 1. Find element (I/O)
    element = find_element_by_name(element_name)
    
    # 2. Calculate click point (LOGIC!)
    if element.bounds.width > 100:
        click_x = element.bounds.x + 50  # Click 50px from left
    else:
        click_x = element.bounds.center_x  # Click center
    
    # 3. Execute click (I/O)
    pyautogui.click(click_x, element.bounds.center_y)
```

**Good:** Extracted calculation
```python
# Pure, testable logic
def calculate_optimal_click_point(
    bounds: ElementBounds,
    strategy: str = "auto"
) -> tuple[int, int]:
    """Calculate optimal click point for element.
    
    Strategy:
    - "auto": Center for small elements, offset for large
    - "center": Always center
    - "offset": 50px from left edge
    """
    if strategy == "center":
        return bounds.center_x, bounds.center_y
    
    if strategy == "offset":
        return bounds.x + 50, bounds.center_y
    
    # Auto strategy
    if bounds.width > 100:
        return bounds.x + 50, bounds.center_y
    else:
        return bounds.center_x, bounds.center_y

# Thin I/O wrapper
def smart_click(element_name: str, strategy: str = "auto"):
    element = find_element_by_name(element_name)
    x, y = calculate_optimal_click_point(element.bounds, strategy)
    pyautogui.click(x, y)

# Easy to test!
def test_large_element_uses_offset():
    bounds = ElementBounds(x=100, y=200, width=500, height=50)
    x, y = calculate_optimal_click_point(bounds, strategy="auto")
    assert x == 150  # 100 + 50
    assert y == 225  # center_y
```

---

## Refactoring Patterns

### Pattern 1: Extract Calculation Functions

**Before:**
```python
# In mouse_control.py (hard to test)
def move_and_click(x: int, y: int, duration: float = 0.5):
    import pyautogui
    
    # Calculate smooth movement curve
    current_x, current_y = pyautogui.position()
    distance = ((x - current_x)**2 + (y - current_y)**2)**0.5
    
    # Adjust duration based on distance
    if distance < 100:
        duration = 0.1
    elif distance < 500:
        duration = 0.3
    else:
        duration = 0.5
    
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()
```

**After:**
```python
# In movement_calculator.py (pure, testable)
def calculate_movement_duration(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    base_duration: float = 0.5
) -> float:
    """Calculate optimal movement duration based on distance.
    
    Returns:
        Duration in seconds (0.1 - 0.5)
    """
    distance = ((end_x - start_x)**2 + (end_y - start_y)**2)**0.5
    
    if distance < 100:
        return 0.1
    elif distance < 500:
        return 0.3
    else:
        return 0.5

# In mouse_control.py (thin wrapper)
def move_and_click(x: int, y: int):
    import pyautogui
    current_x, current_y = pyautogui.position()
    duration = calculate_movement_duration(current_x, current_y, x, y)
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()

# Test the logic!
def test_short_distance_uses_fast_duration():
    duration = calculate_movement_duration(0, 0, 50, 50)
    assert duration == 0.1

def test_long_distance_uses_slow_duration():
    duration = calculate_movement_duration(0, 0, 1000, 1000)
    assert duration == 0.5
```

---

### Pattern 2: Extract Decision Logic

**Before:**
```python
# In multi_strategy_click.py
def click_element(element_name: str, timeout: float = 5.0):
    start_time = time.time()
    
    # Try coordinates
    try:
        element = find_by_coordinates(element_name)
        if element:
            click(element.x, element.y)
            return
    except Exception:
        pass
    
    if time.time() - start_time > timeout:
        raise TimeoutError()
    
    # Try OCR
    try:
        element = find_by_ocr(element_name)
        if element:
            click(element.x, element.y)
            return
    except Exception:
        pass
    
    if time.time() - start_time > timeout:
        raise TimeoutError()
    
    # Try VQA
    element = find_by_vqa(element_name)
    click(element.x, element.y)
```

**After:**
```python
# In strategy_selector.py (pure logic)
from enum import Enum
from dataclasses import dataclass

class ClickStrategy(Enum):
    COORDINATES = "coordinates"
    OCR = "ocr"
    VQA = "vqa"

@dataclass
class StrategyConfig:
    """Configuration for click strategy fallback."""
    strategies: list[ClickStrategy]
    timeout_per_strategy: float = 2.0
    
DEFAULT_STRATEGY = StrategyConfig(
    strategies=[ClickStrategy.COORDINATES, ClickStrategy.OCR, ClickStrategy.VQA],
    timeout_per_strategy=2.0
)

def select_next_strategy(
    attempted: list[ClickStrategy],
    available: list[ClickStrategy],
    elapsed_time: float,
    total_timeout: float
) -> ClickStrategy | None:
    """Select next strategy to try.
    
    Returns:
        Next strategy to attempt, or None if timeout/exhausted
    """
    if elapsed_time >= total_timeout:
        return None
    
    for strategy in available:
        if strategy not in attempted:
            return strategy
    
    return None

# Test the decision logic!
def test_returns_first_unattempted_strategy():
    attempted = [ClickStrategy.COORDINATES]
    available = [ClickStrategy.COORDINATES, ClickStrategy.OCR, ClickStrategy.VQA]
    
    next_strategy = select_next_strategy(attempted, available, elapsed_time=1.0, total_timeout=5.0)
    assert next_strategy == ClickStrategy.OCR

def test_returns_none_when_timeout_exceeded():
    attempted = []
    available = [ClickStrategy.COORDINATES]
    
    next_strategy = select_next_strategy(attempted, available, elapsed_time=6.0, total_timeout=5.0)
    assert next_strategy is None
```

---

### Pattern 3: Extract Validation & Parsing

**Before:**
```python
# In workflows.py
def execute_workflow(workflow_file: str):
    with open(workflow_file) as f:
        workflow_data = yaml.safe_load(f)
    
    # Validation mixed with I/O
    if "steps" not in workflow_data:
        raise ValueError("Missing steps")
    
    for step in workflow_data["steps"]:
        if "action" not in step:
            raise ValueError(f"Step missing action: {step}")
        
        # Execute step
        execute_step(step)
```

**After:**
```python
# In workflow_validator.py (pure logic)
from typing import Any
from dataclasses import dataclass

@dataclass
class ValidationError:
    field: str
    message: str
    step_index: int | None = None

def validate_workflow_dict(workflow_data: dict[str, Any]) -> list[ValidationError]:
    """Validate workflow structure.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if "steps" not in workflow_data:
        errors.append(ValidationError("steps", "Missing required field 'steps'"))
        return errors
    
    if not isinstance(workflow_data["steps"], list):
        errors.append(ValidationError("steps", "Field 'steps' must be a list"))
        return errors
    
    for i, step in enumerate(workflow_data["steps"]):
        if not isinstance(step, dict):
            errors.append(ValidationError("step", f"Step must be dict, got {type(step)}", step_index=i))
            continue
        
        if "action" not in step:
            errors.append(ValidationError("action", "Step missing required field 'action'", step_index=i))
    
    return errors

# In workflows.py (thin I/O wrapper)
def execute_workflow(workflow_file: str):
    with open(workflow_file) as f:
        workflow_data = yaml.safe_load(f)
    
    errors = validate_workflow_dict(workflow_data)
    if errors:
        raise ValueError(f"Invalid workflow: {errors}")
    
    for step in workflow_data["steps"]:
        execute_step(step)

# Easy to test!
def test_detects_missing_steps_field():
    workflow = {"name": "test"}
    errors = validate_workflow_dict(workflow)
    assert len(errors) == 1
    assert errors[0].field == "steps"

def test_detects_missing_action_in_step():
    workflow = {"steps": [{"description": "test"}]}
    errors = validate_workflow_dict(workflow)
    assert len(errors) == 1
    assert errors[0].field == "action"
    assert errors[0].step_index == 0
```

---

## Specific Refactorings for GUI-Cub

### 1. Extract `ClickStrategyEngine`

**Location:** New file `code_puppy/tools/gui_cub/click_strategy_engine.py`

**What it does:**
- Selects optimal click strategy based on context
- Manages fallback ordering
- Scores confidence of each strategy

**Pure functions to extract:**
```python
def score_coordinate_confidence(
    element_bounds: ElementBounds,
    last_known_position: tuple[int, int] | None,
    time_since_update: float
) -> float:
    """Score confidence in coordinate-based clicking (0.0-1.0)."""
    ...

def score_ocr_confidence(
    text_match_score: float,
    text_length: int,
    font_clarity: float
) -> float:
    """Score confidence in OCR-based clicking (0.0-1.0)."""
    ...

def select_best_strategy(
    coordinate_score: float,
    ocr_score: float,
    vqa_score: float,
    threshold: float = 0.7
) -> ClickStrategy:
    """Select strategy with highest confidence above threshold."""
    ...
```

**Tests:**
```python
def test_prefers_coordinates_when_recently_updated():
    score = score_coordinate_confidence(
        element_bounds=ElementBounds(...),
        last_known_position=(100, 200),
        time_since_update=0.5  # Recent
    )
    assert score > 0.8

def test_low_confidence_when_stale_coordinates():
    score = score_coordinate_confidence(
        element_bounds=ElementBounds(...),
        last_known_position=(100, 200),
        time_since_update=30.0  # Stale
    )
    assert score < 0.5
```

---

### 2. Extract `ScreenshotProcessor`

**Location:** New file `code_puppy/tools/gui_cub/screenshot_processor.py`

**Pure functions:**
```python
def calculate_hidpi_scaling(
    logical_width: int,
    logical_height: int,
    physical_width: int,
    physical_height: int
) -> tuple[float, float]:
    """Calculate HiDPI scaling factors.
    
    Returns:
        (scale_x, scale_y) scaling factors
    """
    scale_x = physical_width / logical_width
    scale_y = physical_height / logical_height
    return scale_x, scale_y

def map_logical_to_physical(
    logical_x: int,
    logical_y: int,
    scale_x: float,
    scale_y: float
) -> tuple[int, int]:
    """Map logical coordinates to physical pixels."""
    physical_x = int(logical_x * scale_x)
    physical_y = int(logical_y * scale_y)
    return physical_x, physical_y

def calculate_crop_region(
    center_x: int,
    center_y: int,
    width: int,
    height: int,
    image_width: int,
    image_height: int
) -> tuple[int, int, int, int]:
    """Calculate crop region clamped to image bounds.
    
    Returns:
        (left, top, right, bottom) in image coordinates
    """
    half_width = width // 2
    half_height = height // 2
    
    left = max(0, center_x - half_width)
    top = max(0, center_y - half_height)
    right = min(image_width, center_x + half_width)
    bottom = min(image_height, center_y + half_height)
    
    return left, top, right, bottom
```

**Tests:**
```python
def test_calculates_2x_retina_scaling():
    scale_x, scale_y = calculate_hidpi_scaling(
        logical_width=1920,
        logical_height=1080,
        physical_width=3840,
        physical_height=2160
    )
    assert scale_x == 2.0
    assert scale_y == 2.0

def test_crop_region_clamped_to_image_bounds():
    # Try to crop near edge - should clamp
    left, top, right, bottom = calculate_crop_region(
        center_x=50,  # Near left edge
        center_y=50,  # Near top edge
        width=200,
        height=200,
        image_width=1920,
        image_height=1080
    )
    assert left == 0  # Clamped to left edge
    assert top == 0   # Clamped to top edge
```

---

### 3. Extract `ElementMatcher`

**Location:** New file `code_puppy/tools/gui_cub/element_matcher.py`

**Pure functions:**
```python
def score_attribute_match(
    search_text: str,
    element_attributes: dict[str, str],
    weights: dict[str, float] | None = None
) -> float:
    """Score how well element attributes match search text.
    
    Args:
        search_text: Text to search for
        element_attributes: {"title": "Submit", "description": "Submit form", ...}
        weights: Attribute weights {"title": 1.0, "description": 0.5, ...}
    
    Returns:
        Match score (0.0-1.0)
    """
    weights = weights or {"title": 1.0, "description": 0.7, "role": 0.5}
    
    total_score = 0.0
    total_weight = 0.0
    
    for attr, value in element_attributes.items():
        if attr not in weights:
            continue
        
        weight = weights[attr]
        similarity = fuzzy_match(search_text, value)  # 0.0-1.0
        
        total_score += similarity * weight
        total_weight += weight
    
    return total_score / total_weight if total_weight > 0 else 0.0

def score_position_relevance(
    element_x: int,
    element_y: int,
    preferred_x: int | None = None,
    preferred_y: int | None = None
) -> float:
    """Score element position relevance (closer = higher score)."""
    if preferred_x is None or preferred_y is None:
        return 1.0  # No position preference
    
    distance = ((element_x - preferred_x)**2 + (element_y - preferred_y)**2)**0.5
    
    # Exponential decay: close = 1.0, far = 0.0
    return math.exp(-distance / 1000)
```

---

## File Organization

```
code_puppy/tools/gui_cub/
├── logic/                      # NEW: Pure business logic
│   ├── __init__.py
│   ├── click_strategy.py      # Strategy selection logic
│   ├── screenshot_processing.py  # Image calculations
│   ├── element_matching.py    # Element scoring/matching
│   ├── workflow_validation.py # Workflow parsing/validation
│   └── movement_calculation.py # Mouse movement math
│
├── adapters/                  # NEW: I/O adapters (thin wrappers)
│   ├── __init__.py
│   ├── pyautogui_adapter.py   # Wraps pyautogui
│   ├── screenshot_adapter.py  # Wraps PIL/mss
│   └── platform_adapter.py    # Wraps OS APIs
│
├── coordinates.py             # KEEP (pure math)
├── fuzzy_matching.py          # KEEP (pure algorithms)
├── pixel_utils.py             # KEEP (pure color math)
├── result_types.py            # KEEP (data structures)
└── ...
```

---

## Migration Strategy

### Phase 1: Extract Pure Logic (Week 1)
1. Create `logic/` directory
2. Move pure functions from existing modules:
   - Coordinate calculations → Already pure!
   - Fuzzy matching → Already pure!
   - Pixel color math → Already pure!
3. Extract new pure logic:
   - Screenshot processing calculations
   - Click strategy scoring
   - Element matching algorithms

### Phase 2: Create Adapters (Week 2)
1. Create `adapters/` directory
2. Wrap external dependencies:
   - `pyautogui_adapter.py` - Mouse/keyboard calls
   - `screenshot_adapter.py` - Screenshot capture
   - `platform_adapter.py` - OS-specific APIs
3. Update existing code to use adapters

### Phase 3: Write Tests (Week 3)
1. Test all `logic/` modules (100% coverage)
2. Delete over-mocked tests from old suite
3. Add integration tests for adapters (optional)

---

## Benefits

1. **Faster tests:** Pure functions run in microseconds, no I/O
2. **Higher coverage:** Can test edge cases without complex mocking
3. **Better design:** Forces thinking about what's logic vs I/O
4. **Easier debugging:** Logic bugs isolated from library issues
5. **Portable:** Logic can be reused across platforms

---

## Anti-Patterns to Avoid

❌ **Don't test library behavior:**
```python
# BAD: Testing that pyautogui.click works
def test_click_calls_pyautogui(mock_pg):
    click(100, 200)
    mock_pg.click.assert_called_with(100, 200)
```

❌ **Don't mock pure functions:**
```python
# BAD: Mocking our own pure logic
def test_coordinate_conversion(mock_converter):
    mock_converter.return_value = (300, 400)
    result = window_to_screen_coords(200, 300, bounds)
    # We're not testing anything!
```

✅ **Do test decision logic:**
```python
# GOOD: Testing our strategy selection
def test_prefers_coordinates_over_ocr_when_confident():
    strategy = select_best_strategy(
        coordinate_confidence=0.95,
        ocr_confidence=0.70,
        vqa_confidence=0.60
    )
    assert strategy == ClickStrategy.COORDINATES
```

✅ **Do test edge cases:**
```python
# GOOD: Testing boundary conditions
def test_crop_region_handles_zero_size_image():
    region = calculate_crop_region(
        center_x=50, center_y=50,
        width=100, height=100,
        image_width=0,  # Edge case!
        image_height=0
    )
    assert region == (0, 0, 0, 0)
```

---

See also:
- `TEST_AUDIT.md` - Which tests to keep/delete
- `TEST_CLEANUP_PLAN.md` - Detailed cleanup steps
- `NEW_TEST_STRATEGY.md` - Testing philosophy going forward
