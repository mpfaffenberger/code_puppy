from typing import Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


def load_agent_names():
    """Load all available agent names (both built-in and JSON agents)."""
    agents = set()

    # Get built-in agents
    try:
        from code_puppy.agents.agent_manager import get_agent_descriptions

        builtin_agents = get_agent_descriptions()
        agents.update(builtin_agents.keys())
    except Exception:
        pass

    # Get JSON agents
    try:
        from code_puppy.agents.json_agent import discover_json_agents

        json_agents = discover_json_agents()
        agents.update(json_agents.keys())
    except Exception:
        pass

    return sorted(list(agents))


def load_model_names():
    """Load model names from the config."""
    try:
        from code_puppy.command_line.model_picker_completion import (
            load_model_names as load_models,
        )

        return load_models()
    except Exception:
        return []


class PinCompleter(Completer):
    """
    A completer that triggers on '/pin_model' to show available agents
    and models for pinning a model to an agent.

    Usage: /pin_model <agent-name> <model-name>
    """

    def __init__(self, trigger: str = "/pin_model"):
        self.trigger = trigger

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text
        cursor_position = document.cursor_position
        text_before_cursor = text[:cursor_position]

        # Only trigger if /pin_model is at the very beginning of the line and has a space after it
        stripped_text = text_before_cursor.lstrip()
        if not stripped_text.startswith(self.trigger + " "):
            return

        # Find where /pin_model actually starts (after any leading whitespace)
        trigger_pos = text_before_cursor.find(self.trigger)

        # Get the command part (everything after the trigger and space)
        command_part = text_before_cursor[
            trigger_pos + len(self.trigger) + 1 :
        ].lstrip()

        # Check if we're positioned at the very end (cursor at end of text)
        cursor_at_end = cursor_position == len(text)

        # Better tokenization: split on spaces, but keep track of cursor position
        tokens = command_part.split() if command_part.strip() else []

        # Case 1: No arguments yet - complete agent names
        if len(tokens) == 0:
            agent_names = load_agent_names()
            for agent_name in agent_names:
                yield Completion(
                    agent_name,
                    start_position=-len(command_part),
                    display=agent_name,
                    display_meta="Agent",
                )

        # Case 2: Completing first argument (agent name)
        elif len(tokens) == 1:
            # Check cursor position to determine if we're still typing agent or ready for model
            partial_agent = tokens[0]

            # If we have exactly one token and the cursor is after it (with space),
            # we should show model completions
            if (
                command_part.endswith(" ")
                and cursor_at_end
                and text_before_cursor.endswith(" ")
            ):
                # User has typed agent + space, show all models
                model_names = load_model_names()
                for model_name in model_names:
                    yield Completion(
                        model_name,
                        start_position=0,  # Insert at cursor position
                        display=model_name,
                        display_meta="Model",
                    )
            else:
                # Still typing agent name, show agent completions
                agent_names = load_agent_names()
                start_pos = -(len(partial_agent))

                for agent_name in agent_names:
                    if agent_name.startswith(partial_agent):
                        yield Completion(
                            agent_name,
                            start_position=start_pos,
                            display=agent_name,
                            display_meta="Agent",
                        )

        # Case 3: Completing second argument (model name)
        elif len(tokens) == 2:
            # We're typing the model name
            model_names = load_model_names()
            partial_model = tokens[1]

            # If partial model is empty (shouldn't happen with split), show all models
            if not partial_model:
                for model_name in model_names:
                    yield Completion(
                        model_name,
                        start_position=0,
                        display=model_name,
                        display_meta="Model",
                    )
            else:
                # Filter models based on what the user has typed
                start_pos = -(len(partial_model))

                for model_name in model_names:
                    if model_name.startswith(partial_model):
                        yield Completion(
                            model_name,
                            start_position=start_pos,
                            display=model_name,
                            display_meta="Model",
                        )

        # Case 4: Have both agent and model - no completion needed
        else:
            return
