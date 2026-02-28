"""
Hook Creator MCP Prompt

Simple MCP prompt that injects hook creation documentation/instructions
before user prompts for creating Code Puppy hooks.
"""

HOOK_CREATION_PROMPT = """
# Creating Hooks in Code Puppy

You are helping a user create hooks for Code Puppy. Code Puppy has two hook systems:

## System 1: Lifecycle Callbacks (Python)
Register Python functions that run at specific phases:
- `startup` - Application boot
- `shutdown` - Application exit
- `custom_command` - User types /slash command
- `pre_tool_call` - Before any tool executes
- `post_tool_call` - After a tool finishes
- `agent_run_start` - Agent run begins
- `agent_run_end` - Agent run completes
- `custom_command_help` - Build /help menu

Example lifecycle callback:
```python
from code_puppy.callbacks import register_callback

async def _on_startup():
    print("Started!")
    
register_callback("startup", _on_startup)
```

## System 2: Event-Based Hooks (Shell/JSON)
Configure shell commands responding to Code Puppy events in `.claude/settings.json`:
- `PreToolUse` - Before a tool executes (can block with exit code 2)
- `PostToolUse` - After a tool succeeds
- `SessionStart` - Session begins/resumes
- `Stop` - Claude finishes responding

Example event hook configuration:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash ./scripts/validate-command.sh"
          }
        ]
      }
    ]
  }
}
```

Example bash hook script:
```bash
#!/bin/bash
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

# Block dangerous commands
if echo "$COMMAND" | grep -q "drop table"; then
  echo "Blocked: SQL injection attempt" >&2
  exit 2
fi

exit 0
```

## Decision Tree
Use **lifecycle callbacks** for:
- Pure Python logic (initialization, cleanup, monitoring)
- Custom /commands
- Startup/shutdown tasks

Use **event-based hooks** for:
- Deterministic shell commands (validation, formatting)
- Blocking/allowing tool calls
- Pre/post-processing

When the user asks about creating a hook, ask them:
1. What should the hook do?
2. When should it run? (Which phase/event?)
3. Should it be Python or shell? (Lifecycle vs Event)
4. Then provide the exact code/config they need.
"""


def inject_hook_prompt(user_message: str) -> str:
    """
    Inject hook creation instructions before user message.
    Use this to add to the system prompt when handling hook creation requests.
    """
    return HOOK_CREATION_PROMPT + "\n\nUser question:\n" + user_message


if __name__ == "__main__":
    print(HOOK_CREATION_PROMPT)
