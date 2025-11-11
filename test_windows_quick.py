#!/usr/bin/env python
"""Quick Windows Element Tree Test"""

import sys
from pathlib import Path

# Add code_puppy to path
sys.path.insert(0, str(Path(__file__).parent))

from code_puppy.tools.gui_cub.windows_automation import (
    list_elements_in_window,
    find_element,
)

print("\n" + "="*80)
print("WINDOWS ELEMENT TREE QUICK TEST")
print("Make sure Calculator is open and focused!")
print("="*80)

# Test 1: List all elements
print("\n[TEST 1] Listing elements in active window...")
result = list_elements_in_window()

if result:
    print(f"Success: {result.get('success')}")
    print(f"Total elements: {result.get('total_elements')}")
    print(f"Filtered count: {result.get('filtered_count')}")
    
    elements = result.get('elements', [])
    print(f"\nElements returned: {len(elements)}")
    
    if elements:
        print("\nFirst 10 elements:")
        for i, elem in enumerate(elements[:10]):
            role = elem.get('role') or elem.get('control_type')
            title = elem.get('title') or elem.get('name')
            print(f"  [{i}] {role}: '{title}'")
    
    # Check for buttons specifically
    buttons = [e for e in elements if e.get('control_type') == 'Button' or e.get('role') == 'Button']
    print(f"\nButtons found: {len(buttons)}")
    if buttons:
        print("Button names:")
        for btn in buttons[:5]:
            print(f"  - {btn.get('title') or btn.get('name')}")
    
    # Check compaction
    if result.get('summary'):
        summary = result.get('summary')
        print("\n[COMPACTION CHECK]")
        print(f"  Found: {summary.get('found_count')}")
        print(f"  Returned: {summary.get('returned_count')}")
        print(f"  Filtered: {summary.get('filtered_count')}")
        print(f"  Compaction ratio: {summary.get('compaction_ratio', 0):.2%}")
else:
    print("ERROR: No result returned!")

# Test 2: Find a specific button
print("\n[TEST 2] Finding 'Plus' button...")
find_result = find_element(title="Plus", control_type="Button", fuzzy=True)

if find_result:
    print(f"Success: {find_result.get('success')}")
    print(f"Found: {find_result.get('found')}")
    if find_result.get('found') and find_result.get('best_match'):
        match = find_result.get('best_match')
        print(f"  Title: {match.get('title')}")
        print(f"  Control Type: {match.get('control_type')}")
        print(f"  Center: ({match.get('center_x')}, {match.get('center_y')})")
else:
    print("ERROR: No result returned!")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80 + "\n")
