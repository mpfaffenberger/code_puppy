#!/usr/bin/env uv run python
"""Quick test script for accessibility element tree.

Tests element finding and compaction WITHOUT running the full agent.
Much faster iteration for debugging!

Usage:
    # Make sure Finder is frontmost app
    python scripts/test_element_tree.py
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from code_puppy.tools.gui_cub.accessibility.element_list import (
    list_accessible_elements,
    _compact_element_list_result,
)
from code_puppy.tools.gui_cub.accessibility.element_finder import (
    find_accessible_element,
)


def test_list_buttons():
    """Test listing button elements."""
    print("\n" + "=" * 80)
    print("TEST 1: List All Buttons")
    print("=" * 80)

    result = list_accessible_elements(role="AXButton", in_frontmost_app=True)

    print(f"\nSuccess: {result.success}")
    print(f"Total buttons: {result.total_elements}")

    if result.by_role and "AXButton" in result.by_role:
        buttons = result.by_role["AXButton"]
        print("\nButton details:")
        for i, btn in enumerate(buttons):
            title = btn.get("title")
            desc = btn.get("description")
            print(f"  [{i}] title='{title}', description='{desc}'")

            # Check if we have EITHER title or description
            has_label = (title and title != "None") or (desc and desc != "None")
            status = "✅" if has_label else "❌"
            print(f"      {status} Has usable label: {has_label}")

    return result


def test_compaction():
    """Test element list compaction."""
    print("\n" + "=" * 80)
    print("TEST 2: Element Compaction")
    print("=" * 80)

    # Get full list
    full_result = list_accessible_elements(in_frontmost_app=True)

    print("\nFull result:")
    print(f"  Total elements: {full_result.total_elements}")
    print(f"  Success: {full_result.success}")

    # Compact it
    compact_result = _compact_element_list_result(full_result, max_elements=20)

    print("\nCompact result:")
    print(
        f"  Elements returned: {len(compact_result.elements) if compact_result.elements else 0}"
    )
    print(f"  Filtered count: {compact_result.filtered_count}")

    if compact_result.elements:
        print("\nCompacted elements:")
        for i, elem in enumerate(compact_result.elements[:10]):
            role = elem.get("role")
            title = elem.get("title")
            desc = elem.get("description")
            relevance = elem.get("relevance")
            print(f"  [{i}] {role}: '{title}' (relevance={relevance})")
            if desc and desc != title:
                print(f"      description: '{desc}'")

    return compact_result


def test_find_element(search_text: str, role: str | None = None):
    """Test finding a specific element."""
    print("\n" + "=" * 80)
    print(f"TEST 3: Find Element '{search_text}' (role={role})")
    print("=" * 80)

    result = find_accessible_element(
        title=search_text,
        role=role,
        in_frontmost_app=True,
        fuzzy=True,  # Make sure fuzzy is enabled
        # Using default threshold (0.25) to allow description matches
    )

    print(f"\nSuccess: {result.success}")
    print(f"Found: {result.found}")

    if result.found and result.best_match:
        print("\nMatch details:")
        print(f"  Role: {result.best_match.role}")
        print(f"  Title: {result.best_match.title}")
        print(f"  Description: {result.best_match.description}")
        print(f"  X: {result.best_match.x}")
        print(f"  Y: {result.best_match.y}")
    else:
        print("\nNot found!")
        if result.error:
            print(f"  Error: {result.error}")

    return result


def test_description_fallback():
    """Test that description fallback works for buttons without titles."""
    print("\n" + "=" * 80)
    print("TEST 4: Description Fallback")
    print("=" * 80)

    # Try to find "back" button (has description but no title)
    print("\nSearching for 'back' button (should use description fallback)...")
    result = find_accessible_element(
        title="back",
        role="AXButton",  # Specify role to speed up search
        in_frontmost_app=True,
        fuzzy=True,
        # Using default threshold (0.25) - allows description matches!
    )

    if result.found and result.best_match:
        print("✅ SUCCESS! Found button using description fallback")
        print(f"   Role: {result.best_match.role}")
        print(f"   Title: '{result.best_match.title}'")
        print(f"   Description: '{result.best_match.description}'")
        print(f"   Coords: ({result.best_match.x}, {result.best_match.y})")
    else:
        print("❌ FAILED! Could not find 'back' button")
        print("   This means description fallback is NOT working!")

    # Try "forward" button too
    print("\nSearching for 'forward' button...")
    result2 = find_accessible_element(
        title="forward",
        role="AXButton",
        in_frontmost_app=True,
        fuzzy=True,
    )

    if result2.found:
        print("✅ SUCCESS! Found button using description fallback")
    else:
        print("❌ FAILED! Could not find 'forward' button")

    # Try "Share" button
    print("\nSearching for 'Share' button...")
    result3 = find_accessible_element(
        title="Share",
        role="AXButton",
        in_frontmost_app=True,
        fuzzy=True,
    )

    if result3.found:
        print("✅ SUCCESS! Found button using description fallback")
    else:
        print("❌ FAILED! Could not find 'Share' button")

    return result


def main():
    """Run all tests."""
    print("\n" + "#" * 80)
    print("#  ELEMENT TREE TEST SUITE")
    print("#  Make sure Finder is the frontmost app!")
    print("#" * 80)

    try:
        # Test 1: List buttons
        test_list_buttons()

        # Test 2: Compaction
        test_compaction()

        # Test 3: Find specific element
        test_find_element("Desktop", role=None)

        # Test 4: Description fallback (THE KEY TEST!)
        test_description_fallback()

        print("\n" + "=" * 80)
        print("ALL TESTS COMPLETE")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
