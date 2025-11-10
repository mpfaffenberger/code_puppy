# GUI-Cub Testing Strategy Going Forward

**Purpose:** Define what and how we test in gui-cub to maintain high quality without over-mocking

## Core Philosophy

### Test Pyramid for GUI-Cub

```
                    ▲
                   ▌ ▎
                  ▌   ▎  Manual/Exploratory
                 ▌     ▎  (5%)
                ▌       ▎
               ▌─────────▎
              ▌           ▎
             ▌             ▎  Integration Tests
            ▌               ▎  (15%)
           ▌                 ▎
          ▌───────────────────▎
         ▌                     ▎
        ▌                       ▎
       ▌                         ▎  Unit Tests (Pure Logic)
      ▌                           ▎  (80%)
     ▌                             ▎
    ▌───────────────────────────────▎
```

### What We Test

✅ **YES - Pure Business Logic**
- Algorithms (fuzzy matching, scoring, calculations)
- Decision trees (strategy selection, fallback ordering)
- Data transformations (coordinate conversion, validation)
- State management (cleanup policies, threshold detection)

❌ **NO - Library Contracts**
- That pyautogui.click() clicks the mouse
- That PIL opens images correctly
- That Win32 APIs return window bounds
- That Pydantic validates types

⚠️ **MAYBE - Integration Points** (sparingly)
- High-level workflows (click → verify → fallback)
- Cross-platform compatibility (if we have abstraction logic)
- Config loading/saving (use temp files, not mocks)

---

## Testing Patterns

### Pattern 1: Pure Function Testing

**What to test:**
```python
# In click_strategy.py
def score_coordinate_confidence(
    element_bounds: ElementBounds,
    last_known_position: tuple[int, int] | None,
    time_since_update: float
) -> float:
    """Score confidence in coordinate-based clicking (0.0-1.0)."""
    if last_known_position is None:
        return 0.3  # No historical data
    
    if time_since_update > 30.0:
        return 0.2  # Stale data
    
    if time_since_update < 1.0:
        return 0.95  # Very recent
    
    # Linear decay from 0.95 to 0.5 over 30 seconds
    return 0.95 - (time_since_update / 30.0) * 0.45
```

**How to test:**
```python
# In tests/gui_cub/logic/test_click_strategy.py
import pytest
from code_puppy.tools.gui_cub.logic.click_strategy import score_coordinate_confidence
from code_puppy.tools.gui_cub.result_types import ElementBounds

class TestScoreCoordinateConfidence:
    """Test coordinate confidence scoring algorithm."""
    
    def test_returns_low_score_when_no_historical_data(self):
        bounds = ElementBounds(x=100, y=200, width=50, height=30)
        score = score_coordinate_confidence(bounds, None, 0.0)
        assert score == 0.3
    
    def test_returns_high_score_for_recent_updates(self):
        bounds = ElementBounds(x=100, y=200, width=50, height=30)
        score = score_coordinate_confidence(bounds, (100, 200), time_since_update=0.5)
        assert score >= 0.9
    
    def test_returns_low_score_for_stale_data(self):
        bounds = ElementBounds(x=100, y=200, width=50, height=30)
        score = score_coordinate_confidence(bounds, (100, 200), time_since_update=35.0)
        assert score <= 0.3
    
    def test_score_decays_linearly_over_time(self):
        bounds = ElementBounds(x=100, y=200, width=50, height=30)
        
        score_1s = score_coordinate_confidence(bounds, (100, 200), 1.0)
        score_15s = score_coordinate_confidence(bounds, (100, 200), 15.0)
        score_30s = score_coordinate_confidence(bounds, (100, 200), 30.0)
        
        # Should decay monotonically
        assert score_1s > score_15s > score_30s
        
        # Check approximate values
        assert 0.9 <= score_1s <= 1.0
        assert 0.6 <= score_15s <= 0.8
        assert 0.4 <= score_30s <= 0.6
```

**Why this works:**
- No mocks needed
- Tests actual algorithm behavior
- Fast (microseconds)
- Easy to add edge cases

---

### Pattern 2: Decision Logic Testing

**What to test:**
```python
# In click_strategy.py
from enum import Enum

class ClickStrategy(Enum):
    COORDINATES = "coordinates"
    OCR = "ocr"
    VQA = "vqa"

def select_best_strategy(
    coordinate_score: float,
    ocr_score: float,
    vqa_score: float,
    threshold: float = 0.7
) -> ClickStrategy:
    """Select best click strategy based on confidence scores.
    
    Priority:
    1. Use strategy with highest score above threshold
    2. If none above threshold, use coordinates (fastest)
    3. If coordinates unavailable, fall back to OCR → VQA
    """
    scores = [
        (coordinate_score, ClickStrategy.COORDINATES),
        (ocr_score, ClickStrategy.OCR),
        (vqa_score, ClickStrategy.VQA),
    ]
    
    # Find highest score above threshold
    valid_strategies = [(score, strategy) for score, strategy in scores if score >= threshold]
    
    if valid_strategies:
        # Return strategy with highest score
        return max(valid_strategies, key=lambda x: x[0])[1]
    
    # No strategy above threshold - use fastest (coordinates)
    return ClickStrategy.COORDINATES
```

**How to test:**
```python
# In tests/gui_cub/logic/test_click_strategy.py
class TestSelectBestStrategy:
    """Test strategy selection logic."""
    
    def test_selects_coordinates_when_highest_confidence(self):
        strategy = select_best_strategy(
            coordinate_score=0.9,
            ocr_score=0.6,
            vqa_score=0.5
        )
        assert strategy == ClickStrategy.COORDINATES
    
    def test_selects_ocr_when_coordinates_low(self):
        strategy = select_best_strategy(
            coordinate_score=0.3,
            ocr_score=0.85,
            vqa_score=0.5
        )
        assert strategy == ClickStrategy.OCR
    
    def test_falls_back_to_coordinates_when_all_below_threshold(self):
        strategy = select_best_strategy(
            coordinate_score=0.5,
            ocr_score=0.4,
            vqa_score=0.3,
            threshold=0.7
        )
        # No strategy above 0.7, so use fastest (coordinates)
        assert strategy == ClickStrategy.COORDINATES
    
    def test_respects_custom_threshold(self):
        strategy = select_best_strategy(
            coordinate_score=0.6,
            ocr_score=0.5,
            vqa_score=0.4,
            threshold=0.5  # Lower threshold
        )
        # Now 0.6 is above threshold
        assert strategy == ClickStrategy.COORDINATES
    
    @pytest.mark.parametrize(
        "coord,ocr,vqa,expected",
        [
            (0.9, 0.8, 0.7, ClickStrategy.COORDINATES),  # Coordinates wins
            (0.7, 0.9, 0.8, ClickStrategy.OCR),          # OCR wins
            (0.7, 0.8, 0.95, ClickStrategy.VQA),         # VQA wins
            (0.5, 0.5, 0.5, ClickStrategy.COORDINATES),  # All low, use fastest
        ],
    )
    def test_strategy_selection_scenarios(self, coord, ocr, vqa, expected):
        strategy = select_best_strategy(coord, ocr, vqa, threshold=0.7)
        assert strategy == expected
```

**Why this works:**
- Tests decision tree exhaustively
- Parametrized tests cover many scenarios
- No external dependencies
- Clear intent (each test documents a rule)

---

### Pattern 3: Calculation Testing

**What to test:**
```python
# In screenshot_processing.py
def calculate_hidpi_scaling(
    logical_width: int,
    logical_height: int,
    physical_width: int,
    physical_height: int
) -> tuple[float, float]:
    """Calculate HiDPI scaling factors."""
    if logical_width == 0 or logical_height == 0:
        return 1.0, 1.0  # Avoid division by zero
    
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
```

**How to test:**
```python
# In tests/gui_cub/logic/test_screenshot_processing.py
class TestCalculateHiDPIScaling:
    """Test HiDPI scaling calculations."""
    
    def test_1x_display_returns_identity_scaling(self):
        scale_x, scale_y = calculate_hidpi_scaling(
            logical_width=1920,
            logical_height=1080,
            physical_width=1920,
            physical_height=1080
        )
        assert scale_x == 1.0
        assert scale_y == 1.0
    
    def test_2x_retina_display(self):
        scale_x, scale_y = calculate_hidpi_scaling(
            logical_width=1920,
            logical_height=1080,
            physical_width=3840,
            physical_height=2160
        )
        assert scale_x == 2.0
        assert scale_y == 2.0
    
    def test_non_uniform_scaling(self):
        # Some displays have different X/Y scaling
        scale_x, scale_y = calculate_hidpi_scaling(
            logical_width=1920,
            logical_height=1080,
            physical_width=3840,
            physical_height=1620  # Different aspect ratio
        )
        assert scale_x == 2.0
        assert scale_y == 1.5
    
    def test_zero_logical_size_returns_identity(self):
        # Edge case: avoid division by zero
        scale_x, scale_y = calculate_hidpi_scaling(
            logical_width=0,
            logical_height=0,
            physical_width=1920,
            physical_height=1080
        )
        assert scale_x == 1.0
        assert scale_y == 1.0

class TestMapLogicalToPhysical:
    """Test coordinate mapping."""
    
    def test_identity_scaling(self):
        physical_x, physical_y = map_logical_to_physical(
            logical_x=100,
            logical_y=200,
            scale_x=1.0,
            scale_y=1.0
        )
        assert physical_x == 100
        assert physical_y == 200
    
    def test_2x_scaling(self):
        physical_x, physical_y = map_logical_to_physical(
            logical_x=100,
            logical_y=200,
            scale_x=2.0,
            scale_y=2.0
        )
        assert physical_x == 200
        assert physical_y == 400
    
    def test_fractional_scaling_truncates(self):
        physical_x, physical_y = map_logical_to_physical(
            logical_x=100,
            logical_y=200,
            scale_x=1.5,
            scale_y=1.5
        )
        # 100 * 1.5 = 150, 200 * 1.5 = 300
        assert physical_x == 150
        assert physical_y == 300
    
    def test_rounding_behavior(self):
        # int() truncates, not rounds
        physical_x, physical_y = map_logical_to_physical(
            logical_x=100,
            logical_y=100,
            scale_x=1.9,  # Would round to 2.0, but int() truncates
            scale_y=1.9
        )
        assert physical_x == 190  # Not 200!
        assert physical_y == 190
```

**Why this works:**
- Pure math, no I/O
- Tests edge cases (zero, fractional, non-uniform)
- Documents rounding behavior
- Fast and deterministic

---

### Pattern 4: Validation Testing

**What to test:**
```python
# In workflow_validation.py
from dataclasses import dataclass
from typing import Any

@dataclass
class ValidationError:
    field: str
    message: str
    step_index: int | None = None

def validate_workflow_dict(workflow_data: dict[str, Any]) -> list[ValidationError]:
    """Validate workflow structure."""
    errors = []
    
    # Check required top-level fields
    if "steps" not in workflow_data:
        errors.append(ValidationError("steps", "Missing required field 'steps'"))
        return errors  # Can't continue without steps
    
    if not isinstance(workflow_data["steps"], list):
        errors.append(ValidationError("steps", "Field 'steps' must be a list"))
        return errors
    
    # Validate each step
    for i, step in enumerate(workflow_data["steps"]):
        if not isinstance(step, dict):
            errors.append(
                ValidationError("step", f"Step must be dict, got {type(step).__name__}", step_index=i)
            )
            continue
        
        # Required step fields
        if "action" not in step:
            errors.append(ValidationError("action", "Missing required field 'action'", step_index=i))
        
        # Validate parameters if present
        if "parameters" in step:
            if not isinstance(step["parameters"], dict):
                errors.append(
                    ValidationError("parameters", "Field 'parameters' must be dict", step_index=i)
                )
    
    return errors
```

**How to test:**
```python
# In tests/gui_cub/logic/test_workflow_validation.py
class TestValidateWorkflowDict:
    """Test workflow validation logic."""
    
    def test_valid_workflow_returns_no_errors(self):
        workflow = {
            "steps": [
                {"action": "click", "parameters": {"x": 100, "y": 200}},
                {"action": "type", "parameters": {"text": "hello"}},
            ]
        }
        errors = validate_workflow_dict(workflow)
        assert len(errors) == 0
    
    def test_missing_steps_field(self):
        workflow = {"name": "test"}
        errors = validate_workflow_dict(workflow)
        
        assert len(errors) == 1
        assert errors[0].field == "steps"
        assert "Missing" in errors[0].message
    
    def test_steps_must_be_list(self):
        workflow = {"steps": "not a list"}
        errors = validate_workflow_dict(workflow)
        
        assert len(errors) == 1
        assert errors[0].field == "steps"
        assert "must be a list" in errors[0].message
    
    def test_step_must_be_dict(self):
        workflow = {"steps": ["not a dict", {"action": "click"}]}
        errors = validate_workflow_dict(workflow)
        
        assert len(errors) == 1
        assert errors[0].field == "step"
        assert errors[0].step_index == 0
    
    def test_step_missing_action(self):
        workflow = {"steps": [{"parameters": {}}]}
        errors = validate_workflow_dict(workflow)
        
        assert len(errors) == 1
        assert errors[0].field == "action"
        assert errors[0].step_index == 0
    
    def test_parameters_must_be_dict(self):
        workflow = {"steps": [{"action": "click", "parameters": "not dict"}]}
        errors = validate_workflow_dict(workflow)
        
        assert len(errors) == 1
        assert errors[0].field == "parameters"
        assert errors[0].step_index == 0
    
    def test_multiple_errors_accumulated(self):
        workflow = {
            "steps": [
                {"parameters": {}},  # Missing action
                "not dict",           # Not a dict
                {"action": "click", "parameters": "bad"},  # Bad parameters
            ]
        }
        errors = validate_workflow_dict(workflow)
        
        assert len(errors) == 3
```

**Why this works:**
- Tests validation rules, not I/O
- Comprehensive error coverage
- Clear error messages documented by tests
- Easy to add new validation rules

---

## When to Use Integration Tests

### Acceptable Integration Test: Config Loading

```python
# In tests/gui_cub/integration/test_config_integration.py
import tempfile
import json
from pathlib import Path

def test_config_roundtrip():
    """Test config save/load roundtrip."""
    # Use real filesystem (temp directory)
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        
        # Save config
        original_config = {
            "threshold": 0.7,
            "strategies": ["coordinates", "ocr", "vqa"],
        }
        
        with open(config_path, "w") as f:
            json.dump(original_config, f)
        
        # Load config
        with open(config_path) as f:
            loaded_config = json.load(f)
        
        # Validate
        assert loaded_config == original_config
```

**Why this is OK:**
- Tests real I/O (using temp files, not mocks)
- Verifies serialization works end-to-end
- Fast enough (filesystem is fast)
- Tests integration of validation + I/O

---

### Acceptable Integration Test: High-Level Workflow

```python
# In tests/gui_cub/integration/test_click_workflow.py
@pytest.mark.integration
def test_click_workflow_with_fallback():
    """Test complete click workflow with strategy fallback."""
    # Mock only the I/O boundaries, not our logic
    coordinate_finder = Mock(return_value=None)  # Coordinates fail
    ocr_finder = Mock(return_value=Element(x=100, y=200))  # OCR succeeds
    vqa_finder = Mock()  # Not called
    clicker = Mock()
    
    # Execute workflow
    workflow = ClickWorkflow(
        coordinate_finder=coordinate_finder,
        ocr_finder=ocr_finder,
        vqa_finder=vqa_finder,
        clicker=clicker,
    )
    
    result = workflow.execute("Submit Button")
    
    # Verify correct fallback ordering
    assert coordinate_finder.called  # Tried coordinates first
    assert ocr_finder.called         # Fell back to OCR
    assert not vqa_finder.called     # Stopped after OCR success
    assert clicker.called            # Clicked the found element
    assert result.strategy == "ocr"
```

**Why this is OK:**
- Tests orchestration logic, not library contracts
- Mocks are at I/O boundaries only
- Verifies fallback ordering (our business logic)
- Documents intended behavior

---

## What NOT to Test

### ❌ Don't Test Library Behavior

```python
# BAD
def test_pyautogui_clicks(mock_pyautogui):
    click(100, 200)
    mock_pyautogui.click.assert_called_with(100, 200)
    # We're just testing that we call the library!
```

### ❌ Don't Test Pydantic

```python
# BAD
def test_mouse_result_has_x_coordinate():
    result = MouseActionResult(success=True, x=100, y=200)
    assert result.x == 100
    # This tests Pydantic, not our logic
```

### ❌ Don't Mock Our Own Pure Functions

```python
# BAD
def test_click_strategy(mock_score_function):
    mock_score_function.return_value = 0.9
    strategy = select_best_strategy(...)
    # We're not testing our logic at all!
```

---

## Testing Checklist

Before writing a test, ask:

- [ ] **Is this testing OUR logic?** (Not a library)
- [ ] **Can I test this without mocks?** (Pure function)
- [ ] **Does this test document behavior?** (Not implementation)
- [ ] **Will this catch real bugs?** (Not just type errors)
- [ ] **Is this fast?** (< 1ms ideal, < 100ms max)

If 4/5 are "yes", write the test. If <2 are "yes", skip it.

---

## Coverage Goals

### Target Coverage by Module Type

| Module Type | Target Coverage | Why |
|------------|----------------|-----|
| Pure logic (`logic/`) | **95%+** | Easy to test, high value |
| Algorithms (`fuzzy_matching.py`) | **95%+** | Critical, pure functions |
| Data structures (`result_types.py`) | **60%** | Validation only, not creation |
| I/O wrappers (`adapters/`) | **0-20%** | Don't test library contracts |
| Integration (`multi_strategy_click.py`) | **40%** | High-level workflows only |

### Overall Project Coverage

- **Current:** ~13% (lots of untestable wrappers)
- **After cleanup:** ~60% (pure logic only)
- **Goal:** ~70% (with new extracted logic)

**Note:** Higher coverage is NOT always better. 70% of pure logic is more valuable than 95% of mocked wrappers.

---

## Example Test Structure

```
tests/gui_cub/
├── logic/                    # Pure business logic tests (80% of tests)
│   ├── __init__.py
│   ├── test_click_strategy.py
│   ├── test_screenshot_processing.py
│   ├── test_element_matching.py
│   ├── test_workflow_validation.py
│   └── test_movement_calculation.py
│
├── integration/             # Integration tests (15% of tests)
│   ├── __init__.py
│   ├── test_config_integration.py
│   └── test_click_workflow.py
│
├── test_coordinates.py      # Existing pure logic tests
├── test_fuzzy_matching.py   # Existing pure logic tests
├── test_pixel_utils.py      # Existing pure logic tests
├── test_workflows.py        # Existing validation tests
└── conftest.py             # Shared fixtures
```

---

## Key Principles Summary

1. **Test behavior, not implementation**
2. **Prefer pure functions over mocked wrappers**
3. **Extract logic from I/O**
4. **Document intent through tests**
5. **Keep tests fast (<10s total)**
6. **Don't test library contracts**
7. **Coverage quality > coverage quantity**

---

See also:
- `TEST_AUDIT.md` - What we're testing now
- `TESTABLE_LOGIC_DESIGN.md` - How to extract testable logic
- `TEST_CLEANUP_PLAN.md` - Execution plan for cleanup
