"""Shared durable model preparation for main-agent and subagent conversations."""

from typing import Any

from code_puppy.model_utils import PreparedPrompt


def saved_system_text(agent: Any) -> str | None:
    """Read the authoritative prepared system text without replaying live hooks."""
    from code_puppy.agents.base_agent import BaseAgent

    if not isinstance(agent, BaseAgent) or agent._session_prepared_prompt is None:
        return None
    saved = agent._session_prepared_prompt
    instructions = saved["instructions"] + agent.get_runtime_prompt_suffix()
    return "\n\n".join(text for text in (saved["system_prompt"], instructions) if text)


def prepare_session_prompt(
    agent: Any,
    model_name: str,
    instructions: str,
    user_prompt: str = "",
    *,
    prepend_system_to_user: bool = False,
    preparation_scope: str = "main",
) -> PreparedPrompt:
    """Freeze system preparation, but keep per-turn user transformations live.

    Callers compose their own durable contract (subagents omit project rules).
    Temporary policy is appended only after hooks, never supplied to a hook that
    could copy it into a persisted user prompt. Saved source text keeps first-turn
    preparation consistent with the builder, including provider fallback models.
    """
    from code_puppy.agents.base_agent import BaseAgent
    from code_puppy.model_utils import prepare_prompt_for_model

    if not isinstance(agent, BaseAgent):
        return prepare_prompt_for_model(
            model_name,
            instructions,
            user_prompt,
            prepend_system_to_user=prepend_system_to_user,
        )

    saved = agent._session_prepared_prompt
    if saved is not None and (
        saved["model_name"] != model_name
        or saved.get("preparation_scope", "main") != preparation_scope
    ):
        saved = None
    source = saved.get("source_prompt", instructions) if saved else instructions
    # Hooks may transform actual user input; their new system output must not
    # replace the saved contract on resume. Empty builder probes need no replay.
    prepared = None
    if saved is None or user_prompt or prepend_system_to_user:
        prepared = prepare_prompt_for_model(
            model_name,
            source,
            user_prompt,
            prepend_system_to_user=prepend_system_to_user,
        )
    if saved is None:
        saved = {
            "model_name": model_name,
            "preparation_scope": preparation_scope,
            "source_prompt": source,
            "instructions": prepared.instructions,
            "system_prompt": prepared.system_prompt,
            "is_claude_code": prepared.is_claude_code,
        }
        agent._session_prepared_prompt = saved
    return PreparedPrompt(
        instructions=saved["instructions"] + agent.get_runtime_prompt_suffix(),
        user_prompt=prepared.user_prompt if prepared is not None else user_prompt,
        is_claude_code=saved["is_claude_code"],
        system_prompt=saved["system_prompt"],
    )
