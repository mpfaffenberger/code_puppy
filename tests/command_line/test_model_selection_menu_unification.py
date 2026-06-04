"""Unification regression tests for the shared ``ModelSelectionMenu``.

The whole point of the ``unify-model-selection-menus`` feature is that the
interactive ``/model`` picker and the agent-pin picker route through *one*
shared ``ModelSelectionMenu`` class instead of bespoke per-flow menus. These
tests pin that contract down: if a future change swaps either flow back to a
hand-rolled menu, these tests should go red.

Everything here is deterministic and offline — the interactive prompt_toolkit
layer is never launched; ``ModelSelectionMenu.run_async`` is mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSharedMenuIdentity:
    """Both entry points must reference the exact same class object."""

    def test_agent_menu_uses_picker_menu_class(self):
        from code_puppy.command_line import agent_menu, model_picker_completion

        assert (
            agent_menu.ModelSelectionMenu is model_picker_completion.ModelSelectionMenu
        )

    def test_model_picker_module_owns_the_menu(self):
        # interactive_model_picker (used by /model) lives next to the menu and
        # instantiates it directly.
        from code_puppy.command_line import model_picker_completion

        assert hasattr(model_picker_completion, "ModelSelectionMenu")
        assert hasattr(model_picker_completion, "interactive_model_picker")


class TestModelCommandRoutesThroughSharedMenu:
    """`/model` (no args) must drive the shared ModelSelectionMenu."""

    @pytest.mark.asyncio
    async def test_selection_is_applied(self):
        from code_puppy.command_line import model_picker_completion
        from code_puppy.command_line.core_commands import handle_model_command

        menu_instance = MagicMock()
        menu_instance.run_async = AsyncMock(return_value="gpt-4")

        with (
            patch.object(
                model_picker_completion,
                "ModelSelectionMenu",
                return_value=menu_instance,
            ) as mock_menu_cls,
            patch.object(
                model_picker_completion, "set_active_model"
            ) as mock_set_active,
            patch("code_puppy.messaging.emit_success") as mock_success,
            patch("code_puppy.messaging.emit_warning"),
        ):
            assert handle_model_command("/model") is True

        # Routed through the shared menu...
        mock_menu_cls.assert_called_once()
        menu_instance.run_async.assert_awaited_once()
        # ...and the returned selection was applied + announced.
        mock_set_active.assert_called_once_with("gpt-4")
        assert any("gpt-4" in str(call.args[0]) for call in mock_success.call_args_list)

    @pytest.mark.asyncio
    async def test_cancel_hits_cancelled_path(self):
        from code_puppy.command_line import model_picker_completion
        from code_puppy.command_line.core_commands import handle_model_command

        menu_instance = MagicMock()
        menu_instance.run_async = AsyncMock(return_value=None)

        with (
            patch.object(
                model_picker_completion,
                "ModelSelectionMenu",
                return_value=menu_instance,
            ) as mock_menu_cls,
            patch.object(
                model_picker_completion, "set_active_model"
            ) as mock_set_active,
            patch("code_puppy.messaging.emit_success"),
            patch("code_puppy.messaging.emit_warning") as mock_warning,
        ):
            assert handle_model_command("/model") is True

        mock_menu_cls.assert_called_once()
        menu_instance.run_async.assert_awaited_once()
        # Cancel => no model applied, and the cancelled message is emitted.
        mock_set_active.assert_not_called()
        assert any(
            "Model selection cancelled" in str(call.args[0])
            for call in mock_warning.call_args_list
        )


class TestAgentPinRoutesThroughSharedMenu:
    """`_select_pinned_model` must drive the same shared ModelSelectionMenu."""

    @pytest.mark.asyncio
    @patch("code_puppy.command_line.agent_menu.ModelSelectionMenu")
    @patch(
        "code_puppy.command_line.agent_menu.load_model_names",
        return_value=["m1", "m2"],
    )
    async def test_selection_is_returned(self, mock_load, mock_menu_cls):
        from code_puppy.command_line.agent_menu import _select_pinned_model

        mock_menu_cls.return_value.run_async = AsyncMock(return_value="m1")

        result = await _select_pinned_model("agent1")

        assert result == "m1"
        mock_menu_cls.assert_called_once()
        mock_menu_cls.return_value.run_async.assert_awaited_once()
        # The /model picker is reused, with the (unpin) sentinel prepended.
        assert mock_menu_cls.call_args.kwargs["model_names"] == [
            "(unpin)",
            "m1",
            "m2",
        ]

    @pytest.mark.asyncio
    @patch("code_puppy.command_line.agent_menu.ModelSelectionMenu")
    @patch(
        "code_puppy.command_line.agent_menu.load_model_names",
        return_value=["m1"],
    )
    async def test_cancel_returns_none(self, mock_load, mock_menu_cls):
        from code_puppy.command_line.agent_menu import _select_pinned_model

        mock_menu_cls.return_value.run_async = AsyncMock(return_value=None)

        result = await _select_pinned_model("agent1")

        assert result is None
        mock_menu_cls.return_value.run_async.assert_awaited_once()
