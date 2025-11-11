#!/usr/bin/env python
"""Quick Windows Element Tree Test - Run directly"""

import sys
from pathlib import Path

# Add code_puppy to path
sys.path.insert(0, str(Path(__file__).parent))

from code_puppy.tools.gui_cub.windows_automation import (
    list_elements_in_window,
    find_element,
)

print("=" * 80)
print("WINDOWS ELEMENT TREE TEST - Calculator")
print("=" * 80)

# Test 1: List all elements
print("\n[1] Listing all elements in Calculator...")
result = list_elements_in_window()

if result.get("success"):
    total = result.get("total_elements", 0)
    print(f"✅ Success! Total elements: {total}")

    elements = result.get("elements", [])

    # Group by control type
    by_type = {}
    for elem in elements:
        ctype = elem.get("control_type", "Unknown")
        if ctype not in by_type:
            by_type[ctype] = []
        by_type[ctype].append(elem)

    print("\n[2] Elements by type:")
    for ctype in sorted(by_type.keys()):
        print(f"  {ctype}: {len(by_type[ctype])}")

    # Show buttons
    if "Button" in by_type:
        buttons = by_type["Button"]
        print(f"\n[3] Buttons found: {len(buttons)}")

        buttons_with_names = 0
        buttons_without_names = 0

        for i, btn in enumerate(buttons):
            name = btn.get("name", "")
            auto_id = btn.get("automation_id", "")

            if name and name.strip():
                buttons_with_names += 1
                if i < 15:  # Show first 15
                    status = "✅"
                    print(f"  {status} [{i}] {name}")
                    if auto_id:
                        print(f"      automation_id: {auto_id}")
            else:
                buttons_without_names += 1
                if i < 15:
                    status = "❌"
                    print(f"  {status} [{i}] (no name) - automation_id: {auto_id}")

        print("\n  Summary:")
        print(f"    Buttons with names: {buttons_with_names}")
        print(f"    Buttons without names: {buttons_without_names}")
        print(
            f"    Percentage with names: {100 * buttons_with_names / len(buttons):.1f}%"
        )

    # Count elements with AutomationId
    with_auto_id = [e for e in elements if e.get("automation_id")]
    print(
        f"\n[4] Elements with AutomationId: {len(with_auto_id)}/{len(elements)} ({100 * len(with_auto_id) / len(elements):.1f}%)"
    )

    # Test finding specific buttons
    print("\n[5] Testing find_element() for specific buttons:")
    test_buttons = [
        "Plus",
        "Equals",
        "Zero",
        "One",
        "Two",
        "Three",
        "Multiply",
        "Divide",
    ]

    found_count = 0
    for btn_name in test_buttons:
        find_result = find_element(name=btn_name, control_type="Button", fuzzy=True)
        if find_result.get("found"):
            found_count += 1
            status = "✅"
            x = find_result.get("x", 0)
            y = find_result.get("y", 0)
            print(f"  {status} Found '{btn_name}' at ({x}, {y})")
        else:
            status = "❌"
            print(f"  {status} NOT found: '{btn_name}'")

    print(
        f"\n  Find success rate: {found_count}/{len(test_buttons)} ({100 * found_count / len(test_buttons):.1f}%)"
    )

else:
    print(f"❌ Failed: {result.get('error')}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
