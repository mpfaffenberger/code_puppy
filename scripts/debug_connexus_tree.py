#!/usr/bin/env python
"""Deep Windows UI Automation Element Tree Debugger for Connexus

This script walks the ENTIRE UI Automation element tree and exports comprehensive
data about every element including AutomationId, Name, ClassName, ControlType,
BoundingRectangle, and hierarchical structure.

Purpose:
    Debug why gui-cub agent can't find elements with AutomationIds in Connexus.exe
    Provide detailed tree structure for analysis

Usage:
    1. Make sure Connexus.exe is running and logged in
    2. Bring Connexus window to foreground
    3. Run: python scripts/debug_connexus_tree.py
    4. Results saved to: connexus_tree_<timestamp>.json

Output includes:
    - Full hierarchical tree structure
    - All UI Automation properties
    - Parent-child relationships
    - Visual tree in console
    - JSON export for offline analysis

Author: Doc the Puppy 🐶
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import comtypes.client
    from comtypes.gen.UIAutomationClient import (
        IUIAutomation,
        IUIAutomationElement,
        TreeScope_Children,
        TreeScope_Descendants,
    )
except ImportError:
    print("❌ Missing comtypes! Install with: pip install comtypes")
    sys.exit(1)


# Control type mapping for readability
CONTROL_TYPE_MAP = {
    50000: "Button",
    50001: "Calendar",
    50002: "CheckBox",
    50003: "ComboBox",
    50004: "Edit",
    50005: "Hyperlink",
    50006: "Image",
    50007: "ListItem",
    50008: "List",
    50009: "Menu",
    50010: "MenuBar",
    50011: "MenuItem",
    50012: "ProgressBar",
    50013: "RadioButton",
    50014: "ScrollBar",
    50015: "Slider",
    50016: "Spinner",
    50017: "StatusBar",
    50018: "Tab",
    50019: "TabItem",
    50020: "Text",
    50021: "ToolBar",
    50022: "ToolTip",
    50023: "Tree",
    50024: "TreeItem",
    50025: "Custom",
    50026: "Group",
    50027: "Thumb",
    50028: "DataGrid",
    50029: "DataItem",
    50030: "Document",
    50031: "SplitButton",
    50032: "Window",
    50033: "Pane",
    50034: "Header",
    50035: "HeaderItem",
    50036: "Table",
    50037: "TitleBar",
    50038: "Separator",
}


class ConnexusTreeWalker:
    """Walks Windows UI Automation tree and collects element data."""

    def __init__(self):
        self.automation = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=IUIAutomation
        )
        self.stats = {
            "total_elements": 0,
            "with_automation_id": 0,
            "with_name": 0,
            "with_class_name": 0,
            "by_control_type": {},
            "max_depth": 0,
        }
        self.elements_data = []

    def get_element_properties(self, element: IUIAutomationElement) -> dict[str, Any]:
        """Extract all useful properties from a UI Automation element."""
        props = {}

        try:
            # Core identification
            props["name"] = element.CurrentName or ""
            props["automation_id"] = element.CurrentAutomationId or ""
            props["class_name"] = element.CurrentClassName or ""
            props["control_type_id"] = element.CurrentControlType
            props["control_type"] = CONTROL_TYPE_MAP.get(
                element.CurrentControlType, f"Unknown({element.CurrentControlType})"
            )

            # Additional metadata
            props["localized_control_type"] = element.CurrentLocalizedControlType or ""
            props["framework_id"] = element.CurrentFrameworkId or ""
            props["help_text"] = element.CurrentHelpText or ""
            props["accelerator_key"] = element.CurrentAcceleratorKey or ""
            props["access_key"] = element.CurrentAccessKey or ""
            props["item_type"] = element.CurrentItemType or ""
            props["item_status"] = element.CurrentItemStatus or ""

            # State
            props["is_enabled"] = bool(element.CurrentIsEnabled)
            props["is_keyboard_focusable"] = bool(element.CurrentIsKeyboardFocusable)
            props["is_offscreen"] = bool(element.CurrentIsOffscreen)
            props["has_keyboard_focus"] = bool(element.CurrentHasKeyboardFocus)
            props["is_password"] = bool(element.CurrentIsPassword)

            # Bounding rectangle
            try:
                rect = element.CurrentBoundingRectangle
                props["bounding_rect"] = {
                    "left": int(rect.left),
                    "top": int(rect.top),
                    "right": int(rect.right),
                    "bottom": int(rect.bottom),
                    "width": int(rect.right - rect.left),
                    "height": int(rect.bottom - rect.top),
                }
            except Exception:
                props["bounding_rect"] = None

            # Process info
            try:
                props["process_id"] = element.CurrentProcessId
            except Exception:
                props["process_id"] = None

            # Runtime ID (for uniqueness)
            try:
                runtime_id = element.GetRuntimeId()
                props["runtime_id"] = "_".join(str(x) for x in runtime_id) if runtime_id else None
            except Exception:
                props["runtime_id"] = None

        except Exception as e:
            props["error"] = str(e)

        return props

    def walk_tree(
        self, element: IUIAutomationElement, depth: int = 0, parent_path: str = "root"
    ) -> dict[str, Any]:
        """Recursively walk element tree and build hierarchy."""
        # Update stats
        self.stats["total_elements"] += 1
        self.stats["max_depth"] = max(self.stats["max_depth"], depth)

        # Get element properties
        props = self.get_element_properties(element)

        # Build path for this element
        control_type = props.get("control_type", "Unknown")
        name = props.get("name", "")
        auto_id = props.get("automation_id", "")
        
        path_segment = f"{control_type}"
        if auto_id:
            path_segment += f"[{auto_id}]"
        elif name:
            path_segment += f"({name[:20]})"
        
        element_path = f"{parent_path}/{path_segment}"

        # Update statistics
        if auto_id:
            self.stats["with_automation_id"] += 1
        if props.get("name"):
            self.stats["with_name"] += 1
        if props.get("class_name"):
            self.stats["with_class_name"] += 1

        control_type_key = props.get("control_type", "Unknown")
        self.stats["by_control_type"][control_type_key] = (
            self.stats["by_control_type"].get(control_type_key, 0) + 1
        )

        # Build node data
        node = {
            "depth": depth,
            "path": element_path,
            "properties": props,
            "children": [],
        }

        # Save to flat list for easier searching
        self.elements_data.append(node)

        # Get children
        try:
            condition = self.automation.CreateTrueCondition()
            children = element.FindAll(TreeScope_Children, condition)

            if children:
                for i in range(children.Length):
                    try:
                        child = children.GetElement(i)
                        child_node = self.walk_tree(child, depth + 1, element_path)
                        node["children"].append(child_node)
                    except Exception as e:
                        print(f"⚠️  Error processing child {i}: {e}")
                        continue
        except Exception as e:
            print(f"⚠️  Error getting children at depth {depth}: {e}")

        return node

    def print_tree_node(self, node: dict, show_all_props: bool = False):
        """Pretty print a tree node with indentation."""
        depth = node["depth"]
        props = node["properties"]
        indent = "  " * depth

        # Visual indicators
        has_auto_id = bool(props.get("automation_id"))
        has_name = bool(props.get("name"))
        is_enabled = props.get("is_enabled", False)

        # Quality emoji
        if has_auto_id:
            quality = "🎯"  # Has AutomationId - best!
        elif has_name:
            quality = "✅"  # Has name - good
        elif props.get("control_type") in ["Button", "Edit", "ComboBox"]:
            quality = "⚠️"  # Interactive but no good identifier
        else:
            quality = "  "  # Static/container element

        # Control type and identifiers
        control_type = props.get("control_type", "Unknown")
        name = props.get("name", "")
        auto_id = props.get("automation_id", "")
        class_name = props.get("class_name", "")

        # Print main line
        print(f"{indent}{quality} [{control_type}]")

        # Print key properties
        if name:
            print(f"{indent}   📝 Name: '{name}'")
        if auto_id:
            print(f"{indent}   🎯 AutomationId: '{auto_id}'")
        if class_name:
            print(f"{indent}   🏷️  ClassName: '{class_name}'")

        # Print bounds if available
        bounds = props.get("bounding_rect")
        if bounds and not props.get("is_offscreen"):
            print(
                f"{indent}   📐 Bounds: ({bounds['left']},{bounds['top']}) "
                f"{bounds['width']}x{bounds['height']}"
            )

        # Print state flags
        if not is_enabled:
            print(f"{indent}   ⛔ Disabled")
        if props.get("is_offscreen"):
            print(f"{indent}   👻 Offscreen")
        if props.get("is_password"):
            print(f"{indent}   🔒 Password field")

        # Show all properties if requested
        if show_all_props:
            for key, value in props.items():
                if key not in [
                    "name",
                    "automation_id",
                    "class_name",
                    "control_type",
                    "bounding_rect",
                    "is_enabled",
                    "is_offscreen",
                    "is_password",
                ] and value:
                    print(f"{indent}   • {key}: {value}")

        print()  # Blank line for readability

        # Recursively print children
        for child in node["children"]:
            self.print_tree_node(child, show_all_props)

    def export_json(self, tree: dict, filename: str):
        """Export tree to JSON file."""
        output = {
            "timestamp": datetime.now().isoformat(),
            "statistics": self.stats,
            "tree": tree,
            "flat_elements": self.elements_data,
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Exported to: {filename}")
        print(f"   Total elements: {self.stats['total_elements']}")
        print(f"   Max depth: {self.stats['max_depth']}")
        print(f"   File size: {Path(filename).stat().st_size / 1024:.1f} KB")

    def print_statistics(self):
        """Print collection statistics."""
        print("\n" + "=" * 80)
        print("📊 ELEMENT TREE STATISTICS")
        print("=" * 80 + "\n")

        print(f"Total elements: {self.stats['total_elements']}")
        print(f"Max depth: {self.stats['max_depth']}")
        print(f"\nElements WITH AutomationId: {self.stats['with_automation_id']} "
              f"({self.stats['with_automation_id'] / max(self.stats['total_elements'], 1) * 100:.1f}%)")
        print(f"Elements WITH Name: {self.stats['with_name']} "
              f"({self.stats['with_name'] / max(self.stats['total_elements'], 1) * 100:.1f}%)")
        print(f"Elements WITH ClassName: {self.stats['with_class_name']} "
              f"({self.stats['with_class_name'] / max(self.stats['total_elements'], 1) * 100:.1f}%)")

        print("\n📋 By Control Type:")
        sorted_types = sorted(
            self.stats["by_control_type"].items(), key=lambda x: x[1], reverse=True
        )
        for control_type, count in sorted_types[:15]:
            percentage = count / max(self.stats['total_elements'], 1) * 100
            print(f"   {control_type:25} {count:4} ({percentage:5.1f}%)")

        if len(sorted_types) > 15:
            print(f"   ... and {len(sorted_types) - 15} more types")

        print("\n" + "=" * 80 + "\n")

    def find_elements_with_automation_id(self) -> list[dict]:
        """Get all elements that have an AutomationId."""
        return [
            elem
            for elem in self.elements_data
            if elem["properties"].get("automation_id")
        ]

    def search_elements(
        self,
        name_contains: str = None,
        auto_id_contains: str = None,
        control_type: str = None,
    ) -> list[dict]:
        """Search elements by criteria."""
        results = self.elements_data

        if name_contains:
            results = [
                e
                for e in results
                if name_contains.lower()
                in e["properties"].get("name", "").lower()
            ]

        if auto_id_contains:
            results = [
                e
                for e in results
                if auto_id_contains.lower()
                in e["properties"].get("automation_id", "").lower()
            ]

        if control_type:
            results = [
                e
                for e in results
                if e["properties"].get("control_type", "").lower()
                == control_type.lower()
            ]

        return results


def main():
    """Main debug script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Connexus UI Automation Element Tree Debugger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Automatic mode (no prompts, immediate execution)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON filename (default: connexus_tree_TIMESTAMP.json)",
    )
    parser.add_argument(
        "--no-console",
        action="store_true",
        help="Suppress console tree output (JSON only)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum tree depth to traverse (default: unlimited)",
    )
    parser.add_argument(
        "--search",
        action="store_true",
        help="Enable interactive search at the end (ignored in --auto mode)",
    )

    args = parser.parse_args()

    print("\n" + "#" * 80)
    print("#  Connexus UI Automation Element Tree Debugger")
    print("#  Doc the Puppy 🐶 - Debugging element tree issues")
    print("#" * 80 + "\n")

    if not args.auto:
        print("This script will:")
        print("  1. Walk the ENTIRE UI Automation element tree")
        print("  2. Show hierarchy with visual indicators")
        print("  3. Export detailed JSON for analysis")
        print("  4. Highlight elements with AutomationId")
        print("\n⚠️  IMPORTANT: Make sure Connexus.exe is running and in foreground!\n")
        input("Press ENTER when ready...")
    else:
        print("🤖 AUTOMATIC MODE - Running immediately...")
        print("⚠️  Assuming Connexus.exe is in foreground!\n")

    try:
        print("\n🔍 Initializing UI Automation...")
        walker = ConnexusTreeWalker()

        print("📡 Getting foreground window...")
        root = walker.automation.GetForegroundWindow()

        if not root:
            print("❌ Could not get foreground window!")
            print("   Make sure Connexus.exe is the active window.")
            return 1

        # Get window info
        window_name = root.CurrentName or "(no name)"
        print(f"✅ Found window: {window_name}\n")

        print("🚶 Walking element tree (this may take a minute)...")
        tree = walker.walk_tree(root)

        # Print statistics
        walker.print_statistics()

        # Show elements with AutomationId
        auto_id_elements = walker.find_elements_with_automation_id()
        print(f"\n🎯 Elements WITH AutomationId ({len(auto_id_elements)}):")
        print("=" * 80 + "\n")
        for elem in auto_id_elements[:20]:
            props = elem["properties"]
            print(f"  {props['control_type']:15} AutomationId: '{props['automation_id']}'")
            if props.get("name"):
                print(f"  {' ' * 15} Name: '{props['name']}'")
            print(f"  {' ' * 15} Path: {elem['path']}")
            print()

        if len(auto_id_elements) > 20:
            print(f"  ... and {len(auto_id_elements) - 20} more\n")

        # Export to JSON
        if args.output:
            json_filename = args.output
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_filename = f"connexus_tree_{timestamp}.json"
        walker.export_json(tree, json_filename)

        # Show sample of tree (unless suppressed)
        if not args.no_console:
            print("\n" + "=" * 80)
            print("📋 VISUAL TREE (showing all elements with depth)")
            print("=" * 80 + "\n")
            print("Legend:")
            print("  🎯 = Has AutomationId (BEST for finding!)")
            print("  ✅ = Has Name property")
            print("  ⚠️  = Interactive but no good identifier")
            print("\n" + "-" * 80 + "\n")

            walker.print_tree_node(tree, show_all_props=False)

        print("\n" + "=" * 80)
        print("✅ COMPLETE!")
        print("=" * 80 + "\n")

        print("📁 Detailed JSON export saved to:", json_filename)
        print("\n💡 Next steps:")
        print("   1. Review elements with 🎯 (AutomationId) - these are findable!")
        print("   2. Check the JSON file for complete property details")
        print("   3. Search for specific elements in the JSON using 'automation_id' field")
        print(f"   4. Total found: {walker.stats['with_automation_id']} elements with AutomationId\n")

        # Offer search (only if requested and not in auto mode)
        if args.search and not args.auto:
            print("\n" + "=" * 80)
            print("🔍 SEARCH (optional)")
            print("=" * 80 + "\n")
            search_choice = input("Want to search for specific elements? (y/n): ").strip().lower()
        else:
            search_choice = "n"

        if search_choice == "y" and not args.auto:
            while True:
                print("\nSearch by:")
                print("  1. Name contains")
                print("  2. AutomationId contains")
                print("  3. Control type")
                print("  4. Done searching")

                choice = input("\nChoice: ").strip()

                if choice == "1":
                    term = input("Name contains: ").strip()
                    results = walker.search_elements(name_contains=term)
                    print(f"\nFound {len(results)} matches:")
                    for elem in results[:10]:
                        props = elem["properties"]
                        print(f"  {props['control_type']:15} '{props.get('name', '')}'")
                        if props.get("automation_id"):
                            print(f"  {' ' * 15} AutomationId: '{props['automation_id']}'")

                elif choice == "2":
                    term = input("AutomationId contains: ").strip()
                    results = walker.search_elements(auto_id_contains=term)
                    print(f"\nFound {len(results)} matches:")
                    for elem in results[:10]:
                        props = elem["properties"]
                        print(f"  {props['control_type']:15} AutomationId: '{props['automation_id']}'")
                        if props.get("name"):
                            print(f"  {' ' * 15} Name: '{props.get('name', '')}'")

                elif choice == "3":
                    term = input("Control type: ").strip()
                    results = walker.search_elements(control_type=term)
                    print(f"\nFound {len(results)} matches:")
                    for elem in results[:10]:
                        props = elem["properties"]
                        print(f"  Name: '{props.get('name', '(none)'):30}' AutomationId: '{props.get('automation_id', '(none)')}'")

                elif choice == "4":
                    break

        return 0

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
