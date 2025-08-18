# Code Puppy Developer Console Commands

Woof! Here’s the scoop on built-in dev-console `~` meta-commands and exactly how you can add your own. This is for the secret society of code hackers (that’s you now).

## Available Console Commands

| Command             | Description                                              |
|---------------------|----------------------------------------------------------|
| `~cd [dir]`         | Show directory listing or change working directory       |
| `~show`             | Show puppy/owner/model status and metadata              |
| `~m <model>`        | Switch the active code model for the agent              |
| `~set KEY=VALUE`      | Set a puppy.cfg setting!                                 |
| `~help` or `~h`     | Show available meta-commands                            |
| any unknown `~...`  | Warn user about unknown command and (for plain `~`)     |
|                     | shows current model                                     |

## How to Add a New Meta-Command

All `~meta` commands are handled in **`code_puppy/command_line/meta_command_handler.py`** inside the `handle_meta_command` function. Follow these steps:

### 1. Edit the Command Handler
- Open `code_puppy/command_line/meta_command_handler.py`.
- Locate the `handle_meta_command(command: str, console: Console) -> bool` function.
- Add a new `if command.startswith("~yourcmd"):` block (do this _above_ the "unknown command" fallback).
    - Use .startswith for prefix commands (e.g., `~foo bar`), or full equality if you want only the bare command to match.
    - Implement your logic. Use rich’s Console to print stuff back to the terminal.
    - Return `True` if you handle the command.

### 2. (Optional) Add Autocomplete

### ~set: Update your code puppy’s settings

`~set` lets you instantly update values in your puppy.cfg, like toggling YOLO_MODE or renaming your puppy on the fly!

- Usage:
  - `~set YOLO_MODE=true`
  - `~set puppy_name Snoopy`
  - `~set owner_name="Best Owner"`

As you type `~set`, tab completion pops up with available config keys so you don’t have to remember them like a boring human.

If your new command needs tab completion/prompt support, check these files:
- `code_puppy/command_line/prompt_toolkit_completion.py` (has completer logic)
- `code_puppy/command_line/model_picker_completion.py`, `file_path_completion.py` (for model/filename completions)

Update them if your command would benefit from better input support. Usually you just need meta_command_handler.py, though!

### 3. (Optional) Update Help
- Update the help text inside the `~help` handler to list your new command and a short description.

### 4. (Optional) Add Utilities
Place any helper logic for your command in an appropriate utils or tools module if it grows big. Don’t go dumping everything in meta_command_handler.py, or the puppy will fetch your slippers in protest!


---

Be concise, be fun, don’t make your files long, and remember: if you find yourself writing more than a quick conditional in meta_command_handler.py, break that logic out into another module! Woof woof!
