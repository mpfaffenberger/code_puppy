# `~show` Command — Code Puppy Dev Console

This doc describes exactly what appears when you run the `~show` console meta-command. This helps with debugging, development, and UI validation.

## What `~show` Prints

The `~show` meta-command displays the following puppy status variables to your console (with colors/formatting via `rich`):

| Field         | Description                                       | Source Location                                         |
| ------------- | ------------------------------------------------- | ------------------------------------------------------- |
| puppy_name    | The current puppy's name                          | code_puppy/config.py:get_puppy_name()                   |
| owner_name    | The current owner/master name                     | code_puppy/config.py:get_owner_name()                   |
| model         | The active LLM code-generation model              | code_puppy/command_line/model_picker_completion.py:get_active_model() |
| YOLO_MODE     | Whether YOLO_MODE / yolo_mode is enabled          | code_puppy/config.py:get_yolo_mode()                    |

## Example Output

```
🐶 Puppy Status
 
puppy_name:     Snoopy
owner_name:     TheMaster
model:          gpt-4.1
YOLO_MODE:      ON
```
The YOLO_MODE field shows `[red]ON[/red]` (bold, red) if active, or `[yellow]off[/yellow]` if it's not enabled.

## Data Flow
- All fields are fetched at runtime when you execute `~show`.
- puppy_name and owner_name fall back to defaults if not explictly set ("Puppy", "Master").
- YOLO_MODE checks the following for value:
  - The environment variable `YOLO_MODE` (if set, this takes precedence; for TRUE, use: `1`, `true`, `yes`, `on` — all case-insensitive)
  - The `[puppy]` section in `puppy.cfg` under key `yolo_mode` (case-insensitive for value, NOT for key)
  - If neither are set, defaults to OFF (False).

## See Also
- [`code_puppy/command_line/meta_command_handler.py`](code_puppy/command_line/meta_command_handler.py)
- [`code_puppy/config.py`](code_puppy/config.py)
