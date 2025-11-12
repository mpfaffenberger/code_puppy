"""Debug script to dump all Calculator elements with their values."""

from pywinauto import Application
import json

try:
    # Connect to active window
    app = Application(backend="uia").connect(active_only=True)
    window = app.top_window()

    print(f"Window: {window.window_text()}")
    print(f"Class: {window.class_name()}")
    print("\n" + "=" * 80)
    print("ALL ELEMENTS WITH THEIR PROPERTIES:")
    print("=" * 80 + "\n")

    elements = []

    def traverse(element, depth=0):
        if depth > 10:  # Deeper traversal
            return

        try:
            info = element.element_info

            # Try multiple ways to get value
            value = None
            texts = None
            legacy_value = None

            try:
                if hasattr(element, "legacy_properties"):
                    props = element.legacy_properties()
                    legacy_value = props.get("Value")
            except Exception:
                pass

            try:
                if hasattr(element, "texts"):
                    texts = element.texts()
            except Exception:
                pass

            try:
                if hasattr(element, "window_text"):
                    value = element.window_text()
            except Exception:
                pass

            elem_data = {
                "depth": depth,
                "control_type": info.control_type,
                "name": info.name,
                "class_name": info.class_name,
                "automation_id": info.automation_id,
                "legacy_value": legacy_value,
                "texts": texts,
                "window_text": value,
            }

            elements.append(elem_data)

            # Print if it has any interesting data
            if legacy_value or texts or (info.name and info.name.strip()):
                indent = "  " * depth
                print(f"{indent}[{info.control_type}] {info.name or '(no name)'}")
                print(f"{indent}  AutoID: {info.automation_id or '(none)'}")
                print(f"{indent}  Legacy Value: {legacy_value}")
                print(f"{indent}  Texts: {texts}")
                print(f"{indent}  Window Text: {value}")
                print()

            # Traverse children
            for child in element.children():
                traverse(child, depth + 1)

        except Exception:
            pass

    traverse(window.wrapper_object())

    print("\n" + "=" * 80)
    print(f"TOTAL ELEMENTS FOUND: {len(elements)}")
    print("=" * 80)

    # Save to JSON for detailed inspection
    with open("calculator_elements_debug.json", "w") as f:
        json.dump(elements, f, indent=2)
    print("\nFull element data saved to: calculator_elements_debug.json")

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
