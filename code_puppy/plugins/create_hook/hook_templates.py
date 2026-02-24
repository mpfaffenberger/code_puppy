"""
Hook template generation for Code Puppy.

Generates boilerplate code for:
- Lifecycle callback plugins
- Event-based hook scripts
- Configuration files
"""

from typing import Optional
import textwrap


def generate_lifecycle_callback_plugin(
    hook_phase: str,
    hook_name: str,
    description: str,
    is_async: bool = True,
) -> str:
    """
    Generate a lifecycle callback plugin.
    
    Args:
        hook_phase: Phase name (startup, custom_command, etc.)
        hook_name: Descriptive name for the hook (e.g., "my_feature")
        description: What the hook does
        is_async: Whether to use async
    
    Returns:
        Complete plugin register_callbacks.py content
    """
    
    async_marker = "async " if is_async else ""
    await_marker = "await " if is_async else ""
    
    if hook_phase == "custom_command":
        return textwrap.dedent(f"""\
            from code_puppy.callbacks import register_callback
            from code_puppy.messaging import emit_info, emit_success, emit_error
            
            
            def _custom_help():
                \"\"\"Help entries for custom commands.\"\"\"
                return [
                    ("{hook_name}", "{description}"),
                ]
            
            
            def _handle_custom_command(command: str, name: str):
                \"\"\"Handle custom /{hook_name} command.
                
                Return values:
                - None: not handled, try next plugin
                - True: handled, no model invocation
                - str: handled, send string to model
                \"\"\"
                if name != "{hook_name}":
                    return None
                
                # Parse arguments if any
                parts = command.split(maxsplit=1)
                args = parts[1] if len(parts) > 1 else ""
                
                # TODO: Implement your command logic here
                emit_success("/{hook_name} command executed!")
                return True
            
            
            register_callback("custom_command_help", _custom_help)
            register_callback("custom_command", _handle_custom_command)
            """)
    
    elif hook_phase in ("pre_tool_call", "post_tool_call"):
        return textwrap.dedent(f"""\
            from code_puppy.callbacks import register_callback
            import logging
            
            logger = logging.getLogger(__name__)
            
            
            {async_marker}def _on_{hook_phase}(tool_name, tool_args, context=None):
                \"\"\"{description}\"\"\"
                logger.debug(f"Tool: {{tool_name}}")
                
                # TODO: Implement your logic here
                pass
            
            
            register_callback("{hook_phase}", _on_{hook_phase})
            """)
    
    else:
        return textwrap.dedent(f"""\
            from code_puppy.callbacks import register_callback
            
            
            {async_marker}def _on_{hook_phase}(*args, **kwargs):
                \"\"\"{description}\"\"\"
                # TODO: Implement your logic here
                pass
            
            
            register_callback("{hook_phase}", _on_{hook_phase})
            """)


def generate_event_hook_command(
    event: str,
    matcher: str,
    description: str,
    language: str = "bash",
) -> str:
    """
    Generate an event-based hook script.
    
    Args:
        event: Event name (PreToolUse, PostToolUse, etc.)
        matcher: Matcher pattern (tool names, etc.)
        description: What the hook does
        language: bash or python
    
    Returns:
        Script content
    """
    
    if language == "bash":
        if event == "PreToolUse":
            return textwrap.dedent(f"""\
                #!/bin/bash
                # {description}
                # Event: {event}
                # Matcher: {matcher}
                
                set -euo pipefail
                
                INPUT=$(cat)
                
                TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name')
                TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input')
                
                # TODO: Implement your validation/blocking logic
                # Examples:
                # - Check tool_name and tool_input
                # - Block with: echo "Reason" >&2 && exit 2
                # - Allow with: exit 0
                
                exit 0
                """)
        
        elif event == "PostToolUse":
            return textwrap.dedent(f"""\
                #!/bin/bash
                # {description}
                # Event: {event}
                # Matcher: {matcher}
                
                set -euo pipefail
                
                INPUT=$(cat)
                
                TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name')
                TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input')
                
                # TODO: Implement your post-processing logic
                # Examples:
                # - Extract file paths and format them
                # - Log tool execution
                # - Trigger side effects
                
                exit 0
                """)
        
        elif event == "SessionStart":
            return textwrap.dedent(f"""\
                #!/bin/bash
                # {description}
                # Event: {event}
                # Matcher: {matcher}
                
                set -euo pipefail
                
                INPUT=$(cat)
                SOURCE=$(echo "$INPUT" | jq -r '.source')
                
                # Output to stdout is added to Claude's context
                echo "Session started with source: $SOURCE"
                
                # TODO: Inject context based on matcher
                # Examples:
                # - matcher "compact": re-inject critical context after compaction
                # - matcher "startup": initial session setup
                
                exit 0
                """)
        
        else:
            return textwrap.dedent(f"""\
                #!/bin/bash
                # {description}
                # Event: {event}
                # Matcher: {matcher}
                
                set -euo pipefail
                
                INPUT=$(cat)
                
                # TODO: Implement your hook logic
                # Check the event schema in .claude/hooks documentation
                
                exit 0
                """)
    
    elif language == "python":
        return textwrap.dedent(f"""\
            #!/usr/bin/env python3
            \"\"\"
            {description}
            Event: {event}
            Matcher: {matcher}
            \"\"\"
            
            import sys
            import json
            
            def main():
                # Read hook input from stdin
                hook_input = json.load(sys.stdin)
                
                tool_name = hook_input.get('tool_name')
                tool_input = hook_input.get('tool_input', {{}})
                
                # TODO: Implement your hook logic
                
                # Exit codes:
                # 0 = success/allow
                # 2 = block (for PreToolUse)
                
                sys.exit(0)
            
            
            if __name__ == "__main__":
                main()
            """)


def generate_hook_config(
    event: str,
    matcher: str,
    hook_type: str = "command",
    command_or_prompt: str = "",
    timeout: int = 5000,
) -> str:
    """
    Generate JSON hook configuration for .claude/settings.json.
    
    Args:
        event: Event name
        matcher: Matcher pattern
        hook_type: "command" or "prompt"
        command_or_prompt: Command string or prompt text
        timeout: Timeout in milliseconds
    
    Returns:
        JSON snippet
    """
    
    import json
    
    hook_config = {
        "hooks": {
            event: [
                {
                    "matcher": matcher,
                    "hooks": [
                        {
                            "type": hook_type,
                            "command" if hook_type == "command" else "prompt": command_or_prompt,
                            "timeout": timeout,
                            "enabled": True,
                        }
                    ],
                }
            ]
        }
    }
    
    return json.dumps(hook_config, indent=2)


def generate_plugin_structure(plugin_name: str, hook_phase: str) -> dict:
    """
    Generate complete plugin directory structure.
    
    Returns:
        Dict of {filepath: content}
    """
    
    return {
        "__init__.py": "# Code Puppy Plugin\n",
        "register_callbacks.py": generate_lifecycle_callback_plugin(
            hook_phase=hook_phase,
            hook_name=plugin_name,
            description=f"Plugin for {hook_phase} hook",
        ),
        "tests/__init__.py": "",
        f"tests/test_{plugin_name}.py": textwrap.dedent(f"""\
            \"\"\"Tests for {plugin_name} plugin.\"\"\"
            
            def test_plugin_loads():
                \"\"\"Verify plugin can be imported.\"\"\"
                from code_puppy.plugins.{plugin_name}.register_callbacks import (
                    _handle_custom_command,
                )
                assert callable(_handle_custom_command)
            """),
    }
