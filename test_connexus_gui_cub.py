#!/usr/bin/env python
"""Test gui-cub element finding on Connexus after depth limit fix.

This script tests the ACTUAL gui-cub library functions (not raw comtypes)
to verify that increasing the depth limit from 5 to 15 allows finding
all interactive elements.

Usage:
    1. Make sure Connexus is open and focused
    2. python test_connexus_gui_cub.py
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from code_puppy.tools.gui_cub.windows_automation.core import (
    list_elements_in_window,
    find_element,
)

print("\n" + "="*80)
print("GUI-CUB ELEMENT FINDING TEST - CONNEXUS DROP-OFF")
print("="*80 + "\n")

print("[*] Testing list_elements_in_window() with depth=15 fix...\n")

# Test 1: Get ALL elements (no compaction)
print("TEST 1: List ALL elements (compact=False)")
print("-" * 80)

result = list_elements_in_window(compact=False)

if result.success:
    print(f"[SUCCESS] Found {result.total_elements} total elements")
    print(f"  - Element types: {len(result.types or [])}")
    
    # Count interactive elements
    interactive_types = ['Button', 'Edit', 'ComboBox', 'CheckBox']
    interactive_count = 0
    
    depth_dist = {}
    interactive_by_depth = {}
    
    for elem in result.elements:
        control_type = elem.get('control_type', '')
        depth = elem.get('depth', 0)
        
        # Track depth distribution
        depth_dist[depth] = depth_dist.get(depth, 0) + 1
        
        if control_type in interactive_types:
            interactive_count += 1
            interactive_by_depth[depth] = interactive_by_depth.get(depth, 0) + 1
    
    print(f"  - Interactive elements: {interactive_count}")
    print(f"\n  Depth Distribution:")
    print(f"  Depth | Total | Interactive")
    print(f"  " + "-" * 35)
    
    max_depth = max(depth_dist.keys()) if depth_dist else 0
    for depth in range(0, max_depth + 1):
        total = depth_dist.get(depth, 0)
        interactive = interactive_by_depth.get(depth, 0)
        marker = "  <-- PREVIOUSLY PRUNED!" if depth > 5 else ""
        print(f"  {depth:5} | {total:5} | {interactive:11}{marker}")
    
    # Count interactive beyond depth 5
    beyond_5 = sum(count for depth, count in interactive_by_depth.items() if depth > 5)
    print(f"\n  [KEY METRIC] Interactive elements beyond depth 5: {beyond_5}")
    
    if beyond_5 > 0:
        print(f"  [SUCCESS] We can now find {beyond_5} elements that were previously pruned!")
    else:
        print(f"  [INFO] All interactive elements are within depth 5")
    
else:
    print(f"[ERROR] {result.error}")

print("\n" + "="*80)

# Test 2: Find specific elements
print("\nTEST 2: Find specific interactive elements")
print("-" * 80)

test_cases = [
    {"title": "Accept", "type": "Button", "description": "Accept button"},
    {"title": "Order Notes", "type": "Button", "description": "Order Notes button"},
    {"title": "Input", "type": None, "description": "Input button (multi-line name)"},
]

for i, test in enumerate(test_cases, 1):
    print(f"\n[{i}] Searching for: {test['description']}")
    print(f"    Query: title='{test['title']}', control_type={test['type']}")
    
    result = find_element(
        title=test['title'],
        control_type=test['type'],
        fuzzy=True,
    )
    
    if result.success and result.found:
        print(f"    [SUCCESS] Found element!")
        print(f"      - Name: '{result.best_match.name}'")
        print(f"      - AutomationId: '{result.best_match.automation_id}'")
        print(f"      - ControlType: {result.best_match.control_type}")
        print(f"      - Position: ({result.best_match.x}, {result.best_match.y})")
    else:
        print(f"    [FAILED] Not found")
        if result.error:
            print(f"      Error: {result.error}")

print("\n" + "="*80)

# Test 3: Search for elements with multi-line names
print("\nTEST 3: Multi-line name handling")
print("-" * 80)

print("\nSearching for elements that have newlines in names...")

# Get all elements
all_result = list_elements_in_window(compact=False)

if all_result.success:
    multiline_elements = [
        e for e in all_result.elements 
        if '\n' in str(e.get('title', ''))
    ]
    
    print(f"Found {len(multiline_elements)} elements with multi-line names\n")
    
    for i, elem in enumerate(multiline_elements[:10], 1):
        name = elem.get('title', '')
        name_preview = name.replace('\n', '\\n')[:60]
        print(f"  [{i}] {elem.get('control_type', 'Unknown'):12} - '{name_preview}'")
        print(f"      AutomationId: '{elem.get('auto_id', '')}'")
    
    if len(multiline_elements) > 10:
        print(f"  ... and {len(multiline_elements) - 10} more")

print("\n" + "="*80)

# Test 4: Elements with empty names but good AutomationIds
print("\nTEST 4: Empty name but AutomationId present")
print("-" * 80)

if all_result.success:
    empty_name_with_id = [
        e for e in all_result.elements
        if not e.get('title', '').strip() and e.get('auto_id', '').strip()
    ]
    
    print(f"\nFound {len(empty_name_with_id)} elements with empty name but AutomationId\n")
    
    for i, elem in enumerate(empty_name_with_id[:10], 1):
        print(f"  [{i}] {elem.get('control_type', 'Unknown'):12} - AutomationId: '{elem.get('auto_id', '')}'")
    
    if len(empty_name_with_id) > 10:
        print(f"  ... and {len(empty_name_with_id) - 10} more")

print("\n" + "="*80)
print("SUMMARY")
print("="*80 + "\n")

if result.success:
    print("[SUCCESS] Depth limit fix is working!")
    print(f"  - Total elements found: {all_result.total_elements}")
    print(f"  - Max depth reached: {max_depth}")
    print(f"  - Interactive beyond depth 5: {beyond_5}")
    print(f"\n  Expected: ~477 elements, max depth 10, ~46 interactive beyond depth 5")
    
    if all_result.total_elements > 400 and max_depth >= 10:
        print(f"\n  [SUCCESS] VERIFICATION PASSED - We're now capturing deep elements!")
    else:
        print(f"\n  [WARNING] Element count or depth seems low")
else:
    print("[ERROR] Failed to list elements")

print("\n" + "="*80 + "\n")
