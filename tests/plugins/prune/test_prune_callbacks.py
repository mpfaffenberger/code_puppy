"""Tests for ``code_puppy.plugins.prune.register_callbacks``.

Covers the custom-command dispatcher, helper predicates
(``_collect_removed_tool_call_ids``, ``_message_has_orphan_tool_return``,
``_prune_dangling_tool_fragments``), the end-to-end ``_perform_prune``
mutator, and the top-level ``_handle_prune_command`` entry point.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
)

from ._helpers import (
    _agent_manager_module,
    _assistant_text,
    _assistant_with_tool,
    _plugin_module,
    _system_msg,
    _system_plus_user_msg,
    _tool_return,
    _user_msg,
)


# ───────────────────────────────────────────────────────────────────────────
# Plugin command handlers
# ───────────────────────────────────────────────────────────────────────────


class TestCustomCommand:
    def test_custom_help_lists_prune(self):
        entries = dict(_plugin_module()._custom_help())
        assert "prune" in entries

    def test_handle_custom_command_ignores_others(self):
        assert _plugin_module()._handle_custom_command("/nope", "nope") is None


# ───────────────────────────────────────────────────────────────────────────
# _collect_removed_tool_call_ids
# ───────────────────────────────────────────────────────────────────────────


class TestCollectRemovedToolCallIds:
    def test_empty_when_nothing_dropped(self):
        mod = _plugin_module()
        ids = mod._collect_removed_tool_call_ids([], set())
        assert ids == set()

    def test_pulls_tool_call_ids_from_dropped_messages(self):
        mod = _plugin_module()
        history = [
            _system_msg(),
            _assistant_with_tool(
                text=None, tool_name="create_file", tool_call_id="tc-x"
            ),
        ]
        ids = mod._collect_removed_tool_call_ids(history, {1})
        assert ids == {"tc-x"}

    def test_ignores_out_of_range(self):
        mod = _plugin_module()
        ids = mod._collect_removed_tool_call_ids([_system_msg()], {99})
        assert ids == set()


# ───────────────────────────────────────────────────────────────────────────
# _message_has_orphan_tool_return — cascade-drop predicate
# ───────────────────────────────────────────────────────────────────────────


class TestMessageHasOrphanToolReturn:
    def test_true_for_matching_tool_return(self):
        mod = _plugin_module()
        msg = _tool_return("tc-orphan")
        assert mod._message_has_orphan_tool_return(msg, {"tc-orphan"}) is True

    def test_false_for_unrelated_tool_return(self):
        mod = _plugin_module()
        msg = _tool_return("keep-me")
        assert mod._message_has_orphan_tool_return(msg, {"other"}) is False

    def test_false_for_assistant_message(self):
        mod = _plugin_module()
        assert (
            mod._message_has_orphan_tool_return(_assistant_text("hi"), {"anything"})
            is False
        )

    def test_false_for_empty_orphan_set(self):
        mod = _plugin_module()
        msg = _tool_return("x")
        assert mod._message_has_orphan_tool_return(msg, set()) is False


# ───────────────────────────────────────────────────────────────────────────
# _prune_dangling_tool_fragments
# ───────────────────────────────────────────────────────────────────────────


class TestPruneDanglingToolFragments:
    def test_removes_orphan_return_tail(self):
        mod = _plugin_module()
        system = _system_msg()
        reply = _assistant_text("hi")
        orphan = _tool_return("tc-orphan")
        cleaned, extra = mod._prune_dangling_tool_fragments([system, reply, orphan])
        assert cleaned == [system, reply]
        assert extra == 1

    def test_leaves_matched_call_return_pair_alone(self):
        """prune's pruner is smarter than pop's — paired call/return at the
        tail is NOT dangling, so it stays put."""
        mod = _plugin_module()
        system = _system_msg()
        text = _assistant_text("hi")
        call = ModelResponse(
            parts=[ToolCallPart(tool_name="t", args="{}", tool_call_id="tc1")]
        )
        ret = _tool_return("tc1")
        cleaned, extra = mod._prune_dangling_tool_fragments([system, text, call, ret])
        assert cleaned == [system, text, call, ret]
        assert extra == 0

    def test_removes_orphan_tool_call_at_tail(self):
        """A tool call without a matching return IS dangling."""
        mod = _plugin_module()
        system = _system_msg()
        text = _assistant_text("hi")
        orphan_call = ModelResponse(
            parts=[ToolCallPart(tool_name="t", args="{}", tool_call_id="orphan")]
        )
        cleaned, extra = mod._prune_dangling_tool_fragments([system, text, orphan_call])
        assert cleaned == [system, text]
        assert extra == 1

    def test_idempotent_on_clean_history(self):
        mod = _plugin_module()
        history = [_system_msg(), _assistant_text("hi")]
        cleaned, extra = mod._prune_dangling_tool_fragments(history)
        assert cleaned == history
        assert extra == 0


# ───────────────────────────────────────────────────────────────────────────
# _perform_prune end-to-end
# ───────────────────────────────────────────────────────────────────────────


class TestPerformPrune:
    def test_empty_history_emits_warning(self):
        agent = MagicMock()
        agent.get_message_history.return_value = []
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch(
                "code_puppy.plugins.prune.register_callbacks.emit_warning"
            ) as mock_warn,
        ):
            _plugin_module()._perform_prune({1})
        agent.set_message_history.assert_not_called()
        mock_warn.assert_called_once()

    def test_nothing_selected_emits_info(self):
        agent = MagicMock()
        agent.get_message_history.return_value = [_system_msg(), _assistant_text("hi")]
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info") as mock_info,
        ):
            _plugin_module()._perform_prune(set())
        agent.set_message_history.assert_not_called()
        mock_info.assert_called_once()

    def test_drops_system_prompt_index_defensively(self):
        """Defensive content-based filter: any index whose message
        carries a SystemPromptPart is silently dropped from the
        selection, regardless of its position. Asking to prune the
        system prompt is a no-op.
        """
        agent = MagicMock()
        agent.get_message_history.return_value = [_system_msg(), _assistant_text("hi")]
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info") as mock_info,
        ):
            _plugin_module()._perform_prune({0})
        agent.set_message_history.assert_not_called()
        mock_info.assert_called_once()

    def test_drops_bundled_system_plus_user_defensively(self):
        """Anthropic-style bundle at history[0] must also be refused —
        the content-based check sees the SystemPromptPart and bails.
        """
        agent = MagicMock()
        agent.get_message_history.return_value = [
            _system_plus_user_msg(),
            _assistant_text("hi"),
        ]
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info") as mock_info,
        ):
            _plugin_module()._perform_prune({0})
        agent.set_message_history.assert_not_called()
        mock_info.assert_called_once()

    def test_pure_user_first_message_is_prunable(self):
        """The whole point of removing the index-0 lock: on non-
        Anthropic transports history[0] is a pure UserPromptPart and
        the user must be allowed to drop it end-to-end.
        """
        first_user = _user_msg("first turn — non-anthropic provider")
        reply = _assistant_text("sure")
        followup = _user_msg("second turn")
        agent = MagicMock()
        agent.get_message_history.return_value = [first_user, reply, followup]
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_success"),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info"),
        ):
            _plugin_module()._perform_prune({0})
        agent.set_message_history.assert_called_once()
        new_history = agent.set_message_history.call_args[0][0]
        assert new_history == [reply, followup]

    def test_drops_message_and_cascades_matching_tool_return(self):
        """Dropping an assistant message should cascade-drop its orphaned
        ToolReturnPart message so the model never sees a tool result
        without a matching tool call.
        """
        system = _system_msg()
        user = _user_msg("step 1")
        asst = _assistant_with_tool(
            text=None, tool_name="create_file", tool_call_id="tc1"
        )
        ret = _tool_return("tc1")
        followup = _user_msg("step 2")

        agent = MagicMock()
        agent.get_message_history.return_value = [system, user, asst, ret, followup]

        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_success"),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info"),
        ):
            # Drop the assistant message (index 2). Its tool-return at
            # index 3 should cascade-drop.
            _plugin_module()._perform_prune({2})

        agent.set_message_history.assert_called_once()
        new_history = agent.set_message_history.call_args[0][0]
        assert new_history == [system, user, followup]

    def test_unrelated_assistant_message_is_left_untouched(self):
        """The big behavioural change: we never edit a ModelResponse's
        parts in place. Messages we didn't select must be the exact same
        object on the way out so thinking-block signatures survive.
        """
        system = _system_msg()
        asst_keep = ModelResponse(
            parts=[
                TextPart(content="doing work"),
                ToolCallPart(tool_name="create_file", args="{}", tool_call_id="keep"),
            ]
        )
        ret_keep = _tool_return("keep")
        user2 = _user_msg("another turn")
        asst_drop = _assistant_text("this one's getting nuked")

        agent = MagicMock()
        agent.get_message_history.return_value = [
            system,
            asst_keep,
            ret_keep,
            user2,
            asst_drop,
        ]

        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_success"),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info"),
        ):
            _plugin_module()._perform_prune({4})

        new_history = agent.set_message_history.call_args[0][0]
        # The kept assistant ModelResponse must be the SAME object — not
        # a model_copy with rebuilt parts.
        assert new_history[1] is asst_keep
        assert new_history[2] is ret_keep

    def test_set_history_failure_emits_error(self):
        agent = MagicMock()
        agent.get_message_history.return_value = [_system_msg(), _assistant_text("hi")]
        agent.set_message_history.side_effect = RuntimeError("boom")

        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch(
                "code_puppy.plugins.prune.register_callbacks.emit_error"
            ) as mock_error,
        ):
            _plugin_module()._perform_prune({1})

        mock_error.assert_called_once()


# ───────────────────────────────────────────────────────────────────────────
# _handle_prune_command (dispatch)
# ───────────────────────────────────────────────────────────────────────────


class TestHandlePruneCommand:
    def test_empty_history_bails_out(self):
        agent = MagicMock()
        agent.get_message_history.return_value = []
        agent.get_full_system_prompt.return_value = ""
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info") as mock_info,
        ):
            result = _plugin_module()._handle_custom_command("/prune", "prune")
        assert result is True
        mock_info.assert_called_once()
        assert "no prunable messages" in mock_info.call_args.args[0].lower()

    def test_only_system_entries_bails_out(self):
        """With a non-empty raw history of just a system message, the
        system-only request is filtered out by ``_extract_message`` and
        the entries list ends up empty — we should bail out gracefully.
        """
        agent = MagicMock()
        agent.get_message_history.return_value = [_system_msg()]
        agent.get_full_system_prompt.return_value = "you are a puppy"
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info") as mock_info,
        ):
            result = _plugin_module()._handle_custom_command("/prune", "prune")
        assert result is True
        mock_info.assert_called_once()

    def test_get_agent_failure_emits_error(self):
        bad_manager = SimpleNamespace(
            get_current_agent=MagicMock(side_effect=RuntimeError("kaboom"))
        )
        with (
            patch.dict(sys.modules, {"code_puppy.agents.agent_manager": bad_manager}),
            patch(
                "code_puppy.plugins.prune.register_callbacks.emit_error"
            ) as mock_error,
        ):
            result = _plugin_module()._handle_custom_command("/prune", "prune")
        assert result is True
        mock_error.assert_called_once()
