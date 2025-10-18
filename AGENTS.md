# Code Puppy

Code Puppy is a code gen agent!

## Code Style

- Clean
- Concise
- Follow yagni, srp, dry, etc
- Don't write files longer than 600 lines
- type hints on everything

## Testing

- `uv run pytest`

## Namespaces Packages

code_puppy
    - agent.py - declares code generation agent
    - agent_prompts.py - declares prompt for agent
    - config.py - global config manager
    - main.py - CLI loop
    - message_history_processor.py - message history trimming, summarization logic
    - __init__.py - package version detection and exposure
    - model_factory.py - constructs models from configuration mapping
    - models.json - available models and metadata registry
    - state_management.py - global message history state helpers
    - summarization_agent.py - specialized agent for history summarization
    - version_checker.py - fetches latest PyPI package version

code_puppy.tools
    - __init__.py - registers all available tool modules
    - common.py - shared console and ignore helpers
    - command_runner.py - shell command execution with confirmations
    - file_modifications.py - robust file editing with diffs
    - file_operations.py - list read grep filesystem files

code_puppy.command_line
    - __init__.py - marks command line subpackage init
    - file_path_completion.py - path completion with @ trigger
    - meta_command_handler.py - handles meta commands and configuration
    - model_picker_completion.py - model selection completion and setters
    - motd.py - message of the day tracking
    - prompt_toolkit_completion.py - interactive prompt with combined completers
    - utils.py - directory listing and table utilities

## Git Workflow

- ALWAYS run `pnpm check` before committing
- Fix linting errors with `ruff check --fix`
- Run `ruff format .` to auto format
- NEVER use `git push --force` on the main branch

## `bd` Issue Tracker Tips

- Initialize locally with `bd init` if missing.
- Create issues fast: `bd create 'Title' --type task --priority 2 --description '...' --acceptance '...'`.
- Update acceptance criteria: `bd update bd-123 --acceptance-criteria 'Given ...'`.
- Append notes to capture decisions: `bd update bd-123 --notes 'context here'`.
- List the backlog: `bd list`.
- Show a single issue: `bd show bd-123`.
- Keep commands under 60s; long multi-line acceptance text can time out—compact it or rerun with shorter strings.
- Remember: `bd update` does *not* change descriptions directly; use notes/design fields when you need to tweak narrative details.
