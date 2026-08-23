import asyncio
import logging
import os
from typing import Iterable, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from termflow.tui import MenuBuilder, MenuItem
from termflow.tui.menu import MenuResult

from code_puppy.callbacks import on_prompt_toolkit_style
from code_puppy.command_line.completion_cache import TTLCache
from code_puppy.command_line.menu_session import menu_session
from code_puppy.command_line.tui_style import themed
from code_puppy.command_line.utils import safe_input
from code_puppy.config import get_global_model_name
from code_puppy.list_filtering import query_matches_text
from code_puppy.model_switching import set_model_and_reload_agent
from code_puppy.provider_credentials import (
    credential_display,
    credential_hint,
    required_env_var_for_model,
    save_credential,
)

logger = logging.getLogger(__name__)

MODEL_PICKER_PAGE_SIZE = 15
_models_config_cache: TTLCache[dict] = TTLCache()


def _read_models_config() -> dict:
    from code_puppy.model_factory import ModelFactory

    return ModelFactory.load_config()


def _load_models_config() -> dict:
    """Return the merged model config, refreshing it after a short TTL."""
    return _models_config_cache.get(_read_models_config)


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
    A completer that triggers on '/model' to show available models from the
    merged model config (bundled models.json + extra_models.json + OAuth
    model files + plugin models). Only '/model' (not just '/') will trigger
    the dropdown.

    When ``prefix`` is set (e.g. ``"@"``), it also matches patterns like
    ``/fork @agent @model`` — the text after the last ``@`` following the
    trigger is used for filtering.
    """

    def __init__(self, trigger: str = "/model", prefix: str = ""):
        self.trigger = trigger
        self.prefix = prefix

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text
        cursor_position = document.cursor_position
        text_before_cursor = text[:cursor_position]

        # Only trigger if /model (or trigger) is at the very beginning of the line
        stripped_text = text_before_cursor.lstrip()
        if not stripped_text.startswith(self.trigger + " "):
            return

        from code_puppy.model_descriptions import get_model_description

        models_config = _load_models_config()

        # --- Prefix mode (e.g. ``/fork @agent @mod``) ---
        if self.prefix:
            # Find trigger start
            trigger_pos = text_before_cursor.find(self.trigger)
            after_trigger = text_before_cursor[trigger_pos + len(self.trigger) + 1 :]
            # Find the LAST occurrence of prefix after the trigger
            last_prefix_pos = after_trigger.rfind(self.prefix)
            if last_prefix_pos < 0:
                return  # no prefix found at all
            text_after_prefix = after_trigger[last_prefix_pos + len(self.prefix) :]
            start_position = -len(text_after_prefix)
        else:
            # --- Standard /model mode ---
            symbol_pos = text_before_cursor.find(self.trigger)
            text_after_prefix = text_before_cursor[
                symbol_pos + len(self.trigger) + 1 :
            ].lstrip()
            start_position = -len(text_after_prefix)

        # Filter model names based on what's typed (case-insensitive).
        # Iterate the freshly loaded config -- NOT a snapshot from __init__:
        # long-lived completer stacks (persistent prompt caches them once)
        # must see models added later via /add_model -> extra_models.json.
        for model_name in models_config:
            if text_after_prefix and not query_matches_text(
                text_after_prefix, model_name
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
    """Paginated interactive model picker for the /model command.

    Built on termflow's MenuBuilder: type-to-filter (fuzzy, via
    ``query_matches_text``), pagination, Ctrl+E credential editing.
    """

    def __init__(self, model_names: Optional[list[str]] = None):
        self.model_names = (
            list(model_names) if model_names is not None else load_model_names()
        )
        self.current_model = get_active_model()
        self.result: Optional[str] = None
        self.pending_credentials_edit: Optional[str] = None

    def _items(self) -> list[MenuItem]:
        return [
            MenuItem(
                name,
                description="(active)" if name == self.current_model else "",
            )
            for name in self.model_names
        ]

    def build_menu(self, **overrides):
        """Build the termflow menu (overrides allow headless test driving)."""

        def _edit_credentials(_menu, item: MenuItem) -> Optional[MenuResult]:
            if not required_env_var_for_model(item.value):
                logger.debug("No env var required for model: %s", item.value)
                return None
            logger.info("User requested credential edit for model: %s", item.value)
            self.pending_credentials_edit = item.value
            return MenuResult(item=item)

        def _clear_filter(menu, _item: MenuItem) -> None:
            menu.clear_search()
            return None

        def _page_left(menu, _item: MenuItem) -> None:
            menu.page_up()
            return None

        def _page_right(menu, _item: MenuItem) -> None:
            menu.page_down()
            return None

        initial = 0
        if self.current_model in self.model_names:
            initial = self.model_names.index(self.current_model)

        builder = themed(
            MenuBuilder(f"Select Active Model  (current: {self.current_model})")
            .items(self._items())
            .searchable()
            .page_size(MODEL_PICKER_PAGE_SIZE)
            .initial_index(initial)
            .filter_fn(lambda query, item: query_matches_text(query, item.label))
            .on_key("ctrl-e", _edit_credentials)
            .on_key("ctrl-u", _clear_filter)
            .on_key("left", _page_left)
            .on_key("right", _page_right)
            .footer_hint(
                "Up/Down navigate - PgUp/PgDn page - type to filter - "
                "Ctrl+U clear - Ctrl+E credentials - Enter select - Esc cancel"
            )
        )
        for name, value in overrides.items():
            getattr(builder, name)(value)
        return builder.build()

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
        print(f"\n{model_name} credential: {env_var} ({status})")
        if hint:
            print(f"   {hint}")
        try:
            value = safe_input("   New value (or Enter to skip): ")
            if value:
                save_credential(env_var, value)
                print(f"Saved {env_var}")
                logger.info("Saved credential %s for model %s", env_var, model_name)
        except (KeyboardInterrupt, EOFError):
            logger.info("Credential editing cancelled by user")
            print("\nCredential editing cancelled")

    async def run_async(self) -> Optional[str]:
        while True:
            with menu_session():
                menu_result = await asyncio.to_thread(
                    self.build_menu(alt_screen=False).run
                )

            # Handle credential editing outside the menu loop (and outside
            # the session: safe_input needs the primary screen + cooked
            # mode), then reopen.
            if self.pending_credentials_edit:
                model_name = self.pending_credentials_edit
                self.pending_credentials_edit = None
                logger.info("Editing credentials for model: %s", model_name)
                self._edit_credentials_for_model(model_name)
                logger.info("Credential edit completed, restarting menu")
                continue

            if menu_result.cancelled or menu_result.item is None:
                self.result = None
            else:
                self.result = menu_result.item.value
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

    set_awaiting_user_input(True, notify=False)
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
        set_awaiting_user_input(False, notify=False)


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
        style=on_prompt_toolkit_style(),
    )
    text = await session.prompt_async(prompt_str)
    possibly_stripped = update_model_in_input(text)
    if possibly_stripped is not None:
        return possibly_stripped
    return text
