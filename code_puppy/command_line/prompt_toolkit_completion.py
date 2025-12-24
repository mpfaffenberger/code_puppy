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
import sys
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
from code_puppy.command_line.command_registry import get_unique_commands
from code_puppy.command_line.file_path_completion import FilePathCompleter
from code_puppy.command_line.load_context_completion import LoadContextCompleter
from code_puppy.command_line.mcp_completion import MCPCompleter
from code_puppy.command_line.model_picker_completion import (
    ModelNameCompleter,
    get_active_model,
)
from code_puppy.command_line.pin_command_completion import PinCompleter, UnpinCompleter
from code_puppy.command_line.utils import list_directory
from code_puppy.config import (
    COMMAND_HISTORY_FILE,
    get_config_keys,
    get_puppy_name,
    get_value,
)


def _sanitize_for_encoding(text: str) -> str:
    """Remove or replace characters that can't be safely encoded.

    This handles:
    - Lone surrogate characters (U+D800-U+DFFF) which are invalid in UTF-8
    - Other problematic Unicode sequences from Windows copy-paste

    Args:
        text: The string to sanitize

    Returns:
        A cleaned string safe for UTF-8 encoding
    """
    # First, try to encode as UTF-8 to catch any problematic characters
    try:
        text.encode("utf-8")
        return text  # String is already valid UTF-8
    except UnicodeEncodeError:
        pass

    # Replace surrogates and other problematic characters
    # Use 'surrogatepass' to encode surrogates, then decode with 'replace' to clean them
    try:
        # Encode allowing surrogates, then decode replacing invalid sequences
        cleaned = text.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )
        return cleaned
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Last resort: filter out all non-BMP and surrogate characters
        return "".join(
            char
            for char in text
            if ord(char) < 0xD800 or (ord(char) > 0xDFFF and ord(char) < 0x10000)
        )


class SafeFileHistory(FileHistory):
    """A FileHistory that handles encoding errors gracefully on Windows.

    Windows terminals and copy-paste operations can introduce invalid
    Unicode surrogate characters that cause UTF-8 encoding to fail.
    This class sanitizes history entries before writing them to disk.
    """

    def store_string(self, string: str) -> None:
        """Store a string in the history, sanitizing it first."""
        sanitized = _sanitize_for_encoding(string)
        try:
            super().store_string(sanitized)
        except (UnicodeEncodeError, UnicodeDecodeError, OSError) as e:
            # If we still can't write, log the error but don't crash
            # This can happen with particularly malformed input
            # Note: Using sys.stderr here intentionally - this is a low-level
            # warning that shouldn't use the messaging system
            sys.stderr.write(f"Warning: Could not save to command history: {e}\n")


class SetCompleter(Completer):
    def __init__(self, trigger: str = "/set"):
        self.trigger = trigger

    def get_completions(self, document, complete_event):
        cursor_position = document.cursor_position
        text_before_cursor = document.text_before_cursor
        stripped_text_for_trigger_check = text_before_cursor.lstrip()

        # If user types just /set (no space), suggest adding a space
        if stripped_text_for_trigger_check == self.trigger:
            from prompt_toolkit.formatted_text import FormattedText

            yield Completion(
                self.trigger + " ",
                start_position=-len(self.trigger),
                display=self.trigger + " ",
                display_meta=FormattedText(
                    [("class:set-completer-meta", "set config key")]
                ),
            )
            return

        # Require a space after /set before showing completions
        if not stripped_text_for_trigger_check.startswith(self.trigger + " "):
            return

        # Determine the part of the text that is relevant for this completer
        # This handles cases like "  /set foo" where the trigger isn't at the start of the string
        actual_trigger_pos = text_before_cursor.find(self.trigger)

        # Extract the input after /set and space (up to cursor)
        trigger_end = actual_trigger_pos + len(self.trigger) + 1  # +1 for the space
        text_after_trigger = text_before_cursor[trigger_end:cursor_position].lstrip()
        start_position = -(len(text_after_trigger))

        # --- SPECIAL HANDLING FOR 'model' KEY ---
        if text_after_trigger == "model":
            # Don't return any completions -- let ModelNameCompleter handle it
            return

        # Get config keys and sort them alphabetically for consistent display
        config_keys = sorted(get_config_keys())

        for key in config_keys:
            if key == "model" or key == "puppy_token":
                continue  # exclude 'model' and 'puppy_token' from regular /set completions
            if key.startswith(text_after_trigger):
                prev_value = get_value(key)
                value_part = f" = {prev_value}" if prev_value is not None else " = "
                completion_text = f"{key}{value_part}"

                yield Completion(
                    completion_text,
                    start_position=start_position,
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
        text_before_cursor = document.text_before_cursor
        stripped_text = text_before_cursor.lstrip()

        # Require a space after /cd before showing completions (consistency with other completers)
        if not stripped_text.startswith(self.trigger + " "):
            return

        # Extract the directory path after /cd and space (up to cursor)
        trigger_pos = text_before_cursor.find(self.trigger)
        trigger_end = trigger_pos + len(self.trigger) + 1  # +1 for the space
        dir_path = text_before_cursor[trigger_end:].lstrip()
        start_position = -(len(dir_path))

        try:
            prefix = os.path.expanduser(dir_path)
            part = os.path.dirname(prefix) if os.path.dirname(prefix) else "."
            dirs, _ = list_directory(part)
            dirnames = [d for d in dirs if d.startswith(os.path.basename(prefix))]
            base_dir = os.path.dirname(prefix)

            # Preserve the user's original prefix (e.g., ~/ or relative paths)
            # Extract what the user originally typed (with ~ or ./ preserved)
            if dir_path.startswith("~"):
                # User typed something with ~, preserve it
                user_prefix = "~" + os.sep
                # For suggestion, we replace the expanded base_dir back with ~/
                original_prefix = dir_path.rstrip(os.sep)
            else:
                user_prefix = None
                original_prefix = None

            for d in dirnames:
                # Build the completion text so we keep the already-typed directory parts.
                if user_prefix and original_prefix:
                    # Restore ~ prefix
                    suggestion = user_prefix + d + os.sep
                elif base_dir and base_dir != ".":
                    suggestion = os.path.join(base_dir, d)
                else:
                    suggestion = d
                # Append trailing slash so the user can continue tabbing into sub-dirs.
                suggestion = suggestion.rstrip(os.sep) + os.sep
                yield Completion(
                    suggestion,
                    start_position=start_position,
                    display=d + os.sep,
                    display_meta="Directory",
                )
        except Exception:
            # Silently ignore errors (e.g., permission issues, non-existent dir)
            pass


class AgentCompleter(Completer):
    """
    A completer that triggers on '/agent' to show available agents.

    Usage: /agent <agent-name>
    """

    def __init__(self, trigger: str = "/agent"):
        self.trigger = trigger

    def get_completions(self, document, complete_event):
        cursor_position = document.cursor_position
        text_before_cursor = document.text_before_cursor
        stripped_text = text_before_cursor.lstrip()

        # Require a space after /agent before showing completions
        if not stripped_text.startswith(self.trigger + " "):
            return

        # Extract the input after /agent and space (up to cursor)
        trigger_pos = text_before_cursor.find(self.trigger)
        trigger_end = trigger_pos + len(self.trigger) + 1  # +1 for the space
        text_after_trigger = text_before_cursor[trigger_end:cursor_position].lstrip()
        start_position = -(len(text_after_trigger))

        # Load all available agent names
        try:
            from code_puppy.command_line.pin_command_completion import load_agent_names

            agent_names = load_agent_names()
        except Exception:
            # If agent loading fails, return no completions
            return

        # Filter and yield agent completions
        try:
            from code_puppy.command_line.pin_command_completion import (
                _get_agent_display_meta,
            )
        except ImportError:
            _get_agent_display_meta = lambda x: "default"  # noqa: E731

        for agent_name in agent_names:
            if agent_name.lower().startswith(text_after_trigger.lower()):
                yield Completion(
                    agent_name,
                    start_position=start_position,
                    display=agent_name,
                    display_meta=_get_agent_display_meta(agent_name),
                )


class SlashCompleter(Completer):
    """
    A completer that triggers on '/' at the beginning of the line
    to show all available slash commands.
    """

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor
        stripped_text = text_before_cursor.lstrip()

        # Only trigger if '/' is the first non-whitespace character
        if not stripped_text.startswith("/"):
            return

        # Get the text after the initial slash
        if len(stripped_text) == 1:
            # User just typed '/', show all commands
            partial = ""
            start_position = 0  # Don't replace anything, just insert at cursor
        else:
            # User is typing a command after the slash
            partial = stripped_text[1:]  # text after '/'
            start_position = -(len(partial))  # Replace what was typed after '/'

        # Load all available commands
        try:
            commands = get_unique_commands()
        except Exception:
            # If command loading fails, return no completions
            return

        # Collect all primary commands and their aliases for proper alphabetical sorting
        all_completions = []

        # Convert partial to lowercase for case-insensitive matching
        partial_lower = partial.lower()

        for cmd in commands:
            # Add primary command (case-insensitive matching)
            if cmd.name.lower().startswith(partial_lower):
                all_completions.append(
                    {
                        "text": cmd.name,
                        "display": f"/{cmd.name}",
                        "meta": cmd.description,
                        "sort_key": cmd.name.lower(),  # Case-insensitive sort
                    }
                )

            # Add all aliases (case-insensitive matching)
            for alias in cmd.aliases:
                if alias.lower().startswith(partial_lower):
                    all_completions.append(
                        {
                            "text": alias,
                            "display": f"/{alias} (alias for /{cmd.name})",
                            "meta": cmd.description,
                            "sort_key": alias.lower(),  # Sort by alias name, not primary command
                        }
                    )

        # Also include custom commands from plugins (like claude-code-auth)
        try:
            from code_puppy import callbacks, plugins

            # Ensure plugins are loaded so custom commands are registered
            plugins.load_plugin_callbacks()
            custom_help_results = callbacks.on_custom_command_help()
            for res in custom_help_results:
                if not res:
                    continue
                # Format 1: List of tuples (command_name, description)
                if isinstance(res, list):
                    for item in res:
                        if isinstance(item, tuple) and len(item) == 2:
                            cmd_name = str(item[0])
                            description = str(item[1])
                            if cmd_name.lower().startswith(partial_lower):
                                all_completions.append(
                                    {
                                        "text": cmd_name,
                                        "display": f"/{cmd_name}",
                                        "meta": description,
                                        "sort_key": cmd_name.lower(),
                                    }
                                )
                # Format 2: Single tuple (command_name, description)
                elif isinstance(res, tuple) and len(res) == 2:
                    cmd_name = str(res[0])
                    description = str(res[1])
                    if cmd_name.lower().startswith(partial_lower):
                        all_completions.append(
                            {
                                "text": cmd_name,
                                "display": f"/{cmd_name}",
                                "meta": description,
                                "sort_key": cmd_name.lower(),
                            }
                        )
        except Exception:
            # If custom command loading fails, continue with registered commands only
            pass

        # Sort all completions alphabetically
        all_completions.sort(key=lambda x: x["sort_key"])

        # Yield the sorted completions
        for completion in all_completions:
            yield Completion(
                completion["text"],
                start_position=start_position,
                display=completion["display"],
                display_meta=completion["meta"],
            )


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
    # Use SafeFileHistory to handle encoding errors gracefully on Windows
    history = SafeFileHistory(history_file) if history_file else None
    completer = merge_completers(
        [
            FilePathCompleter(symbol="@"),
            ModelNameCompleter(trigger="/model"),
            ModelNameCompleter(trigger="/m"),
            CDCompleter(trigger="/cd"),
            SetCompleter(trigger="/set"),
            LoadContextCompleter(trigger="/load_context"),
            PinCompleter(trigger="/pin_model"),
            UnpinCompleter(trigger="/unpin"),
            AgentCompleter(trigger="/agent"),
            AgentCompleter(trigger="/a"),
            MCPCompleter(trigger="/mcp"),
            SlashCompleter(),
        ]
    )
    # Add custom key bindings and multiline toggle
    bindings = KeyBindings()

    # Multiline mode state
    multiline = {"enabled": False}

    # Ctrl+X keybinding - exit with KeyboardInterrupt for shell command cancellation
    @bindings.add(Keys.ControlX)
    def _(event):
        try:
            event.app.exit(exception=KeyboardInterrupt)
        except Exception:
            # Ignore "Return value already set" errors when exit was already called
            # This happens when user presses multiple exit keys in quick succession
            pass

    # Escape keybinding - exit with KeyboardInterrupt
    @bindings.add(Keys.Escape)
    def _(event):
        try:
            event.app.exit(exception=KeyboardInterrupt)
        except Exception:
            # Ignore "Return value already set" errors when exit was already called
            pass

    # NOTE: We intentionally do NOT override Ctrl+C here.
    # prompt_toolkit's default Ctrl+C handler properly resets the terminal state on Windows.
    # Overriding it with event.app.exit(exception=KeyboardInterrupt) can leave the terminal
    # in a bad state where characters cannot be typed. Let prompt_toolkit handle Ctrl+C natively.

    # Toggle multiline with Alt+M
    @bindings.add(Keys.Escape, "m")
    def _(event):
        multiline["enabled"] = not multiline["enabled"]
        status = "ON" if multiline["enabled"] else "OFF"
        # Print status for user feedback (version-agnostic)
        # Note: Using sys.stdout here for immediate feedback during input
        sys.stdout.write(f"[multiline] {status}\n")
        sys.stdout.flush()

    # Also toggle multiline with F2 (more reliable across platforms)
    @bindings.add("f2")
    def _(event):
        multiline["enabled"] = not multiline["enabled"]
        status = "ON" if multiline["enabled"] else "OFF"
        sys.stdout.write(f"[multiline] {status}\n")
        sys.stdout.flush()

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
            "puppy": "bold ansibrightcyan",
            "owner": "bold ansibrightblue",
            "agent": "bold ansibrightblue",
            "model": "bold ansibrightcyan",
            "cwd": "bold ansibrightgreen",
            "arrow": "bold ansibrightblue",
            "attachment-placeholder": "italic ansicyan",
        }
    )
    text = await session.prompt_async(prompt_str, style=style)
    # NOTE: We used to call update_model_in_input(text) here to handle /model and /m
    # commands at the prompt level, but that prevented the command handler from running
    # and emitting success messages. Now we let all /model commands fall through to
    # the command handler in main.py for consistent handling.
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
