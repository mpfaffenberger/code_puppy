import os
from typing import Iterable, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory

from code_puppy.config import get_model_name, set_model_name
from code_puppy.model_factory import ModelFactory


def load_model_names():
    """Load model names from the config that's fetched from the endpoint."""
    models_config = ModelFactory.load_config()
    return list(models_config.keys())


def get_active_model():
    """
    Returns the active model from the config using get_model_name().
    This ensures consistency across the codebase by always using the config value.
    """
    return get_model_name()


def set_active_model(model_name: str):
    """
    Sets the active model name by updating the config (for persistence).
    """
    set_model_name(model_name)
    # Reload agent globally
    try:
        from code_puppy.agent import reload_code_generation_agent

        reload_code_generation_agent()  # This will reload dynamically everywhere
    except Exception:
        pass  # If reload fails, agent will still be switched next interpreter run


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
        if self.trigger not in text_before_cursor:
            return
        symbol_pos = text_before_cursor.rfind(self.trigger)
        text_after_trigger = text_before_cursor[symbol_pos + len(self.trigger) :]
        start_position = -(len(text_after_trigger))
        for model_name in self.model_names:
            meta = "Model (selected)" if model_name == get_active_model() else "Model"
            yield Completion(
                model_name,
                start_position=start_position,
                display=model_name,
                display_meta=meta,
            )


def update_model_in_input(text: str) -> Optional[str]:
    # If input starts with /model or /m and a model name, set model and strip it out
    content = text.strip()

    # Check for /model command
    if content.startswith("/model"):
        rest = content[6:].strip()  # Remove '/model'
        for model in load_model_names():
            if rest == model:
                set_active_model(model)
                # Remove /model from the input
                idx = text.find("/model" + model)
                if idx != -1:
                    new_text = (
                        text[:idx] + text[idx + len("/model" + model) :]
                    ).strip()
                    return new_text

    # Check for /m command
    elif content.startswith("/m "):
        rest = content[3:].strip()  # Remove '/m '
        for model in load_model_names():
            if rest == model:
                set_active_model(model)
                # Remove /m from the input
                idx = text.find("/m " + model)
                if idx != -1:
                    new_text = (text[:idx] + text[idx + len("/m " + model) :]).strip()
                    return new_text

    return None


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
