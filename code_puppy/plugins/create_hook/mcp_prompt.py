"""
MCP-Compatible Hook Creator Prompt

This module exposes the hook creation logic as structured MCP prompts
that can be extracted and used in other tools (Claude Code, MCP clients, etc.).

Export this to share the hook creation knowledge with other systems.
"""

import json
from typing import Dict, List, Any
from .hook_knowledge_base import (
    LIFECYCLE_CALLBACKS,
    EVENT_BASED_HOOKS,
    CLAUDE_CODE_REFERENCE_HOOKS,
)


def export_hook_knowledge_base() -> str:
    """
    Export the complete hook knowledge base as JSON.
    Can be imported by other tools and MCP clients.
    """
    callbacks = [
        {
            "name": h.name,
            "category": h.category,
            "description": h.description,
            "matcher_support": h.matcher_support,
            "matcher_examples": h.matcher_examples,
            "input_fields": h.input_fields,
            "output_options": h.output_options,
            "timeout_default": h.timeout_default,
            "code_example": h.code_example,
        }
        for h in LIFECYCLE_CALLBACKS
    ]
    
    events = [
        {
            "name": h.name,
            "category": h.category,
            "description": h.description,
            "matcher_support": h.matcher_support,
            "matcher_examples": h.matcher_examples,
            "input_fields": h.input_fields,
            "output_options": h.output_options,
            "timeout_default": h.timeout_default,
            "code_example": h.code_example,
        }
        for h in EVENT_BASED_HOOKS
    ]
    
    return json.dumps(
        {
            "lifecycle_callbacks": callbacks,
            "event_based_hooks": events,
            "claude_code_reference": CLAUDE_CODE_REFERENCE_HOOKS,
        },
        indent=2,
    )


def get_mcp_system_prompt() -> str:
    """
    System prompt for MCP clients implementing hook creation.
    
    This prompt can be used as the base system prompt for an MCP-based
    hook creation assistant in other tools.
    """
    return """You are a Code Puppy Hook Creation Assistant.

Your role is to guide users through creating hooks in Code Puppy.

## Hook Types

Code Puppy has two hook systems:

### 1. Lifecycle Callbacks (Python)
Functions registered at startup that execute at specific phases:
- startup: Application boot
- shutdown: Application exit  
- custom_command: User types /slash command
- pre_tool_call: Before any tool executes
- post_tool_call: After a tool finishes
- agent_run_start: Agent run begins
- agent_run_end: Agent run completes

### 2. Event-Based Hooks (Shell/JSON)
Commands/scripts responding to Code Puppy events:
- PreToolUse: Before a tool executes (can block)
- PostToolUse: After a tool succeeds
- SessionStart: Session begins/resumes
- Stop: Claude finishes responding

## Your Workflow

1. **Ask** what the user wants to achieve
2. **Recommend** the best hook type (lifecycle vs event)
3. **Guide** them through configuration
4. **Explain** the input/output schemas
5. **Generate** boilerplate code
6. **Suggest** where to save it

## Key Principles

- **Lifecycle callbacks** for pure Python logic (startup tasks, command handlers, monitoring)
- **Event-based hooks** for deterministic shell commands (validation, formatting, logging)
- Always explain the matcher pattern and timeout
- Show working examples
- Reference Claude Code docs for parity when applicable
"""


def get_mcp_tool_definitions() -> List[Dict[str, Any]]:
    """
    Tool definitions for MCP clients.
    
    These tools enable the MCP-based assistant to help users create hooks.
    """
    return [
        {
            "name": "get_hook_info",
            "description": "Get detailed information about a specific hook",
            "input_schema": {
                "type": "object",
                "properties": {
                    "hook_name": {
                        "type": "string",
                        "description": "Name of the hook (e.g., 'startup', 'PreToolUse')",
                    }
                },
                "required": ["hook_name"],
            },
        },
        {
            "name": "list_hooks",
            "description": "List all available hooks in a category",
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["lifecycle", "event", "all"],
                        "description": "Hook category to list",
                    }
                },
                "required": ["category"],
            },
        },
        {
            "name": "generate_callback_plugin",
            "description": "Generate a lifecycle callback plugin template",
            "input_schema": {
                "type": "object",
                "properties": {
                    "hook_phase": {
                        "type": "string",
                        "description": "Phase name (startup, custom_command, etc.)",
                    },
                    "plugin_name": {
                        "type": "string",
                        "description": "Name of the plugin",
                    },
                    "description": {
                        "type": "string",
                        "description": "What the hook does",
                    },
                },
                "required": ["hook_phase", "plugin_name", "description"],
            },
        },
        {
            "name": "generate_event_hook",
            "description": "Generate an event-based hook script",
            "input_schema": {
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "description": "Event name (PreToolUse, PostToolUse, etc.)",
                    },
                    "matcher": {
                        "type": "string",
                        "description": "Matcher pattern",
                    },
                    "description": {
                        "type": "string",
                        "description": "What the hook does",
                    },
                    "language": {
                        "type": "string",
                        "enum": ["bash", "python"],
                        "description": "Script language",
                    },
                },
                "required": ["event", "matcher", "description"],
            },
        },
    ]


def get_mcp_context_prompt() -> str:
    """
    Context prompt showing the hook landscape.
    Use this to prime an MCP client with hook information.
    """
    
    callbacks_list = "\n".join(
        f"  - {h.name}: {h.description}" for h in LIFECYCLE_CALLBACKS
    )
    
    events_list = "\n".join(
        f"  - {h.name}: {h.description}" for h in EVENT_BASED_HOOKS
    )
    
    claude_list = "\n".join(f"  - {h}" for h in CLAUDE_CODE_REFERENCE_HOOKS)
    
    return f"""## Code Puppy Hook Landscape

### Available Lifecycle Callbacks
{callbacks_list}

### Available Event-Based Hooks
{events_list}

### Claude Code Hook Reference (for parity)
{claude_list}

## Decision Tree

Use this to recommend the right hook type:

**User wants to...**

1. Run code at startup/shutdown
   → Use: `startup` or `shutdown` lifecycle callback

2. Create a custom /command
   → Use: `custom_command` lifecycle callback

3. Monitor/log tool execution
   → Use: `pre_tool_call` or `post_tool_call` lifecycle callback

4. Validate/block tool calls
   → Use: `PreToolUse` event-based hook

5. Post-process after edits
   → Use: `PostToolUse` event-based hook with matcher

6. Reinject context after compaction
   → Use: `SessionStart` event-based hook

7. Verify task completion
   → Use: `Stop` event-based hook

## Code Puppy vs Claude Code

| Feature | Code Puppy | Claude Code |
|---------|-----------|------------|
| Lifecycle | Python callbacks | Plugins |
| Events | Shell scripts | JSON config |
| Matchers | Tool names | Multiple types |
| Deterministic | Yes, always runs | Yes, always runs |
| Async | Both sync & async | Event loop |

"""


if __name__ == "__main__":
    # Export for MCP usage
    print("=== Hook Knowledge Base ===")
    print(export_hook_knowledge_base())
    print("\n=== MCP System Prompt ===")
    print(get_mcp_system_prompt())
    print("\n=== MCP Tools ===")
    print(json.dumps(get_mcp_tool_definitions(), indent=2))
    print("\n=== MCP Context ===")
    print(get_mcp_context_prompt())
