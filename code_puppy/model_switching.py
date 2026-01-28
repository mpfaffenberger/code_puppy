"""Shared helpers for switching models and reloading agents safely."""

from __future__ import annotations

from typing import Optional

from code_puppy.config import set_model_name


def _get_effective_agent_model(agent) -> Optional[str]:
    """Safely fetch the effective model name for an agent."""
    try:
        return agent.get_model_name()
    except Exception:
        return None


def set_model_and_reload_agent(
    model_name: str,
    *,
    warn_on_pinned_mismatch: bool = True,
) -> None:
    """Set the global model and reload the active agent.

    This keeps model switching consistent across commands while avoiding
    direct imports that can trigger circular dependencies.
    """
    from code_puppy.messaging import emit_info, emit_warning

    set_model_name(model_name)

    try:
        from code_puppy.agents import get_current_agent

        current_agent = get_current_agent()
        if current_agent is None:
            emit_warning("Model changed but no active agent was found to reload")
            return

        # JSON agents may need to refresh their config before reload
        if hasattr(current_agent, "refresh_config"):
            try:
                current_agent.refresh_config()
            except Exception:
                # Non-fatal, continue to reload
                ...

        if warn_on_pinned_mismatch:
            effective_model = _get_effective_agent_model(current_agent)
            if effective_model and effective_model != model_name:
                display_name = getattr(
                    current_agent, "display_name", current_agent.name
                )
                emit_warning(
                    "Active agent "
                    f"'{display_name}' is pinned to '{effective_model}', "
                    f"so '{model_name}' will not take effect until unpinned."
                )

        current_agent.reload_code_generation_agent()
        emit_info("Active agent reloaded")
    except Exception as exc:
        emit_warning(f"Model changed but agent reload failed: {exc}")
