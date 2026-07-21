from code_puppy.tools import subagent_invocation
from code_puppy.tools.subagent_context import (
    get_subagent_depth,
    get_subagent_model_name,
    subagent_context,
)


def test_subagent_context_tracks_model_and_restores_parent():
    assert get_subagent_depth() == 0
    assert get_subagent_model_name() is None

    with subagent_context("parent", "gpt-5.6-sol"):
        assert get_subagent_depth() == 1
        assert get_subagent_model_name() == "gpt-5.6-sol"
        with subagent_context("child", "gpt-5.5"):
            assert get_subagent_depth() == 2
            assert get_subagent_model_name() == "gpt-5.5"
        assert get_subagent_model_name() == "gpt-5.6-sol"

    assert get_subagent_depth() == 0
    assert get_subagent_model_name() is None


def test_recursion_guard_checks_caller_model_not_child_model():
    with subagent_context("gpt-parent", "gpt-5.6-sol"):
        assert subagent_invocation._gpt_5_6_recursion_blocked()

    with subagent_context("other-parent", "gpt-5.5"):
        assert not subagent_invocation._gpt_5_6_recursion_blocked()


def test_subagent_context_restores_model_after_error():
    try:
        with subagent_context("agent", "gpt-5.6-sol"):
            raise RuntimeError
    except RuntimeError:
        pass

    assert get_subagent_model_name() is None
