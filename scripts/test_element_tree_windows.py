#!/usr/bin/env python
"""Windows Element Tree Testing Script

Tests Windows UI Automation accessibility element tree.
Based on WINDOWS_ELEMENT_TREE_TESTING_GUIDE.md

Usage:
    # Make sure Calculator/Notepad/Explorer is open and focused
    python scripts/test_element_tree_windows.py
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from code_puppy.tools.gui_cub.windows_automation import (
    list_elements_in_window,
    find_element,
)


def test_list_buttons():
    """Test listing button elements."""
    print("\n" + "=" * 80)
    print("TEST 1: List All Buttons")
    print("=" * 80)

    result = list_elements_in_window()

    print(f"\nSuccess: {result.get('success', False)}")
    print(f"Total elements: {result.get('total_elements', 0)}")

    elements = result.get('elements', [])
    buttons = [e for e in elements if e.get('control_type') == 'Button']
    
    print(f"Total buttons: {len(buttons)}")

    if buttons:
        print("\nButton details:")
        for i, btn in enumerate(buttons[:20]):  # Show first 20
            name = btn.get('name', '')
            auto_id = btn.get('automation_id', '')
            class_name = btn.get('class_name', '')
            print(f"  [{i}] type='Button', name='{name}'")
            if auto_id:
                print(f"      automation_id: '{auto_id}'")
            if class_name:
                print(f"      class_name: '{class_name}'")

            # Check if button has a name
            has_label = bool(name and name.strip())
            status = "✅" if has_label else "❌"
            print(f"      {status} Has name: {has_label}")

    return result


def test_find_element(search_name: str, control_type: str = None):
    """Test finding a specific element."""
    print("\n" + "=" * 80)
    print(f"TEST 2: Find Element '{search_name}' (type={control_type})")
    print("=" * 80)

    result = find_element(
        name=search_name,
        control_type=control_type,
        fuzzy=True,
    )

    print(f"\nSuccess: {result.get('success', False)}")
    print(f"Found: {result.get('found', False)}")

    if result.get('found'):
        print("\nMatch details:")
        print(f"  Name: {result.get('name')}")
        print(f"  ControlType: {result.get('control_type')}")
        print(f"  AutomationId: {result.get('automation_id')}")
        print(f"  ClassName: {result.get('class_name')}")
        print(f"  X: {result.get('x')}")
        print(f"  Y: {result.get('y')}")
    else:
        print("\nNot found!")
        if result.get('error'):
            print(f"  Error: {result.get('error')}")

    return result


def test_calculator():
    """Test Calculator app element tree."""
    print("\n" + "#" * 80)
    print("#  CALCULATOR APP TESTS")
    print("#  Make sure Calculator is open and focused!")
    print("#" * 80)

    # Test 1: List all buttons
    list_result = test_list_buttons()
    
    # Test 2: Find Plus button
    test_find_element("Plus", control_type="Button")
    
    # Test 3: Find Equals button
    test_find_element("Equals", control_type="Button")
    
    # Test 4: Find Zero button
    test_find_element("Zero", control_type="Button")

    return list_result


def test_notepad():
    """Test Notepad app element tree."""
    print("\n" + "#" * 80)
    print("#  NOTEPAD APP TESTS")
    print("#  Make sure Notepad is open and focused!")
    print("#" * 80)

    # Test 1: List all elements
    result = list_elements_in_window()
    
    print(f"\nSuccess: {result.get('success', False)}")
    print(f"Total elements: {result.get('total_elements', 0)}")

    elements = result.get('elements', [])
    
    # Find menu items
    menu_items = [e for e in elements if e.get('control_type') == 'MenuItem']
    print(f"\nMenu items found: {len(menu_items)}")
    for item in menu_items[:10]:
        print(f"  - {item.get('name')}")
    
    # Find text editor
    edit_controls = [e for e in elements if e.get('control_type') == 'Edit']
    print(f"\nEdit controls found: {len(edit_controls)}")
    for edit in edit_controls:
        print(f"  - {edit.get('name')} (automation_id: {edit.get('automation_id')})")
    
    # Test finding File menu
    test_find_element("File", control_type="MenuItem")

    return result


def test_file_explorer():
    """Test File Explorer app element tree."""
    print("\n" + "#" * 80)
    print("#  FILE EXPLORER APP TESTS")
    print("#  Make sure File Explorer is open and focused!")
    print("#" * 80)

    # Test 1: List all elements
    result = list_elements_in_window()
    
    print(f"\nSuccess: {result.get('success', False)}")
    print(f"Total elements: {result.get('total_elements', 0)}")

    elements = result.get('elements', [])
    buttons = [e for e in elements if e.get('control_type') == 'Button']
    
    print(f"\nButtons found: {len(buttons)}")
    for btn in buttons[:15]:
        name = btn.get('name', '')
        auto_id = btn.get('automation_id', '')
        print(f"  - {name} (automation_id: {auto_id})")
    
    # Test finding Back button
    test_find_element("Back", control_type="Button")
    
    # Test finding Forward button
    test_find_element("Forward", control_type="Button")
    
    # Test finding Search
    test_find_element("Search", control_type="Edit")

    return result


def test_automation_id():
    """Test AutomationId-based finding."""
    print("\n" + "#" * 80)
    print("#  AUTOMATION ID TESTS")
    print("#  Make sure Calculator is open and focused!")
    print("#" * 80)

    # First, list all elements to see automation IDs
    result = list_elements_in_window()
    elements = result.get('elements', [])
    
    print("\nElements with AutomationId:")
    with_auto_id = [e for e in elements if e.get('automation_id')]
    print(f"Total: {len(with_auto_id)}")
    
    for elem in with_auto_id[:20]:
        print(f"  - {elem.get('name')} (automation_id: {elem.get('automation_id')})")


def main():
    """Run all tests."""
    import time
    
    print("\n" + "#" * 80)
    print("#  WINDOWS ELEMENT TREE TEST SUITE")
    print("#" * 80)
    print("\nThis script will run tests for:")
    print("  1. Calculator")
    print("  2. Notepad")
    print("  3. File Explorer")
    print("  4. AutomationId testing")
    print("\nYou will be prompted to open each app.")
    print("=" * 80)

    try:
        # Test Calculator
        input("\n[Press ENTER when Calculator is open and focused]")
        test_calculator()
        
        # Test Notepad
        input("\n[Press ENTER when Notepad is open and focused]")
        test_notepad()
        
        # Test File Explorer
        input("\n[Press ENTER when File Explorer is open and focused]")
        test_file_explorer()
        
        # Test AutomationId
        input("\n[Press ENTER when Calculator is open and focused for AutomationId test]")
        test_automation_id()

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
