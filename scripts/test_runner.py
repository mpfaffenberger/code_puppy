#!/usr/bin/env python
"""Automated test runner for Windows Element Tree tests.

Opens each application and runs the tests automatically.
"""

import sys
import subprocess
import time
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from code_puppy.tools.gui_cub.windows_automation import (
    list_elements_in_window,
    find_element,
)


def open_application(app_command: str, app_name: str, wait_time: float = 2.0):
    """Open an application and wait for it to start."""
    print(f"\n📱 Opening {app_name}...")
    try:
        subprocess.Popen(app_command, shell=True)
        time.sleep(wait_time)
        print(f"✅ {app_name} should be open now")
        return True
    except Exception as e:
        print(f"❌ Failed to open {app_name}: {e}")
        return False


def test_list_buttons():
    """Test listing button elements."""
    print("\n" + "=" * 80)
    print("TEST 1: List All Buttons")
    print("=" * 80)

    result = list_elements_in_window()

    print(f"\nSuccess: {result.get('success', False)}")
    print(f"Total elements: {result.get('total_elements', 0)}")

    elements = result.get("elements", [])
    buttons = [e for e in elements if e.get("control_type") == "Button"]

    print(f"Total buttons: {len(buttons)}")

    if buttons:
        print("\nButton details (first 20):")
        for i, btn in enumerate(buttons[:20]):
            name = btn.get("name", "")
            auto_id = btn.get("automation_id", "")
            class_name = btn.get("class_name", "")
            print(f"  [{i}] type='Button', name='{name}'")
            if auto_id:
                print(f"      automation_id: '{auto_id}'")
            if class_name:
                print(f"      class_name: '{class_name}'")

            # Check if button has a name
            has_label = bool(name and name.strip())
            status = "✅" if has_label else "❌"
            print(f"      {status} Has name: {has_label}")
    else:
        print("\n❌ No buttons found!")

    return result


def test_find_element(search_name: str, control_type: str = None):
    """Test finding a specific element."""
    print("\n" + "=" * 80)
    print(f"TEST: Find Element '{search_name}' (type={control_type})")
    print("=" * 80)

    result = find_element(
        name=search_name,
        control_type=control_type,
        fuzzy=True,
    )

    print(f"\nSuccess: {result.get('success', False)}")
    print(f"Found: {result.get('found', False)}")

    if result.get("found"):
        print("\n✅ Match details:")
        print(f"  Name: {result.get('name')}")
        print(f"  ControlType: {result.get('control_type')}")
        print(f"  AutomationId: {result.get('automation_id')}")
        print(f"  ClassName: {result.get('class_name')}")
        print(f"  X: {result.get('x')}")
        print(f"  Y: {result.get('y')}")
    else:
        print("\n❌ Not found!")
        if result.get("error"):
            print(f"  Error: {result.get('error')}")

    return result


def test_calculator():
    """Test Calculator app element tree."""
    print("\n" + "#" * 80)
    print("#  CALCULATOR APP TESTS")
    print("#" * 80)

    if not open_application("calc.exe", "Calculator", wait_time=3.0):
        return None

    # Give Calculator time to fully load
    time.sleep(2)

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
    print("#" * 80)

    if not open_application("notepad.exe", "Notepad", wait_time=2.0):
        return None

    time.sleep(2)

    # Test 1: List all elements
    result = list_elements_in_window()

    print(f"\nSuccess: {result.get('success', False)}")
    print(f"Total elements: {result.get('total_elements', 0)}")

    elements = result.get("elements", [])

    # Find menu items
    menu_items = [e for e in elements if e.get("control_type") == "MenuItem"]
    print(f"\nMenu items found: {len(menu_items)}")
    if menu_items:
        for item in menu_items[:10]:
            print(f"  ✅ {item.get('name')}")
    else:
        print("  ❌ No menu items found")

    # Find text editor
    edit_controls = [e for e in elements if e.get("control_type") == "Edit"]
    print(f"\nEdit controls found: {len(edit_controls)}")
    if edit_controls:
        for edit in edit_controls:
            auto_id = edit.get("automation_id", "N/A")
            print(f"  ✅ {edit.get('name')} (automation_id: {auto_id})")
    else:
        print("  ❌ No edit controls found")

    # Test finding File menu
    test_find_element("File", control_type="MenuItem")

    return result


def test_file_explorer():
    """Test File Explorer app element tree."""
    print("\n" + "#" * 80)
    print("#  FILE EXPLORER APP TESTS")
    print("#" * 80)

    if not open_application("explorer.exe", "File Explorer", wait_time=2.0):
        return None

    time.sleep(2)

    # Test 1: List all elements
    result = list_elements_in_window()

    print(f"\nSuccess: {result.get('success', False)}")
    print(f"Total elements: {result.get('total_elements', 0)}")

    elements = result.get("elements", [])
    buttons = [e for e in elements if e.get("control_type") == "Button"]

    print(f"\nButtons found: {len(buttons)}")
    if buttons:
        print("\nFirst 15 buttons:")
        for btn in buttons[:15]:
            name = btn.get("name", "")
            auto_id = btn.get("automation_id", "")
            print(f"  ✅ {name} (automation_id: {auto_id})")
    else:
        print("  ❌ No buttons found")

    # Test finding Back button
    test_find_element("Back", control_type="Button")

    # Test finding Forward button (may not be available)
    test_find_element("Forward", control_type="Button")

    return result


def test_automation_id():
    """Test AutomationId-based finding."""
    print("\n" + "#" * 80)
    print("#  AUTOMATION ID TESTS")
    print("#  (Calculator should still be open)")
    print("#" * 80)

    # Make sure Calculator is in focus
    open_application("calc.exe", "Calculator", wait_time=2.0)
    time.sleep(1)

    # First, list all elements to see automation IDs
    result = list_elements_in_window()
    elements = result.get("elements", [])

    print("\nElements with AutomationId:")
    with_auto_id = [e for e in elements if e.get("automation_id")]
    print(f"Total: {len(with_auto_id)}")

    if with_auto_id:
        print("\nFirst 20 elements with AutomationId:")
        for elem in with_auto_id[:20]:
            name = elem.get("name", "N/A")
            auto_id = elem.get("automation_id")
            control_type = elem.get("control_type", "Unknown")
            print(f"  ✅ {name} ({control_type}) - automation_id: {auto_id}")
    else:
        print("  ❌ No elements with AutomationId found")


def generate_summary_report(results: dict):
    """Generate a summary report of test results."""
    print("\n" + "#" * 80)
    print("#  TEST SUMMARY REPORT")
    print("#" * 80)

    print("\n## Calculator Test")
    calc = results.get("calculator", {})
    if calc:
        total_elements = calc.get("total_elements", 0)
        elements = calc.get("elements", [])
        buttons = [e for e in elements if e.get("control_type") == "Button"]
        buttons_with_names = [b for b in buttons if b.get("name", "").strip()]

        print(f"- Total elements found: {total_elements}")
        print(f"- Total buttons found: {len(buttons)}")
        if buttons:
            pct = len(buttons_with_names) / len(buttons) * 100
            print(f"- Buttons with good names: {len(buttons_with_names)} ({pct:.0f}%)")
        else:
            print("- No buttons found")
    else:
        print("- ❌ Test failed or not run")

    print("\n## Notepad Test")
    notepad = results.get("notepad", {})
    if notepad:
        total_elements = notepad.get("total_elements", 0)
        elements = notepad.get("elements", [])
        buttons = [e for e in elements if e.get("control_type") == "Button"]
        menu_items = [e for e in elements if e.get("control_type") == "MenuItem"]

        print(f"- Total elements found: {total_elements}")
        print(f"- Total buttons found: {len(buttons)}")
        print(f"- Menu items found: {len(menu_items)}")
    else:
        print("- ❌ Test failed or not run")

    print("\n## File Explorer Test")
    explorer = results.get("explorer", {})
    if explorer:
        total_elements = explorer.get("total_elements", 0)
        elements = explorer.get("elements", [])
        buttons = [e for e in elements if e.get("control_type") == "Button"]

        print(f"- Total elements found: {total_elements}")
        print(f"- Total buttons found: {len(buttons)}")
    else:
        print("- ❌ Test failed or not run")

    print("\n" + "=" * 80)


def main():
    """Run all tests."""
    print("\n" + "#" * 80)
    print("#  WINDOWS ELEMENT TREE AUTOMATED TEST SUITE")
    print("#" * 80)
    print("\nThis script will:")
    print("  1. Open and test Calculator")
    print("  2. Open and test Notepad")
    print("  3. Open and test File Explorer")
    print("  4. Test AutomationId functionality")
    print("  5. Generate summary report")
    print("\n" + "=" * 80)

    results = {}

    try:
        # Test Calculator
        calc_result = test_calculator()
        results["calculator"] = calc_result

        # Test Notepad
        notepad_result = test_notepad()
        results["notepad"] = notepad_result

        # Test File Explorer
        explorer_result = test_file_explorer()
        results["explorer"] = explorer_result

        # Test AutomationId
        test_automation_id()

        # Generate summary
        generate_summary_report(results)

        print("\n" + "=" * 80)
        print("✅ ALL TESTS COMPLETE")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
