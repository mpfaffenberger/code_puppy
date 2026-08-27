"""Slash-command completers and the REPL prompt prefix.

Home of the completion stack (on termflow's completer protocol) and the
prompt-prefix builder, extracted from the retired classic
prompt_toolkit input path. The raw bottom-bar editor consumes the stack
through :func:`build_completer_stack`.
"""

from __future__ import annotations

import os
import shutil
import unicodedata

from rich.cells import cell_len
from termflow.tui.completion import Completer, Completion, merge_completers

from code_puppy.command_line.command_registry import get_unique_commands
from code_puppy.command_line.completion_cache import TTLCache
from code_puppy.command_line.utils import list_directory
from code_puppy.config import (
    get_config_keys,
    get_puppy_name,
    get_value,
)

_config_keys_cache: TTLCache[tuple[object, list[str]]] = TTLCache()
_slash_catalog_cache: TTLCache[list[dict[str, str]]] = TTLCache()


def _sanitize_for_encoding(text: str) -> str:
    """Remove or replace characters that can't be safely encoded.

    Handles lone surrogates (U+D800-U+DFFF, invalid in UTF-8) and other
    problematic sequences from Windows copy-paste.
    """
    try:
        text.encode("utf-8")
        return text  # String is already valid UTF-8
    except UnicodeEncodeError:
        pass

    try:
        return text.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Last resort: filter out all non-BMP and surrogate characters
        return "".join(
            char
            for char in text
            if ord(char) < 0xD800 or (ord(char) > 0xDFFF and ord(char) < 0x10000)
        )


def _strip_variation_selectors(text: str) -> str:
    """Remove variation selectors (U+FE00-FE0F) from text.

    These invisible characters modify emoji rendering but cause width
    calculation mismatches between line editors and terminal emulators.
    """
    return "".join(c for c in text if not (0xFE00 <= ord(c) <= 0xFE0F))


def _normalize_emoji_spacing(text: str) -> str:
    """Normalize emoji spacing for consistent terminal rendering.

    Some emojis have East Asian Width 'N' (Neutral) which terminals render
    inconsistently. This adds a space after such emojis to prevent
    the following character from overlapping.
    """
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


# ---------------------------------------------------------------------------
# Completers
# ---------------------------------------------------------------------------


class SetCompleter(Completer):
    def __init__(self, trigger: str = "/set"):
        self.trigger = trigger

    def get_completions(self, document, complete_event):
        cursor_position = document.cursor_position
        text_before_cursor = document.text_before_cursor
        stripped_text_for_trigger_check = text_before_cursor.lstrip()

        # If user types just /set (no space), suggest adding a space
        if stripped_text_for_trigger_check == self.trigger:
            yield Completion(
                self.trigger + " ",
                start_position=-len(self.trigger),
                display=self.trigger + " ",
                display_meta="set config key",
            )
            return

        # Require a space after /set before showing completions
        if not stripped_text_for_trigger_check.startswith(self.trigger + " "):
            return

        # Determine the part of the text that is relevant for this completer
        # (handles cases like "  /set foo" where the trigger isn't at index 0)
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

        cached_getter, config_keys = _config_keys_cache.get(
            lambda: (get_config_keys, sorted(get_config_keys()))
        )
        if cached_getter is not get_config_keys:
            _config_keys_cache.clear()
            _, config_keys = _config_keys_cache.get(
                lambda: (get_config_keys, sorted(get_config_keys()))
            )

        for key in config_keys:
            if key in {"model", "puppy_token"} | MODEL_SETTINGS_ONLY_KEYS:
                continue
            if key.startswith(text_after_trigger):
                prev_value = get_value(key)
                value_part = f" = {prev_value}" if prev_value is not None else " = "
                completion_text = f"{key}{value_part}"

                yield Completion(
                    completion_text,
                    start_position=start_position,
                    display_meta="",
                )


class CDCompleter(Completer):
    def __init__(self, trigger: str = "/cd"):
        self.trigger = trigger

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor
        stripped_text = text_before_cursor.lstrip()

        # Require a space after /cd before showing completions
        if not stripped_text.startswith(self.trigger + " "):
            return

        # Extract the directory path after /cd and space (up to cursor)
        trigger_pos = text_before_cursor.find(self.trigger)
        trigger_end = trigger_pos + len(self.trigger) + 1  # +1 for the space
        dir_path = text_before_cursor[trigger_end:].lstrip()
        start_position = -(len(dir_path))

        try:
            # Treat a bare `~` as `~/` so we complete inside the home
            # directory, not the parent containing the username folder.
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
    """A completer that triggers on '/agent' to show available agents."""

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

        try:
            from code_puppy.command_line.pin_command_completion import load_agent_names

            agent_names = load_agent_names()
        except Exception:
            return

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


def _read_slash_catalog() -> list[dict[str, str]]:
    """Load registered and plugin command help without filtering or reordering."""
    catalog = []
    for cmd in get_unique_commands():
        catalog.append(
            {"text": cmd.name, "display": f"/{cmd.name}", "meta": cmd.description}
        )
        catalog.extend(
            {
                "text": alias,
                "display": f"/{alias} (alias for /{cmd.name})",
                "meta": cmd.description,
            }
            for alias in cmd.aliases
        )
    try:
        from code_puppy import callbacks, plugins

        plugins.load_plugin_callbacks()
        for result in callbacks.on_custom_command_help():
            items = result if isinstance(result, list) else [result]
            for item in items:
                if isinstance(item, tuple) and len(item) == 2:
                    name, description = map(str, item)
                    catalog.append(
                        {"text": name, "display": f"/{name}", "meta": description}
                    )
    except Exception:
        pass
    return catalog


class SlashCompleter(Completer):
    """Completes '/' at the beginning of the line with all slash commands."""

    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor
        stripped_text = text_before_cursor.lstrip()

        # Only trigger if '/' is the first non-whitespace character
        if not stripped_text.startswith("/"):
            return

        # A bare slash intentionally yields every command so the menu
        # appears immediately while typing.
        partial = stripped_text[1:]
        start_position = -len(partial)

        try:
            catalog = _slash_catalog_cache.get(_read_slash_catalog)
        except Exception:
            return
        partial_lower = partial.lower()
        all_completions = [
            item for item in catalog if item["text"].lower().startswith(partial_lower)
        ]
        all_completions.sort(key=lambda item: item["text"].lower())

        # Strip variation selectors (U+FE00-FE0F) from display strings: they
        # cause width mismatches -> phantom spaces (e.g. in the /judges menu).
        for completion in all_completions:
            yield Completion(
                completion["text"],
                start_position=start_position,
                display=_strip_variation_selectors(completion["display"]),
                display_meta=_strip_variation_selectors(completion["meta"]),
            )


def build_completer_stack() -> Completer:
    """The full REPL completer stack (single source of truth)."""
    from code_puppy.callbacks import get_completion_providers
    from code_puppy.command_line.file_path_completion import FilePathCompleter
    from code_puppy.command_line.load_context_completion import LoadContextCompleter
    from code_puppy.command_line.mcp_completion import MCPCompleter
    from code_puppy.command_line.model_picker_completion import ModelNameCompleter
    from code_puppy.command_line.pin_command_completion import (
        PinCompleter,
        UnpinCompleter,
    )
    from code_puppy.command_line.skills_completion import SkillsCompleter

    return merge_completers(
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
            ModelNameCompleter(trigger="/fork", prefix="@"),
            MCPCompleter(trigger="/mcp"),
            SkillsCompleter(trigger="/skills"),
            *get_completion_providers(),
            SlashCompleter(),
        ]
    )


# ---------------------------------------------------------------------------
# Prompt prefix
# ---------------------------------------------------------------------------

# REPL prompt palette (source of truth -- the bottom-bar prompt converts
# these to raw SGR via messaging.prompt_prefix_style). IMPORTANT: use
# `ansi*` names -- bare names resolve to truecolor hex and IGNORE the terminal
# palette, so /theme's OSC remap couldn't restyle the prompt.
PROMPT_STYLES = {
    "puppy": "bold ansimagenta",
    "agent": "bold ansiblue",
    "model": "bold ansicyan",
    "cwd": "bold ansigreen",
    "arrow": "bold ansiyellow",
}


#: Columns kept clear to the right of the prompt so there is always room to
#: type. Below this the prompt is not a prompt, it is a wall.
_MIN_TYPING_ROOM = 24

#: Give up and render a bare arrow rather than a shredded prefix.
_MIN_PREFIX_BUDGET = 8


def _middle_truncate(text: str, limit: int) -> str:
    """Shorten ``text`` to ``limit`` cells, dropping from the middle.

    Model ids carry their meaning at both ends (``openrouter/...`` and
    ``...-opus-4-8``), so a trailing ellipsis throws away the half that
    tells you which model is actually spending your money.
    """
    if limit <= 0:
        return ""
    if cell_len(text) <= limit:
        return text
    if limit <= 1:
        return "…"
    keep = limit - 1
    head = (keep + 1) // 2
    tail = keep - head
    return text[:head] + "…" + (text[len(text) - tail :] if tail else "")


def _fit_prompt_parts(
    puppy: str,
    agent_display: str,
    model_display: str,
    cwd_display: str,
    base: str,
    columns: int,
) -> tuple:
    """Trim prompt segments to fit ``columns``, most droppable first.

    ``platform_utils.startup_banner_text`` already budgets the *banner* by
    width; the prompt had no such budget, so at 80 columns -- the most
    common terminal width there is -- the line wrapped and split the
    ``>>>`` marker across two rows, leaving the user typing after a lone
    ``>``. Reduce in priority order instead: the arrow always survives,
    then the model (you need to know what you are paying for), then the
    agent, then cwd, then the puppy name.

    Returns ``(puppy, agent_display, model_display, cwd_display)`` with
    dropped segments as empty strings.
    """
    budget = columns - _MIN_TYPING_ROOM - cell_len(base)
    if budget < _MIN_PREFIX_BUDGET:
        return "", "", "", ""

    def width(p: str, a: str, m: str, c: str) -> int:
        total = 0
        if p:
            total += cell_len(p) + 1
        if a:
            total += cell_len(a) + 3  # "[" + "] "
        if m:
            total += cell_len(m) + 1
        if c:
            total += cell_len(c) + 3  # "(" + ") "
        return total

    if width(puppy, agent_display, model_display, cwd_display) <= budget:
        return puppy, agent_display, model_display, cwd_display

    # 1. cwd to its basename -- the leaf is the part you actually read.
    if cwd_display:
        leaf = cwd_display.rstrip("/").rsplit("/", 1)[-1] or cwd_display
        if leaf != cwd_display:
            cwd_display = "…/" + leaf
            if width(puppy, agent_display, model_display, cwd_display) <= budget:
                return puppy, agent_display, model_display, cwd_display

    # 2. Drop the puppy name -- decorative once the line is under pressure.
    if puppy:
        puppy = ""
        if width(puppy, agent_display, model_display, cwd_display) <= budget:
            return puppy, agent_display, model_display, cwd_display

    # 3. Drop cwd entirely.
    if cwd_display:
        cwd_display = ""
        if width(puppy, agent_display, model_display, cwd_display) <= budget:
            return puppy, agent_display, model_display, cwd_display

    # 4. Drop the agent label before mangling the model id.
    if agent_display:
        agent_display = ""
        if width(puppy, agent_display, model_display, cwd_display) <= budget:
            return puppy, agent_display, model_display, cwd_display

    # 5. Last resort: squeeze the model itself.
    if model_display:
        model_display = _middle_truncate(model_display, max(budget - 1, 0))

    return puppy, agent_display, model_display, cwd_display


def get_prompt_with_active_model(base: str = ">>> ") -> list:
    """Styled prompt fragments: puppy [agent] [model] (cwd) >>>.

    Returns a plain list of ``(style, text)`` tuples (the FormattedText
    shape without the class) for ``flatten_prompt_fragments``.

    Segments are fitted to the detected terminal width so the prompt never
    wraps and never splits its own arrow.

    The signature is deliberately frozen at ``(base)``. Shipped plugins
    (``statusline``, ``prompt_newline``) wrap this function with
    ``def patched(base=">>> ")`` and no ``**kwargs``, so adding a
    parameter here raises ``TypeError`` and takes the prompt out entirely
    for anyone running them. Width is detected inside instead; tests
    drive it by patching ``shutil.get_terminal_size``.
    """
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.command_line.model_picker_completion import get_active_model

    puppy = get_puppy_name()
    # When nothing is configured this is None - surface that explicitly as
    # [None] so the user immediately sees they need to /add_model.
    global_model = get_active_model()

    current_agent = get_current_agent()
    agent_display = current_agent.display_name if current_agent else "code-puppy"

    agent_model = None
    if current_agent and hasattr(current_agent, "get_model_name"):
        agent_model = current_agent.get_model_name()

    if agent_model and agent_model != global_model:
        model_display = f"[{global_model} \u2192 {agent_model}]"
    elif agent_model:
        model_display = f"[{agent_model}]"
    else:
        # global_model may be None -> renders as [None].
        model_display = f"[{global_model}]"

    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd_display = "~" + cwd[len(home) :]
    else:
        cwd_display = cwd

    columns = shutil.get_terminal_size(fallback=(80, 24)).columns

    agent_display = _normalize_emoji_spacing(agent_display)
    puppy, agent_display, model_display, cwd_display = _fit_prompt_parts(
        puppy, agent_display, model_display, str(cwd_display), base, columns
    )

    fragments = []
    if puppy:
        fragments.append(("class:puppy class:tui.header", f"{puppy}"))
        fragments.append(("", " "))
    if agent_display:
        fragments.append(("class:agent class:tui.label", f"[{agent_display}] "))
    if model_display:
        fragments.append(("class:model class:tui.title", model_display + " "))
    if cwd_display:
        fragments.append(("class:cwd class:tui.muted", "(" + cwd_display + ") "))
    fragments.append(("class:arrow class:tui.help-key", str(base)))
    return fragments
