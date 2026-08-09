"""Coverage tests for agent_menu.py - exercises all uncovered code paths."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from code_puppy.command_line.agent_menu import (
    _apply_pinned_model,
    _get_pinned_model,
    _reload_agent_if_current,
    _select_pinned_model,
    interactive_agent_picker,
)


class TestApplyPinnedModel:
    @patch("code_puppy.command_line.agent_menu.emit_warning")
    @patch(
        "code_puppy.agents.json_agent.discover_json_agents",
        side_effect=Exception("fail"),
    )
    @patch(
        "code_puppy.command_line.agent_menu.set_agent_pinned_model",
        side_effect=Exception("fail"),
    )
    def test_exception(self, mock_set, mock_json, mock_warn):
        _apply_pinned_model("agent1", "gpt-4")
        mock_warn.assert_called()


class TestGetPinnedModel:
    @patch(
        "code_puppy.command_line.agent_menu.get_agent_pinned_model",
        side_effect=Exception,
    )
    def test_exception_in_builtin(self, mock_pin):
        with patch(
            "code_puppy.agents.json_agent.discover_json_agents", side_effect=Exception
        ):
            assert _get_pinned_model("agent1") is None


class TestInteractiveAgentPicker:
    @pytest.mark.asyncio
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions", return_value={})
    @patch("code_puppy.command_line.agent_menu.get_available_agents", return_value={})
    async def test_no_agents(self, mock_avail, mock_desc, mock_current):
        result = await interactive_agent_picker()
        assert result is None


class TestReloadAgentIfCurrent:
    @patch("code_puppy.command_line.agent_menu.emit_info")
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    def test_current_no_pinned(self, mock_get, mock_emit):
        agent = MagicMock()
        agent.name = "agent1"
        mock_get.return_value = agent
        _reload_agent_if_current("agent1", None)
        assert any("default" in str(c) for c in mock_emit.call_args_list)

    @patch("code_puppy.command_line.agent_menu.emit_info")
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    def test_current_with_pinned(self, mock_get, mock_emit):
        agent = MagicMock()
        agent.name = "agent1"
        mock_get.return_value = agent
        _reload_agent_if_current("agent1", "m1")
        agent.reload_code_generation_agent.assert_called()

    @patch("code_puppy.command_line.agent_menu.emit_warning")
    @patch("code_puppy.command_line.agent_menu.get_current_agent")
    def test_reload_fails(self, mock_get, mock_warn):
        agent = MagicMock()
        agent.name = "agent1"
        agent.reload_code_generation_agent.side_effect = Exception("boom")
        mock_get.return_value = agent
        _reload_agent_if_current("agent1", "m1")
        mock_warn.assert_called()


class TestSelectPinnedModel:
    @pytest.mark.asyncio
    @patch(
        "code_puppy.command_line.agent_menu.load_model_names",
        side_effect=Exception("fail"),
    )
    async def test_load_error(self, mock_load):
        result = await _select_pinned_model("agent1")
        assert result is None

    @pytest.mark.asyncio
    @patch("code_puppy.command_line.agent_menu.ModelSelectionMenu")
    @patch(
        "code_puppy.command_line.agent_menu.load_model_names", return_value=["m1", "m2"]
    )
    async def test_success(self, mock_load, mock_menu_cls):
        mock_menu_cls.return_value.run_async = AsyncMock(return_value="m1")
        result = await _select_pinned_model("agent1")
        assert result == "m1"
        # The /model picker is reused, with the unpin sentinel prepended.
        assert mock_menu_cls.call_args.kwargs["model_names"] == ["(unpin)", "m1", "m2"]
