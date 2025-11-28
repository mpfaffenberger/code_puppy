import os
from typing import Iterable, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory

from code_puppy.config import get_global_model_name, set_model_name
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
    return get_global_model_name()


def set_active_model(model_name: str):
    """
    Sets the active model name by updating the config (for persistence).
    """
    from code_puppy.messaging import emit_info, emit_warning

    set_model_name(model_name)
    # Reload the currently active agent so the new model takes effect immediately
    try:
        from code_puppy.agents import get_current_agent

        current_agent = get_current_agent()
        # JSON agents may need to refresh their config before reload
        if hasattr(current_agent, "refresh_config"):
            try:
                current_agent.refresh_config()
            except Exception:
                # Non-fatal, continue to reload
                ...
        current_agent.reload_code_generation_agent()
        emit_info("Active agent reloaded")
    except Exception as e:
        emit_warning(f"Model changed but agent reload failed: {e}")


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
            if text_after_trigger and not model_name.lower().startswith(
                text_after_trigger.lower()
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


def update_model_in_input(text: str) -> Optional[str]:
    # If input starts with /model or /m and a model name, set model and strip it out
    content = text.strip()
    model_names = load_model_names()

    # Check for /model command (require space after /model, case-insensitive)
    if content.lower().startswith("/model "):
        # Find the actual /model command (case-insensitive)
        model_cmd = content.split(" ", 1)[0]  # Get the command part
        rest = content[len(model_cmd) :].strip()  # Remove the actual command

        # Look for a model name at the start of rest (case-insensitive)
        for model in model_names:
            if rest.lower().startswith(model.lower()):
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

        # Look for a model name at the start of rest (case-insensitive)
        for model in model_names:
            if rest.lower().startswith(model.lower()):
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
