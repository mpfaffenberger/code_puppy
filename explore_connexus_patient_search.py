"""Exploration script to discover Connexus Patient Search dialog elements."""

from pywinauto import Application
import time

# Connect to Connexus by PID (we know it's 20928)
PID = 20928

print("Connecting to Connexus...")
app = Application(backend="uia").connect(process=PID)

# Get all windows
print("\n=== WINDOWS ===")
for window in app.windows():
    try:
        print(f"Window: {window.window_text()} | Class: {window.class_name()}")
    except:
        print(f"Window: <error getting text>")

# Find the Search window
print("\n=== SEARCH WINDOW ===")
try:
    search_window = app.window(title="Search")
    print(f"Found Search window: {search_window.window_text()}")
    print(f"Visible: {search_window.is_visible()}")
    print(f"Enabled: {search_window.is_enabled()}")
    
    # Print all descendants
    print("\n=== ALL ELEMENTS (FLAT) ===")
    elements = search_window.descendants()
    print(f"Total elements: {len(elements)}")
    
    for i, elem in enumerate(elements[:50]):  # First 50 elements
        try:
            info = elem.element_info
            print(f"\n[{i}] {info.control_type}")
            print(f"    Name: {info.name}")
            print(f"    Class: {info.class_name}")
            print(f"    AutomationId: {info.automation_id}")
            
            # Try to get value/text if it's an Edit control
            if info.control_type == "Edit":
                try:
                    value = elem.window_text()
                    print(f"    VALUE: '{value}'")
                except:
                    print(f"    VALUE: <error>")
                    
        except Exception as e:
            print(f"[{i}] Error: {e}")
    
    # Look specifically for Edit controls
    print("\n=== EDIT CONTROLS (TEXT FIELDS) ===")
    edits = search_window.children(control_type="Edit")
    print(f"Found {len(edits)} Edit controls")
    
    for i, edit in enumerate(edits):
        try:
            info = edit.element_info
            value = edit.window_text()
            print(f"\nEdit [{i}]:")
            print(f"    Name: {info.name}")
            print(f"    AutomationId: {info.automation_id}")
            print(f"    Value: '{value}'")
            print(f"    Class: {info.class_name}")
        except Exception as e:
            print(f"Edit [{i}] Error: {e}")
            
except Exception as e:
    print(f"Error finding Search window: {e}")

print("\n=== DONE ===")
