"""Regression coverage: a sub-agent's pinned/configured model can vanish from
``models.json`` after being pinned (deleted entry, unsupported type, missing
creds, ...). Sub-agent invocation must degrade the same way the main agent
does -- warn and fall back to the global default model -- instead of
hard-failing the whole invocation.

Also locks in the "warn once per (agent, model) combo per conversation, with
fix instructions, never auto-clear the pin" behavior in
``load_model_with_fallback`` (code_puppy/agents/_builder.py), reached both
from the main agent build path and sub-agent invocation
(code_puppy/tools/subagent_invocation.py).
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.agents._builder import (
    load_model_with_fallback,
    reset_model_fallback_warnings,
)
from code_puppy.tools.subagent_invocation import (
    register_invoke_agent,
    register_invoke_agent_with_model,
)


@pytest.fixture(autouse=True)
def _clean_fallback_warning_state():
    """``_warned_model_fallbacks`` is process-lifetime module state in
    ``_builder.py`` -- reset it around every test so ordering across this
    file (and the rest of the suite) can't leak a "already warned" flag.
    """
    reset_model_fallback_warnings()
    yield
    reset_model_fallback_warnings()


def _capture_invoke_default():
    """Capture the registered invoke_agent (no model override) callable."""
    mock_agent = MagicMock()
    captured = {}

    def capture_tool(func):
        captured["func"] = func
        return func

    mock_agent.tool = capture_tool
    register_invoke_agent(mock_agent)
    return captured["func"]


def _capture_invoke_with_model():
    """Capture the registered invoke_agent_with_model (explicit override) callable."""
    mock_agent = MagicMock()
    captured = {}

    def capture_tool(func):
        captured["func"] = func
        return func

    mock_agent.tool = capture_tool
    register_invoke_agent_with_model(mock_agent)
    return captured["func"]


def _build_agent_config(pinned_model_name):
    config = MagicMock()

    @contextmanager
    def temporary_override(_model_name):
        yield

    config.temporary_model_name_override.side_effect = temporary_override
    config.get_model_name.return_value = pinned_model_name
    config.get_full_system_prompt.return_value = "Test instructions"
    config.get_available_tools.return_value = ["list_files"]
    config.get_message_history.return_value = []
    return config


def _passthrough_retry(*_args, **_kwargs):
    def _decorator(func):
        return func

    return _decorator


async def _invoke_with_dead_pin(
    agent_name="test-agent", pinned_model="dead-model", conversation_scope="parent"
):
    """Drive ``invoke_agent`` for ``agent_name`` pinned to a model that isn't
    in ``models_config``, and return ``(output, mock_warning)``.

    ``mock_warning`` is the patched ``emit_warning`` in ``_builder.py`` --
    that's where ``load_model_with_fallback`` actually emits the fallback
    warning, not ``subagent_invocation.py``.

    ``conversation_scope`` stands in for this conversation's root identity
    (``get_conversation_root_id()``, a ContextVar set once at the true
    top-level conversation boundary -- e.g. an ACP session's prompt handler)
    -- vary it across calls to simulate two independent conversations (e.g.
    two concurrent ACP sessions) sharing one process.
    """
    invoke = _capture_invoke_default()
    mock_context = MagicMock()
    agent_config = _build_agent_config(pinned_model)

    result = MagicMock()
    result.output = "subagent response"
    result.all_messages.return_value = ["updated-history"]
    # `result.usage` is a property since pydantic-ai 1.107 (no parentheses).
    result.usage = None

    mock_temp_agent = MagicMock()
    mock_temp_agent.run = AsyncMock(return_value=result)

    def fake_get_model(model_name, config):
        if model_name not in config:
            raise ValueError(f"Model '{model_name}' not found in configuration.")
        return MagicMock()

    with ExitStack() as stack:
        p = stack.enter_context
        p(
            patch(
                "code_puppy.tools.subagent_invocation.generate_group_id",
                return_value="test-group",
            )
        )
        p(patch("code_puppy.tools.subagent_invocation.get_message_bus"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation.get_session_context",
                return_value="parent",
            )
        )
        p(patch("code_puppy.tools.subagent_invocation.set_session_context"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation.get_conversation_root_id",
                return_value=conversation_scope,
            )
        )
        p(patch("code_puppy.tools.subagent_invocation.emit_info"))
        p(patch("code_puppy.tools.subagent_invocation.emit_error"))
        p(patch("code_puppy.tools.subagent_invocation.emit_success"))
        p(patch("code_puppy.tools.subagent_invocation.emit_warning"))
        # load_model_with_fallback imports emit_warning into its own module
        # namespace — that's the one to assert against.
        mock_warning = p(patch("code_puppy.agents._builder.emit_warning"))
        p(patch("code_puppy.tools.subagent_invocation._save_session_history"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation._load_session_history",
                return_value=[],
            )
        )
        p(
            patch(
                "code_puppy.tools.subagent_invocation._generate_session_hash_suffix",
                return_value="abc123",
            )
        )
        p(
            patch(
                "code_puppy.agents.agent_manager.load_agent",
                return_value=agent_config,
            )
        )
        p(
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"global-default-model": {}},
            )
        )
        p(
            patch(
                "code_puppy.model_factory.ModelFactory.get_model",
                side_effect=fake_get_model,
            )
        )
        p(patch("code_puppy.model_factory.make_model_settings"))
        p(
            patch(
                "code_puppy.agents._builder.get_global_model_name",
                return_value="global-default-model",
            )
        )
        p(patch("code_puppy.agents._builder.load_puppy_rules", return_value=None))
        p(patch("code_puppy.callbacks.on_load_prompt", return_value=[]))
        mock_prepare = p(patch("code_puppy.model_utils.prepare_prompt_for_model"))
        mock_prepare.return_value = MagicMock(
            instructions="prepared instructions", user_prompt="prepared prompt"
        )
        p(
            patch(
                "code_puppy.agents._builder.autostart_bound_servers_async",
                new=AsyncMock(),
            )
        )
        p(patch("code_puppy.config.get_value", return_value="true"))
        p(patch("code_puppy.config.get_output_level", return_value="medium"))
        p(
            patch(
                "code_puppy.agents._compaction.make_history_processor",
                return_value=lambda messages: messages,
            )
        )
        p(
            patch(
                "code_puppy.tools.subagent_invocation.Agent",
                return_value=mock_temp_agent,
            )
        )
        p(patch("code_puppy.tools.register_tools_for_agent"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation.on_wrap_pydantic_agent",
                side_effect=lambda _cfg, agent, **_kwargs: agent,
            )
        )
        p(
            patch(
                "code_puppy.tools.subagent_invocation.on_agent_run_context",
                return_value=[],
            )
        )
        p(
            patch(
                "code_puppy.agents.retry_profiles.make_streaming_retry",
                new=_passthrough_retry,
            )
        )

        out = await invoke(mock_context, agent_name=agent_name, prompt="Hello")

    return out, mock_warning


class TestPinnedModelFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_global_default_model(self):
        out, mock_warning = await _invoke_with_dead_pin()

        # No hard failure: the run completed using the fallback model.
        assert out.error is None
        assert out.response == "subagent response"
        assert out.model_name == "global-default-model"
        # A warning was emitted about the dead pin, not a swallowed silence.
        assert any(
            "dead-model" in str(call.args[0]) for call in mock_warning.call_args_list
        )

    @pytest.mark.asyncio
    async def test_warning_includes_fix_instructions(self):
        _out, mock_warning = await _invoke_with_dead_pin(agent_name="qa-expert")

        warning_text = mock_warning.call_args_list[0].args[0]
        assert "/pin qa-expert" in warning_text
        assert "/unpin qa-expert" in warning_text

    @pytest.mark.asyncio
    async def test_only_warns_once_per_agent_model_combo(self):
        """Repeated invocations with the same dead pin, in the same
        conversation, must only warn the first time -- not spam every call.
        """
        _out1, mock_warning = await _invoke_with_dead_pin(agent_name="qa-expert")
        assert mock_warning.call_count == 1

        # Same agent, same dead pin, no /clear in between -> silent this time.
        _out2, mock_warning_again = await _invoke_with_dead_pin(agent_name="qa-expert")
        assert mock_warning_again.call_count == 0

    @pytest.mark.asyncio
    async def test_different_agent_gets_its_own_warning(self):
        """The dedup key is (agent, model) -- a different agent pinned to the
        same dead model still deserves its own warning.
        """
        await _invoke_with_dead_pin(agent_name="qa-expert")
        _out, mock_warning = await _invoke_with_dead_pin(agent_name="reviewer")
        assert mock_warning.call_count == 1

    @pytest.mark.asyncio
    async def test_reset_reopens_warning_for_a_new_conversation(self):
        """``/clear`` calls ``reset_model_fallback_warnings()``; simulate
        that boundary and confirm the warning resurfaces.
        """
        await _invoke_with_dead_pin(agent_name="qa-expert")
        reset_model_fallback_warnings()
        _out, mock_warning = await _invoke_with_dead_pin(agent_name="qa-expert")
        assert mock_warning.call_count == 1

    @pytest.mark.asyncio
    async def test_independent_conversations_do_not_share_warning_state(self):
        """Two independent conversations (e.g. two concurrent ACP sessions)
        sharing one process must each get their own warning for the exact
        same (agent, dead-model) combo -- one conversation's warning must
        NOT silently suppress the identical warning for a totally unrelated
        conversation that never saw it.
        """
        _out_a, warning_a = await _invoke_with_dead_pin(
            agent_name="qa-expert", conversation_scope="acp-session-a"
        )
        assert warning_a.call_count == 1

        _out_b, warning_b = await _invoke_with_dead_pin(
            agent_name="qa-expert", conversation_scope="acp-session-b"
        )
        assert warning_b.call_count == 1

    @pytest.mark.asyncio
    async def test_unscoped_reset_does_not_wipe_other_conversations(self):
        """``reset_model_fallback_warnings(scope=None)`` (what ACP's
        ``_make_session`` calls on every new/loaded/forked session) must only
        clear the shared/unscoped bucket -- it must NOT wipe a different,
        already-scoped conversation's warning state. Otherwise creating an
        unrelated ACP session would re-open a warning for a conversation
        that's still live and already saw it once.
        """
        await _invoke_with_dead_pin(
            agent_name="qa-expert", conversation_scope="acp-session-a"
        )

        reset_model_fallback_warnings(scope=None)

        # Session A's own warning state must have survived the scope=None
        # reset triggered by session B's creation.
        _out, mock_warning_again = await _invoke_with_dead_pin(
            agent_name="qa-expert", conversation_scope="acp-session-a"
        )
        assert mock_warning_again.call_count == 0


async def _invoke_with_dead_explicit_override(dead_model="dead-model"):
    """Drive ``invoke_agent_with_model`` with an EXPLICIT ``model_name``
    override that isn't in ``models_config``, and return the output.

    Unlike the ambient/pinned path (``_invoke_with_dead_pin``), a bad explicit
    override must hard-fail -- silently substituting a different model than
    the one the caller explicitly asked for would violate that tool's
    contract for automated callers.
    """
    invoke = _capture_invoke_with_model()
    mock_context = MagicMock()
    agent_config = _build_agent_config(dead_model)

    def fake_get_model(model_name, config):
        if model_name not in config:
            raise ValueError(f"Model '{model_name}' not found in configuration.")
        return MagicMock()

    with ExitStack() as stack:
        p = stack.enter_context
        p(
            patch(
                "code_puppy.tools.subagent_invocation.generate_group_id",
                return_value="test-group",
            )
        )
        p(patch("code_puppy.tools.subagent_invocation.get_message_bus"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation.get_session_context",
                return_value="parent",
            )
        )
        p(patch("code_puppy.tools.subagent_invocation.set_session_context"))
        p(patch("code_puppy.tools.subagent_invocation.emit_info"))
        p(patch("code_puppy.tools.subagent_invocation.emit_error"))
        p(patch("code_puppy.tools.subagent_invocation.emit_warning"))
        p(patch("code_puppy.agents._builder.emit_warning"))
        p(patch("code_puppy.tools.subagent_invocation._save_session_history"))
        p(
            patch(
                "code_puppy.tools.subagent_invocation._load_session_history",
                return_value=[],
            )
        )
        p(
            patch(
                "code_puppy.tools.subagent_invocation._generate_session_hash_suffix",
                return_value="abc123",
            )
        )
        p(
            patch(
                "code_puppy.agents.agent_manager.load_agent",
                return_value=agent_config,
            )
        )
        p(
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"global-default-model": {}, "healthy-model": {}},
            )
        )
        p(
            patch(
                "code_puppy.model_factory.ModelFactory.get_model",
                side_effect=fake_get_model,
            )
        )
        p(patch("code_puppy.model_factory.make_model_settings"))
        p(
            patch(
                "code_puppy.agents._builder.get_global_model_name",
                return_value="global-default-model",
            )
        )

        return await invoke(
            mock_context,
            agent_name="test-agent",
            prompt="Hello",
            model_name=dead_model,
        )


class TestExplicitModelOverrideHardFails:
    """``invoke_agent_with_model``'s ``model_name`` is an explicit, per-call
    contract ("run this exactly on this model"), unlike the ambient pinned
    model. A bad explicit override must raise immediately -- NOT silently
    substitute a different model the caller never asked for.
    """

    @pytest.mark.asyncio
    async def test_bad_explicit_override_raises_instead_of_falling_back(self):
        out = await _invoke_with_dead_explicit_override()

        # A hard failure surfaced through the tool's normal error contract,
        # not a silently-substituted model reported as success.
        assert out.response is None
        assert out.error is not None
        assert "dead-model" in out.error

    @pytest.mark.asyncio
    async def test_error_message_names_available_models(self):
        out = await _invoke_with_dead_explicit_override()

        assert "healthy-model" in out.error
        assert "global-default-model" in out.error

    @pytest.mark.asyncio
    async def test_does_not_touch_the_ambient_fallback_warning_path(self):
        """The explicit-override hard-fail must not route through, or
        interfere with, ``load_model_with_fallback``'s dedup state -- it's a
        different contract entirely.
        """
        await _invoke_with_dead_explicit_override(dead_model="another-dead-model")

        # The ambient/pinned path for the same agent+model must still warn
        # (not be marked "already warned" by the override's hard failure).
        _out, mock_warning = await _invoke_with_dead_pin(
            agent_name="test-agent", pinned_model="another-dead-model"
        )
        assert mock_warning.call_count == 1


class TestLoadModelWithFallbackScopingUnit:
    """Fast, direct unit tests on ``load_model_with_fallback`` itself (no
    sub-agent-invocation mock stack) pinning down the exact
    ``conversation_scope`` dedup-key and ``reset_model_fallback_warnings``
    semantics the integration-style tests above exercise indirectly.
    """

    @staticmethod
    def _fake_get_model(model_name, config):
        if model_name not in config:
            raise ValueError(f"Model '{model_name}' not found in configuration.")
        return MagicMock()

    def _call(self, *, agent_name="qa-expert", conversation_scope=None):
        models_config = {"global-default-model": {}}
        with (
            patch(
                "code_puppy.agents._builder.ModelFactory.get_model",
                side_effect=self._fake_get_model,
            ),
            patch(
                "code_puppy.agents._builder.get_global_model_name",
                return_value="global-default-model",
            ),
            patch("code_puppy.agents._builder.emit_info"),
            patch("code_puppy.agents._builder.emit_error"),
            patch("code_puppy.agents._builder.emit_warning") as mock_warning,
        ):
            load_model_with_fallback(
                "dead-model",
                models_config,
                "group-id",
                agent_name=agent_name,
                conversation_scope=conversation_scope,
            )
        return mock_warning

    def test_same_scope_warns_once(self):
        assert self._call(conversation_scope="session-a").call_count == 1
        assert self._call(conversation_scope="session-a").call_count == 0

    def test_different_scope_warns_independently(self):
        assert self._call(conversation_scope="session-a").call_count == 1
        assert self._call(conversation_scope="session-b").call_count == 1

    def test_none_scope_is_its_own_bucket(self):
        """``conversation_scope=None`` (the main-agent-build default) is a
        distinct bucket from any named scope, not "no dedup at all".
        """
        assert self._call(conversation_scope=None).call_count == 1
        assert self._call(conversation_scope=None).call_count == 0
        assert self._call(conversation_scope="session-a").call_count == 1

    def test_full_reset_clears_every_scope(self):
        self._call(conversation_scope="session-a")
        self._call(conversation_scope=None)

        reset_model_fallback_warnings()

        assert self._call(conversation_scope="session-a").call_count == 1
        assert self._call(conversation_scope=None).call_count == 1

    def test_scoped_reset_only_clears_that_scope(self):
        """This is the exact property ACP's ``_make_session`` relies on:
        ``reset_model_fallback_warnings(scope=None)`` must clear ONLY the
        unscoped bucket, leaving a different named scope's already-earned
        warning state untouched.
        """
        self._call(conversation_scope="session-a")
        self._call(conversation_scope=None)

        reset_model_fallback_warnings(scope=None)

        # The unscoped bucket was cleared -> warns again.
        assert self._call(conversation_scope=None).call_count == 1
        # session-a's bucket was untouched -> stays silent.
        assert self._call(conversation_scope="session-a").call_count == 0
