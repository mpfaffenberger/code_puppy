#!/usr/bin/env python
"""Quick Connexus Element Finder - Fast debugging script

This is a lightweight script for quickly finding and testing specific elements
in Connexus.exe. Use this when you know what you're looking for.

Usage:
    python scripts/debug_connexus_quick.py

Features:
    - Interactive search by name, AutomationId, or control type
    - Shows matching elements immediately
    - Tests if element is clickable/interactable
    - No tree walking - fast and simple

Author: Doc the Puppy 🐶
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import comtypes.client
    from comtypes.gen.UIAutomationClient import (
        IUIAutomation,
        IUIAutomationElement,
        TreeScope_Descendants,
    )
except ImportError:
    print("❌ Missing comtypes! Install with: pip install comtypes")
    sys.exit(1)


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


class QuickFinder:
    """Quick element finder."""

    def __init__(self):
        self.automation = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=IUIAutomation
        )

    def get_element_info(self, element: IUIAutomationElement) -> dict:
        """Get basic info about element."""
        try:
            info = {
                "name": element.CurrentName or "(no name)",
                "automation_id": element.CurrentAutomationId or "(no id)",
                "class_name": element.CurrentClassName or "(no class)",
                "control_type": CONTROL_TYPE_MAP.get(
                    element.CurrentControlType, "Unknown"
                ),
                "is_enabled": element.CurrentIsEnabled,
                "is_offscreen": element.CurrentIsOffscreen,
                "is_keyboard_focusable": element.CurrentIsKeyboardFocusable,
            }

            try:
                rect = element.CurrentBoundingRectangle
                info["bounds"] = f"({rect.left},{rect.top}) {rect.right - rect.left}x{rect.bottom - rect.top}"
            except Exception:
                info["bounds"] = "(unknown)"

            return info
        except Exception as e:
            return {"error": str(e)}

    def find_by_automation_id(self, automation_id: str) -> list:
        """Find elements by AutomationId."""
        root = self.automation.GetForegroundWindow()
        condition = self.automation.CreatePropertyCondition(30011, automation_id)  # AutomationId property
        elements = root.FindAll(TreeScope_Descendants, condition)

        results = []
        if elements:
            for i in range(elements.Length):
                elem = elements.GetElement(i)
                results.append(self.get_element_info(elem))

        return results

    def find_by_name(self, name: str, partial: bool = True) -> list:
        """Find elements by name."""
        root = self.automation.GetForegroundWindow()

        if partial:
            # Find all and filter
            condition = self.automation.CreateTrueCondition()
            elements = root.FindAll(TreeScope_Descendants, condition)

            results = []
            if elements:
                for i in range(min(elements.Length, 500)):  # Cap at 500 for speed
                    try:
                        elem = elements.GetElement(i)
                        elem_name = elem.CurrentName or ""
                        if name.lower() in elem_name.lower():
                            results.append(self.get_element_info(elem))
                    except Exception:
                        continue
        else:
            # Exact match
            condition = self.automation.CreatePropertyCondition(30005, name)  # Name property
            elements = root.FindAll(TreeScope_Descendants, condition)
            results = []
            if elements:
                for i in range(elements.Length):
                    elem = elements.GetElement(i)
                    results.append(self.get_element_info(elem))

        return results

    def find_by_control_type(self, control_type: str) -> list:
        """Find elements by control type."""
        # Map control type name to ID
        control_type_id = None
        for cid, cname in CONTROL_TYPE_MAP.items():
            if cname.lower() == control_type.lower():
                control_type_id = cid
                break

        if not control_type_id:
            return [{"error": f"Unknown control type: {control_type}"}]

        root = self.automation.GetForegroundWindow()
        condition = self.automation.CreatePropertyCondition(30003, control_type_id)  # ControlType property
        elements = root.FindAll(TreeScope_Descendants, condition)

        results = []
        if elements:
            for i in range(min(elements.Length, 50)):  # Limit to 50 results
                elem = elements.GetElement(i)
                results.append(self.get_element_info(elem))

        return results

    def list_all_automation_ids(self) -> list:
        """List all elements that have an AutomationId."""
        root = self.automation.GetForegroundWindow()
        condition = self.automation.CreateTrueCondition()
        elements = root.FindAll(TreeScope_Descendants, condition)

        results = []
        if elements:
            for i in range(min(elements.Length, 1000)):  # Cap at 1000
                try:
                    elem = elements.GetElement(i)
                    auto_id = elem.CurrentAutomationId
                    if auto_id:
                        results.append(self.get_element_info(elem))
                except Exception:
                    continue

        return results


def print_element(info: dict, index: int = None):
    """Pretty print element info."""
    if "error" in info:
        print(f"❌ Error: {info['error']}")
        return

    prefix = f"[{index}] " if index is not None else ""

    # Visual indicator
    has_auto_id = info.get("automation_id") != "(no id)"
    quality = "🎯" if has_auto_id else "✅"

    print(f"{prefix}{quality} {info['control_type']}")
    print(f"   Name: {info['name']}")
    print(f"   AutomationId: {info['automation_id']}")
    print(f"   ClassName: {info['class_name']}")
    print(f"   Bounds: {info['bounds']}")

    status = []
    if info.get("is_enabled"):
        status.append("✅ Enabled")
    else:
        status.append("⛔ Disabled")

    if info.get("is_keyboard_focusable"):
        status.append("⌨️ Focusable")

    if info.get("is_offscreen"):
        status.append("👻 Offscreen")

    if status:
        print(f"   Status: {', '.join(status)}")

    print()


def main():
    """Main finder - supports both interactive and command-line modes."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Connexus Quick Element Finder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--auto-id",
        help="Find element by AutomationId (non-interactive)",
    )
    parser.add_argument(
        "--name",
        help="Find element by Name (non-interactive, partial match)",
    )
    parser.add_argument(
        "--control-type",
        help="Find elements by Control Type (non-interactive)",
    )
    parser.add_argument(
        "--list-all-ids",
        action="store_true",
        help="List all elements with AutomationId (non-interactive)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum results to show (default: 50)",
    )

    args = parser.parse_args()

    print("\n" + "#" * 80)
    print("#  Connexus Quick Element Finder")
    print("#  Doc the Puppy 🐶")
    print("#" * 80 + "\n")

    # Check if running in non-interactive mode
    non_interactive = any([args.auto_id, args.name, args.control_type, args.list_all_ids])

    if not non_interactive:
        print("⚠️  Make sure Connexus.exe is the foreground window!\n")
        input("Press ENTER when ready...")
    else:
        print("🤖 NON-INTERACTIVE MODE - Running immediately...")
        print("⚠️  Assuming Connexus.exe is in foreground!\n")

    try:
        finder = QuickFinder()
        print("✅ Connected to UI Automation\n")

        # Handle non-interactive mode
        if non_interactive:
            results = []

            if args.auto_id:
                print(f"🔎 Searching for AutomationId='{args.auto_id}'...\n")
                results = finder.find_by_automation_id(args.auto_id)

            elif args.name:
                print(f"🔎 Searching for name containing '{args.name}'...\n")
                results = finder.find_by_name(args.name, partial=True)

            elif args.control_type:
                print(f"🔎 Searching for {args.control_type} elements...\n")
                results = finder.find_by_control_type(args.control_type)

            elif args.list_all_ids:
                print("🔎 Listing ALL elements with AutomationId...\n")
                results = finder.list_all_automation_ids()

            # Output results
            if args.json:
                import json
                output = {
                    "success": len(results) > 0,
                    "count": len(results),
                    "results": results[:args.max_results],
                    "total_found": len(results),
                }
                print(json.dumps(output, indent=2))
            else:
                if results:
                    print(f"✅ Found {len(results)} match(es) (showing max {args.max_results}):\n")
                    for i, elem in enumerate(results[:args.max_results]):
                        print_element(elem, i)
                    if len(results) > args.max_results:
                        print(f"\n... and {len(results) - args.max_results} more matches\n")
                else:
                    print("❌ No matches found\n")

            return 0 if results else 1

        # Interactive mode
        while True:
            print("\n" + "=" * 80)
            print("🔍 SEARCH OPTIONS")
            print("=" * 80 + "\n")
            print("  1. Find by AutomationId")
            print("  2. Find by Name (partial match)")
            print("  3. Find by Control Type")
            print("  4. List ALL elements with AutomationId")
            print("  5. Exit")

            choice = input("\nChoice: ").strip()

            if choice == "1":
                auto_id = input("\nEnter AutomationId: ").strip()
                print(f"\n🔎 Searching for AutomationId='{auto_id}'...\n")
                results = finder.find_by_automation_id(auto_id)

                if results:
                    print(f"✅ Found {len(results)} match(es):\n")
                    for i, elem in enumerate(results):
                        print_element(elem, i)
                else:
                    print("❌ No matches found")
                    print("\n💡 Tip: AutomationId is case-sensitive!")

            elif choice == "2":
                name = input("\nEnter Name (partial match): ").strip()
                print(f"\n🔎 Searching for name containing '{name}'...\n")
                results = finder.find_by_name(name, partial=True)

                if results:
                    print(f"✅ Found {len(results)} match(es):\n")
                    for i, elem in enumerate(results[:20]):
                        print_element(elem, i)
                    if len(results) > 20:
                        print(f"... and {len(results) - 20} more matches\n")
                else:
                    print("❌ No matches found")

            elif choice == "3":
                print("\nCommon control types:")
                print("  Button, Edit, ComboBox, ListItem, MenuItem, CheckBox, Text, Pane")
                control_type = input("\nEnter Control Type: ").strip()
                print(f"\n🔎 Searching for {control_type} elements...\n")
                results = finder.find_by_control_type(control_type)

                if results:
                    print(f"✅ Found {len(results)} match(es) (showing max 50):\n")
                    for i, elem in enumerate(results):
                        print_element(elem, i)
                else:
                    print("❌ No matches found")

            elif choice == "4":
                print("\n🔎 Listing ALL elements with AutomationId (max 1000)...\n")
                results = finder.list_all_automation_ids()

                if results:
                    print(f"✅ Found {len(results)} elements with AutomationId:\n")
                    for i, elem in enumerate(results[:30]):
                        print_element(elem, i)
                    if len(results) > 30:
                        print(f"... and {len(results) - 30} more elements\n")

                    # Group by control type
                    by_type = {}
                    for elem in results:
                        ctype = elem.get("control_type", "Unknown")
                        by_type[ctype] = by_type.get(ctype, 0) + 1

                    print("\n📋 By Control Type:")
                    for ctype, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
                        print(f"   {ctype:20} {count}")
                else:
                    print("❌ No elements with AutomationId found!")
                    print("\n🐞 This might be a problem - most UI frameworks set AutomationIds.")

            elif choice == "5":
                print("\n👋 Goodbye!\n")
                break

            else:
                print("❌ Invalid choice")

    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user\n")
        return 0
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
