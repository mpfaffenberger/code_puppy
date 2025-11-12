#!/usr/bin/env python
"""Debug multi-window capture."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import re
from pywinauto import Desktop

print("Step 1: List all windows and test pattern matching...\n")

desktop = Desktop(backend="uia")
all_windows = desktop.windows()
pattern = ".*Connexus.*"

print(f"Found {len(all_windows)} total windows\n")

matching = []
for i, win in enumerate(all_windows, 1):
    try:
        title = win.window_text()
        if title:
            matches = re.search(pattern, title, re.IGNORECASE)
            if matches:
                print(f"  {i}. '{title}' <-- MATCH!")
                matching.append((win, title))
            else:
                print(f"  {i}. '{title}'")
    except Exception as e:
        print(f"  {i}. [ERROR: {e}]")

print(f"\nMatched {len(matching)} windows")

if matching:
    print("\nStep 2: Try to traverse first matching window...\n")
    
    win, title = matching[0]
    print(f"Window: '{title}'")
    
    try:
        print("  Getting wrapper_object()...")
        wrapper = win.wrapper_object()
        print(f"  Wrapper: {wrapper}")
        
        print("  Getting children()...")
        children = wrapper.children()
        print(f"  Children count: {len(children)}")
        
        if children:
            print("  First child info:")
            first_child = children[0]
            info = first_child.element_info
            print(f"    Control type: {info.control_type}")
            print(f"    Name: {info.name}")
            
        print("\n  [SUCCESS] Can traverse window!")
        
    except Exception as e:
        print(f"\n  [ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "="*80)
print("\nStep 3: Test list_elements_in_application()...\n")

from code_puppy.tools.gui_cub.windows_automation.core import list_elements_in_application

result = list_elements_in_application(
    app_title_pattern=".*Connexus.*",
    compact=False,
)

print(f"Success: {result.success}")
print(f"Error: {result.error}")
print(f"Total elements: {result.total_elements}")
if isinstance(result.summary, dict):
    print(f"Window count: {result.summary.get('window_count', 0)}")

if result.elements:
    print(f"\nSample elements:")
    for elem in result.elements[:5]:
        print(f"  - {elem.get('control_type')}: '{elem.get('title', '')}' (window: '{elem.get('window_title', '')}')")
