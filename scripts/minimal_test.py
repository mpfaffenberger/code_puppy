#!/usr/bin/env python
"""Minimal test to verify Windows automation is working."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

print("Testing Windows automation import...")

try:
    from code_puppy.tools.gui_cub.windows_automation import (
        list_elements_in_window,
        WINDOWS_AUTOMATION_AVAILABLE,
    )

    print("✅ Import successful!")
    print(f"Windows automation available: {WINDOWS_AUTOMATION_AVAILABLE}")

    if WINDOWS_AUTOMATION_AVAILABLE:
        print("\nTesting list_elements_in_window()...")
        result = list_elements_in_window()
        print(f"Success: {result.get('success', False)}")
        print(f"Total elements: {result.get('total_elements', 0)}")

        if result.get("success"):
            print("✅ Windows automation is working!")
        else:
            print(f"❌ Windows automation failed: {result.get('error')}")
    else:
        print("❌ Windows automation not available on this platform")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
