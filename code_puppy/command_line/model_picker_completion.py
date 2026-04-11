import os
from typing import Iterable, Optional

from prompt_toolkit import Application, PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)
from code_puppy.config import get_global_model_name
from code_puppy.list_filtering import query_matches_text
from code_puppy.model_switching import set_model_and_reload_agent

MODEL_PICKER_PAGE_SIZE = 15


def load_model_names():
    """Load model names from the config that's fetched from the endpoint."""
    from code_puppy.model_factory import ModelFactory

    models_config = ModelFactory.load_config()
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

        # Filter model names based on what's typed after /model (case-insensitive)
        for model_name in self.model_names:
            if text_after_trigger and not query_matches_text(
                text_after_trigger, model_name
            ):
                continue  # Skip models that don't match the typed text

            meta = (
                "Model (selected)"
                if model_name.lower() == get_active_model().lower()
                else "Model"
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
    """Paginated interactive model picker for the /model command."""

    def __init__(self, model_names: Optional[list[str]] = None):
        self.model_names = (
            list(model_names) if model_names is not None else load_model_names()
        )
        self.current_model = get_active_model()
        self.filter_text = ""
        self.selected_index = 0
        self.page = 0
        self.page_size = MODEL_PICKER_PAGE_SIZE
        self.result: Optional[str] = None

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
    def visible_model_names(self) -> list[str]:
        if not self.filter_text:
            return self.model_names
        return [
            model_name
            for model_name in self.model_names
            if query_matches_text(self.filter_text, model_name)
        ]

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
        lines = [("bold cyan", " 🤖 Select Active Model")]
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

        lines.append(("fg:ansibrightblack", f"\n  Current: {self.current_model}\n\n"))

        for offset, model_name in enumerate(self.models_on_page):
            absolute_index = self.page_start + offset
            is_selected = absolute_index == self.selected_index
            is_current = model_name == self.current_model

            prefix = " › " if is_selected else "   "
            style = "fg:ansiwhite bold" if is_selected else "fg:ansibrightblack"
            lines.append((style, f"{prefix}{model_name}"))
            if is_current:
                lines.append(("fg:ansigreen", " (active)"))
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
        lines.append(("fg:ansiyellow", "  Esc  "))
        lines.append(("", "Cancel\n"))
        return lines

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

        app = Application(
            layout=Layout(Window(content=control, wrap_lines=True)),
            key_bindings=kb,
            full_screen=False,
        )
        await app.run_async()
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
