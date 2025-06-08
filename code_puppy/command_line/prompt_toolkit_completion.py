# ANSI color codes are no longer necessary because prompt_toolkit handles
# styling via the `Style` class. We keep them here commented-out in case
# someone needs raw ANSI later, but they are unused in the current code.
# RESET = '\033[0m'
# GREEN = '\033[1;32m'
# CYAN = '\033[1;36m'
# YELLOW = '\033[1;33m'
# BOLD = '\033[1m'
import asyncio
import os
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, merge_completers
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style

from code_puppy.command_line.file_path_completion import FilePathCompleter
from code_puppy.command_line.model_picker_completion import (
    ModelNameCompleter,
    get_active_model,
    update_model_in_input,
)
from code_puppy.command_line.utils import list_directory
from code_puppy.config import get_config_keys, get_puppy_name, get_value


class SetCompleter(Completer):
    def __init__(self, trigger: str = "~set"):
        self.trigger = trigger

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor
        stripped_text_for_trigger_check = text_before_cursor.lstrip()

        if not stripped_text_for_trigger_check.startswith(self.trigger):
            return

        # Determine the part of the text that is relevant for this completer
        # This handles cases like "  ~set foo" where the trigger isn't at the start of the string
        actual_trigger_pos = text_before_cursor.find(self.trigger)
        effective_input = text_before_cursor[
            actual_trigger_pos:
        ]  # e.g., "~set keypart" or "~set " or "~set"

        tokens = effective_input.split()

        # Case 1: Input is exactly the trigger (e.g., "~set") and nothing more (not even a trailing space on effective_input).
        # Suggest adding a space.
        if (
            len(tokens) == 1
            and tokens[0] == self.trigger
            and not effective_input.endswith(" ")
        ):
            yield Completion(
                text=self.trigger + " ",  # Text to insert
                start_position=-len(tokens[0]),  # Replace the trigger itself
                display=self.trigger + " ",  # Visual display
                display_meta="set config key",
            )
            return

        # Case 2: Input is trigger + space (e.g., "~set ") or trigger + partial key (e.g., "~set partial")
        base_to_complete = ""
        if len(tokens) > 1:  # e.g., ["~set", "partialkey"]
            base_to_complete = tokens[1]
        # If len(tokens) == 1, it implies effective_input was like "~set ", so base_to_complete remains ""
        # This means we list all keys.

        # --- SPECIAL HANDLING FOR 'model' KEY ---
        if base_to_complete == "model":
            # Don't return any completions -- let ModelNameCompleter handle it
            return
        for key in get_config_keys():
            if key == "model":
                continue  # exclude 'model' from regular ~set completions
            if key.startswith(base_to_complete):
                prev_value = get_value(key)
                value_part = f" = {prev_value}" if prev_value is not None else " = "
                completion_text = f"{key}{value_part}"

                yield Completion(
                    completion_text,
                    start_position=-len(
                        base_to_complete
                    ),  # Correctly replace only the typed part of the key
                    display_meta=f"puppy.cfg key (was: {prev_value})"
                    if prev_value is not None
                    else "puppy.cfg key",
                )


class CDCompleter(Completer):
    def __init__(self, trigger: str = "~cd"):
        self.trigger = trigger

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.strip().startswith(self.trigger):
            return
        tokens = text.strip().split()
        if len(tokens) == 1:
            base = ""
        else:
            base = tokens[1]
        try:
            prefix = os.path.expanduser(base)
            part = os.path.dirname(prefix) if os.path.dirname(prefix) else "."
            dirs, _ = list_directory(part)
            dirnames = [d for d in dirs if d.startswith(os.path.basename(base))]
            base_dir = os.path.dirname(base)
            for d in dirnames:
                # Build the completion text so we keep the already-typed directory parts.
                if base_dir and base_dir != ".":
                    suggestion = os.path.join(base_dir, d)
                else:
                    suggestion = d
                # Append trailing slash so the user can continue tabbing into sub-dirs.
                suggestion = suggestion.rstrip(os.sep) + os.sep
                yield Completion(
                    suggestion,
                    start_position=-len(base),
                    display=d + os.sep,
                    display_meta="Directory",
                )
        except Exception:
            # Silently ignore errors (e.g., permission issues, non-existent dir)
            pass


def get_prompt_with_active_model(base: str = ">>> "):
    puppy = get_puppy_name()
    model = get_active_model() or "(default)"
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd_display = "~" + cwd[len(home) :]
    else:
        cwd_display = cwd
    return FormattedText(
        [
            ("bold", "🐶 "),
            ("class:puppy", f"{puppy}"),
            ("", " "),
            ("class:model", "[" + str(model) + "] "),
            ("class:cwd", "(" + str(cwd_display) + ") "),
            ("class:arrow", str(base)),
        ]
    )


async def get_input_with_combined_completion(
    prompt_str=">>> ", history_file: Optional[str] = None
) -> str:
    history = FileHistory(history_file) if history_file else None
    completer = merge_completers(
        [
            FilePathCompleter(symbol="@"),
            ModelNameCompleter(trigger="~m"),
            CDCompleter(trigger="~cd"),
            SetCompleter(trigger="~set"),
        ]
    )
    # Add custom key bindings for Alt+M to insert a new line without submitting
    bindings = KeyBindings()

    @bindings.add(Keys.Escape, "m")  # Alt+M
    def _(event):
        event.app.current_buffer.insert_text("\n")

    @bindings.add(Keys.Escape)
    def _(event):
        """Cancel the current prompt when the user presses the ESC key alone."""
        event.app.exit(exception=KeyboardInterrupt)

    session = PromptSession(
        completer=completer,
        history=history,
        complete_while_typing=True,
        key_bindings=bindings,
    )
    # If they pass a string, backward-compat: convert it to formatted_text
    if isinstance(prompt_str, str):
        from prompt_toolkit.formatted_text import FormattedText

        prompt_str = FormattedText([(None, prompt_str)])
    style = Style.from_dict(
        {
            # Keys must AVOID the 'class:' prefix – that prefix is used only when
            # tagging tokens in `FormattedText`. See prompt_toolkit docs.
            "puppy": "bold magenta",
            "owner": "bold white",
            "model": "bold cyan",
            "cwd": "bold green",
            "arrow": "bold yellow",
        }
    )
    text = await session.prompt_async(prompt_str, style=style)
    possibly_stripped = update_model_in_input(text)
    if possibly_stripped is not None:
        return possibly_stripped
    return text


if __name__ == "__main__":
    print("Type '@' for path-completion or '~m' to pick a model. Ctrl+D to exit.")

    async def main():
        while True:
            try:
                inp = await get_input_with_combined_completion(
                    get_prompt_with_active_model(),
                    history_file="~/.path_completion_history.txt",
                )
                print(f"You entered: {inp}")
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
        print("\nGoodbye!")

    asyncio.run(main())
