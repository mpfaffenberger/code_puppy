from pathlib import Path

from prompt_toolkit.completion import Completer, Completion

from code_puppy.config import CONFIG_DIR


class LoadContextCompleter(Completer):
    def __init__(self, trigger: str = "/load_context"):
        self.trigger = trigger

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor
        stripped_text_for_trigger_check = text_before_cursor.lstrip()

        if not stripped_text_for_trigger_check.startswith(self.trigger):
            return

        # Determine the part of the text that is relevant for this completer
        actual_trigger_pos = text_before_cursor.find(self.trigger)
        effective_input = text_before_cursor[actual_trigger_pos:]

        tokens = effective_input.split()

        # Case 1: Input is exactly the trigger (e.g., "/load_context") and nothing more
        if (
            len(tokens) == 1
            and tokens[0] == self.trigger
            and not effective_input.endswith(" ")
        ):
            yield Completion(
                text=self.trigger + " ",
                start_position=-len(tokens[0]),
                display=self.trigger + " ",
                display_meta="load saved context",
            )
            return

        # Case 2: Input is trigger + space or trigger + partial session name
        session_filter = ""
        if len(tokens) > 1:  # e.g., ["/load_context", "partial"]
            session_filter = tokens[1]

        # Get available context files
        try:
            contexts_dir = Path(CONFIG_DIR) / "contexts"
            if contexts_dir.exists():
                for pkl_file in contexts_dir.glob("*.pkl"):
                    session_name = pkl_file.stem  # removes .pkl extension
                    if session_name.startswith(session_filter):
                        yield Completion(
                            session_name,
                            start_position=-len(session_filter),
                            display=session_name,
                            display_meta="saved context session",
                        )
        except Exception:
            # Silently ignore errors (e.g., permission issues, non-existent dir)
            pass
