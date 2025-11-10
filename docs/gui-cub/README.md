# GUI-Cub Documentation

Comprehensive documentation for the GUI-Cub desktop automation toolkit.

## Quick Links

### Test Refactoring Initiative (January 2025)

**Start here:** [`TEST_REFACTOR_SUMMARY.md`](TEST_REFACTOR_SUMMARY.md) - Executive summary

Complete refactoring documentation:

1. **[TEST_AUDIT.md](TEST_AUDIT.md)** - Analysis of current 341 tests
   - Categorization: pure logic vs over-mocked
   - 15 files to delete, 6 files to keep
   - Identified missing testable logic

2. **[TESTABLE_LOGIC_DESIGN.md](TESTABLE_LOGIC_DESIGN.md)** - Architecture design
   - Functional Core, Imperative Shell pattern
   - Refactoring patterns with examples
   - New `logic/` and `adapters/` structure

3. **[TEST_CLEANUP_PLAN.md](TEST_CLEANUP_PLAN.md)** - Execution plan
   - Step-by-step deletion instructions
   - Before/after metrics
   - Validation checklist

4. **[NEW_TEST_STRATEGY.md](NEW_TEST_STRATEGY.md)** - Testing philosophy
   - Test pyramid for gui-cub
   - What to test vs what NOT to test
   - Testing patterns and examples

5. **[TEST_REFACTOR_SUMMARY.md](TEST_REFACTOR_SUMMARY.md)** - Executive summary
   - Problem statement
   - 3-phase plan
   - Expected outcomes

**Status:** Design complete, ready for Phase 1 execution

---

### Feature Documentation

- **[TYPE_STUBS_AND_DISCOVERABILITY_PLAN.md](TYPE_STUBS_AND_DISCOVERABILITY_PLAN.md)** - Type stubs for organizational publishing
- **[FINAL_TYPE_STUBS_AUDIT.md](FINAL_TYPE_STUBS_AUDIT.md)** - Type stubs implementation summary
- **[TOOL_DISCOVERY_BRAINSTORM.md](TOOL_DISCOVERY_BRAINSTORM.md)** - Tool discovery system design
- **[COMPREHENSIVE_VALIDATION_REPORT.md](COMPREHENSIVE_VALIDATION_REPORT.md)** - Static analysis validation

### Accessibility & Quality

- **[ACCESSIBILITY_IMPROVEMENTS.md](ACCESSIBILITY_IMPROVEMENTS.md)** - Accessibility audit and roadmap
- **[QUICK_WINS_SUMMARY.md](QUICK_WINS_SUMMARY.md)** - Quick wins for accessibility
- **[QUICK_WINS_TEST_CASES.md](QUICK_WINS_TEST_CASES.md)** - Test scenarios for quick wins

### Prompts & Testing

- **[TEST_PROMPT.md](TEST_PROMPT.md)** - Testing prompts for gui-cub agent
- **[PROMPT_DUPLICATION_ANALYSIS.md](PROMPT_DUPLICATION_ANALYSIS.md)** - Analysis of prompt duplication

### Future Features

- **[PYWINRT_Future_Features.md](PYWINRT_Future_Features.md)** - WinRT integration roadmap

---

## Project Overview

### What is GUI-Cub?

GUI-Cub is a cross-platform desktop automation toolkit that enables AI agents to interact with desktop applications through:

- **Mouse & Keyboard Control** - Precise input simulation
- **Screen Capture & Analysis** - Screenshot-based element detection
- **OCR & Vision** - Text and visual element recognition  
- **Accessibility APIs** - Native UI element interaction
- **Multi-Monitor Support** - HiDPI and multi-display awareness
- **Workflow Automation** - YAML-based automation workflows

### Architecture

```
gui_cub/
├── logic/               # Pure business logic (testable)
│   ├── click_strategy
│   ├── screenshot_processing
│   └── element_matching
│
├── adapters/           # I/O wrappers (thin, minimal tests)
│   ├── pyautogui_adapter
│   └── screenshot_adapter
│
├── accessibility/      # Native UI element APIs
├── calibration/        # Display detection & scaling
├── ocr/               # Text recognition
├── screen_capture/    # Screenshot utilities
└── workflows/         # Automation workflows
```

### Design Principles

1. **Separation of Concerns** - Logic separate from I/O
2. **Cross-Platform** - Works on macOS, Windows, Linux
3. **HiDPI Aware** - Handles Retina/high-DPI displays
4. **Testable** - Pure functions, minimal mocking
5. **Accessible** - Leverages native accessibility APIs

---

## Testing

### Current State (Pre-Refactoring)

- **Tests:** 341 passing, 24 skipped
- **Files:** 29 test files (~175 KB)
- **Coverage:** 13% (mostly I/O wrappers)
- **Speed:** ~30 seconds
- **Quality:** ❌ 60% over-mocked

### Target State (Post-Refactoring)

- **Tests:** ~150-200 passing
- **Files:** ~17 test files (~70 KB)  
- **Coverage:** ~70% (business logic)
- **Speed:** ~5-8 seconds
- **Quality:** ✅ 100% valuable tests

See [TEST_REFACTOR_SUMMARY.md](TEST_REFACTOR_SUMMARY.md) for details.

---

## Development

### Running Tests

```bash
# Run all gui-cub tests
uv run pytest tests/gui_cub/ -v

# Run specific test file
uv run pytest tests/gui_cub/test_fuzzy_matching.py -v

# Run with coverage
uv run pytest tests/gui_cub/ --cov=code_puppy.tools.gui_cub
```

### Code Organization

Follows **3 consistent organizational patterns** throughout gui-cub:

1. **Flat modules** - Single files for simple features
2. **Package directories** - Complex features with submodules
3. **Type stubs** - `.pyi` files for organizational publishing

See [`__init__.py`](../../code_puppy/tools/gui_cub/__init__.py) for details.

---

## Contributing

### Adding New Features

1. **Identify business logic** - What calculations/decisions are needed?
2. **Extract to `logic/`** - Create pure functions
3. **Write tests first** - Test the logic before I/O
4. **Add I/O wrapper** - Thin adapter in appropriate module
5. **Document** - Add to this README and relevant docs

### Testing Guidelines

See [NEW_TEST_STRATEGY.md](NEW_TEST_STRATEGY.md) for:

- What to test vs what NOT to test
- Testing patterns and examples
- Coverage goals by module type

**Key rule:** Test business logic, not library contracts.

---

## Resources

### Internal Documentation

- All docs in `docs/gui-cub/`
- Start with `TEST_REFACTOR_SUMMARY.md` for current initiative

### External Resources

- [PyAutoGUI Documentation](https://pyautogui.readthedocs.io/)
- [Pillow (PIL) Documentation](https://pillow.readthedocs.io/)
- [macOS Accessibility API](https://developer.apple.com/documentation/accessibility)
- [Windows UI Automation](https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32)

---

## Roadmap

### Q1 2025

- [x] Complete test audit
- [x] Design testable architecture  
- [ ] Execute test cleanup (Phase 1)
- [ ] Extract business logic (Phase 2)
- [ ] Write new tests (Phase 3)

### Q2 2025

- [ ] WinRT integration (see PYWINRT_Future_Features.md)
- [ ] Enhanced accessibility support
- [ ] Performance optimizations

---

## Questions?

See the relevant doc:

- **Testing:** [NEW_TEST_STRATEGY.md](NEW_TEST_STRATEGY.md)
- **Architecture:** [TESTABLE_LOGIC_DESIGN.md](TESTABLE_LOGIC_DESIGN.md)  
- **Refactoring:** [TEST_REFACTOR_SUMMARY.md](TEST_REFACTOR_SUMMARY.md)
- **Accessibility:** [ACCESSIBILITY_IMPROVEMENTS.md](ACCESSIBILITY_IMPROVEMENTS.md)

Or ask in #gui-cub channel.
