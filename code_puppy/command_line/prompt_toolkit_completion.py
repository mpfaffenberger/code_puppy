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
from dataclasses import dataclass
from typing import Literal, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.completion import (
    Completer,
    Completion,
    ConditionalCompleter,
    merge_completers,
)
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, is_searching
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.processors import Processor, Transformation
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style

from code_puppy.command_line.attachments import (
    DEFAULT_ACCEPTED_DOCUMENT_EXTENSIONS,
    DEFAULT_ACCEPTED_IMAGE_EXTENSIONS,
    _detect_path_tokens,
    _tokenise,
)
from code_puppy.command_line.clipboard import (
    capture_clipboard_image_to_pending,
    has_image_in_clipboard,
)
from code_puppy.command_line.command_registry import get_unique_commands
from code_puppy.command_line.file_path_completion import FilePathCompleter
from code_puppy.command_line.interactive_runtime import (
    PromptRuntimeState,
    get_active_interactive_runtime,
)
from code_puppy.command_line.load_context_completion import LoadContextCompleter
from code_puppy.command_line.mcp_completion import MCPCompleter
from code_puppy.command_line.model_picker_completion import (
    ModelNameCompleter,
    get_active_model,
)
from code_puppy.command_line.pin_command_completion import PinCompleter, UnpinCompleter
from code_puppy.command_line.skills_completion import SkillsCompleter
from code_puppy.command_line.utils import list_directory
from code_puppy.config import COMMAND_HISTORY_FILE, get_config_keys, get_puppy_name, get_value
from code_puppy.messaging.spinner.spinner_base import SpinnerBase


@dataclass(frozen=True)
class PromptSubmission:
    action: Literal["submit", "queue", "interject"]
    text: str
    echo_in_transcript: bool = False
    allow_command_dispatch: bool = True


def _get_runtime() -> PromptRuntimeState | None:
    return get_active_interactive_runtime()


def register_active_prompt_surface(
    kind: Literal["main", "interject"], session: PromptSession
) -> None:
    runtime = _get_runtime()
    if runtime is None:
        return
    runtime.register_prompt_surface(session, kind="main")


def clear_active_prompt_surface(session: PromptSession | None = None) -> None:
    runtime = _get_runtime()
    if runtime is None:
        return
    runtime.clear_prompt_surface(session)


def get_active_prompt_surface_kind() -> Literal["main", "interject"] | None:
    runtime = _get_runtime()
    if runtime is None:
        return None
    if runtime.prompt_surface_kind == "main":
        return "main"
    return None


def has_active_prompt_surface() -> bool:
    runtime = _get_runtime()
    return runtime.has_prompt_surface() if runtime is not None else False


def is_shell_prompt_suspended() -> bool:
    runtime = _get_runtime()
    return runtime.has_active_shell() if runtime is not None else False


def set_shell_prompt_suspended(suspended: bool) -> None:
    """Compatibility shim for tests that now maps to shell-active state."""
    runtime = _get_runtime()
    if runtime is None:
        return
    if suspended:
        if not runtime.has_active_shell():
            runtime.notify_shell_started()
        return
    while runtime.has_active_shell():
        runtime.notify_shell_finished()


def _interrupt_shell_from_prompt(label: str) -> None:
    from code_puppy.messaging import emit_warning
    from code_puppy.tools.command_runner import kill_all_running_shell_processes

    emit_warning(f"\n🛑 {label} detected! Interrupting shell command...")
    kill_all_running_shell_processes()

def _truncate_queue_line(text: str, max_len: int) -> str:
    if max_len <= 2:
        return ".."
    if len(text) <= max_len:
        return text
    return text[: max_len - 2] + ".."


def _get_queue_preview(
    prompts: list[str], term_width: int, max_visible: int = 3
) -> tuple[list[str], int]:
    """Return visible queue lines and hidden count from current offset."""
    runtime = _get_runtime()
    queue_offset = runtime.queue_view_offset if runtime is not None else 0
    if not prompts:
        if runtime is not None:
            runtime.queue_view_offset = 0
        return [], 0

    max_start = max(0, len(prompts) - max_visible)
    queue_offset = max(0, min(queue_offset, max_start))
    if runtime is not None:
        runtime.queue_view_offset = queue_offset
    start = queue_offset
    visible = prompts[start : start + max_visible]
    lines: list[str] = []
    line_room = max(8, term_width - 8)
    for idx, prompt in enumerate(visible, start=start + 1):
        lines.append(f"  [{idx}] {_truncate_queue_line(prompt, line_room)}")
    hidden = max(0, len(prompts) - (start + len(visible)))
    return lines, hidden


def _is_exit_text(text: str) -> bool:
    return text.strip().lower() in {"exit", "quit", "/exit", "/quit"}


def _allows_busy_command_dispatch(text: str) -> bool:
    stripped = text.strip()
    return not stripped.startswith("/") or _is_exit_text(stripped)


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
        runtime = _get_runtime()
        if runtime is not None and runtime.has_pending_submission():
            return Transformation(list(transformation_input.fragments))

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


def get_prompt_with_active_model(base: str = ">>> ", is_interject: bool = False):
    return FormattedText(
        _build_prompt_parts(
            is_interject=is_interject,
            include_queue_preview=True,
            include_pending_hint=True,
        )
    )


def _build_prompt_style() -> Style:
    return Style.from_dict(
        {
            # Keys must AVOID the 'class:' prefix – that prefix is used only when
            # tagging tokens in `FormattedText`. See prompt_toolkit docs.
            "puppy": "bold ansibrightcyan",
            "owner": "bold ansibrightblue",
            "agent": "bold ansibrightblue",
            "model": "bold ansibrightcyan",
            "cwd": "bold ansibrightgreen",
            "arrow": "bold ansibrightcyan",
            "separator": "bold ansigray",
            "attachment-placeholder": "italic ansicyan",
            "queue-item": "italic ansiyellow",
            "thinking": "bold ansibrightcyan",
            "thinking-context": "bold white",
        }
    )


def _build_prompt_status_parts(runtime: PromptRuntimeState) -> list[tuple[str, str]]:
    """Build the lightweight thinking line shown above the prompt separator."""
    parts: list[tuple[str, str]] = [
        ("class:thinking", f"{get_puppy_name().title()} is thinking... "),
        ("class:thinking", runtime.get_prompt_status_frame()),
    ]
    context_info = SpinnerBase.get_context_info()
    if context_info:
        parts.append(("", " "))
        parts.append(("class:thinking-context", context_info))
    parts.append(("", "\n"))
    return parts


def _build_prompt_parts(
    *,
    is_interject: bool,
    include_queue_preview: bool,
    include_pending_hint: bool,
) -> list[tuple[str, str]]:
    from code_puppy.agents.agent_manager import get_current_agent

    puppy = get_puppy_name()
    global_model = get_active_model() or "(default)"
    runtime = _get_runtime()

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

    # We add a visual top border using terminal width
    import shutil

    term_width = shutil.get_terminal_size().columns
    sep_line = "─" * term_width

    parts = [("", "\n")]

    if runtime is not None and runtime.running:
        parts.extend(_build_prompt_status_parts(runtime))

    parts.append(("class:separator", f"{sep_line}\n"))

    queue_preview = runtime.queue_preview_texts() if runtime is not None else []
    if include_queue_preview and queue_preview:
        preview_lines, hidden = _get_queue_preview(queue_preview, term_width=term_width)
        for line in preview_lines:
            parts.append(("class:queue-item", f"{line}\n"))
        if hidden:
            parts.append(("class:queue-item", f"  ... and {hidden} more\n"))

    parts.extend([
        ("class:separator", "╭─ "),
        ("bold", "🐶 "),
        ("class:puppy", f"{puppy}"),
        ("", " "),
        ("class:agent", f"[{agent_display}] "),
        ("class:model", model_display + " "),
        ("class:cwd", "(" + str(cwd_display) + ") \n"),
    ])

    if include_pending_hint and (
        is_interject or (runtime is not None and runtime.has_pending_submission())
    ):
        # Add hint above the prompt line to keep the cursor position consistent
        parts.append(
            (
                "class:queue-item",
                "  [i]nterject [q]ueue [e]dit [esc]ape\n",
            )
        )

    parts.extend([
        ("class:separator", "╰─"),
        ("class:arrow", "❯ "),
    ])

    return parts


def render_submitted_prompt_echo(text: str) -> None:
    """Print a submitted prompt using the same prompt chrome as the composer."""
    echo_text = text.rstrip("\n")
    if not echo_text:
        return

    parts = _build_prompt_parts(
        is_interject=False,
        include_queue_preview=False,
        include_pending_hint=False,
    )
    parts.append(("", echo_text))
    parts.append(("", "\n"))
    formatted = FormattedText(parts)
    style = _build_prompt_style()
    runtime = _get_runtime()

    def _print_echo() -> None:
        from prompt_toolkit.output.defaults import create_output

        out = create_output(stdout=sys.__stdout__)
        if hasattr(out, "enable_cpr"):
            out.enable_cpr = False
        print_formatted_text(formatted, style=style, output=out)

    if (
        runtime is not None
        and runtime.has_prompt_surface()
        and not runtime.is_rendering_above_prompt()
    ):
        try:
            if runtime.run_above_prompt(_print_echo):
                return
        except Exception:
            pass

    _print_echo()


def render_transcript_notice(text: str) -> None:
    """Print a plain transcript line above the composer without prompt chrome."""
    notice_text = text.rstrip("\n")
    if not notice_text:
        return

    formatted = FormattedText([("", notice_text), ("", "\n")])
    runtime = _get_runtime()

    def _print_notice() -> None:
        from prompt_toolkit.output.defaults import create_output

        out = create_output(stdout=sys.__stdout__)
        if hasattr(out, "enable_cpr"):
            out.enable_cpr = False
        print_formatted_text(formatted, output=out)

    if (
        runtime is not None
        and runtime.has_prompt_surface()
        and not runtime.is_rendering_above_prompt()
    ):
        try:
            if runtime.run_above_prompt(_print_notice):
                return
        except Exception:
            pass

    _print_notice()


async def prompt_for_submission(
    prompt_str=">>> ", history_file: Optional[str] = None, erase_when_done: bool = False
) -> PromptSubmission:
    # Use SafeFileHistory to handle encoding errors gracefully on Windows
    history = SafeFileHistory(history_file) if history_file else None
    runtime = _get_runtime()
    # Add custom key bindings and multiline toggle
    bindings = KeyBindings()
    recalled_queue_item = {"item": None}
    recalled_queue_allow_command_dispatch = {"value": True}
    pending_decision_filter = Condition(
        lambda: runtime is not None and runtime.has_pending_submission()
    )
    shell_active_filter = Condition(
        lambda: runtime is not None and runtime.has_active_shell()
    )
    busy_run_filter = Condition(lambda: runtime is not None and runtime.running)
    command_completion_filter = Condition(
        lambda: runtime is None
        or not (runtime.running or runtime.has_pending_submission())
    )
    attachment_completion_filter = Condition(
        lambda: runtime is None or not runtime.has_pending_submission()
    )

    completer = merge_completers(
        [
            ConditionalCompleter(
                FilePathCompleter(symbol="@"),
                filter=attachment_completion_filter,
            ),
            ConditionalCompleter(
                ModelNameCompleter(trigger="/model"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                ModelNameCompleter(trigger="/m"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                CDCompleter(trigger="/cd"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                SetCompleter(trigger="/set"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                LoadContextCompleter(trigger="/load_context"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                PinCompleter(trigger="/pin_model"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                UnpinCompleter(trigger="/unpin"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                AgentCompleter(trigger="/agent"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                AgentCompleter(trigger="/a"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                MCPCompleter(trigger="/mcp"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                SkillsCompleter(trigger="/skills"),
                filter=command_completion_filter,
            ),
            ConditionalCompleter(
                SlashCompleter(),
                filter=command_completion_filter,
            ),
        ]
    )

    # Multiline mode state
    multiline = {"enabled": False}

    def awaiting_decision() -> bool:
        return runtime is not None and runtime.has_pending_submission()

    def clear_chooser_input(event) -> None:
        try:
            event.app.current_buffer.reset()
        except Exception:
            pass

    def restore_pending_submission_to_buffer(event) -> None:
        if runtime is None:
            return

        text = runtime.take_pending_submission() or ""
        try:
            event.app.current_buffer.document = Document(
                text=text,
                cursor_position=len(text),
            )
        except Exception:
            try:
                event.app.current_buffer.text = text
            except Exception:
                pass

    def recall_next_paused_queue_to_buffer(event) -> bool:
        if runtime is None:
            return False
        if runtime.running or runtime.has_pending_submission():
            return False
        if not runtime.is_queue_autodrain_suppressed():
            return False
        if not runtime.queue:
            return False

        item = runtime.queue[0]
        recalled_queue_item["item"] = item
        recalled_queue_allow_command_dispatch["value"] = item.allow_command_dispatch
        try:
            event.app.current_buffer.document = Document(
                text=item.text,
                cursor_position=len(item.text),
            )
        except Exception:
            try:
                event.app.current_buffer.text = item.text
            except Exception:
                return False
        return True

    # Ctrl+X keybinding - exit with KeyboardInterrupt for input cancellation
    @bindings.add(Keys.ControlX)
    def _(event):
        if runtime is not None and runtime.has_active_shell():
            _interrupt_shell_from_prompt("Ctrl-X")
            return
        try:
            event.app.exit(exception=KeyboardInterrupt)
        except Exception:
            # Ignore "Return value already set" errors when exit was already called
            # This happens when user presses multiple exit keys in quick succession
            pass

    @bindings.add("c-c", filter=busy_run_filter, eager=True)
    def _(event):
        if runtime is not None and runtime.has_active_shell():
            _interrupt_shell_from_prompt("Ctrl-C")
            runtime.suppress_queue_autodrain()
            runtime.set_pending_submission(None)
            clear_chooser_input(event)
            return
        if runtime is not None:
            runtime.set_pending_submission(None)
            clear_chooser_input(event)
            if runtime.request_active_cancel("ctrl_c"):
                return
        try:
            event.app.exit(exception=KeyboardInterrupt)
        except Exception:
            pass

    configured_cancel_key = str(get_value("cancel_agent_key") or "ctrl+c").lower()
    configured_binding = {"ctrl+k": "c-k", "ctrl+q": "c-q"}.get(configured_cancel_key)
    if configured_binding is not None:

        @bindings.add(configured_binding, filter=busy_run_filter, eager=True)
        def _(event):
            if runtime is not None and runtime.has_active_shell():
                _interrupt_shell_from_prompt(configured_cancel_key.upper())
                runtime.suppress_queue_autodrain()
                runtime.set_pending_submission(None)
                clear_chooser_input(event)
                return
            if runtime is not None:
                runtime.set_pending_submission(None)
                clear_chooser_input(event)
                if runtime.request_active_cancel(configured_cancel_key):
                    return
            try:
                event.app.exit(exception=KeyboardInterrupt)
            except Exception:
                pass

    # Escape keybinding - exit with KeyboardInterrupt
    @bindings.add(Keys.Escape)
    def _(event):
        if awaiting_decision():
            runtime.set_pending_submission(None)
            clear_chooser_input(event)
            return
        if runtime is not None and runtime.has_active_shell():
            return
        try:
            event.app.exit(exception=KeyboardInterrupt)
        except Exception:
            # Ignore "Return value already set" errors when exit was already called
            pass

    # Idle Ctrl+C is still left to prompt_toolkit.
    # We only intercept it while work is actively running so busy-state cancel stays local
    # to the interactive runtime instead of tearing down the terminal session.

    @bindings.add("i", filter=pending_decision_filter, eager=True)
    @bindings.add("I", filter=pending_decision_filter, eager=True)
    def _(event):
        text, allow_command_dispatch = runtime.take_pending_submission_with_policy()
        clear_chooser_input(event)
        event.app.exit(
            result=PromptSubmission(
                action="interject",
                text=text or "",
                allow_command_dispatch=allow_command_dispatch,
            )
        )

    @bindings.add("q", filter=pending_decision_filter, eager=True)
    @bindings.add("Q", filter=pending_decision_filter, eager=True)
    def _(event):
        text, allow_command_dispatch = runtime.take_pending_submission_with_policy()
        clear_chooser_input(event)
        event.app.exit(
            result=PromptSubmission(
                action="queue",
                text=text or "",
                allow_command_dispatch=allow_command_dispatch,
            )
        )

    @bindings.add("e", filter=pending_decision_filter, eager=True)
    @bindings.add("E", filter=pending_decision_filter, eager=True)
    @bindings.add("up", filter=pending_decision_filter, eager=True)
    def _(event):
        clear_chooser_input(event)
        restore_pending_submission_to_buffer(event)

    # Toggle multiline with Alt+M
    @bindings.add(Keys.Escape, "m")
    def _(event):
        if awaiting_decision():
            return
        multiline["enabled"] = not multiline["enabled"]
        status = "ON" if multiline["enabled"] else "OFF"
        # Print status for user feedback (version-agnostic)
        # Note: Using sys.stdout here for immediate feedback during input
        sys.stdout.write(f"[multiline] {status}\n")
        sys.stdout.flush()

    # Also toggle multiline with F2 (more reliable across platforms)
    @bindings.add("f2")
    def _(event):
        if awaiting_decision():
            return
        multiline["enabled"] = not multiline["enabled"]
        status = "ON" if multiline["enabled"] else "OFF"
        sys.stdout.write(f"[multiline] {status}\n")
        sys.stdout.flush()

    # Newline insert bindings — robust and explicit
    # Ctrl+J (line feed) works in virtually all terminals; mark eager so it wins
    @bindings.add("c-j", eager=True)
    def _(event):
        if awaiting_decision():
            return
        event.app.current_buffer.insert_text("\n")

    # Also allow Ctrl+Enter for newline (terminal-dependent)
    try:

        @bindings.add("c-enter", eager=True)
        def _(event):
            if awaiting_decision():
                return
            event.app.current_buffer.insert_text("\n")
    except Exception:
        pass

    # Enter behavior depends on multiline mode
    @bindings.add("enter", filter=~is_searching, eager=True)
    def _(event):
        if awaiting_decision():
            choice = event.app.current_buffer.text.strip()
            if _is_exit_text(choice):
                runtime.set_pending_submission(None)
                clear_chooser_input(event)
                event.app.exit(
                    result=PromptSubmission(
                        action="submit",
                        text=choice,
                        allow_command_dispatch=True,
                    )
                )
            return
        text = event.app.current_buffer.text
        if not text.strip() and recall_next_paused_queue_to_buffer(event):
            return
        if (
            runtime is not None
            and runtime.running
            and text.strip()
            and not _is_exit_text(text)
        ):
            runtime.set_pending_submission(
                text,
                allow_command_dispatch=_allows_busy_command_dispatch(text),
            )
            clear_chooser_input(event)
            return
        if multiline["enabled"]:
            event.app.current_buffer.insert_text("\n")
        else:
            event.current_buffer.validate_and_handle()

    # Backspace/Delete: trigger completions after deletion
    # By default, complete_while_typing only triggers on character insertion,
    # not deletion. This fixes completions not reappearing after backspace.
    @bindings.add("c-h", eager=True)  # Backspace (Ctrl+H)
    @bindings.add("backspace", eager=True)
    def handle_backspace_with_completion(event):
        if awaiting_decision():
            return
        buffer = event.app.current_buffer
        # Perform the deletion first
        buffer.delete_before_cursor(count=1)
        # Then trigger completion if text starts with '/'
        text = buffer.text.lstrip()
        if text.startswith("/") and command_completion_filter():
            buffer.start_completion(select_first=False)

    @bindings.add("delete", eager=True)
    def handle_delete_with_completion(event):
        if awaiting_decision():
            return
        buffer = event.app.current_buffer
        # Perform the deletion first
        buffer.delete(count=1)
        # Then trigger completion if text starts with '/'
        text = buffer.text.lstrip()
        if text.startswith("/") and command_completion_filter():
            buffer.start_completion(select_first=False)

    @bindings.add("c-up", eager=True)
    def handle_queue_scroll_up(event):
        if runtime is None or len(runtime.queue) <= 3:
            return
        runtime.shift_queue_view_offset(-1)

    @bindings.add("c-down", eager=True)
    def handle_queue_scroll_down(event):
        if runtime is None or len(runtime.queue) <= 3:
            return
        runtime.shift_queue_view_offset(1)

    # Handle bracketed paste - smart detection for text vs images.
    # Most terminals (Windows included!) send Ctrl+V through bracketed paste.
    # - If there's meaningful text content → paste as text (drag-and-drop file paths, copied text)
    # - If text is empty/whitespace → check for clipboard image (image paste on Windows)
    @bindings.add(Keys.BracketedPaste)
    def handle_bracketed_paste(event):
        """Handle bracketed paste - smart text vs image detection."""
        if awaiting_decision():
            return
        pasted_data = event.data

        # If we have meaningful text content, paste it (don't check for images)
        # This handles drag-and-drop file paths and normal text paste
        if pasted_data and pasted_data.strip():
            # Normalize Windows line endings to Unix style
            sanitized_data = pasted_data.replace("\r\n", "\n").replace("\r", "\n")
            event.app.current_buffer.insert_text(sanitized_data)
            return

        # No meaningful text - check if clipboard has an image (Windows image paste!)
        try:
            if has_image_in_clipboard():
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
        if awaiting_decision():
            return
        try:
            # Check for image first
            if has_image_in_clipboard():
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
        if awaiting_decision():
            return
        try:
            if has_image_in_clipboard():
                placeholder = capture_clipboard_image_to_pending()
                if placeholder:
                    event.app.current_buffer.insert_text(placeholder + " ")
                    # The placeholder itself is visible feedback
                    # Use bell for audible feedback (works in most terminals)
                    event.app.output.bell()
            else:
                # Insert a transient message that user can delete
                event.app.current_buffer.insert_text("[⚠️ no image in clipboard] ")
                event.app.output.bell()
        except Exception:
            event.app.current_buffer.insert_text("[❌ clipboard error] ")
            event.app.output.bell()

    from prompt_toolkit.output.defaults import create_output

    out = create_output(stdout=sys.stdout)
    if hasattr(out, "enable_cpr"):
        out.enable_cpr = False
    session = PromptSession(
        completer=completer,
        history=history,
        complete_while_typing=True,
        key_bindings=bindings,
        input_processors=[AttachmentPlaceholderProcessor()],
        output=out,
        erase_when_done=erase_when_done,
    )
    # Keep the chooser truly modal: while a pending submission exists, only the
    # explicit chooser bindings should work and the buffer should reject edits.
    session.default_buffer.read_only = pending_decision_filter
    # If they pass a string, backward-compat: convert it to formatted_text
    if isinstance(prompt_str, str):
        from prompt_toolkit.formatted_text import FormattedText

        prompt_str = FormattedText([(None, prompt_str)])
    style = _build_prompt_style()
    register_active_prompt_surface("main", session)
    try:
        with patch_stdout():
            result = await session.prompt_async(prompt_str, style=style)
    except (KeyboardInterrupt, EOFError):
        if runtime is not None:
            runtime.set_pending_submission(None)
        raise
    finally:
        clear_active_prompt_surface(session)
    if isinstance(result, PromptSubmission):
        return PromptSubmission(
            action=result.action,
            text=result.text,
            echo_in_transcript=erase_when_done,
            allow_command_dispatch=result.allow_command_dispatch,
        )
    allow_command_dispatch = True
    recalled_item = recalled_queue_item["item"]
    if recalled_item is not None:
        allow_command_dispatch = recalled_queue_allow_command_dispatch["value"]
        if (
            runtime is not None
            and result.strip()
            and runtime.queue
            and runtime.queue[0] is recalled_item
        ):
            runtime.dequeue()
    # NOTE: We used to call update_model_in_input(text) here to handle /model and /m
    # commands at the prompt level, but that prevented the command handler from running
    # and emitting success messages. Now we let all /model commands fall through to
    # the command handler in main.py for consistent handling.
    return PromptSubmission(
        action="submit",
        text=result,
        echo_in_transcript=erase_when_done,
        allow_command_dispatch=allow_command_dispatch,
    )


async def get_input_with_combined_completion(
    prompt_str=">>> ", history_file: Optional[str] = None, erase_when_done: bool = False
) -> str:
    submission = await prompt_for_submission(
        prompt_str=prompt_str,
        history_file=history_file,
        erase_when_done=erase_when_done,
    )
    return submission.text


async def get_interject_action() -> str:
    """Compatibility shim for tests; interactive_mode no longer uses this."""
    submission = await prompt_for_submission(
        prompt_str=lambda: get_prompt_with_active_model(is_interject=True),
        erase_when_done=True,
    )
    if submission.action == "interject":
        return "i"
    if submission.action == "queue":
        return "q"
    return ""



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
