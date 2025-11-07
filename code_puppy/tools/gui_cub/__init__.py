"""GUI-Cub tools for desktop automation.

SUBPACKAGE STRUCTURE PATTERNS:
================================

Three consistent organizational patterns used throughout gui-cub:

1. CORE + TOOLS (for modules with agent tools)
   - core.py: Core functionality and implementation
   - tools.py: Agent tool registration (@agent.tool functions)
   - Example: window_control/, windows_automation/, calibration/

2. FUNCTIONAL SPLIT (for complex feature modules)
   - Multiple focused files by responsibility
   - tools.py: Agent tool registration if applicable
   - Example: screen_capture/ (capture.py, take_screenshot.py, image_utils.py, tools.py)
   - Example: ocr/ (extraction.py, search.py, result_types.py, tools.py)
   - Example: accessibility/ (element_finder.py, element_list.py, tools.py)

3. SINGLE RESPONSIBILITY (for small, focused modules)
   - 2-4 files, each with clear single purpose
   - No tools.py if not registering agent tools
   - Example: vqa_vision_click/ (click.py, utils.py)
   - Example: window_button_detector/ (detector.py, types.py)
   - Example: ocr_providers/ (base.py, provider_chain.py, vision_provider.py)

NOTE: tools.py files are intentionally large (600-1150 lines) because they register
multiple @agent.tool functions with extensive docstrings and examples. This is expected
and correct - breaking them up would fragment related tool definitions.

File Size Target: < 600 lines per file (93% compliance, justified exceptions for tools.py)
"""
