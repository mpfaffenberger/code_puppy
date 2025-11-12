#!/usr/bin/env python
"""Test multi-window element capture for Connexus.

This tests the new list_elements_in_application() function that captures
all windows belonging to an application (e.g., Connexus main + dialogs).

Usage:
    python test_connexus_multiwindow.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from code_puppy.tools.gui_cub.windows_automation.core import (
    list_elements_in_window,
    list_elements_in_application,
)

print("\n" + "="*80)
print("CONNEXUS MULTI-WINDOW ELEMENT CAPTURE TEST")
print("="*80 + "\n")

# Test 1: Single window (old behavior)
print("TEST 1: list_elements_in_window() - Active window only")
print("-" * 80)

try:
    result = list_elements_in_window(compact=False)
    
    if result.success:
        print(f"[SUCCESS] Found {result.total_elements} elements")
        print(f"  - Element types: {len(result.types or [])}")
    else:
        print(f"[FAILED] {result.error}")
except Exception as e:
    print(f"[ERROR] {e}")

print("\n" + "="*80 + "\n")

# Test 2: All windows (new behavior)
print("TEST 2: list_elements_in_application() - ALL Connexus windows")
print("-" * 80)

try:
    result = list_elements_in_application(
        app_title_pattern=".*Connexus.*",
        compact=False,
    )
    
    if result.success:
        print(f"[SUCCESS] Found {result.total_elements} elements across all windows")
        print(f"  - Element types: {len(result.types or [])}")
        window_count = result.summary.get('window_count', 0) if isinstance(result.summary, dict) else 0
        print(f"  - Windows captured: {window_count}")
        
        # Show which windows were captured
        print(f"\n  Windows found:")
        unique_windows = set(e.get('window_title', '') for e in result.elements)
        for i, window_title in enumerate(sorted(unique_windows), 1):
            if window_title:
                elem_count = sum(1 for e in result.elements if e.get('window_title') == window_title)
                print(f"    {i}. '{window_title}' ({elem_count} elements)")
        
        # Count interactive elements
        interactive_types = ['Button', 'Edit', 'ComboBox', 'CheckBox']
        interactive = [e for e in result.elements if e.get('control_type') in interactive_types]
        print(f"\n  Interactive elements: {len(interactive)}")
        
        # Show depth distribution
        depth_dist = {}
        for elem in result.elements:
            depth = elem.get('depth', 0)
            depth_dist[depth] = depth_dist.get(depth, 0) + 1
        
        max_depth = max(depth_dist.keys()) if depth_dist else 0
        print(f"  Max depth: {max_depth}")
        
        if max_depth > 5:
            beyond_5 = sum(count for depth, count in depth_dist.items() if depth > 5)
            print(f"  Elements beyond depth 5: {beyond_5} (would have been pruned before!)")
        
        # Show sample elements from different windows
        print(f"\n  Sample elements by window:")
        for window_title in sorted(unique_windows)[:3]:
            if window_title:
                window_elements = [e for e in result.elements if e.get('window_title') == window_title]
                print(f"\n    Window: '{window_title}'")
                for elem in window_elements[:5]:
                    ctrl_type = elem.get('control_type', 'Unknown')
                    title = elem.get('title', '')
                    auto_id = elem.get('auto_id', '')
                    print(f"      - {ctrl_type:12} title='{title[:30]}' auto_id='{auto_id}'")
    else:
        print(f"[FAILED] {result.error}")
        
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("COMPARISON")
print("="*80 + "\n")

print("Single window vs. All windows:")
print(f"  - Single window would miss popup dialogs/subflows")
print(f"  - All windows captures complete Connexus UI state")
print(f"\nRecommendation:")
print(f"  - Use list_elements_in_window() for focused interaction")
print(f"  - Use list_elements_in_application() for comprehensive search")

print("\n" + "="*80 + "\n")
