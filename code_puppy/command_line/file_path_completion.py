import glob
import os
from typing import Iterable

from prompt_toolkit.completion import Completer, Completion
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
        text_before_cursor = text[:cursor_position]
        if self.symbol not in text_before_cursor:
            return
        symbol_pos = text_before_cursor.rfind(self.symbol)
        text_after_symbol = text_before_cursor[symbol_pos + len(self.symbol) :]
        start_position = -(len(text_after_symbol))
        try:
            pattern = text_after_symbol + "*"
            if not pattern.strip("*") or pattern.strip("*").endswith("/"):
                base_path = pattern.strip("*")
                if not base_path:
                    base_path = "."
                if base_path.startswith("~"):
                    base_path = os.path.expanduser(base_path)
                if os.path.isdir(base_path):
                    paths = [
                        os.path.join(base_path, f)
                        for f in os.listdir(base_path)
                        if not f.startswith(".") or text_after_symbol.endswith(".")
                    ]
                else:
                    paths = []
            else:
                paths = glob.glob(pattern)
                if not pattern.startswith(".") and not pattern.startswith("*/."):
                    paths = [
                        p for p in paths if not os.path.basename(p).startswith(".")
                    ]
            paths.sort()
            for path in paths:
                is_dir = os.path.isdir(path)
                display = os.path.basename(path)
                if os.path.isabs(path):
                    display_path = path
                else:
                    if text_after_symbol.startswith("/"):
                        display_path = os.path.abspath(path)
                    elif text_after_symbol.startswith("~"):
                        home = os.path.expanduser("~")
                        if path.startswith(home):
                            display_path = "~" + path[len(home) :]
                        else:
                            display_path = path
                    else:
                        display_path = path
                display_meta = "Directory" if is_dir else "File"
                yield Completion(
                    display_path,
                    start_position=start_position,
                    display=display,
                    display_meta=display_meta,
                )
        except (PermissionError, FileNotFoundError, OSError):
            pass
