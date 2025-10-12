# Enhanced edit_file Plugin

## Overview

This plugin provides enhanced feedback when users reject file operations in Code Puppy. Instead of generic "operation cancelled" messages, the model now receives detailed information about why the operation was rejected and actionable guidance for next steps.

## Problem Solved

**Before:** When users rejected file operations, the model received generic messages like:
```json
{
  "success": false,
  "message": "Operation cancelled by user",
  "changed": false
}
```

This caused the model to guess reasons like "Oops, probably failed due to a diff misalignment."

**After:** The model now receives detailed rejection information:
```json
{
  "success": false,
  "message": "Operation cancelled by user - rejected file write after reviewing diff preview",
  "changed": false,
  "rejection_reason": "user_denied_permission",
  "rejection_details": {
    "type": "user_interaction",
    "phase": "permission_prompt", 
    "user_action": "rejected_diff",
    "explanation": "The user was shown a preview diff and explicitly rejected the changes",
    "model_guidance": {
      "what_happened": "User rejected the proposed file changes after reviewing the diff",
      "why_it_failed": "The user did not approve the modifications when prompted",
      "next_steps": [
        "Review the rejected changes and make them less invasive",
        "Break down large changes into smaller, more targeted modifications",
        "Consider if the changes are actually necessary",
        "Try a different approach that addresses the same goal"
      ],
      "common_causes": [
        "The diff was too large or contained unintended changes",
        "The user didn't understand the purpose of the changes",
        "The changes might break existing functionality",
        "The user wants to review the changes more carefully"
      ]
    }
  }
}
```

## Features

1. **Detailed Rejection Context**: Captures what operation was rejected and why
2. **Model Guidance**: Provides actionable next steps for the AI model
3. **Common Causes**: Lists typical reasons users reject changes
4. **Operation Type Awareness**: Differentiates between write, replace, and delete operations
5. **Non-Intrusive**: Only enhances user rejections, leaves other results unchanged

## How It Works

1. **Callback Registration**: The plugin registers callbacks for `edit_file` and `delete_file` operations
2. **Rejection Detection**: Identifies user rejections by checking for specific patterns in the result
3. **Enhancement**: Adds structured rejection information with model guidance
4. **Integration**: Seamlessly integrates with existing file modification tools

## Supported Operations

- File creation/overwrite (`write_to_file`)
- Text replacements (`replace_in_file`) 
- Snippet deletion (`delete_snippet_from_file`)
- File deletion (`delete_file`)

## Plugin Structure

```
enhanced_edit_file/
├── __init__.py              # Plugin metadata
├── register_callbacks.py    # Main plugin logic
└── README.md               # This documentation
```

## Testing

Run the test to verify the plugin works correctly:
```bash
cd code_puppy
python -c "
from code_puppy.plugins import load_plugin_callbacks
load_plugin_callbacks()
from code_puppy.callbacks import get_callbacks
print(f'edit_file callbacks: {len(get_callbacks("edit_file"))}')
print(f'delete_file callbacks: {len(get_callbacks("delete_file"))}')
"
```

## Benefits

- **Better Model Understanding**: AI models get specific feedback about why operations failed
- **Reduced Guesswork**: No more "probably failed due to a diff misalignment" assumptions
- **Actionable Guidance**: Models get concrete next steps to try
- **User Experience**: More informative feedback when users reject changes
- **Developer Debugging**: Clear visibility into why operations were cancelled