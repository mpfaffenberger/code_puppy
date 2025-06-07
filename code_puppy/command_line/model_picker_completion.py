import json
import os
from typing import Iterable, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory

from code_puppy.config import get_model_name, set_model_name

MODELS_JSON_PATH = os.environ.get("MODELS_JSON_PATH")
if not MODELS_JSON_PATH:
    MODELS_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "models.json")
    MODELS_JSON_PATH = os.path.abspath(MODELS_JSON_PATH)


def load_model_names():
    with open(MODELS_JSON_PATH, "r") as f:
        models = json.load(f)
    return list(models.keys())


def get_active_model():
    """
    Returns the active model from the config using get_model_name().
    This ensures consistency across the codebase by always using the config value.
    """
    return get_model_name()


def set_active_model(model_name: str):
    """
    Sets the active model name by updating both config (for persistence)
    and env (for process lifetime override).
    """
    set_model_name(model_name)
    os.environ["MODEL_NAME"] = model_name.strip()
    # Reload agent globally
    try:
        from code_puppy.agent import reload_code_generation_agent

        reload_code_generation_agent()  # This will reload dynamically everywhere
    except Exception:
        pass  # If reload fails, agent will still be switched next interpreter run


class ModelNameCompleter(Completer):
    """
    A completer that triggers on '~m' to show available models from models.json.
    Only '~m' (not just '~') will trigger the dropdown.
    """

    def __init__(self, trigger: str = "~m"):
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
    # If input starts with ~m and a model name, set model and strip it out
    content = text.strip()
    if content.startswith("~m"):
        rest = content[2:].strip()
        for model in load_model_names():
            if rest == model:
                set_active_model(model)
                # Remove ~mmodel from the input
                idx = text.find("~m" + model)
                if idx != -1:
                    new_text = (text[:idx] + text[idx + len("~m" + model) :]).strip()
                    return new_text
    return None


async def get_input_with_model_completion(
    prompt_str: str = ">>> ", trigger: str = "~m", history_file: Optional[str] = None
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
