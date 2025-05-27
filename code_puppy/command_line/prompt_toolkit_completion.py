import os
import glob
from typing import Optional, Iterable
import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.document import Document


class FilePathCompleter(Completer):
    """A simple file path completer that works with a trigger symbol."""

    def __init__(self, symbol: str = "@"):
        self.symbol = symbol

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text
        cursor_position = document.cursor_position

        # Check if our symbol is in the text before the cursor
        text_before_cursor = text[:cursor_position]
        if self.symbol not in text_before_cursor:
            return  # Symbol not found, no completions

        # Find the position of the last occurrence of the symbol before cursor
        symbol_pos = text_before_cursor.rfind(self.symbol)

        # Get the text after the symbol up to the cursor
        text_after_symbol = text_before_cursor[symbol_pos + len(self.symbol) :]

        # Calculate start position - entire path will be replaced
        start_position = -(len(text_after_symbol))

        # Get matching files using glob pattern
        try:
            pattern = text_after_symbol + "*"

            # For empty pattern or pattern ending with /, list current directory
            if not pattern.strip("*") or pattern.strip("*").endswith("/"):
                base_path = pattern.strip("*")
                if not base_path:  # If empty, use current directory
                    base_path = "."

                # Make sure we have an absolute path or handle ~ expansion
                if base_path.startswith("~"):
                    base_path = os.path.expanduser(base_path)

                # List all files in the directory
                if os.path.isdir(base_path):
                    paths = [
                        os.path.join(base_path, f)
                        for f in os.listdir(base_path)
                        if not f.startswith(".") or text_after_symbol.endswith(".")
                    ]
                else:
                    paths = []
            else:
                # For partial filename, use glob directly
                paths = glob.glob(pattern)

                # Filter out hidden files unless explicitly requested
                if not pattern.startswith(".") and not pattern.startswith("*/."):
                    paths = [
                        p for p in paths if not os.path.basename(p).startswith(".")
                    ]

            # Sort for consistent display
            paths.sort()

            for path in paths:
                is_dir = os.path.isdir(path)
                display = os.path.basename(path)

                # Determine display path (what gets inserted)
                if os.path.isabs(path):
                    # Already absolute path
                    display_path = path
                else:
                    # Convert to relative or absolute based on input
                    if text_after_symbol.startswith("/"):
                        # User wants absolute path
                        display_path = os.path.abspath(path)
                    elif text_after_symbol.startswith("~"):
                        # User wants home-relative path
                        home = os.path.expanduser("~")
                        if path.startswith(home):
                            display_path = "~" + path[len(home) :]
                        else:
                            display_path = path
                    else:
                        # Keep it as is (relative to current directory)
                        display_path = path

                display_meta = "Directory" if is_dir else "File"

                yield Completion(
                    display_path,
                    start_position=start_position,
                    display=display,
                    display_meta=display_meta,
                )
        except (PermissionError, FileNotFoundError, OSError):
            # Handle access errors gracefully
            pass


async def get_input_with_path_completion(
    prompt_str: str = ">>> ", symbol: str = "@", history_file: Optional[str] = None
) -> str:
    """
    Get user input with path completion support.

    Args:
        prompt_str: The prompt string to display
        symbol: The symbol that triggers path completion
        history_file: Path to the history file

    Returns:
        The user input string
    """
    # Create history instance if a history file is provided
    history = FileHistory(os.path.expanduser(history_file)) if history_file else None

    # Create a session with our custom completer
    session = PromptSession(
        completer=FilePathCompleter(symbol), history=history, complete_while_typing=True
    )

    # Get input with completion - using async prompt to work with existing event loop
    return await session.prompt_async(prompt_str)


# Example usage
if __name__ == "__main__":
    print(
        "Type '@' followed by a path to see completion in action. Press Ctrl+D to exit."
    )

    async def main():
        while True:
            try:
                user_input = await get_input_with_path_completion(
                    ">>> ", history_file="~/.path_completion_history.txt"
                )
                print(f"You entered: {user_input}")
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
        print("\nGoodbye!")

    asyncio.run(main())
