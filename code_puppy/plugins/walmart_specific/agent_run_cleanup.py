"""Cleanup helpers for Walmart-specific agent lifecycle hooks."""


def prune_interrupted_tool_calls_on_agent_run_start(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
) -> None:
    """Prune interrupted tool calls from the active agent before a run starts.

    This targets the case where stale interrupted tool-call state is still sitting
    in message history when a user submits the next prompt.

    The hook is intentionally defensive:
    - It lazy-imports the current agent lookup to avoid import-cycle nonsense.
    - It only touches the currently active agent when its name matches the hook's
      agent name.
    - It silently fails rather than interfering with agent startup.
    """
    del model_name, session_id

    try:
        from code_puppy.agents.agent_manager import get_current_agent

        current_agent = get_current_agent()
        if current_agent is None or getattr(current_agent, "name", None) != agent_name:
            return

        message_history = current_agent.get_message_history()
        pruned_history = current_agent.prune_interrupted_tool_calls(message_history)

        if len(pruned_history) < len(message_history):
            current_agent.set_message_history(pruned_history)
    except Exception:
        return
