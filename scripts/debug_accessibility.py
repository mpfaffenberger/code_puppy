#!/usr/bin/env uv run python
"""Standalone accessibility diagnostic script.

This script tests accessibility API functionality WITHOUT the agent to help
diagnose why element tree tools aren't returning good labels/info.

Usage:
    python scripts/debug_accessibility.py [options]
    
    --app <name>        Focus specific app (default: frontmost)
    --role <role>       Filter by role (e.g., AXButton)
    --full-tree         Show entire element hierarchy
    --compare-ocr       Compare accessibility vs OCR results
    --output <file>     Save results to file
    --interactive       Interactive element browser
    --stats             Show statistics about element quality

Examples:
    python scripts/debug_accessibility.py --stats
    python scripts/debug_accessibility.py --compare-ocr
    python scripts/debug_accessibility.py --full-tree --output tree.json
    python scripts/debug_accessibility.py --app Safari --role AXButton
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import only what we need - avoid loading agent stuff
try:
    from code_puppy.tools.gui_cub.accessibility.element_list import (
        list_accessible_elements,
        _compact_element_list_result,
    )
    from code_puppy.tools.gui_cub.platform import get_platform
except ImportError as e:
    print(f"Error importing gui-cub tools: {e}")
    print("Make sure you're running from the code-puppy directory")
    sys.exit(1)


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{'=' * 80}")
    print(f"  {text}")
    print(f"{'=' * 80}\n")


def print_section(text: str):
    """Print formatted section."""
    print(f"\n{'-' * 80}")
    print(f"  {text}")
    print(f"{'-' * 80}\n")


def analyze_element_quality(elements: list[dict]) -> dict:
    """Analyze quality of element data."""
    stats = {
        "total": len(elements),
        "with_title": 0,
        "with_label": 0,
        "with_value": 0,
        "with_description": 0,
        "empty_title": 0,
        "useless_title": 0,  # Single char, numbers only, etc.
        "good_title": 0,
        "by_role": {},
        "title_lengths": [],
        "interactive_elements": 0,
        "static_elements": 0,
    }
    
    interactive_roles = {
        "AXButton", "AXTextField", "AXSearchField", "AXTextArea",
        "AXMenuItem", "AXCheckBox", "AXRadioButton", "AXPopUpButton",
        "AXComboBox", "AXLink",
        "Button", "Edit", "ComboBox", "ListItem", "MenuItem",
        "CheckBox", "RadioButton", "Hyperlink",
    }
    
    for elem in elements:
        title = elem.get("title", "")
        role = elem.get("role") or elem.get("type") or elem.get("control_type") or "Unknown"
        
        # Count attributes
        if title:
            stats["with_title"] += 1
            stats["title_lengths"].append(len(title))
            
            # Quality check
            if len(title.strip()) == 0:
                stats["empty_title"] += 1
            elif len(title.strip()) == 1 or title.strip().isdigit():
                stats["useless_title"] += 1
            else:
                stats["good_title"] += 1
        else:
            stats["empty_title"] += 1
            
        if elem.get("label"):
            stats["with_label"] += 1
        if elem.get("value"):
            stats["with_value"] += 1
        if elem.get("description"):
            stats["with_description"] += 1
            
        # Role tracking
        stats["by_role"][role] = stats["by_role"].get(role, 0) + 1
        
        # Interactive vs static
        if role in interactive_roles:
            stats["interactive_elements"] += 1
        else:
            stats["static_elements"] += 1
    
    # Calculate averages
    if stats["title_lengths"]:
        stats["avg_title_length"] = sum(stats["title_lengths"]) / len(stats["title_lengths"])
        stats["min_title_length"] = min(stats["title_lengths"])
        stats["max_title_length"] = max(stats["title_lengths"])
    else:
        stats["avg_title_length"] = 0
        stats["min_title_length"] = 0
        stats["max_title_length"] = 0
    
    del stats["title_lengths"]  # Don't need raw list in output
    
    return stats


def print_element(elem: dict, indent: int = 0, show_all: bool = False):
    """Pretty print an element."""
    prefix = "  " * indent
    role = elem.get("role") or elem.get("type") or elem.get("control_type") or "Unknown"
    title = elem.get("title", "")
    label = elem.get("label", "")
    value = elem.get("value", "")
    
    # Color code based on quality
    if title and len(title.strip()) > 2:
        quality = "✅"  # Good
    elif title:
        quality = "⚠️"  # Marginal
    else:
        quality = "❌"  # No title
    
    print(f"{prefix}{quality} [{role}]")
    print(f"{prefix}   title: '{title}'")
    
    if label:
        print(f"{prefix}   label: '{label}'")
    if value:
        print(f"{prefix}   value: '{value}'")
    
    if show_all:
        # Show all attributes
        for key, val in elem.items():
            if key not in ["role", "type", "control_type", "title", "label", "value"]:
                print(f"{prefix}   {key}: {val}")
    
    print()  # Blank line


def compare_with_ocr():
    """Compare accessibility results with OCR results."""
    print_section("Comparing Accessibility vs OCR")
    
    try:
        from code_puppy.tools.gui_cub.ocr.extraction import extract_text_from_image
        import pyautogui
        
        # Get accessibility elements
        print("📱 Fetching accessibility elements...")
        ax_result = list_accessible_elements(in_frontmost_app=True)
        
        if not ax_result.success:
            print(f"❌ Accessibility failed: {ax_result.error}")
            return
        
        # Handle both formats
        elements = ax_result.elements
        if not elements and ax_result.by_role:
            elements = []
            for role, role_elements in ax_result.by_role.items():
                for elem in role_elements:
                    elem_copy = elem.copy()
                    elem_copy["role"] = role
                    elements.append(elem_copy)
        
        elements = elements or []
        if not elements:
            print(f"❌ No accessibility elements found (list is None or empty)")
            print(f"   Total elements: {ax_result.total_elements}")
            print(f"   Success: {ax_result.success}")
            return
        
        # Get OCR text
        print("👁️  Running OCR...")
        screenshot = pyautogui.screenshot()
        ocr_result = extract_text_from_image(screenshot)
        
        if not ocr_result.success:
            print(f"❌ OCR failed: {ocr_result.error}")
            return
        
        if not ocr_result.text_elements:
            print(f"❌ No OCR text elements found")
            return
        
        # Compare results
        print(f"\n📊 Results:")
        print(f"   Accessibility elements: {len(elements)}")
        print(f"   OCR text elements: {len(ocr_result.text_elements)}")
        print(f"   OCR total words: {ocr_result.total_words}")
        
        # Find accessibility elements with titles
        ax_titles = set()
        for elem in elements:
            title = (elem.get("title") or "").strip()
            if title and len(title) > 2:
                ax_titles.add(title.lower())
        
        # Find OCR text
        ocr_texts = set()
        for elem in ocr_result.text_elements:
            text = elem.text.strip()
            if text and len(text) > 2:
                ocr_texts.add(text.lower())
        
        print(f"\n📝 Text Content:")
        print(f"   Accessibility unique titles: {len(ax_titles)}")
        print(f"   OCR unique texts: {len(ocr_texts)}")
        
        # Find overlap
        overlap = ax_titles & ocr_texts
        ocr_only = ocr_texts - ax_titles
        ax_only = ax_titles - ocr_texts
        
        print(f"\n🔍 Overlap Analysis:")
        print(f"   Both found: {len(overlap)} texts")
        print(f"   OCR only: {len(ocr_only)} texts")
        print(f"   Accessibility only: {len(ax_only)} texts")
        
        if overlap:
            print(f"\n✅ Found by both (sample):")
            for text in list(overlap)[:10]:
                print(f"      '{text}'")
        
        if ocr_only:
            print(f"\n👁️  OCR found but accessibility missed (sample):")
            for text in list(ocr_only)[:10]:
                print(f"      '{text}'")
        
        if ax_only:
            print(f"\n📱 Accessibility found but OCR missed (sample):")
            for text in list(ax_only)[:10]:
                print(f"      '{text}'")
        
        # Quality assessment
        print(f"\n💡 Assessment:")
        if len(ocr_only) > len(ax_titles) * 0.5:
            print("   ⚠️  Accessibility is missing a lot of visible text!")
            print("   ➜  Consider: OCR might be better for text-heavy UIs")
        
        if len(ax_only) > len(ocr_texts) * 0.5:
            print("   ⚠️  Accessibility has labels that aren't visible!")
            print("   ➜  This is normal for aria-labels and accessibility names")
        
        if len(overlap) < 10 and len(ocr_texts) > 50:
            print("   ❌ Very low overlap - accessibility labels may be poor quality")
            print("   ➜  Recommendation: Prefer OCR or VQA for this application")
        
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        print("   Install with: uv pip install pyautogui pillow")


def test_compaction_impact():
    """Test how compaction affects results."""
    print_section("Testing Compaction Impact")
    
    print("📱 Fetching FULL accessibility tree...")
    full_result = list_accessible_elements(in_frontmost_app=True)
    
    if not full_result.success:
        print(f"❌ Failed: {full_result.error}")
        return
    
    print(f"✅ Found {len(full_result.elements)} total elements\n")
    
    # Analyze full result
    print("📊 FULL TREE Analysis:")
    full_stats = analyze_element_quality(full_result.elements)
    print(json.dumps(full_stats, indent=2))
    
    # Compact it
    print("\n🗜️  Applying compaction...")
    compact_result = _compact_element_list_result(full_result, max_elements=20)
    
    print(f"\n📊 COMPACTED Analysis ({len(compact_result.elements)} elements):")
    compact_stats = analyze_element_quality(compact_result.elements)
    print(json.dumps(compact_stats, indent=2))
    
    # Show what was lost
    print("\n⚖️  Compaction Impact:")
    print(f"   Elements: {full_stats['total']} → {compact_stats['total']}")
    print(f"   With good titles: {full_stats['good_title']} → {compact_stats['good_title']}")
    print(f"   Interactive: {full_stats['interactive_elements']} → {compact_stats['interactive_elements']}")
    print(f"   Static: {full_stats['static_elements']} → {compact_stats['static_elements']}")
    
    # Show filtered elements
    filtered_count = full_stats['total'] - compact_stats['total']
    print(f"\n🗑️  Filtered out {filtered_count} elements")
    
    if filtered_count > 0:
        print("\n🔍 Sample of filtered elements:")
        filtered = [e for e in full_result.elements if e not in compact_result.elements]
        for elem in filtered[:10]:
            print_element(elem, indent=1)


def interactive_browser():
    """Interactive element browser."""
    print_section("Interactive Element Browser")
    print("Commands:")
    print("  list [role]     - List elements (optionally filter by role)")
    print("  show <index>    - Show detailed info for element")
    print("  stats           - Show statistics")
    print("  compare         - Compare with OCR")
    print("  refresh         - Refresh element tree")
    print("  quit            - Exit")
    print()
    
    elements = []
    
    def refresh():
        nonlocal elements
        print("📱 Fetching elements...")
        result = list_accessible_elements(in_frontmost_app=True)
        if result.success:
            elements = result.elements
            print(f"✅ Loaded {len(elements)} elements\n")
        else:
            print(f"❌ Failed: {result.error}\n")
    
    refresh()
    
    while True:
        try:
            cmd = input("\n> ").strip().lower()
            
            if cmd == "quit" or cmd == "q":
                break
            
            elif cmd == "refresh" or cmd == "r":
                refresh()
            
            elif cmd == "stats" or cmd == "s":
                stats = analyze_element_quality(elements)
                print(json.dumps(stats, indent=2))
            
            elif cmd == "compare" or cmd == "c":
                compare_with_ocr()
            
            elif cmd.startswith("list"):
                parts = cmd.split()
                role_filter = parts[1] if len(parts) > 1 else None
                
                filtered = elements
                if role_filter:
                    filtered = [
                        e for e in elements
                        if (e.get("role") or e.get("type") or "").lower() == role_filter.lower()
                    ]
                    print(f"\n📋 Elements with role='{role_filter}' ({len(filtered)}):")
                else:
                    print(f"\n📋 All Elements ({len(filtered)}):")
                
                for i, elem in enumerate(filtered[:50]):
                    role = elem.get("role") or elem.get("type") or "Unknown"
                    title = elem.get("title", "")
                    print(f"  [{i}] {role}: '{title}'")
                
                if len(filtered) > 50:
                    print(f"  ... and {len(filtered) - 50} more")
            
            elif cmd.startswith("show"):
                parts = cmd.split()
                if len(parts) < 2:
                    print("Usage: show <index>")
                    continue
                
                try:
                    idx = int(parts[1])
                    if 0 <= idx < len(elements):
                        print("\n📄 Element Details:")
                        print_element(elements[idx], show_all=True)
                    else:
                        print(f"❌ Index out of range (0-{len(elements)-1})")
                except ValueError:
                    print("❌ Invalid index")
            
            else:
                print("❌ Unknown command. Try: list, show <index>, stats, compare, refresh, quit")
        
        except KeyboardInterrupt:
            print("\n")
            break
        except EOFError:
            break


def main():
    parser = argparse.ArgumentParser(
        description="Accessibility API diagnostic tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--app", help="Focus specific app name")
    parser.add_argument("--role", help="Filter by role")
    parser.add_argument("--full-tree", action="store_true", help="Show full element tree")
    parser.add_argument("--compare-ocr", action="store_true", help="Compare with OCR")
    parser.add_argument("--output", help="Save output to file")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--test-compaction", action="store_true", help="Test compaction impact")
    
    args = parser.parse_args()
    
    print_header(f"GUI-Cub Accessibility Diagnostic Tool")
    print(f"Platform: {get_platform()}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Interactive mode
    if args.interactive:
        interactive_browser()
        return
    
    # Test compaction
    if args.test_compaction:
        test_compaction_impact()
        return
    
    # Compare with OCR
    if args.compare_ocr:
        compare_with_ocr()
        return
    
    # Default: fetch and analyze
    print_section("Fetching Accessibility Elements")
    
    result = list_accessible_elements(
        role=args.role,
        in_frontmost_app=not args.app  # If app specified, search all
    )
    
    if not result.success:
        print(f"❌ Failed: {result.error}")
        return 1
    
    # Handle both formats: elements list or by_role dict
    elements = result.elements
    if not elements and result.by_role:
        # Flatten by_role dict into elements list
        elements = []
        for role, role_elements in result.by_role.items():
            for elem in role_elements:
                elem_copy = elem.copy()
                elem_copy["role"] = role
                elements.append(elem_copy)
    
    elements = elements or []
    print(f"✅ Found {len(elements)} elements")
    
    if not elements:
        print("⚠️  No elements returned (list is empty or None)")
        print(f"   Total elements in result: {result.total_elements}")
        print(f"   Success: {result.success}")
        if result.error:
            print(f"   Error: {result.error}")
        return 1
    
    # Show statistics
    if args.stats or not args.full_tree:
        print_section("Element Quality Statistics")
        stats = analyze_element_quality(elements)
        print(json.dumps(stats, indent=2))
        
        # Quality assessment
        print("\n💡 Quality Assessment:")
        if stats["good_title"] < stats["total"] * 0.3:
            print("   ⚠️  Less than 30% of elements have good titles!")
            print("   ➜  Accessibility API may not be effective for this app")
        
        if stats["interactive_elements"] < 10:
            print("   ⚠️  Very few interactive elements found")
            print("   ➜  Check if correct window is focused")
        
        if stats["empty_title"] > stats["with_title"]:
            print("   ❌ More empty titles than filled titles!")
            print("   ➜  Strong recommendation: Use OCR or VQA instead")
    
    # Show full tree
    if args.full_tree:
        print_section("Element Tree")
        for i, elem in enumerate(elements):
            print(f"[{i}]")
            print_element(elem, show_all=True)
    else:
        print_section("Sample Elements (first 20)")
        for elem in elements[:20]:
            print_element(elem)
    
    # Save to file
    if args.output:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "platform": get_platform(),
            "total_elements": len(elements),
            "statistics": analyze_element_quality(elements),
            "elements": elements
        }
        
        output_path = Path(args.output)
        output_path.write_text(json.dumps(output_data, indent=2))
        print(f"\n💾 Saved to: {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())