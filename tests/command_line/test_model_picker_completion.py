"""Tests for model_picker_completion.py to achieve 100% coverage."""

from unittest.mock import MagicMock, call, patch

import pytest
from prompt_toolkit.document import Document

from code_puppy.command_line.model_picker_completion import ModelSelectionMenu


class TestLoadModelNames:
    def test_returns_model_list(self):
        from code_puppy.command_line.model_picker_completion import load_model_names

        with patch(
            "code_puppy.command_line.model_picker_completion._load_models_config",
            return_value={"gpt-4": {}, "claude-3": {}},
        ):
            result = load_model_names()
            assert "gpt-4" in result
            assert "claude-3" in result


class TestGetActiveModel:
    def test_returns_model_name(self):
        from code_puppy.command_line.model_picker_completion import get_active_model

        with patch(
            "code_puppy.command_line.model_picker_completion.get_global_model_name",
            return_value="gpt-4",
        ):
            assert get_active_model() == "gpt-4"


class TestSetActiveModel:
    def test_delegates_to_set_model(self):
        from code_puppy.command_line.model_picker_completion import set_active_model

        with patch(
            "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
        ) as mock_set:
            set_active_model("gpt-4")
            mock_set.assert_called_once_with("gpt-4")


class TestModelNameCompleter:
    def _make_doc(self, text, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(text)
        return Document(text=text, cursor_position=cursor_pos)

    def test_no_trigger(self):
        from code_puppy.command_line.model_picker_completion import ModelNameCompleter

        with patch(
            "code_puppy.command_line.model_picker_completion._load_models_config",
            return_value={"gpt-4": {}},
        ):
            c = ModelNameCompleter(trigger="/model")
            completions = list(c.get_completions(self._make_doc("/other "), None))
            assert completions == []

    def test_shows_all_models(self):
        from code_puppy.command_line.model_picker_completion import ModelNameCompleter

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={
                    "gpt-4": {"description": "Fast all-round model"},
                    "claude-3": {"description": "Deep reasoning model"},
                },
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
        ):
            c = ModelNameCompleter(trigger="/model")
            completions = list(c.get_completions(self._make_doc("/model "), None))
            assert len(completions) == 2
            metas = {
                completion.text: str(completion.display_meta)
                for completion in completions
            }
            assert "✓" in metas["gpt-4"]
            assert "Fast all-round model" in metas["gpt-4"]
            assert "Deep reasoning model" in metas["claude-3"]

    def test_uses_fallback_description_when_missing(self):
        from code_puppy.command_line.model_picker_completion import ModelNameCompleter

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={"gpt-4": {}, "claude-3": {"description": ""}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
        ):
            c = ModelNameCompleter(trigger="/model")
            completions = list(c.get_completions(self._make_doc("/model "), None))
            metas = {
                completion.text: str(completion.display_meta)
                for completion in completions
            }
            assert "No description available." in metas["gpt-4"]
            assert "No description available." in metas["claude-3"]

    def test_filters_by_prefix(self):
        from code_puppy.command_line.model_picker_completion import ModelNameCompleter

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={"gpt-4": {}, "claude-3": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4",
            ),
        ):
            c = ModelNameCompleter(trigger="/model")
            completions = list(c.get_completions(self._make_doc("/model cl"), None))
            assert len(completions) == 1
            assert completions[0].text == "claude-3"

    def test_sees_model_added_after_construction(self):
        """Regression: /add_model writes extra_models.json, but completer
        stacks (the persistent prompt caches its stack for the whole
        session) were built before the add -- completions must reflect the
        config as of *each keystroke*, not as of construction time."""
        from code_puppy.command_line.model_picker_completion import ModelNameCompleter

        before_add = {"gpt-4o": {}, "claude-3": {}}
        after_add = {**before_add, "xai-grok-4": {}}
        states = iter([before_add, after_add])

        def _load():
            try:
                return next(states)
            except StopIteration:
                raise AssertionError(
                    "_load_models_config called more times than expected"
                ) from None

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                side_effect=_load,
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="gpt-4o",
            ),
        ):
            completer = ModelNameCompleter(trigger="/model")

            # Before /add_model: no grok suggestions.
            completions = list(
                completer.get_completions(self._make_doc("/model grok"), None)
            )
            assert completions == []

            # After /add_model: the newly added model is suggested immediately.
            completions = list(
                completer.get_completions(self._make_doc("/model grok"), None)
            )
            assert [c.text for c in completions] == ["xai-grok-4"]


class TestFindMatchingModel:
    @pytest.mark.parametrize(
        "query,models,expected",
        [
            ("gpt-4", ["gpt-4", "claude-3"], "gpt-4"),
            ("GPT-4", ["gpt-4"], "gpt-4"),
            ("gpt-4 tell me a joke", ["gpt-4", "gpt-4o"], "gpt-4"),
            ("gpt", ["gpt-4", "claude-3"], "gpt-4"),
            ("4.1", ["gpt-4o", "gpt-4.1-mini"], "gpt-4.1-mini"),
            ("xyz", ["gpt-4", "claude-3"], None),
            ("gpt-4-turbo hello", ["gpt-4", "gpt-4-turbo"], "gpt-4-turbo"),
        ],
        ids=[
            "exact_match",
            "case_insensitive",
            "input_starts_with_model",
            "prefix_match",
            "query_match_fallback",
            "no_match",
            "longest_model_wins",
        ],
    )
    def test_find_matching_model(self, query, models, expected):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model(query, models) == expected


class TestUpdateModelInInput:
    def test_model_command(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ) as mock_set,
        ):
            result = update_model_in_input("/model gpt-4")
            mock_set.assert_called_once_with("gpt-4")
            # After stripping the command and model, should be empty or None
            assert result is not None  # Empty string after strip

    def test_m_command(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ) as mock_set,
        ):
            update_model_in_input("/m gpt-4")
            mock_set.assert_called_once_with("gpt-4")

    def test_no_model_command(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        assert update_model_in_input("hello world") is None

    @pytest.mark.parametrize("cmd", ["/model xyz", "/m xyz"], ids=["model", "m"])
    def test_command_no_match(self, cmd):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with patch(
            "code_puppy.command_line.model_picker_completion._load_models_config",
            return_value={"gpt-4": {}},
        ):
            assert update_model_in_input(cmd) is None

    @pytest.mark.parametrize(
        "cmd",
        ["/model gpt-4 tell me a joke", "/m gpt-4 tell me a joke"],
        ids=["model", "m"],
    )
    def test_command_with_trailing_text(self, cmd):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ),
        ):
            result = update_model_in_input(cmd)
            assert result is not None
            assert "tell me a joke" in result


class TestModelSelectionMenu:
    """Drive the termflow-backed picker headlessly with scripted keys."""

    MODELS = [f"model-{i:02d}" for i in range(40)]

    def _drive(self, keys, models=None, active="model-00"):
        from io import StringIO

        script = iter(keys)
        out = StringIO()
        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value=active,
        ):
            menu_obj = ModelSelectionMenu(model_names=models or self.MODELS)
            menu = menu_obj.build_menu(
                key_source=lambda: next(script),
                output=out,
                size=lambda: (100, 40),
                alt_screen=False,
            )
            result = menu.run()
        return menu_obj, result, out.getvalue()

    def test_preselects_active_model(self):
        _, result, _ = self._drive(["enter"], active="model-17")
        assert result.item.value == "model-17"

    def test_active_model_marked(self):
        _, _, screen = self._drive(["escape"], active="model-01")
        assert "(active)" in screen

    def test_page_navigation_moves_selection(self):
        _, result, _ = self._drive(["page-down", "enter"], active="model-00")
        assert result.item.value == "model-15"  # MODEL_PICKER_PAGE_SIZE == 15

    def test_left_right_page_via_bound_keys(self):
        _, result, _ = self._drive(["right", "enter"], active="model-00")
        assert result.item.value == "model-15"
        _, result, _ = self._drive(["right", "left", "enter"], active="model-00")
        assert result.item.value == "model-00"

    def test_filter_narrows_matches(self):
        _, result, _ = self._drive(["3", "9", "enter"])
        assert result.item.value == "model-39"

    def test_ctrl_u_clears_filter(self):
        _, result, _ = self._drive(["3", "9", "ctrl-u", "enter"])
        # Filter cleared: cursor clamps back into the full list.
        assert result.item.value in self.MODELS

    def test_enter_ignored_when_filter_has_no_matches(self):
        _, result, _ = self._drive(["z", "z", "enter", "escape"])
        assert result.cancelled

    def test_no_matches_renders_hint(self):
        from termflow.ansi.utils import visible

        _, _, screen = self._drive(["z", "escape"])
        assert "(no matches)" in visible(screen)

    def test_escape_cancels(self):
        menu_obj, result, _ = self._drive(["escape"])
        assert result.cancelled
        assert menu_obj.pending_credentials_edit is None


class TestModelSelectionMenuKeybindings:
    def test_edit_credentials_bound_to_ctrl_e(self):
        from io import StringIO

        script = iter(["ctrl-e"])
        with (
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="m1",
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.required_env_var_for_model",
                return_value="API_KEY",
            ),
        ):
            menu_obj = ModelSelectionMenu(model_names=["m1", "m2"])
            menu = menu_obj.build_menu(
                key_source=lambda: next(script),
                output=StringIO(),
                size=lambda: (100, 30),
                alt_screen=False,
            )
            result = menu.run()
        assert menu_obj.pending_credentials_edit == "m1"
        assert result.item.value == "m1"

    def test_ctrl_e_without_env_var_stays_in_menu(self):
        from io import StringIO

        script = iter(["ctrl-e", "escape"])
        with (
            patch(
                "code_puppy.command_line.model_picker_completion.get_active_model",
                return_value="m1",
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.required_env_var_for_model",
                return_value=None,
            ),
        ):
            menu_obj = ModelSelectionMenu(model_names=["m1"])
            menu = menu_obj.build_menu(
                key_source=lambda: next(script),
                output=StringIO(),
                size=lambda: (100, 30),
                alt_screen=False,
            )
            result = menu.run()
        assert menu_obj.pending_credentials_edit is None
        assert result.cancelled

    def test_plain_e_reaches_filter(self):
        from io import StringIO

        script = iter(["e", "escape"])
        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="alpha",
        ):
            menu_obj = ModelSelectionMenu(model_names=["alpha", "beta"])
            menu = menu_obj.build_menu(
                key_source=lambda: next(script),
                output=(out := StringIO()),
                size=lambda: (100, 30),
                alt_screen=False,
            )
            menu.run()
        # "e" became search text, not a credential action.
        assert menu_obj.pending_credentials_edit is None
        assert "search: " in out.getvalue() or "e" in out.getvalue()


class TestInteractiveModelPicker:
    @pytest.mark.asyncio
    async def test_sets_awaiting_user_input_around_picker(self):
        from code_puppy.command_line.model_picker_completion import (
            interactive_model_picker,
        )

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.ModelSelectionMenu.run_async",
                return_value="gpt-4",
            ) as mock_run,
            patch(
                "code_puppy.tools.command_runner.set_awaiting_user_input"
            ) as mock_set,
        ):
            result = await interactive_model_picker()

        assert result == "gpt-4"
        mock_run.assert_called_once()
        mock_set.assert_has_calls([call(True, notify=False), call(False, notify=False)])


class TestGetInputWithModelCompletion:
    @pytest.mark.asyncio
    async def test_basic(self):
        from code_puppy.command_line.model_picker_completion import (
            get_input_with_model_completion,
        )

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.PromptSession"
            ) as mock_session_cls,
        ):
            mock_session = MagicMock()
            mock_session.prompt_async = MagicMock(
                return_value=self._make_coro("hello world")
            )
            mock_session_cls.return_value = mock_session
            result = await get_input_with_model_completion()
            assert result == "hello world"

    @pytest.mark.asyncio
    async def test_with_model_command(self):
        from code_puppy.command_line.model_picker_completion import (
            get_input_with_model_completion,
        )

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.PromptSession"
            ) as mock_session_cls,
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ),
        ):
            mock_session = MagicMock()
            mock_session.prompt_async = MagicMock(
                return_value=self._make_coro("/model gpt-4 hello")
            )
            mock_session_cls.return_value = mock_session
            result = await get_input_with_model_completion()
            assert "hello" in result

    @pytest.mark.asyncio
    async def test_with_history_file(self, tmp_path):
        from code_puppy.command_line.model_picker_completion import (
            get_input_with_model_completion,
        )

        hfile = str(tmp_path / "history.txt")
        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.PromptSession"
            ) as mock_session_cls,
        ):
            mock_session = MagicMock()
            mock_session.prompt_async = MagicMock(return_value=self._make_coro("test"))
            mock_session_cls.return_value = mock_session
            result = await get_input_with_model_completion(history_file=hfile)
            assert result == "test"

    @staticmethod
    async def _make_coro(value):
        return value

    @pytest.mark.parametrize(
        "cmd", ["  /model  gpt-4", "  /m  gpt-4"], ids=["model", "m"]
    )
    def test_idx_not_found(self, cmd):
        """Cover the return None when idx == -1 (extra spacing hides pattern)."""
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with (
            patch(
                "code_puppy.command_line.model_picker_completion._load_models_config",
                return_value={"gpt-4": {}},
            ),
            patch(
                "code_puppy.command_line.model_picker_completion.set_model_and_reload_agent"
            ),
        ):
            result = update_model_in_input(cmd)
            assert result is None
