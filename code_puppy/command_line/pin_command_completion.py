import json
from typing import Iterable

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


def _get_json_agents_for_model(model_name: str) -> list:
    """Get JSON agents that have this model pinned in their JSON file."""
    try:
        from code_puppy.agents.json_agent import discover_json_agents

        pinned = []
        json_agents = discover_json_agents()
        for agent_name, agent_path in json_agents.items():
            try:
                with open(agent_path, "r") as f:
                    agent_data = json.load(f)
                    if agent_data.get("model") == model_name:
                        pinned.append(agent_name)
            except Exception:
                continue
        return pinned
    except Exception:
        return []


def _get_pinned_model_for_agent(agent_name: str) -> str | None:
    """Get the pinned model for an agent (config or JSON)."""
    # Check config first (for built-in agents)
    try:
        from code_puppy.config import get_agent_pinned_model

        pinned = get_agent_pinned_model(agent_name)
        if pinned:
            return pinned
    except Exception:
        pass

    # Check if it's a JSON agent with a model key
    try:
        from code_puppy.agents.json_agent import discover_json_agents

        json_agents = discover_json_agents()
        if agent_name in json_agents:
            with open(json_agents[agent_name], "r") as f:
                agent_data = json.load(f)
                return agent_data.get("model")
    except Exception:
        pass

    return None


def _get_model_display_meta(model_name: str) -> str:
    """Get display meta for a model showing pinned agents."""
    try:
        from code_puppy.config import get_agents_pinned_to_model

        pinned_agents = get_agents_pinned_to_model(model_name)
        pinned_agents.extend(_get_json_agents_for_model(model_name))
        pinned_agents = list(set(pinned_agents))  # Deduplicate

        if pinned_agents:
            agents_str = ", ".join(pinned_agents[:2])
            if len(pinned_agents) > 2:
                agents_str += "..."
            return f"Pinned: [{agents_str}]"
    except Exception:
        pass
    return "Model"


def _get_agent_display_meta(agent_name: str) -> str:
    """Get display meta for an agent showing pinned model."""
    pinned_model = _get_pinned_model_for_agent(agent_name)
    if pinned_model:
        return f"→ {pinned_model}"
    return "default"


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
                    display_meta=_get_agent_display_meta(agent_name),
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
                # Always show (unpin) option first
                yield Completion(
                    "(unpin)",
                    start_position=0,  # Insert at cursor position
                    display="(unpin)",
                    display_meta="Reset to default",
                )
                for model_name in model_names:
                    yield Completion(
                        model_name,
                        start_position=0,  # Insert at cursor position
                        display=model_name,
                        display_meta=_get_model_display_meta(model_name),
                    )
            else:
                # Still typing agent name, show agent completions
                agent_names = load_agent_names()
                start_pos = -(len(partial_agent))

                for agent_name in agent_names:
                    if agent_name.lower().startswith(partial_agent.lower()):
                        yield Completion(
                            agent_name,
                            start_position=start_pos,
                            display=agent_name,
                            display_meta=_get_agent_display_meta(agent_name),
                        )

        # Case 3: Completing second argument (model name)
        elif len(tokens) == 2:
            # We're typing the model name
            model_names = load_model_names()
            partial_model = tokens[1]

            # If partial model is empty (shouldn't happen with split), show all models + (unpin)
            if not partial_model:
                # Always show (unpin) option first
                yield Completion(
                    "(unpin)",
                    start_position=0,
                    display="(unpin)",
                    display_meta="Reset to default",
                )

                for model_name in model_names:
                    yield Completion(
                        model_name,
                        start_position=0,
                        display=model_name,
                        display_meta=_get_model_display_meta(model_name),
                    )
            else:
                # Filter based on what the user has typed
                start_pos = -(len(partial_model))

                # Check if (unpin) matches the partial input (case-insensitive)
                if "(unpin)".lower().startswith(partial_model.lower()):
                    yield Completion(
                        "(unpin)",
                        start_position=start_pos,
                        display="(unpin)",
                        display_meta="Reset to default",
                    )

                # Filter models based on what the user has typed (case-insensitive)
                for model_name in model_names:
                    if model_name.lower().startswith(partial_model.lower()):
                        yield Completion(
                            model_name,
                            start_position=start_pos,
                            display=model_name,
                            display_meta=_get_model_display_meta(model_name),
                        )

        # Case 4: Handle special case when user selected (unpin)
        elif len(tokens) >= 2 and tokens[1].lower() == "(unpin)".lower():
            # No completion needed, the (unpin) option is complete
            return

        # Case 5: Have both agent and model - no completion needed
        else:
            return


# Alias for backwards compatibility
PinModelCompleter = PinCompleter


class UnpinCompleter(Completer):
    """
    A completer that triggers on '/unpin' to show available agents
    for unpinning models from agents.

    Usage: /unpin <agent-name>
    """

    def __init__(self, trigger: str = "/unpin"):
        self.trigger = trigger

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        text = document.text
        cursor_position = document.cursor_position
        text_before_cursor = text[:cursor_position]

        # Only trigger if /unpin is at the very beginning of the line and has a space after it
        stripped_text = text_before_cursor.lstrip()
        if not stripped_text.startswith(self.trigger + " "):
            return

        # Find where /unpin actually starts (after any leading whitespace)
        trigger_pos = text_before_cursor.find(self.trigger)

        # Get the command part (everything after the trigger and space)
        command_part = text_before_cursor[
            trigger_pos + len(self.trigger) + 1 :
        ].lstrip()

        # Only complete agent names (single argument)
        tokens = command_part.split() if command_part.strip() else []

        if len(tokens) == 0:
            # Show all available agents
            agent_names = load_agent_names()
            for agent_name in agent_names:
                yield Completion(
                    agent_name,
                    start_position=-len(command_part),
                    display=agent_name,
                    display_meta=_get_agent_display_meta(agent_name),
                )
        elif len(tokens) == 1:
            # Filter agent names based on partial input
            agent_names = load_agent_names()
            partial_agent = tokens[0]
            start_pos = -(len(partial_agent))

            for agent_name in agent_names:
                if agent_name.lower().startswith(partial_agent.lower()):
                    yield Completion(
                        agent_name,
                        start_position=start_pos,
                        display=agent_name,
                        display_meta=_get_agent_display_meta(agent_name),
                    )
        else:
            # No completion for additional arguments
            return
