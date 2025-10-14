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
from prompt_toolkit.filters import is_searching
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.processors import Processor, Transformation
from prompt_toolkit.styles import Style

from code_puppy.command_line.attachments import (
    DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS,
    DEFAULT_ACCEPTED_IMAGE_EXTENSIONS,
    _detect_path_tokens,
    _tokenise,
)
from code_puppy.command_line.file_path_completion import FilePathCompleter
from code_puppy.command_line.load_context_completion import LoadContextCompleter
from code_puppy.command_line.model_picker_completion import (
    ModelNameCompleter,
    get_active_model,
    update_model_in_input,
)
from code_puppy.command_line.utils import list_directory
from code_puppy.config import (
    COMMAND_HISTORY_FILE,
    get_config_keys,
    get_puppy_name,
    get_value,
)


class SetCompleter(Completer):
    def __init__(self, trigger: str = "/set"):
        self.trigger = trigger

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor
        stripped_text_for_trigger_check = text_before_cursor.lstrip()

        if not stripped_text_for_trigger_check.startswith(self.trigger):
            return

        # Determine the part of the text that is relevant for this completer
        # This handles cases like "  /set foo" where the trigger isn't at the start of the string
        actual_trigger_pos = text_before_cursor.find(self.trigger)
        effective_input = text_before_cursor[
            actual_trigger_pos:
        ]  # e.g., "/set keypart" or "/set "

        tokens = effective_input.split()

        # Case 1: Input is exactly the trigger (e.g., "/set") and nothing more (not even a trailing space on effective_input).
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

        # Case 2: Input is trigger + space (e.g., "/set ") or trigger + partial key (e.g., "/set partial")
        base_to_complete = ""
        if len(tokens) > 1:  # e.g., ["/set", "partialkey"]
            base_to_complete = tokens[1]
        # If len(tokens) == 1, it implies effective_input was like "/set ", so base_to_complete remains ""
        # This means we list all keys.

        # --- SPECIAL HANDLING FOR 'model' KEY ---
        if base_to_complete == "model":
            # Don't return any completions -- let ModelNameCompleter handle it
            return
        for key in get_config_keys():
            if key == "model" or key == "puppy_token":
                continue  # exclude 'model' and 'puppy_token' from regular /set completions
            if key.startswith(base_to_complete):
                prev_value = get_value(key)
                value_part = f" = {prev_value}" if prev_value is not None else " = "
                completion_text = f"{key}{value_part}"

                yield Completion(
                    completion_text,
                    start_position=-len(
                        base_to_complete
                    ),  # Correctly replace only the typed part of the key
                    display_meta="",
                )


class AttachmentPlaceholderProcessor(Processor):
    """Display friendly placeholders for recognised attachments."""

    _PLACEHOLDER_STYLE = "class:attachment-placeholder"
    # Skip expensive path detection for very long input (likely pasted content)
    _MAX_TEXT_LENGTH_FOR_REALTIME = 500

    def apply_transformation(self, transformation_input):
        document = transformation_input.document
        text = document.text
        if not text:
            return Transformation(list(transformation_input.fragments))

        # Skip real-time path detection for long text to avoid slowdown
        if len(text) > self._MAX_TEXT_LENGTH_FOR_REALTIME:
            return Transformation(list(transformation_input.fragments))

        detections, _warnings = _detect_path_tokens(text)
        replacements: list[tuple[int, int, str]] = []
        search_cursor = 0
        ESCAPE_MARKER = "\u0000ESCAPED_SPACE\u0000"
        masked_text = text.replace(r"\ ", ESCAPE_MARKER)
        token_view = list(_tokenise(masked_text))
        for detection in detections:
            display_text: str | None = None
            if detection.path and detection.has_path():
                suffix = detection.path.suffix.lower()
                if suffix in DEFAULT_ACCEPTED_IMAGE_EXTENSIONS:
                    display_text = f"[{suffix.lstrip('.') or 'image'} image]"
                elif suffix in DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS:
                    display_text = f"[{suffix.lstrip('.') or 'file'} document]"
                else:
                    display_text = "[file attachment]"
            elif detection.link is not None:
                display_text = "[link]"

            if not display_text:
                continue

            # Use token-span for robust lookup (handles escaped spaces)
            span_tokens = token_view[detection.start_index : detection.consumed_until]
            raw_span = " ".join(span_tokens).replace(ESCAPE_MARKER, r"\ ")
            index = text.find(raw_span, search_cursor)
            span_len = len(raw_span)
            if index == -1:
                # Fallback to placeholder string
                placeholder = detection.placeholder
                index = text.find(placeholder, search_cursor)
                span_len = len(placeholder)
            if index == -1:
                continue
            replacements.append((index, index + span_len, display_text))
            search_cursor = index + span_len

        if not replacements:
            return Transformation(list(transformation_input.fragments))

        replacements.sort(key=lambda item: item[0])

        new_fragments: list[tuple[str, str]] = []
        source_to_display_map: list[int] = []
        display_to_source_map: list[int] = []

        source_index = 0
        display_index = 0

        def append_plain_segment(segment: str) -> None:
            nonlocal source_index, display_index
            if not segment:
                return
            new_fragments.append(("", segment))
            for _ in segment:
                source_to_display_map.append(display_index)
                display_to_source_map.append(source_index)
                source_index += 1
                display_index += 1

        for start, end, replacement_text in replacements:
            if start > source_index:
                append_plain_segment(text[source_index:start])

            placeholder = replacement_text or ""
            placeholder_start = display_index
            if placeholder:
                new_fragments.append((self._PLACEHOLDER_STYLE, placeholder))
                for _ in placeholder:
                    display_to_source_map.append(start)
                    display_index += 1

            for _ in text[source_index:end]:
                source_to_display_map.append(
                    placeholder_start if placeholder else display_index
                )
                source_index += 1

        if source_index < len(text):
            append_plain_segment(text[source_index:])

        def source_to_display(pos: int) -> int:
            if pos < 0:
                return 0
            if pos < len(source_to_display_map):
                return source_to_display_map[pos]
            return display_index

        def display_to_source(pos: int) -> int:
            if pos < 0:
                return 0
            if pos < len(display_to_source_map):
                return display_to_source_map[pos]
            return len(source_to_display_map)

        return Transformation(
            new_fragments,
            source_to_display=source_to_display,
            display_to_source=display_to_source,
        )


class CDCompleter(Completer):
    def __init__(self, trigger: str = "/cd"):
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
    from code_puppy.agents.agent_manager import get_current_agent

    puppy = get_puppy_name()
    global_model = get_active_model() or "(default)"

    # Get current agent information
    current_agent = get_current_agent()
    agent_display = current_agent.display_name if current_agent else "code-puppy"

    # Check if current agent has a pinned model
    agent_model = None
    if current_agent and hasattr(current_agent, "get_model_name"):
        agent_model = current_agent.get_model_name()

    # Determine which model to display
    if agent_model and agent_model != global_model:
        # Show both models when they differ
        model_display = f"[{global_model} → {agent_model}]"
    elif agent_model:
        # Show only the agent model when pinned
        model_display = f"[{agent_model}]"
    else:
        # Show only the global model when no agent model is pinned
        model_display = f"[{global_model}]"

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
            ("class:agent", f"[{agent_display}] "),
            ("class:model", model_display + " "),
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
            ModelNameCompleter(trigger="/model"),
            CDCompleter(trigger="/cd"),
            SetCompleter(trigger="/set"),
            LoadContextCompleter(trigger="/load_context"),
        ]
    )
    # Add custom key bindings and multiline toggle
    bindings = KeyBindings()

    # Multiline mode state
    multiline = {"enabled": False}

    # Toggle multiline with Alt+M
    @bindings.add(Keys.Escape, "m")
    def _(event):
        multiline["enabled"] = not multiline["enabled"]
        status = "ON" if multiline["enabled"] else "OFF"
        # Print status for user feedback (version-agnostic)
        print(f"[multiline] {status}", flush=True)

    # Also toggle multiline with F2 (more reliable across platforms)
    @bindings.add("f2")
    def _(event):
        multiline["enabled"] = not multiline["enabled"]
        status = "ON" if multiline["enabled"] else "OFF"
        print(f"[multiline] {status}", flush=True)

    # Newline insert bindings — robust and explicit
    # Ctrl+J (line feed) works in virtually all terminals; mark eager so it wins
    @bindings.add("c-j", eager=True)
    def _(event):
        event.app.current_buffer.insert_text("\n")

    # Also allow Ctrl+Enter for newline (terminal-dependent)
    try:

        @bindings.add("c-enter", eager=True)
        def _(event):
            event.app.current_buffer.insert_text("\n")
    except Exception:
        pass

    # Enter behavior depends on multiline mode
    @bindings.add("enter", filter=~is_searching, eager=True)
    def _(event):
        if multiline["enabled"]:
            event.app.current_buffer.insert_text("\n")
        else:
            event.current_buffer.validate_and_handle()

    @bindings.add(Keys.Escape)
    def _(event):
        """Cancel the current prompt when the user presses the ESC key alone."""
        event.app.exit(exception=KeyboardInterrupt)

    session = PromptSession(
        completer=completer,
        history=history,
        complete_while_typing=True,
        key_bindings=bindings,
        input_processors=[AttachmentPlaceholderProcessor()],
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
            "agent": "bold blue",
            "model": "bold cyan",
            "cwd": "bold green",
            "arrow": "bold yellow",
            "attachment-placeholder": "italic cyan",
        }
    )
    text = await session.prompt_async(prompt_str, style=style)
    possibly_stripped = update_model_in_input(text)
    if possibly_stripped is not None:
        return possibly_stripped
    return text


if __name__ == "__main__":
    print("Type '@' for path-completion or '/model' to pick a model. Ctrl+D to exit.")

    async def main():
        while True:
            try:
                inp = await get_input_with_combined_completion(
                    get_prompt_with_active_model(), history_file=COMMAND_HISTORY_FILE
                )
                print(f"You entered: {inp}")
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
        print("\nGoodbye!")

    asyncio.run(main())
