#!/usr/bin/env python
"""Automated Windows Element Tree Testing Script

Runs automatically on currently focused window.
"""

import sys
from pathlib import Path
import subprocess
import time

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from code_puppy.tools.gui_cub.windows_automation import (
    list_elements_in_window,
    find_element,
)


def get_active_window_title():
    """Get the title of the currently active window."""
    try:
        from code_puppy.tools.gui_cub.windows_automation.core import _get_foreground_window_info
        info = _get_foreground_window_info()
        return info.get('title', 'Unknown')
    except:
        return 'Unknown'


def test_current_window():
    """Test the currently focused window."""
    window_title = get_active_window_title()
    
    print("\n" + "=" * 80)
    print(f"Testing Window: {window_title}")
    print("=" * 80)

    # List all elements
    print("\n[1] Listing all elements...")
    result = list_elements_in_window()
    
    print(f"Success: {result.get('success', False)}")
    print(f"Total elements: {result.get('total_elements', 0)}")

    elements = result.get('elements', [])
    if not elements:
        print("❌ No elements found!")
        return
    
    # Group by control type
    by_type = {}
    for elem in elements:
        ctype = elem.get('control_type', 'Unknown')
        if ctype not in by_type:
            by_type[ctype] = []
        by_type[ctype].append(elem)
    
    print("\n[2] Elements by control type:")
    for ctype, elems in sorted(by_type.items()):
        print(f"  {ctype}: {len(elems)}")
    
    # Show buttons in detail
    if 'Button' in by_type:
        print("\n[3] Button details:")
        buttons = by_type['Button']
        for i, btn in enumerate(buttons[:20]):
            name = btn.get('name', '')
            auto_id = btn.get('automation_id', '')
            has_name = bool(name and name.strip())
            status = "✅" if has_name else "❌"
            print(f"  [{i}] {status} {name or '(no name)'}")
            if auto_id:
                print(f"      automation_id: '{auto_id}'")
    
    # Show elements with AutomationId
    print("\n[4] Elements with AutomationId:")
    with_auto_id = [e for e in elements if e.get('automation_id')]
    print(f"Total: {len(with_auto_id)} / {len(elements)} ({100*len(with_auto_id)/len(elements):.1f}%)")
    
    for elem in with_auto_id[:15]:
        print(f"  - {elem.get('control_type')}: {elem.get('name')} (id: {elem.get('automation_id')})")
    
    # Test finding specific elements for Calculator
    if 'Calculator' in window_title:
        print("\n[5] Calculator-specific tests:")
        
        for button_name in ['Plus', 'Equals', 'Zero', 'One', 'Two']:
            result = find_element(name=button_name, control_type='Button', fuzzy=True)
            status = "✅" if result.get('found') else "❌"
            print(f"  {status} Find '{button_name}': {result.get('found', False)}")
            if result.get('found'):
                print(f"      Position: ({result.get('x')}, {result.get('y')})")
    
    # Test for Notepad
    if 'Notepad' in window_title:
        print("\n[5] Notepad-specific tests:")
        
        # Find menu items
        menu_items = by_type.get('MenuItem', [])
        print(f"  Menu items: {len(menu_items)}")
        for item in menu_items[:10]:
            print(f"    - {item.get('name')}")
        
        # Find text editor
        edit_controls = by_type.get('Edit', [])
        print(f"  Edit controls: {len(edit_controls)}")
        for edit in edit_controls:
            print(f"    - {edit.get('name')} (automation_id: {edit.get('automation_id')})")
    
    # Test for File Explorer
    if 'Explorer' in window_title or 'File Explorer' in window_title:
        print("\n[5] File Explorer-specific tests:")
        
        for button_name in ['Back', 'Forward', 'Up']:
            result = find_element(name=button_name, control_type='Button', fuzzy=True)
            status = "✅" if result.get('found') else "❌"
            print(f"  {status} Find '{button_name}': {result.get('found', False)}")


def main():
    """Run tests."""
    print("\n" + "#" * 80)
    print("#  WINDOWS ELEMENT TREE AUTOMATED TEST")
    print("#" * 80)
    
    try:
        test_current_window()
        
        print("\n" + "=" * 80)
        print("TEST COMPLETE")
        print("=" * 80 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
