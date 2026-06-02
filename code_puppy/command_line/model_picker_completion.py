import os
import sys
import logging
from typing import Iterable, Optional

from prompt_toolkit import Application, PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from code_puppy.agents._key_listeners import suspended_key_listener
from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)
from code_puppy.config import get_global_model_name
from code_puppy.list_filtering import query_matches_text
from code_puppy.model_switching import set_model_and_reload_agent
from code_puppy.provider_credentials import (
    credential_display,
    credential_hint,
    required_env_var_for_model,
    save_credential,
)
from code_puppy.command_line.utils import safe_input

logger = logging.getLogger(__name__)

MODEL_PICKER_PAGE_SIZE = 15


def _load_models_config() -> dict:
    from code_puppy.model_factory import ModelFactory

    return ModelFactory.load_config()


def load_model_names():
    """Load model names from the config that's fetched from the endpoint."""
    models_config = _load_models_config()
    return list(models_config.keys())


def get_active_model():
    """
    Returns the active model from the config using get_model_name().
    This ensures consistency across the codebase by always using the config value.
    """
    return get_global_model_name()


def set_active_model(model_name: str):
    """
    Sets the active model name by updating the config (for persistence).
    """
    set_model_and_reload_agent(model_name)


class ModelNameCompleter(Completer):
    """
    A completer that triggers on '/model' to show available models from models.json.
    Only '/model' (not just '/') will trigger the dropdown.
    """

    def __init__(self, trigger: str = "/model"):
        self.trigger = trigger
        self.model_names = load_model_names()

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text
        cursor_position = document.cursor_position
        text_before_cursor = text[:cursor_position]

        # Only trigger if /model is at the very beginning of the line and has a space after it
        stripped_text = text_before_cursor.lstrip()
        if not stripped_text.startswith(self.trigger + " "):
            return

        # Find where /model actually starts (after any leading whitespace)
        symbol_pos = text_before_cursor.find(self.trigger)
        text_after_trigger = text_before_cursor[
            symbol_pos + len(self.trigger) + 1 :
        ].lstrip()
        start_position = -(len(text_after_trigger))

        from code_puppy.model_descriptions import get_model_description

        models_config = _load_models_config()

        # Filter model names based on what's typed after /model (case-insensitive)
        for model_name in self.model_names:
            if text_after_trigger and not query_matches_text(
                text_after_trigger, model_name
            ):
                continue  # Skip models that don't match the typed text

            description = get_model_description(models_config, model_name)
            active_model_name = get_active_model()
            if model_name.lower() == active_model_name.lower():
                short = (
                    description[:45] + "..." if len(description) > 48 else description
                )
                meta = f"✓ {short}"
            else:
                meta = (
                    description[:48] + "..." if len(description) > 51 else description
                )

            yield Completion(
                model_name,
                start_position=start_position,
                display=model_name,
                display_meta=meta,
            )


def _find_matching_model(rest: str, model_names: list[str]) -> Optional[str]:
    """
    Find the best matching model for the given input.

    Priority:
    1. Exact match (case-insensitive)
    2. Input starts with a model name (longest/most specific wins)
    3. Model starts with input (prefix/completion match, longest wins)
    """
    rest_lower = rest.lower()

    # First check for exact match
    for model in model_names:
        if rest_lower == model.lower():
            return model

    # Sort by length (longest first) so more specific matches win
    sorted_models = sorted(model_names, key=len, reverse=True)

    # Check if input starts with a model name (e.g. "gpt-5 tell me a joke")
    for model in sorted_models:
        model_lower = model.lower()
        if rest_lower.startswith(model_lower) and (
            len(rest_lower) == len(model_lower) or rest_lower[len(model_lower)] == " "
        ):
            return model

    # Check for prefix/completion match (input is partial model name)
    for model in sorted_models:
        if model.lower().startswith(rest_lower):
            return model

    # Fall back to the same fuzzy matcher used by the completer.
    for model in sorted_models:
        if query_matches_text(rest, model):
            return model

    return None


def update_model_in_input(text: str) -> Optional[str]:
    # If input starts with /model or /m and a model name, set model and strip it out
    content = text.strip()
    model_names = load_model_names()

    # Check for /model command (require space after /model, case-insensitive)
    if content.lower().startswith("/model "):
        # Find the actual /model command (case-insensitive)
        model_cmd = content.split(" ", 1)[0]  # Get the command part
        rest = content[len(model_cmd) :].strip()  # Remove the actual command

        # Find the best matching model
        model = _find_matching_model(rest, model_names)
        if model:
            # Found a matching model - now extract it properly
            set_active_model(model)

            # Find the actual model name in the original text (preserving case)
            # We need to find where the model ends in the original rest string
            model_end_idx = len(model)

            # Build the full command+model part to remove
            cmd_and_model_pattern = model_cmd + " " + rest[:model_end_idx]
            idx = text.find(cmd_and_model_pattern)
            if idx != -1:
                new_text = (
                    text[:idx] + text[idx + len(cmd_and_model_pattern) :]
                ).strip()
                return new_text
            return None

    # Check for /m command (case-insensitive)
    elif content.lower().startswith("/m ") and not content.lower().startswith(
        "/model "
    ):
        # Find the actual /m command (case-insensitive)
        m_cmd = content.split(" ", 1)[0]  # Get the command part
        rest = content[len(m_cmd) :].strip()  # Remove the actual command

        # Find the best matching model
        model = _find_matching_model(rest, model_names)
        if model:
            # Found a matching model - now extract it properly
            set_active_model(model)

            # Find the actual model name in the original text (preserving case)
            # We need to find where the model ends in the original rest string
            model_end_idx = len(model)

            # Build the full command+model part to remove
            # Handle space variations in the original text
            cmd_and_model_pattern = m_cmd + " " + rest[:model_end_idx]
            idx = text.find(cmd_and_model_pattern)
            if idx != -1:
                new_text = (
                    text[:idx] + text[idx + len(cmd_and_model_pattern) :]
                ).strip()
                return new_text
            return None

    return None


class ModelSelectionMenu:
    """Paginated interactive model picker.

    Used by ``/model`` and reused (with ``extra_options``) by the model
    pinning flows in the agent menu and the ``/pin_model`` slash command.

    The defaults are tuned so ``ModelSelectionMenu()`` reproduces the
    legacy ``/model`` picker output byte-for-byte.
    """

    def __init__(
        self,
        model_names: Optional[list[str]] = None,
        *,
        title: str = " 🤖 Select Active Model",
        current_model: Optional[str] = None,
        extra_options: Optional[list[tuple[str, str]]] = None,
        active_label: str = "(active)",
    ):
        self.model_names = (
            list(model_names) if model_names is not None else load_model_names()
        )
        # ``current_model`` falls back to ``get_active_model()`` so the
        # ``/model`` default behaviour is preserved when nothing is passed.
        self.current_model = (
            current_model if current_model is not None else get_active_model()
        )
        self.title = title
        self.active_label = active_label
        # Sentinel rows pinned at the top of the list, e.g.
        # ``[("(unpin)", "Reset to default model")]``. Selecting one
        # makes ``run_async`` return the value (e.g. ``"(unpin)"``).
        self.extra_options: list[tuple[str, str]] = list(extra_options or [])
        # Cached value -> description map. Used by ``_render`` to
        # classify rows as sentinel vs. model WITHOUT relying on the
        # (filtered) absolute index -- that misclassified real models
        # as sentinels when the filter hid the sentinel rows.
        self._extra_option_descriptions: dict[str, str] = dict(self.extra_options)
        self.filter_text = ""
        self.selected_index = 0
        self.page = 0
        self.page_size = MODEL_PICKER_PAGE_SIZE
        self.result: Optional[str] = None
        self.pending_credentials_edit: Optional[str] = None

        # Pre-select ``current_model`` if it's a visible row. This
        # covers both MODEL rows and SENTINEL rows (the pin flows
        # pass ``current_model = pinned or "(unpin)"`` so the
        # (unpin) sentinel gets pre-selected when the agent has no
        # pin, instead of falling back to the global active model).
        if self.current_model in self.visible_model_names:
            self.selected_index = self.visible_model_names.index(self.current_model)
            self.page = get_page_for_index(self.selected_index, self.page_size)

    @property
    def total_pages(self) -> int:
        return get_total_pages(len(self.visible_model_names), self.page_size)

    @property
    def page_start(self) -> int:
        start, _ = get_page_bounds(
            self.page, len(self.visible_model_names), self.page_size
        )
        return start

    @property
    def page_end(self) -> int:
        _, end = get_page_bounds(
            self.page, len(self.visible_model_names), self.page_size
        )
        return end

    @property
    def models_on_page(self) -> list[str]:
        return self.visible_model_names[self.page_start : self.page_end]

    @property
    def extra_option_values(self) -> list[str]:
        """Return just the sentinel values from ``extra_options``."""
        return [value for value, _ in self.extra_options]

    @property
    def extra_option_descriptions(self) -> dict[str, str]:
        """Map sentinel value -> description for rendering.

        Returns the cached dict built once in ``__init__`` so we don't
        rebuild it on every ``_render()`` call.
        """
        return self._extra_option_descriptions

    @property
    def visible_model_names(self) -> list[str]:
        """Return selectable entries: sentinel rows first, then models.

        Ordering is always ``matched sentinels`` (sentinels whose
        VALUE matches the filter, in the order given in
        ``extra_options``) followed by ``matched models`` (models
        whose name matches the filter, in the order given in
        ``model_names``). When there is no filter, all sentinels
        and all models are returned.

        IMPORTANT: the index of a row in this list is NOT a
        reliable way to tell whether it is a sentinel. When the
        filter hides some sentinel rows, real model rows slide
        into low indices and the index-based classification used
        by the old buggy code misclassified them. Callers that
        need to know whether a value is a sentinel MUST check
        ``value in self._extra_option_descriptions`` -- the value
        membership test, not the (filtered) index.

        When ``extra_options`` is empty (the default), the result
        is identical to the original ``/model`` picker behaviour.
        """
        extras = self.extra_option_values
        if not self.filter_text:
            return list(extras) + list(self.model_names)
        matched_extras = [
            value for value in extras if query_matches_text(self.filter_text, value)
        ]
        matched_models = [
            model_name
            for model_name in self.model_names
            if query_matches_text(self.filter_text, model_name)
        ]
        return matched_extras + matched_models

    def _get_selected_model_name(self) -> Optional[str]:
        if 0 <= self.selected_index < len(self.visible_model_names):
            return self.visible_model_names[self.selected_index]
        return None

    def _ensure_selection_visible(self) -> None:
        self.page = ensure_visible_page(
            self.selected_index,
            self.page,
            len(self.visible_model_names),
            self.page_size,
        )

    def _set_filter_text(self, value: str) -> None:
        selected_model = self._get_selected_model_name()
        self.filter_text = value
        visible_models = self.visible_model_names
        if not visible_models:
            self.selected_index = 0
            self.page = 0
            return

        if selected_model and selected_model in visible_models:
            self.selected_index = visible_models.index(selected_model)
        elif self.current_model in visible_models:
            self.selected_index = visible_models.index(self.current_model)
        else:
            self.selected_index = 0
        self._ensure_selection_visible()

    def _append_filter_char(self, value: str) -> None:
        self._set_filter_text(self.filter_text + value)

    def _delete_filter_char(self) -> None:
        if self.filter_text:
            self._set_filter_text(self.filter_text[:-1])

    def _accept_selection(self) -> bool:
        """Store the currently selected visible model if one is available."""
        selected_model = self._get_selected_model_name()
        if selected_model is None:
            return False
        self.result = selected_model
        return True

    def _move_up(self) -> None:
        if self.selected_index > 0:
            self.selected_index -= 1
            self._ensure_selection_visible()

    def _move_down(self) -> None:
        if self.selected_index < len(self.visible_model_names) - 1:
            self.selected_index += 1
            self._ensure_selection_visible()

    def _page_up(self) -> None:
        if self.page > 0:
            self.page -= 1
            self.selected_index = self.page_start

    def _page_down(self) -> None:
        if self.page < self.total_pages - 1:
            self.page += 1
            self.selected_index = self.page_start

    def _render(self):
        lines = [("bold cyan", self.title)]
        filter_label = self.filter_text or "type to filter"
        lines.append(("fg:ansibrightblack", f"\n  Filter: {filter_label}"))
        if self.total_pages > 1:
            lines.append(
                ("fg:ansibrightblack", f"  (Page {self.page + 1}/{self.total_pages})")
            )
        lines.append(("", "\n"))

        if not self.visible_model_names:
            empty_message = (
                "No models match the current filter."
                if self.filter_text
                else "No models available."
            )
            lines.append(("fg:ansiyellow", f"\n  {empty_message}\n"))
            lines.append(("fg:ansibrightblack", "  Type  "))
            lines.append(("", "Adjust filter\n"))
            lines.append(("fg:ansibrightblack", "  Backspace  "))
            lines.append(("", "Delete filter char\n"))
            if self.filter_text:
                lines.append(("fg:ansibrightblack", "  Ctrl+U  "))
                lines.append(("", "Clear filter\n"))
            lines.append(("fg:ansiyellow", "  Esc  "))
            lines.append(("", "Exit\n"))
            return lines

        # The "Current:" header. When ``current_model`` is a sentinel
        # value (e.g. the pin flow passes ``"(unpin)"`` to mean
        # "no pin / default"), printing the raw sentinel would be
        # confusing -- show a friendly label instead.
        if self.current_model in self._extra_option_descriptions:
            current_header = "(no pin / default)"
        else:
            current_header = self.current_model
        lines.append(("fg:ansibrightblack", f"\n  Current: {current_header}\n\n"))

        for offset, value in enumerate(self.models_on_page):
            absolute_index = self.page_start + offset
            is_selected = absolute_index == self.selected_index
            # Classify by VALUE membership, not by (filtered)
            # absolute index. When the filter hides the sentinel
            # rows, real model rows slide into low indices and would
            # otherwise be misclassified as sentinels -- losing
            # their active/pinned label.
            is_sentinel = value in self._extra_option_descriptions

            prefix = " › " if is_selected else "   "
            style = "fg:ansiwhite bold" if is_selected else "fg:ansibrightblack"
            lines.append((style, f"{prefix}{value}"))
            if is_sentinel:
                # Sentinel row -- show its description (e.g.
                # "(unpin)  Reset to default model"). These are
                # actions, not models, so we never append the
                # ``active_label`` (e.g. "(pinned)" would read
                # "(unpin) (pinned)" which is nonsense).
                #
                # If the sentinel value is the CURRENT state
                # (pin flows pass ``current_model = pinned or
                # "(unpin)"``), mark it with a "(current)" suffix
                # so the user can see the existing state without
                # needing to read the header.
                if value == self.current_model:
                    lines.append(("fg:ansigreen", " (current)"))
                description = self._extra_option_descriptions.get(value, "")
                if description:
                    lines.append(("fg:ansibrightblack", f"  {description}"))
            elif (
                value == self.current_model
                and self.current_model not in self._extra_option_descriptions
            ):
                # Model row that matches the current model.
                # Guarded so we don't double-label a row whose
                # value happens to coincide with a sentinel value.
                lines.append(("fg:ansigreen", f" {self.active_label}"))
            lines.append(("", "\n"))

        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓  "))
        lines.append(("", "Navigate\n"))
        if self.total_pages > 1:
            lines.append(("fg:ansibrightblack", "  PgUp/PgDn  "))
            lines.append(("", "Change page\n"))
        lines.append(("fg:ansibrightblack", "  Type  "))
        lines.append(("", "Filter models\n"))
        lines.append(("fg:ansibrightblack", "  Backspace  "))
        lines.append(("", "Delete filter char\n"))
        lines.append(("fg:ansibrightblack", "  Ctrl+U  "))
        lines.append(("", "Clear filter\n"))
        lines.append(("fg:ansigreen", "  Enter  "))
        lines.append(("", "Select model\n"))
        lines.append(("fg:cyan", "  e  "))
        lines.append(("", "Edit credentials\n"))
        lines.append(("fg:ansiyellow", "  Esc  "))
        lines.append(("", "Cancel\n"))
        return lines

    def _edit_credentials_for_model(self, model_name: str) -> None:
        """Prompt user to edit the credential for a specific model.

        Looks up the required env var for the model via the merged config
        and then lets the user update it (or skip).
        """
        env_var = required_env_var_for_model(model_name)
        if not env_var:
            logger.warning("No env var found for model: %s", model_name)
            return
        status = credential_display(env_var)
        hint = credential_hint(env_var)
        logger.info(
            "Editing credential %s for model %s (status: %s)",
            env_var,
            model_name,
            status,
        )
        print(f"\n🔑 {model_name} credential: {env_var} ({status})")
        if hint:
            print(f"   {hint}")
        try:
            value = safe_input("   New value (or Enter to skip): ")
            if value:
                save_credential(env_var, value)
                print(f"✅ Saved {env_var}")
                logger.info("Saved credential %s for model %s", env_var, model_name)
        except (KeyboardInterrupt, EOFError):
            logger.info("Credential editing cancelled by user")
            print("\n⚠️ Credential editing cancelled")

    async def run_async(self) -> Optional[str]:
        control = FormattedTextControl(lambda: self._render())
        kb = KeyBindings()

        def refresh() -> None:
            control.text = self._render()

        @kb.add("up")
        @kb.add("c-p")
        def _(event):
            self._move_up()
            refresh()
            event.app.invalidate()

        @kb.add("down")
        @kb.add("c-n")
        def _(event):
            self._move_down()
            refresh()
            event.app.invalidate()

        @kb.add("pageup")
        @kb.add("left")
        def _(event):
            self._page_up()
            refresh()
            event.app.invalidate()

        @kb.add("pagedown")
        @kb.add("right")
        def _(event):
            self._page_down()
            refresh()
            event.app.invalidate()

        @kb.add("backspace")
        def _(event):
            if not self.filter_text:
                return
            self._delete_filter_char()
            refresh()
            event.app.invalidate()

        @kb.add("c-u")
        def _(event):
            if not self.filter_text:
                return
            self._set_filter_text("")
            refresh()
            event.app.invalidate()

        @kb.add("e")
        def _(event):
            """Edit credentials for the selected model."""
            selected = self._get_selected_model_name()
            if not selected:
                logger.debug("No model selected for credential editing")
                return
            env_var = required_env_var_for_model(selected)
            if not env_var:
                logger.debug("No env var required for model: %s", selected)
                return
            logger.info("User requested credential edit for model: %s", selected)
            self.pending_credentials_edit = selected
            event.app.exit()

        @kb.add("<any>")
        def _(event):
            if not event.data or not event.data.isprintable():
                return
            self._append_filter_char(event.data)
            refresh()
            event.app.invalidate()

        @kb.add("enter")
        def _(event):
            if not self._accept_selection():
                return
            event.app.exit()

        @kb.add("escape")
        @kb.add("c-c")
        def _(event):
            self.result = None
            event.app.exit()

        while True:
            # Enter alternate screen buffer for this session
            sys.stdout.write("\033[?1049h")  # Enter alternate buffer
            sys.stdout.write("\033[2J\033[H")  # Clear and home
            sys.stdout.flush()

            # Create a fresh Application each iteration — reusing a
            # prompt_toolkit Application after exit() is unreliable
            app = Application(
                layout=Layout(Window(content=control, wrap_lines=True)),
                key_bindings=kb,
                full_screen=False,
            )
            # Suspend the background key listener for the duration of
            # this picker iteration. ``suspended_key_listener()`` is a
            # reentrant context manager that is a no-op when no
            # listener is active, so this is safe in tests and in
            # flows that don't spawn a listener (e.g. legacy
            # ``/model``). When the listener IS active (the agent pin
            # flow, the ``/pin_model`` slash command, or a re-entrant
            # picker run after credential editing), suspending it
            # gives prompt_toolkit exclusive ownership of stdin --
            # otherwise arrow keys behave erratically and
            # prompt_toolkit emits "your terminal doesn't support
            # cursor position requests (CPR)".
            #
            # We enter the suspension INSIDE the ``while True`` loop
            # so each picker iteration (including the ones
            # restarted by credential editing) gets its own
            # clean listener suspension; we also exit it BEFORE
            # ``_edit_credentials_for_model`` runs so the
            # credential prompt isn't held under a stale listener
            # suspension.
            with suspended_key_listener():
                await app.run_async()

            # Exit alternate screen buffer
            sys.stdout.write("\033[?1049l")  # Exit alternate buffer
            sys.stdout.flush()

            # Handle credential editing outside the event loop
            if self.pending_credentials_edit:
                model_name = self.pending_credentials_edit
                self.pending_credentials_edit = None
                logger.info("Editing credentials for model: %s", model_name)
                self._edit_credentials_for_model(model_name)
                logger.info("Credential edit completed, restarting application")
                continue  # Restart the application

            return self.result


def _build_legacy_picker_choices(
    model_names: list[str], current_model: str
) -> list[str]:
    """Build simple picker labels for test and non-interactive fallback paths."""
    choices = []
    for model_name in model_names:
        suffix = " (current)" if model_name == current_model else ""
        choices.append(f"{model_name}{suffix}")
    return choices


def _normalize_legacy_picker_choice(choice: str) -> str:
    """Extract the model name from a legacy picker label."""
    return choice.removesuffix(" (current)")


async def interactive_model_picker() -> Optional[str]:
    """Run the paginated interactive model picker used by /model."""
    from code_puppy.tools.command_runner import set_awaiting_user_input

    set_awaiting_user_input(True)
    try:
        try:
            return await ModelSelectionMenu().run_async()
        except EOFError:
            model_names = load_model_names()
            current_model = get_active_model()
            choices = _build_legacy_picker_choices(model_names, current_model)
            if not choices:
                return None

            from code_puppy.tools.common import arrow_select_async

            try:
                selected = await arrow_select_async("Select Active Model", choices)
            except KeyboardInterrupt:
                return None
            return _normalize_legacy_picker_choice(selected)
    finally:
        set_awaiting_user_input(False)


async def get_input_with_model_completion(
    prompt_str: str = ">>> ",
    trigger: str = "/model",
    history_file: Optional[str] = None,
) -> str:
    history = FileHistory(os.path.expanduser(history_file)) if history_file else None
    session = PromptSession(
        completer=ModelNameCompleter(trigger),
        history=history,
        complete_while_typing=True,
    )
    text = await session.prompt_async(prompt_str)
    possibly_stripped = update_model_in_input(text)
    if possibly_stripped is not None:
        return possibly_stripped
    return text
