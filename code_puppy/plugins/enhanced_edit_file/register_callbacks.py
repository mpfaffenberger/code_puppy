"""Enhanced edit_file plugin with detailed user rejection feedback.

This plugin provides enhanced feedback when users reject file operations,
giving the model specific information about why the operation was rejected
rather than generic "operation cancelled" messages.
"""

from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback


def enhance_edit_file_result(context: Any, result: Dict[str, Any], payload: Any = None) -> Dict[str, Any]:
    """Enhance edit_file results with detailed rejection information.
    
    This callback is called after an edit_file operation and can enhance
    the result with additional context about user rejections.
    
    Args:
        context: The PydanticAI RunContext
        result: The current result from the edit_file operation
        payload: The original payload sent to edit_file
        
    Returns:
        Enhanced result with detailed rejection information if applicable
    """
    if not result or not isinstance(result, dict):
        return result
        
    # Check if this was a user cancellation
    if (result.get("success") is False and 
        result.get("changed") is False and
        "cancelled" in result.get("message", "").lower()):
        
        # Add detailed rejection information
        enhanced_result = result.copy()
        enhanced_result.update({
            "rejection_reason": "user_denied_permission",
            "rejection_details": {
                "type": "user_interaction",
                "phase": "permission_prompt",
                "user_action": "rejected_diff",
                "file_path": result.get("path", "unknown"),
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
        })
        
        return enhanced_result
    
    return result


def get_enhanced_edit_file_help() -> str:
    """Return help information for the enhanced edit_file functionality."""
    return """Enhanced edit_file plugin provides:
- Detailed user rejection feedback when operations are cancelled
- Specific guidance for models when changes are rejected
- Better context about why operations failed
- Actionable suggestions for next attempts"""


# Register the callbacks
register_callback("edit_file", enhance_edit_file_result)
register_callback("delete_file", enhance_edit_file_result)