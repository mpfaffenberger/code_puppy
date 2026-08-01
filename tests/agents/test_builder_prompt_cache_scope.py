from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from code_puppy.agents._builder import build_pydantic_agent


def _agent(identity: str):
    agent = MagicMock()
    agent.name = "code-puppy"
    agent.identity = identity
    agent.get_model_name.return_value = "codex-gpt-5.6-sol"
    agent.get_available_tools.return_value = []
    return agent


def test_two_agent_builds_use_same_logical_cache_scope():
    """Per-instance identity text must not leak into the cross-launch key scope."""
    first = _agent("random-id-one")
    second = _agent("random-id-two")
    built = [SimpleNamespace(_tools={}) for _ in range(4)]

    with (
        patch("code_puppy.agents._builder.ModelFactory.load_config", return_value={}),
        patch(
            "code_puppy.agents._builder.load_model_with_fallback",
            return_value=(MagicMock(), "codex-gpt-5.6-sol"),
        ),
        patch(
            "code_puppy.agents._builder._assemble_instructions",
            side_effect=["instructions random-id-one", "instructions random-id-two"],
        ),
        patch("code_puppy.agents._builder.load_mcp_servers", return_value=[]),
        patch("code_puppy.agents._builder.make_model_settings") as settings,
        patch("code_puppy.agents._builder.make_history_processor"),
        patch("code_puppy.agents._builder.make_steer_history_processor"),
        patch("code_puppy.agents._builder.PydanticAgent", side_effect=built),
        patch("code_puppy.tools.register_tools_for_agent"),
        patch(
            "code_puppy.agents._builder.on_wrap_pydantic_agent",
            side_effect=lambda _agent, pydantic_agent, **_kwargs: pydantic_agent,
        ),
    ):
        build_pydantic_agent(first)
        build_pydantic_agent(second)

    assert settings.call_args_list == [
        call("codex-gpt-5.6-sol", prompt_cache_scope="code-puppy"),
        call("codex-gpt-5.6-sol", prompt_cache_scope="code-puppy"),
    ]
