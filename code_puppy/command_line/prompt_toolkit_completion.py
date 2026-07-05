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
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.processors import Processor, Transformation
from prompt_toolkit.styles import Style

from code_puppy.command_line.attachments import (
    _detect_path_tokens,
    _tokenise,
    attachment_placeholder_label,
)
from code_puppy.command_line.clipboard import (
    capture_clipboard_image_to_pending,
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
from code_puppy.command_line.skills_completion import SkillsCompleter
from code_puppy.command_line.utils import list_directory
from code_puppy.callbacks import on_prompt_text_color, on_prompt_toolkit_style
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
        start_position = -len(text_after_trigger)

        # --- SPECIAL HANDLING FOR 'model' KEY ---
        if text_after_trigger == "model":
            # Don't return any completions -- let ModelNameCompleter handle it
            return

        # Get config keys and sort them alphabetically for consistent display.
        # Per-model controls belong exclusively to /model_settings.
        from code_puppy.command_line.config_apply import MODEL_SETTINGS_ONLY_KEYS

        config_keys = sorted(get_config_keys())

        for key in config_keys:
            if key in {"model", "puppy_token"} | MODEL_SETTINGS_ONLY_KEYS:
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

    _PLACEHOLDER_STYLE = "class:attachment-placeholder class:tui.title"
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
                display_text = attachment_placeholder_label(detection.path)
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
            # Treat a bare `~` as `~/` for lookup so we complete inside the
            # user's home directory (not the parent directory containing their
            # username folder).
            lookup_path = "~/" if dir_path == "~" else dir_path
            expanded_lookup = os.path.expanduser(lookup_path)

            # If the typed path ends with a separator, we're completing inside
            # that directory and should match all child names.
            if lookup_path.endswith(os.sep):
                part = expanded_lookup
                name_prefix = ""
            else:
                part = os.path.dirname(expanded_lookup) or "."
                name_prefix = os.path.basename(expanded_lookup)

            dirs, _ = list_directory(part)
            dirnames = [d for d in dirs if d.startswith(name_prefix)]

            # Preserve user's typed style (~, relative, absolute) in emitted
            # completion text instead of leaking expanded absolute paths.
            if dir_path == "~":
                typed_base = "~"
            elif dir_path.endswith(os.sep):
                stripped_base = dir_path.rstrip(os.sep)
                if not stripped_base and dir_path.startswith(os.sep):
                    typed_base = os.sep
                else:
                    typed_base = stripped_base
            else:
                typed_base = os.path.dirname(dir_path.rstrip(os.sep))

            for d in dirnames:
                suggestion = os.path.join(typed_base, d) if typed_base else d
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

    def __init__(self, trigger: str = "/agent", prefix: str = ""):
        self.trigger = trigger
        self.prefix = prefix

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
        if self.prefix:
            if not text_after_trigger.startswith(self.prefix):
                return
            text_after_trigger = text_after_trigger[len(self.prefix) :]
        start_position = -len(text_after_trigger)

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

        # Get the text after the initial slash. A bare slash intentionally
        # yields every command so the menu appears immediately while typing.
        partial = stripped_text[1:]
        start_position = -len(partial)

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

        # Yield the sorted completions.
        # Strip variation selectors (U+FE00-FE0F) from display strings to avoid
        # width-calculation mismatches between prompt_toolkit and the terminal,
        # which manifest as phantom spaces in the input line (e.g. /judges ⚖️).
        for completion in all_completions:
            yield Completion(
                completion["text"],
                start_position=start_position,
                display=_strip_variation_selectors(completion["display"]),
                display_meta=_strip_variation_selectors(completion["meta"]),
            )


def _strip_variation_selectors(text: str) -> str:
    """Remove variation selectors (U+FE00-FE0F) from text.

    These invisible characters modify emoji rendering but cause width
    calculation mismatches between prompt_toolkit and terminal emulators.
    """
    return "".join(c for c in text if not (0xFE00 <= ord(c) <= 0xFE0F))


def _normalize_emoji_spacing(text: str) -> str:
    """Normalize emoji spacing for consistent terminal rendering.

    Some emojis have East Asian Width 'N' (Neutral) which terminals render
    inconsistently. This adds a space after such emojis to prevent
    the following character from overlapping.
    """
    import unicodedata

    result = []
    text = _strip_variation_selectors(text)
    for char in text:
        result.append(char)
        # Add padding after Neutral-width emoji to prevent overlap
        if (
            0x1F300 <= ord(char) <= 0x1FAFF
            and unicodedata.east_asian_width(char) == "N"
        ):
            result.append(" ")  # Extra space buffer
    return "".join(result)


# Classic prompt palette (single source of truth — the persistent bottom-bar
# prompt converts these to raw SGR codes via messaging.prompt_prefix_style).
# IMPORTANT: use `ansi*`-prefixed names — bare names like "magenta" resolve to
# truecolor hex (#ff00ff) in prompt_toolkit and would IGNORE the terminal
# palette. The ansi names emit real ANSI codes, so the /theme plugin's OSC
# palette remap (Level 3) restyles the prompt to the chosen theme.
PROMPT_STYLES = {
    "puppy": "bold ansimagenta",
    "agent": "bold ansiblue",
    "model": "bold ansicyan",
    "cwd": "bold ansigreen",
    "arrow": "bold ansiyellow",
}


def get_prompt_with_active_model(base: str = ">>> "):
    from code_puppy.agents.agent_manager import get_current_agent

    puppy = get_puppy_name()
    # When nothing is configured this is None - surface that explicitly as
    # [None] so the user immediately sees they need to /add_model.
    global_model = get_active_model()

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
        model_display = f"[{global_model} \u2192 {agent_model}]"
    elif agent_model:
        # Show only the agent model when pinned
        model_display = f"[{agent_model}]"
    else:
        # Show only the global model when no agent model is pinned.
        # global_model may be None -> renders as [None].
        model_display = f"[{global_model}]"

    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd_display = "~" + cwd[len(home) :]
    else:
        cwd_display = cwd
    return FormattedText(
        [
            ("class:puppy class:tui.header", f"{puppy}"),
            ("", " "),
            (
                "class:agent class:tui.label",
                f"[{_normalize_emoji_spacing(agent_display)}] ",
            ),
            ("class:model class:tui.title", model_display + " "),
            ("class:cwd class:tui.muted", "(" + str(cwd_display) + ") "),
            ("class:arrow class:tui.help-key", str(base)),
        ]
    )


class _NoGhostLinesPromptSession(PromptSession):
    """A `PromptSession` that only reserves menu space while the menu is open.

    Stock prompt_toolkit reserves `reserve_space_for_menu` (8) rows for the
    completion menu for the *entire lifetime* of the prompt whenever
    `complete_while_typing=True` — see `_get_default_buffer_control_height`.
    The renderer then moves the cursor to the bottom of that taller canvas on
    first paint, force-scrolling the terminal and leaving a block of ghost
    blank lines under (or above, after scroll) the prompt even if the
    completion menu never appears — and terminals can't un-scroll.

    Overriding the height hook so the space is reserved *only while a
    completion state is active* means the prompt stays a single line until a
    menu is genuinely on screen. The scroll still happens while the menu is
    visible (physics), but it no longer haunts every prompt render or
    lingers after a `/` is typo'd and deleted.
    """

    def _get_default_buffer_control_height(self) -> Dimension:
        if self.default_buffer.complete_state is None:
            return Dimension()
        return super()._get_default_buffer_control_height()


def _left_justify_completion_menu(session: PromptSession) -> None:
    """Pin the completion menu's `Float` to the left edge of the screen.

    prompt_toolkit's default `PromptSession` layout attaches the completion
    menu as a `Float(xcursor=True, ycursor=True, content=CompletionsMenu(...))`,
    so the menu drifts horizontally with the cursor. We walk the layout,
    find every `Float` whose content is a `CompletionsMenu` (or the
    multi-column variant), and flip it to `left=0` / `xcursor=False` so the
    menu always anchors to column 0 regardless of where the cursor sits.

    Wrapped in a broad try/except: prompt_toolkit's internal layout layout
    can shift between versions and we'd rather silently degrade to the
    default positioning than crash the prompt.
    """
    try:
        from prompt_toolkit.layout.containers import FloatContainer
        from prompt_toolkit.layout.menus import (
            CompletionsMenu,
            MultiColumnCompletionsMenu,
        )

        menu_types = (CompletionsMenu, MultiColumnCompletionsMenu)
        for node in session.layout.walk():
            if not isinstance(node, FloatContainer):
                continue
            for float_obj in node.floats or []:
                if isinstance(float_obj.content, menu_types):
                    float_obj.xcursor = False
                    float_obj.ycursor = True  # keep vertical anchoring
                    float_obj.left = 0
    except Exception:
        pass


def _complete_or_cycle(buffer) -> None:
    """Apply an unambiguous completion, otherwise cycle the available choices.

    ``complete_while_typing`` opens a completion state without selecting an
    item. prompt_toolkit's default Tab binding selects even a sole candidate,
    requiring a pointless second Tab to apply it. Start completion explicitly
    when needed, then immediately apply a single candidate while preserving
    normal cycling for ambiguous input.
    """
    if buffer.complete_state is None:
        buffer.start_completion(select_first=False)

    complete_state = buffer.complete_state
    if complete_state is None:
        return

    completions = complete_state.completions
    if len(completions) == 1:
        buffer.apply_completion(completions[0])
    elif completions:
        buffer.complete_next()


async def get_input_with_combined_completion(
    prompt_str=">>> ", history_file: Optional[str] = None
) -> str:
    # Use SafeFileHistory to handle encoding errors gracefully on Windows
    history = SafeFileHistory(history_file) if history_file else None
    # Build the base completer list, then bolt on any plugin completers.
    from code_puppy.plugins.ollama_setup.completer import OllamaSetupCompleter

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
            AgentCompleter(trigger="/switch-agent"),
            AgentCompleter(trigger="/sa"),
            AgentCompleter(trigger="/fork", prefix="@"),
            MCPCompleter(trigger="/mcp"),
            SkillsCompleter(trigger="/skills"),
            OllamaSetupCompleter(),
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

    # Enter behavior depends on multiline mode AND completion-menu state.
    # Priority order:
    #   1. If the completion menu is open with a highlighted item that would
    #      actually CHANGE the buffer, accept that completion and close the
    #      menu (don't submit). This matches how editors like VSCode/Helix
    #      behave — Enter on a popup = pick, not commit.
    #   2. If the highlighted completion is a no-op (you've already typed the
    #      whole word, so applying it changes nothing), don't swallow the
    #      keystroke — close the menu and fall through to submit. Otherwise
    #      you'd have to press Enter twice for a fully-typed command.
    #   3. Multiline mode: insert a newline.
    #   4. Default: submit the prompt.
    @bindings.add("enter", filter=~is_searching, eager=True)
    def _(event):
        buffer = event.current_buffer
        complete_state = buffer.complete_state
        completion = complete_state.current_completion if complete_state else None
        if completion is not None:
            # The fragment this completion would overwrite (start_position is
            # a <= 0 offset from the cursor). If it already equals the
            # completion text, applying it is a no-op -> treat Enter as submit.
            before = buffer.document.text_before_cursor
            overwritten = before[len(before) + completion.start_position :]
            if overwritten != completion.text:
                buffer.apply_completion(completion)
                return
            # No-op completion: dismiss the menu and continue to submit/newline.
            buffer.cancel_completion()
        if multiline["enabled"]:
            buffer.insert_text("\n")
        else:
            buffer.validate_and_handle()

    # Tab: finish an unambiguous completion in one press. For multiple
    # candidates, retain prompt_toolkit's familiar select/cycle behavior.
    @bindings.add(Keys.Tab, eager=True)
    def handle_tab_completion(event):
        _complete_or_cycle(event.app.current_buffer)

    # Backspace/Delete: trigger completions after deletion.
    # By default, complete_while_typing only triggers on character insertion,
    # not deletion — so the menu vanishes the moment you backspace. We
    # unconditionally restart completion after a delete and let each
    # individual Completer decide whether it has anything to yield for the
    # new buffer state (no-yield = menu naturally closes). This keeps `@`
    # file completions, `/model <name>` sub-completions, etc. alive while
    # editing — not just bare `/` slash commands.
    def _restart_completion(buffer) -> None:
        if buffer.text:
            buffer.start_completion(select_first=False)

    @bindings.add("c-h", eager=True)  # Backspace (Ctrl+H)
    @bindings.add("backspace", eager=True)
    def handle_backspace_with_completion(event):
        buffer = event.app.current_buffer
        buffer.delete_before_cursor(count=1)
        _restart_completion(buffer)

    @bindings.add("delete", eager=True)
    def handle_delete_with_completion(event):
        buffer = event.app.current_buffer
        buffer.delete(count=1)
        _restart_completion(buffer)

    # Handle bracketed paste - smart detection for text vs images.
    # Most terminals (Windows included!) send Ctrl+V through bracketed paste.
    # - If there's meaningful text content → paste as text (drag-and-drop file paths, copied text)
    # - If text is empty/whitespace → check for clipboard image (image paste on Windows)
    @bindings.add(Keys.BracketedPaste)
    def handle_bracketed_paste(event):
        """Handle bracketed paste - smart text vs image detection."""
        pasted_data = event.data

        # If we have meaningful text content, paste it (don't check for images)
        # This handles drag-and-drop file paths and normal text paste
        if pasted_data and pasted_data.strip():
            # Normalize Windows line endings to Unix style
            sanitized_data = pasted_data.replace("\r\n", "\n").replace("\r", "\n")
            event.app.current_buffer.insert_text(sanitized_data)
            return

        # No meaningful text - try capturing a clipboard image directly
        # (Windows image paste!). Single clipboard read: a separate
        # "has image?" probe would double the (slow, osascript-backed on
        # macOS) clipboard round-trip and make the keypress feel dead.
        try:
            placeholder = capture_clipboard_image_to_pending()
            if placeholder:
                event.app.current_buffer.insert_text(placeholder + " ")
                event.app.output.bell()
                return
        except Exception:
            pass

        # Fallback: if there was whitespace-only data, paste it
        if pasted_data:
            sanitized_data = pasted_data.replace("\r\n", "\n").replace("\r", "\n")
            event.app.current_buffer.insert_text(sanitized_data)

    # Fallback Ctrl+V for terminals without bracketed paste support
    @bindings.add("c-v", eager=True)
    def handle_smart_paste(event):
        """Handle Ctrl+V - auto-detect image vs text in clipboard."""
        try:
            # Try capturing an image directly — ONE clipboard read. The old
            # has_image_in_clipboard() probe + capture did two full reads
            # (each an osascript round-trip on macOS), freezing the prompt
            # long enough that users pressed Ctrl+V twice.
            placeholder = capture_clipboard_image_to_pending()
            if placeholder:
                event.app.current_buffer.insert_text(placeholder + " ")
                # The placeholder itself is visible feedback - no need for extra output
                # Use bell for audible feedback (works in most terminals)
                event.app.output.bell()
                return  # Don't also paste text
        except Exception:
            pass  # Fall through to text paste on any error

        # No image (or error) - do normal text paste
        # prompt_toolkit doesn't have built-in paste, so we handle it manually
        try:
            import platform
            import subprocess

            text = None
            system = platform.system()

            if system == "Darwin":  # macOS
                result = subprocess.run(
                    ["pbpaste"], capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0:
                    text = result.stdout
            elif system == "Windows":
                # Windows - use powershell
                result = subprocess.run(
                    ["powershell", "-command", "Get-Clipboard"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    text = result.stdout
            else:  # Linux
                # Try xclip first, then xsel
                for cmd in [
                    ["xclip", "-selection", "clipboard", "-o"],
                    ["xsel", "--clipboard", "--output"],
                ]:
                    try:
                        result = subprocess.run(
                            cmd, capture_output=True, text=True, timeout=2
                        )
                        if result.returncode == 0:
                            text = result.stdout
                            break
                    except FileNotFoundError:
                        continue

            if text:
                # Normalize Windows line endings to Unix style
                text = text.replace("\r\n", "\n").replace("\r", "\n")
                # Strip trailing newline that clipboard tools often add
                text = text.rstrip("\n")
                event.app.current_buffer.insert_text(text)
        except Exception:
            pass  # Silently fail if text paste doesn't work

    # F3 - dedicated image paste (shows error if no image)
    @bindings.add("f3")
    def handle_image_paste_f3(event):
        """Handle F3 - paste image from clipboard (image-only, shows error if none)."""
        try:
            placeholder = capture_clipboard_image_to_pending()
            if placeholder:
                event.app.current_buffer.insert_text(placeholder + " ")
                # The placeholder itself is visible feedback
                # Use bell for audible feedback (works in most terminals)
                event.app.output.bell()
            else:
                # Insert a transient message that user can delete
                event.app.current_buffer.insert_text("[no image in clipboard] ")
                event.app.output.bell()
        except Exception:
            event.app.current_buffer.insert_text("[clipboard error] ")
            event.app.output.bell()

    session = _NoGhostLinesPromptSession(
        completer=completer,
        history=history,
        complete_while_typing=True,
        key_bindings=bindings,
        input_processors=[AttachmentPlaceholderProcessor()],
    )
    _left_justify_completion_menu(session)
    # If they pass a string, backward-compat: convert it to formatted_text.
    # NOTE: the style field must be a str — `None` crashes `to_formatted_text`.
    if isinstance(prompt_str, str):
        prompt_str = FormattedText([("", prompt_str)])
    prompt_text_color = on_prompt_text_color()
    default_input_style = f"fg:{prompt_text_color}" if prompt_text_color else ""
    local_style = Style.from_dict(
        {
            # Keep the prompt useful without the theme plugin. With the plugin
            # active, its semantic root supplies the palette underneath these
            # structural rules while an explicit prompt-text override still wins.
            "": default_input_style,
            "attachment-placeholder": "italic",
            # Suppress prompt_toolkit's fixed white/grey/reverse completion
            # presentation. Colors now inherit from the semantic theme root;
            # only hierarchy and emphasis belong to this local component.
            "completion-menu": "noreverse",
            "completion-menu.completion": "noreverse",
            "completion-menu.completion.current": "noreverse bold underline",
            "completion-menu.meta.completion": "noreverse italic",
            "completion-menu.meta.completion.current": "noreverse italic bold",
            "completion-menu.multi-column-meta": "noreverse",
            "scrollbar.background": "noreverse",
            "scrollbar.button": "noreverse bold",
        }
    )
    style = on_prompt_toolkit_style(local_style)
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
