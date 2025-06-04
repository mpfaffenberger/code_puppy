import asyncio
from typing import Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import merge_completers
from prompt_toolkit.history import FileHistory

from code_puppy.command_line.model_picker_completion import (
    ModelNameCompleter,
    get_active_model,
    update_model_in_input,
)
from code_puppy.command_line.file_path_completion import FilePathCompleter

def get_prompt_with_active_model(base: str = ">>> ") -> str:
    model = get_active_model() or "(default)"
    return f"🐶[{model}] {base}"

async def get_input_with_combined_completion(prompt_str: str = ">>> ", history_file: Optional[str] = None) -> str:
    history = FileHistory(history_file) if history_file else None
    completer = merge_completers([
        FilePathCompleter(symbol="@"),
        ModelNameCompleter(trigger="~m")
    ])
    session = PromptSession(
        completer=completer,
        history=history,
        complete_while_typing=True
    )
    text = await session.prompt_async(prompt_str)
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
                    history_file="~/.path_completion_history.txt"
                )
                print(f"You entered: {inp}")
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
        print("\nGoodbye!")
    asyncio.run(main())
