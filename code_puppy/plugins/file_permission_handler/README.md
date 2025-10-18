# File Permission Handler Plugin

## Overview

This plugin provides a unified, extensible permission prompt system for all file operations in Code Puppy. It replaces the duplicated permission logic that was previously scattered across multiple files.

## Problem Solved

**Before**: File permission logic was duplicated between:
- `code_puppy/tools/file_permission.py` (separate module)
- `code_puppy/tools/file_modifications.py` (embedded function)

This violated DRY principles and made maintenance difficult.

**After**: All file permission handling is centralized in this plugin, providing:
- Single source of truth for permission logic
- Consistent user experience across all file operations
- Easy extensibility for new permission strategies
- Better separation of concerns

## Features

1. **Unified Permission System**: Single handler for all file operations
2. **YOLO Mode Support**: Automatic approval in yolo mode
3. **Thread Safety**: Prevents multiple simultaneous permission prompts
4. **Interactive Detection**: Handles non-interactive terminals gracefully
5. **Preview Support**: Shows diff previews before requesting permission
6. **Plugin Architecture**: Easily extensible and replaceable

## How It Works

1. **Callback Registration**: The plugin registers a `file_permission` callback
2. **Permission Request**: File operations call `on_file_permission()` to check permissions
3. **User Prompt**: If not in yolo mode and in interactive terminal, prompts user
4. **Result Return**: Returns True/False to allow or deny the operation

## Integration Points

### File Operations Using This Plugin:
- `edit_file()` - All three payload types (content, replacements, delete_snippet)
- `delete_file()` - File deletion operations
- Any future file operations can easily hook into this system

### Callback Flow:
```python
# In file_modifications.py
def prompt_for_file_permission(file_path, operation, preview=None):
    permission_results = on_file_permission(None, file_path, operation, preview)
    return all(result for result in permission_results if result is not None)
```

## Configuration

The plugin respects these configuration options:
- **yolo_mode**: Automatically approves all file operations when enabled
- **Interactive TTY Detection**: Automatically approves in non-interactive environments

## Plugin Structure

```
file_permission_handler/
├── __init__.py              # Plugin metadata
├── register_callbacks.py    # Main permission handling logic
└── README.md               # This documentation
```

## Benefits

1. **DRY Compliance**: Eliminates code duplication
2. **Maintainability**: Single place to update permission logic
3. **Testability**: Easy to test permission logic in isolation
4. **Extensibility**: Easy to add new permission types (e.g., file type restrictions)
5. **Consistency**: Same permission behavior across all file operations
6. **Modularity**: Can be disabled or replaced without affecting core functionality

## Testing

```python
from code_puppy.plugins import load_plugin_callbacks
from code_puppy.callbacks import get_callbacks

load_plugin_callbacks()
callbacks = get_callbacks('file_permission')
print(f'Permission handlers registered: {len(callbacks)}')
```

## Future Enhancements

Potential extensions to this plugin:
- File type-specific permissions (e.g., require confirmation for config files)
- Pattern-based permission rules
- Integration with external permission systems
- Permission caching for repeated operations
- Auditing and logging of permission decisions