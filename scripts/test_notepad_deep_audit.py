#!/usr/bin/env python
"""Deep audit of Notepad element detection"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from pywinauto import Application
except ImportError:
    print("ERROR: pywinauto not installed")
    sys.exit(1)

print("\n" + "=" * 80)
print("DEEP AUDIT: Notepad Element Tree")
print("=" * 80)

try:
    # Connect to active window (should be Notepad)
    app = Application(backend="uia").connect(active_only=True)
    window = app.top_window()

    print(f"\nConnected to window: {window.window_text()}")
    print("=" * 80)

    elements = []

    def traverse(element, depth=0, parent_name="ROOT"):
        if depth > 5:
            return

        try:
            info = element.element_info

            # Get coordinates
            try:
                rect = element.rectangle()
                x, y = rect.left, rect.top
                width, height = rect.width(), rect.height()
                center_x, center_y = rect.mid_point().x, rect.mid_point().y
            except Exception:
                x = y = width = height = center_x = center_y = None

            elem = {
                "depth": depth,
                "parent": parent_name,
                "control_type": info.control_type,
                "name": info.name,
                "automation_id": info.automation_id,
                "class_name": info.class_name,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "center_x": center_x,
                "center_y": center_y,
            }

            elements.append(elem)

            # Print immediately for visibility
            indent = "  " * depth
            print(f"{indent}[{len(elements) - 1}] {info.control_type}: '{info.name}'")
            if info.automation_id:
                print(f"{indent}    automation_id: '{info.automation_id}'")
            if info.class_name:
                print(f"{indent}    class_name: '{info.class_name}'")
            if center_x and center_y:
                print(f"{indent}    position: ({center_x}, {center_y})")
            if width and height:
                print(f"{indent}    size: {width}x{height}")

            # Traverse children
            for child in element.children():
                traverse(child, depth + 1, info.name or info.control_type)

        except Exception as e:
            print(f"{indent}ERROR at depth {depth}: {e}")

    print("\nElement Tree:")
    print("-" * 80)
    traverse(window.wrapper_object())

    print("\n" + "=" * 80)
    print(f"Total elements found: {len(elements)}")
    print("=" * 80)

    # Now find the Edit control specifically
    print("\n" + "=" * 80)
    print("LOOKING FOR EDIT CONTROLS (Text Editor)")
    print("=" * 80)

    edit_controls = [e for e in elements if e["control_type"] == "Edit"]
    print(f"\nFound {len(edit_controls)} Edit control(s):\n")

    for i, edit in enumerate(edit_controls):
        print(f"Edit Control #{i + 1}:")
        print(f"  Name: '{edit['name']}'")
        print(f"  AutomationId: '{edit['automation_id']}'")
        print(f"  ClassName: '{edit['class_name']}'")
        print(f"  Position: ({edit['center_x']}, {edit['center_y']})")
        print(f"  Size: {edit['width']}x{edit['height']}")
        print(f"  Parent: {edit['parent']}")
        print(f"  Depth: {edit['depth']}")
        print()

    # Check what the testing guide expects
    print("=" * 80)
    print("VERIFICATION: Does this match testing guide expectations?")
    print("=" * 80)
    print("\nExpected from testing guide:")
    print("  - Text editor should have automation_id (e.g., '15')")
    print("  - Should be control_type 'Edit'")
    print("  - Should be the main text editing area")
    print("\nActual findings:")
    if edit_controls:
        main_edit = edit_controls[0]
        print("  ✓ Found Edit control")
        print(f"  ✓ automation_id: '{main_edit['automation_id']}'")
        print("  ? Is this really the text editor? Let's verify...")

        # Check if it's likely the main editor by size
        if main_edit["width"] and main_edit["height"]:
            area = main_edit["width"] * main_edit["height"]
            print(f"  - Area: {area:,} pixels²")
            if area > 100000:
                print("  ✓ Large area suggests main editor")
            else:
                print("  ? Small area - might not be main editor")
    else:
        print("  ✗ No Edit controls found!")

    print("\n" + "=" * 80)
    print("VERIFICATION: Let's check ALL element types")
    print("=" * 80)

    by_type = {}
    for elem in elements:
        t = elem["control_type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(elem)

    print("\nElement count by type:")
    for elem_type, elems in sorted(
        by_type.items(), key=lambda x: len(x[1]), reverse=True
    ):
        print(f"  {elem_type}: {len(elems)}")
        # Show first few elements of each type
        for elem in elems[:3]:
            name = elem["name"] or "(no name)"
            auto_id = elem["automation_id"] or "(no id)"
            print(f"    - '{name}' (automation_id: '{auto_id}')")
        if len(elems) > 3:
            print(f"    ... and {len(elems) - 3} more")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 80)
print("END OF DEEP AUDIT")
print("=" * 80 + "\n")
