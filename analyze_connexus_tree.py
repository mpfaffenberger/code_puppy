#!/usr/bin/env python
"""Analyze Connexus element tree for search strategy insights."""

import json
from collections import defaultdict

# Load the tree
with open('connexus_dropoff_tree.json', 'r') as f:
    data = json.load(f)

# Flatten tree to elements list
def flatten_tree(node, elements=None):
    if elements is None:
        elements = []
    elements.append(node)
    for child in node.get('children', []):
        flatten_tree(child, elements)
    return elements

elements = flatten_tree(data['tree'])

print(f"\n{'='*80}")
print("CONNEXUS DROP-OFF SCREEN - ELEMENT TREE ANALYSIS")
print(f"{'='*80}\n")

print(f"Total elements: {len(elements)}")
print(f"Statistics: {data['statistics']}\n")

# Analyze buttons
print(f"\n{'='*80}")
print("BUTTON ANALYSIS")
print(f"{'='*80}\n")

buttons = [e for e in elements if e['properties'].get('control_type') == 'Button']
print(f"Found {len(buttons)} buttons\n")

for i, btn in enumerate(buttons[:25]):
    props = btn['properties']
    name = props.get('name', '')
    auto_id = props.get('automation_id', '')
    class_name = props.get('class_name', '')
    enabled = props.get('is_enabled', False)
    offscreen = props.get('is_offscreen', False)
    
    print(f"[{i+1}] Name: '{name}'")
    if auto_id:
        print(f"    AutomationId: '{auto_id}'")
    if class_name:
        print(f"    ClassName: '{class_name}'")
    print(f"    Enabled: {enabled}, Offscreen: {offscreen}")
    print()

# Analyze edit fields
print(f"\n{'='*80}")
print("EDIT FIELD ANALYSIS")
print(f"{'='*80}\n")

edits = [e for e in elements if e['properties'].get('control_type') == 'Edit']
print(f"Found {len(edits)} edit fields\n")

for i, edit in enumerate(edits):
    props = edit['properties']
    name = props.get('name', '')
    auto_id = props.get('automation_id', '')
    class_name = props.get('class_name', '')
    
    print(f"[{i+1}] Name: '{name}'")
    if auto_id:
        print(f"    AutomationId: '{auto_id}'")
    if class_name:
        print(f"    ClassName: '{class_name}'")
    print()

# Analyze elements WITHOUT identifiers
print(f"\n{'='*80}")
print("ELEMENTS WITH POOR IDENTIFIERS (Potential Search Issues)")
print(f"{'='*80}\n")

interactive_types = ['Button', 'Edit', 'ComboBox', 'CheckBox']
poor_elements = []

for e in elements:
    props = e['properties']
    control_type = props.get('control_type', '')
    
    if control_type in interactive_types:
        name = props.get('name', '').strip()
        auto_id = props.get('automation_id', '').strip()
        
        # Check if element has poor identifiers
        if not auto_id and (not name or len(name) < 2):
            poor_elements.append(e)

print(f"Found {len(poor_elements)} interactive elements with poor identifiers\n")

for i, elem in enumerate(poor_elements[:10]):
    props = elem['properties']
    print(f"[{i+1}] Type: {props.get('control_type')}")
    print(f"    Name: '{props.get('name', '')}'")
    print(f"    AutomationId: '{props.get('automation_id', '')}'")
    print(f"    ClassName: '{props.get('class_name', '')}'")
    print()

# Analyze name patterns
print(f"\n{'='*80}")
print("NAME PATTERN ANALYSIS (for fuzzy matching)")
print(f"{'='*80}\n")

name_patterns = defaultdict(list)

for e in elements:
    props = e['properties']
    name = props.get('name', '').strip()
    control_type = props.get('control_type', '')
    
    if name and control_type in interactive_types:
        # Check for multi-line names
        if '\n' in name:
            name_patterns['multi_line'].append((control_type, name[:50]))
        # Check for very long names
        elif len(name) > 50:
            name_patterns['long_names'].append((control_type, name[:50]))
        # Check for numeric-only names
        elif name.isdigit():
            name_patterns['numeric'].append((control_type, name))
        # Check for single-char names
        elif len(name) == 1:
            name_patterns['single_char'].append((control_type, name))

for pattern, items in name_patterns.items():
    print(f"\n{pattern.upper()}: {len(items)} elements")
    for control_type, name in items[:5]:
        print(f"  {control_type}: '{name}'")

# Analyze depth distribution
print(f"\n{'='*80}")
print("DEPTH DISTRIBUTION (for pruning analysis)")
print(f"{'='*80}\n")

depth_dist = defaultdict(int)
interactive_by_depth = defaultdict(int)

for e in elements:
    depth = e['depth']
    control_type = e['properties'].get('control_type', '')
    depth_dist[depth] += 1
    
    if control_type in interactive_types:
        interactive_by_depth[depth] += 1

print("Depth | Total Elements | Interactive Elements")
print("-" * 50)
for depth in sorted(depth_dist.keys()):
    total = depth_dist[depth]
    interactive = interactive_by_depth[depth]
    print(f"{depth:5} | {total:14} | {interactive:20}")

print(f"\n{'='*80}")
print("KEY INSIGHTS FOR SEARCH STRATEGY")
print(f"{'='*80}\n")

print("1. AUTOMATION ID COVERAGE:")
print(f"   - {data['statistics']['with_automation_id']} elements ({data['statistics']['with_automation_id']/data['statistics']['total_elements']*100:.1f}%) have AutomationId")
print(f"   - This is GOOD coverage - prioritize AutomationId in search!\n")

print("2. NAME COVERAGE:")
print(f"   - {data['statistics']['with_name']} elements ({data['statistics']['with_name']/data['statistics']['total_elements']*100:.1f}%) have Name")
print(f"   - Excellent! Name should be secondary fallback\n")

print("3. INTERACTIVE ELEMENTS:")
interactive_count = sum(1 for e in elements if e['properties'].get('control_type') in interactive_types)
print(f"   - {interactive_count} interactive elements (Buttons, Edits, etc.)")
print(f"   - {len(poor_elements)} have poor identifiers (needs better search logic)\n")

print("4. DEPTH DISTRIBUTION:")
print(f"   - Max depth: {data['statistics']['max_depth']}")
print(f"   - Current gui-cub depth limit: 5")
if data['statistics']['max_depth'] > 5:
    print(f"   - [WARNING] We're pruning elements at depth > 5!")
    deep_interactive = sum(count for depth, count in interactive_by_depth.items() if depth > 5)
    print(f"   - {deep_interactive} interactive elements are beyond depth 5!\n")
else:
    print(f"   - [OK] Current depth limit of 5 is sufficient\n")

print("5. NAME PATTERNS:")
for pattern, items in name_patterns.items():
    if len(items) > 0:
        print(f"   - {len(items)} elements with {pattern} names (fuzzy matching may struggle)")

print(f"\n{'='*80}\n")
