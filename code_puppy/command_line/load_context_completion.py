from pathlib import Path

from prompt_toolkit.completion import Completer, Completion

from code_puppy.config import CONFIG_DIR


class LoadContextCompleter(Completer):
    def __init__(self, trigger: str = "/load_context"):
        self.trigger = trigger

    def get_completions(self, document, complete_event):
        cursor_position = document.cursor_position
        text_before_cursor = document.text_before_cursor
        stripped_text_for_trigger_check = text_before_cursor.lstrip()

        # If user types just /load_context (no space), suggest adding a space
        if stripped_text_for_trigger_check == self.trigger:
            yield Completion(
                self.trigger + " ",
                start_position=-len(self.trigger),
                display=self.trigger + " ",
                display_meta="load saved context",
            )
            return

        # Require a space after /load_context before showing completions (consistency with other completers)
        if not stripped_text_for_trigger_check.startswith(self.trigger + " "):
            return

        # Extract the session name after /load_context and space (up to cursor)
        actual_trigger_pos = text_before_cursor.find(self.trigger)
        trigger_end = actual_trigger_pos + len(self.trigger) + 1  # +1 for the space
        session_filter = text_before_cursor[trigger_end:cursor_position].lstrip()
        start_position = -(len(session_filter))

        # Get available context files
        try:
            contexts_dir = Path(CONFIG_DIR) / "contexts"
            if contexts_dir.exists():
                for pkl_file in contexts_dir.glob("*.pkl"):
                    session_name = pkl_file.stem  # removes .pkl extension
                    if session_name.startswith(session_filter):
                        yield Completion(
                            session_name,
                            start_position=start_position,
                            display=session_name,
                            display_meta="saved context session",
                        )
        except Exception:
            # Silently ignore errors (e.g., permission issues, non-existent dir)
            pass
