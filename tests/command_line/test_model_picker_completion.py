"""Tests for model_picker_completion.py to achieve 100% coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prompt_toolkit.document import Document


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


class TestFindMatchingModel:
    def test_exact_match(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model("gpt-4", ["gpt-4", "claude-3"]) == "gpt-4"

    def test_case_insensitive(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model("GPT-4", ["gpt-4"]) == "gpt-4"

    def test_input_starts_with_model(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert (
            _find_matching_model("gpt-4 tell me a joke", ["gpt-4", "gpt-4o"]) == "gpt-4"
        )

    def test_prefix_match(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model("gpt", ["gpt-4", "claude-3"]) == "gpt-4"

    def test_query_match_fallback(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model("4.1", ["gpt-4o", "gpt-4.1-mini"]) == "gpt-4.1-mini"

    def test_no_match(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        assert _find_matching_model("xyz", ["gpt-4", "claude-3"]) is None

    def test_longest_model_wins(self):
        from code_puppy.command_line.model_picker_completion import (
            _find_matching_model,
        )

        # "gpt-4-turbo hello" should match "gpt-4-turbo" not "gpt-4"
        assert (
            _find_matching_model("gpt-4-turbo hello", ["gpt-4", "gpt-4-turbo"])
            == "gpt-4-turbo"
        )


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

    def test_model_command_no_match(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with patch(
            "code_puppy.command_line.model_picker_completion._load_models_config",
            return_value={"gpt-4": {}},
        ):
            assert update_model_in_input("/model xyz") is None

    def test_m_command_no_match(self):
        from code_puppy.command_line.model_picker_completion import (
            update_model_in_input,
        )

        with patch(
            "code_puppy.command_line.model_picker_completion._load_models_config",
            return_value={"gpt-4": {}},
        ):
            assert update_model_in_input("/m xyz") is None

    def test_model_with_trailing_text(self):
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
            result = update_model_in_input("/model gpt-4 tell me a joke")
            assert result is not None
            assert "tell me a joke" in result


class TestModelSelectionMenu:
    def test_preselects_active_model_page(self):
        from code_puppy.command_line.model_picker_completion import (
            MODEL_PICKER_PAGE_SIZE,
            ModelSelectionMenu,
        )

        models = [f"model-{i}" for i in range(MODEL_PICKER_PAGE_SIZE + 5)]
        active_model = models[-1]

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value=active_model,
        ):
            menu = ModelSelectionMenu(models)

        assert menu.selected_index == len(models) - 1
        assert menu.page == 1
        assert active_model in menu.models_on_page

    def test_page_navigation_moves_selection_to_page_start(self):
        from code_puppy.command_line.model_picker_completion import (
            MODEL_PICKER_PAGE_SIZE,
            ModelSelectionMenu,
        )

        models = [f"model-{i}" for i in range(MODEL_PICKER_PAGE_SIZE * 2 + 1)]

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="missing-model",
        ):
            menu = ModelSelectionMenu(models)

        menu._page_down()
        assert menu.page == 1
        assert menu.selected_index == MODEL_PICKER_PAGE_SIZE

        menu._page_up()
        assert menu.page == 0
        assert menu.selected_index == 0

    def test_move_down_keeps_selection_visible(self):
        from code_puppy.command_line.model_picker_completion import (
            MODEL_PICKER_PAGE_SIZE,
            ModelSelectionMenu,
        )

        models = [f"model-{i}" for i in range(MODEL_PICKER_PAGE_SIZE + 1)]

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="missing-model",
        ):
            menu = ModelSelectionMenu(models)

        menu.selected_index = MODEL_PICKER_PAGE_SIZE - 1
        menu.page = 0
        menu._move_down()

        assert menu.selected_index == MODEL_PICKER_PAGE_SIZE
        assert menu.page == 1

    def test_filter_keeps_current_model_selected_when_visible(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="claude-3-sonnet",
        ):
            menu = ModelSelectionMenu(
                ["gpt-5-mini", "claude-3-sonnet", "claude-3-opus"]
            )

        menu._set_filter_text("claude")

        assert menu.visible_model_names == ["claude-3-sonnet", "claude-3-opus"]
        assert menu.selected_index == 0

    def test_filter_resets_to_first_visible_match_when_selection_disappears(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="gpt-5-mini",
        ):
            menu = ModelSelectionMenu(
                ["gpt-5-mini", "claude-3-sonnet", "claude-3-opus"]
            )

        menu._set_filter_text("opus")

        assert menu.visible_model_names == ["claude-3-opus"]
        assert menu.selected_index == 0

    def test_accept_selection_returns_false_when_filter_has_no_matches(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="missing-model",
        ):
            menu = ModelSelectionMenu(["gpt-5-mini", "claude-3-sonnet"])

        menu._set_filter_text("nope")

        assert menu._accept_selection() is False
        assert menu.result is None

    def test_accept_selection_guards_invalid_selected_index(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="missing-model",
        ):
            menu = ModelSelectionMenu(["gpt-5-mini"])

        menu.selected_index = 99

        assert menu._accept_selection() is False
        assert menu.result is None

    def test_render_no_matches_mentions_filter_and_clear_shortcut(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="missing-model",
        ):
            menu = ModelSelectionMenu(["gpt-5-mini", "claude-3-sonnet"])

        menu._set_filter_text("nope")

        rendered = "".join(text for _, text in menu._render())

        assert "No models match the current filter." in rendered
        assert "Clear filter" in rendered


class TestModelSelectionMenuParams:
    """Tests for the reusable ``ModelSelectionMenu`` parameterisation
    introduced in 2026-06: ``title``, ``current_model``,
    ``extra_options`` (sentinel rows), and ``active_label``.

    These exist so the model picker can be reused by the agent-menu
    ``p`` pin flow and the ``/pin_model`` slash command without
    regressing the original ``/model`` behaviour (default args
    must reproduce the legacy picker byte-for-byte).
    """

    def test_default_construction_matches_legacy_defaults(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        # Patch get_active_model to a model in the list so the
        # constructor's pre-selection logic has something to find.
        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="m1",
        ):
            menu = ModelSelectionMenu(["m1", "m2"])

        assert menu.title == " \U0001f916 Select Active Model"
        assert menu.active_label == "(active)"
        assert menu.current_model == "m1"
        assert menu.extra_options == []
        # visible_model_names should be just the model list -- no sentinels.
        assert menu.visible_model_names == ["m1", "m2"]
        # selected_index should pre-select the current model.
        assert menu.selected_index == menu.visible_model_names.index("m1")

    def test_explicit_current_model_overrides_get_active_model(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="should-be-ignored",
        ):
            menu = ModelSelectionMenu(
                ["m1", "m2", "pinned-model"],
                current_model="pinned-model",
            )

        assert menu.current_model == "pinned-model"
        assert menu.selected_index == menu.visible_model_names.index("pinned-model")

    def test_extra_options_pinned_at_top_of_visible(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            ["alpha", "beta", "gamma"],
            extra_options=[("(unpin)", "Reset to default model")],
        )

        # Sentinel row at index 0, model rows after.
        assert menu.extra_option_values == ["(unpin)"]
        assert menu.visible_model_names == ["(unpin)", "alpha", "beta", "gamma"]
        assert menu.extra_option_descriptions == {"(unpin)": "Reset to default model"}

    def test_extra_options_multiple_sentinels_in_order(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            ["alpha", "beta"],
            extra_options=[
                ("(unpin)", "Reset to default model"),
                ("(reset-foo)", "Reset just the foo"),
            ],
        )

        assert menu.extra_option_values == ["(unpin)", "(reset-foo)"]
        assert menu.visible_model_names == [
            "(unpin)",
            "(reset-foo)",
            "alpha",
            "beta",
        ]

    def test_extra_options_filter_matches_against_value(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            ["alpha", "beta", "gamma"],
            extra_options=[("(unpin)", "Reset to default model")],
        )

        # Filtering by "unpin" should include the sentinel (matched
        # against the value text "(unpin)").
        menu._set_filter_text("unpin")
        assert menu.visible_model_names == ["(unpin)"]

    def test_extra_options_filter_can_hide_sentinels(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            ["alpha", "beta"],
            extra_options=[("(unpin)", "Reset to default model")],
        )

        # Filtering by "alp" should not match the sentinel value.
        menu._set_filter_text("alp")
        assert menu.visible_model_names == ["alpha"]

    def test_accept_selection_returns_sentinel_value(self):
        """Selecting a sentinel row returns the sentinel VALUE, not its
        description. This is the contract ``(unpin)`` and the pin
        flows rely on.
        """
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="not-a-model",
        ):
            menu = ModelSelectionMenu(
                ["alpha", "beta"],
                extra_options=[("(unpin)", "Reset to default model")],
            )

        # Default selected_index is 0, which is the sentinel.
        assert menu.selected_index == 0
        assert menu._accept_selection() is True
        assert menu.result == "(unpin)"

    def test_accept_selection_returns_model_value(self):
        """After moving past the sentinel, accept_selection returns the
        model name (not "(unpin)")."""
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="not-a-model",
        ):
            menu = ModelSelectionMenu(
                ["alpha", "beta"],
                extra_options=[("(unpin)", "Reset to default model")],
            )

        # Move down once -- now selecting "alpha".
        menu._move_down()
        assert menu.selected_index == 1
        assert menu._accept_selection() is True
        assert menu.result == "alpha"

    def test_active_label_override_in_render(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            ["alpha", "beta"],
            current_model="beta",
            active_label="(pinned)",
        )

        rendered = "".join(text for _, text in menu._render())
        # The override label appears next to the current model.
        assert "(pinned)" in rendered
        # The legacy default label does NOT appear in the row output.
        assert "(active)" not in rendered

    def test_active_label_default_in_render(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="alpha",
        ):
            menu = ModelSelectionMenu(["alpha", "beta"])

        rendered = "".join(text for _, text in menu._render())
        assert "(active)" in rendered

    def test_custom_title_in_render(self):
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(["alpha"], title=" Pin a model for 'agent-1'")

        rendered = "".join(text for _, text in menu._render())
        assert " Pin a model for 'agent-1'" in rendered
        # The legacy default title must not appear.
        assert "Select Active Model" not in rendered

    def test_extra_options_sentinel_render_uses_description(self):
        """Sentinel rows render the description next to the value --
        NOT the active_label."""
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            ["alpha"],
            current_model="alpha",
            extra_options=[("(unpin)", "Reset to default model")],
            active_label="(pinned)",
        )

        rendered = "".join(text for _, text in menu._render())
        # Sentinel row text and its description.
        assert "(unpin)" in rendered
        assert "Reset to default model" in rendered
        # The active_label is reserved for model rows, not sentinels.
        # We can confirm the (pinned) marker appears next to the model.
        assert "(pinned)" in rendered

    def test_pagination_with_extra_options(self):
        from code_puppy.command_line.model_picker_completion import (
            MODEL_PICKER_PAGE_SIZE,
            ModelSelectionMenu,
        )

        # More models than a single page; verify pagination math
        # still works when extra_options are present.
        models = [f"model-{i}" for i in range(MODEL_PICKER_PAGE_SIZE * 2 + 3)]
        with patch(
            "code_puppy.command_line.model_picker_completion.get_active_model",
            return_value="not-a-model",
        ):
            menu = ModelSelectionMenu(
                models,
                extra_options=[("(unpin)", "Reset to default model")],
            )

        # The visible total includes the sentinel.
        assert len(menu.visible_model_names) == len(models) + 1
        # The sentinel is on page 0.
        assert "(unpin)" in menu.models_on_page
        # Navigate to page 1 and ensure the sentinel is gone.
        menu._page_down()
        assert menu.page == 1
        assert "(unpin)" not in menu.models_on_page
        # _page_down sets selected_index to the start of the new page.
        assert menu.selected_index == MODEL_PICKER_PAGE_SIZE

    def test_extra_options_with_empty_model_list(self):
        """Sentinels can still render when no models are available
        (used by the agent menu to allow unpinning when models are
        gone)."""
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            [],
            extra_options=[("(unpin)", "Reset to default model")],
        )

        assert menu.visible_model_names == ["(unpin)"]
        assert menu._accept_selection() is True
        assert menu.result == "(unpin)"

    def test_run_async_wraps_suspended_key_listener(self):
        """``run_async`` should suspend the background key listener
        for the duration of the picker run. We patch both the
        listener and ``app.run_async`` so we never start a real
        TUI. The import is at module level in
        ``model_picker_completion`` so we patch there."""
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        with (
            patch(
                "code_puppy.command_line.model_picker_completion.Application"
            ) as mock_app_cls,
            patch(
                "code_puppy.command_line.model_picker_completion.suspended_key_listener"
            ) as mock_suspend,
        ):
            mock_app = MagicMock()
            mock_app.run_async = AsyncMock()
            mock_app_cls.return_value = mock_app
            mock_suspend.return_value.__enter__ = MagicMock()
            mock_suspend.return_value.__exit__ = MagicMock(return_value=False)

            import asyncio

            menu = ModelSelectionMenu(["alpha", "beta"])
            asyncio.run(menu.run_async())

            # The listener suspension context was entered.
            mock_suspend.assert_called_once()

    # ------------------------------------------------------------------
    # Regression tests for the two critical bugs in code review.
    # ------------------------------------------------------------------
    def _flatten_render(self, menu) -> list[str]:
        """Helper: flatten ``_render()`` tuples into a list of strings,
        preserving order. Used to make assertions easier to read."""
        return [text for (_style, text) in menu._render()]

    def test_render_filter_hides_sentinel_keeps_model_labels(self):
        """CRITICAL #1: when the filter hides the sentinel row, model
        rows must NOT be misclassified as sentinels -- they must
        still receive their ``active_label`` ("(pinned)" in the pin
        flow). The buggy code classified by absolute index, so a
        model row that slid into the sentinel region lost its
        marker."""
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            model_names=["gpt-4", "claude-3"],
            title="  Pin a model for 'agent1'",
            current_model="claude-3",  # pin is on a model the filter keeps
            extra_options=[("(unpin)", "Reset to default model")],
            active_label="(pinned)",
        )
        # Type "cl" -- matches "claude-3" but NOT "(unpin)" or
        # "gpt-4". The sentinel is hidden, the surviving model is
        # the "current" one.
        menu._set_filter_text("cl")
        flat = self._flatten_render(menu)
        joined = " | ".join(flat)

        # The "current" header still shows the real model name
        # (NOT the sentinel) because current_model is a real model.
        assert "Current: claude-3" in joined
        # The sentinel row is hidden (the filter would have to
        # match "(unpin)" or "unpin" for it to appear).
        assert "(unpin)" not in joined
        assert "Reset to default model" not in joined
        # The surviving model row keeps its "(pinned)" label --
        # this is the regression assertion. With the BUG, the
        # sentinel-classification used ``absolute_index <
        # extra_count``; the surviving "claude-3" sat at index
        # 0 in the FILTERED list, so it was misclassified as a
        # sentinel and the "(pinned)" label was lost.
        assert "claude-3" in joined
        assert "(pinned)" in joined

    def test_render_unpinned_state_does_not_label_global_model(self):
        """CRITICAL #2: when ``current_model`` is the "(unpin)"
        sentinel (i.e. the agent has no pin), the picker must NOT
        label some other model "(pinned)" -- that would be
        factually wrong. The sentinel row should show the
        "(current)" marker instead."""
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            model_names=["gpt-4", "claude-3"],
            title="  Pin a model for 'agent1'",
            current_model="(unpin)",  # pin flow: no pin => sentinel
            extra_options=[("(unpin)", "Reset to default model")],
            active_label="(pinned)",
        )
        flat = self._flatten_render(menu)
        joined = " | ".join(flat)

        # Header shows a friendly label, NOT the raw "(unpin)"
        # sentinel.
        assert "Current: (no pin / default)" in joined
        assert "Current: (unpin)" not in joined
        # The sentinel row carries the "(current)" marker.
        assert "(unpin)" in joined
        assert "(current)" in joined
        # No model row is labeled "(pinned)" -- there is no pin.
        assert "(pinned)" not in joined, (
            f"Found '(pinned)' in unpinned state; full render: {flat!r}"
        )

    def test_render_unpinned_state_label_construction(self):
        """Companion to the above: in the unpinned state, the
        "(unpin)" sentinel row should show the description and
        the "(current)" marker on the SAME line block -- NOT the
        "(pinned)" label. The bug-prone code would either show
        nothing or show "(pinned)"."""
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            model_names=["gpt-4"],
            current_model="(unpin)",
            extra_options=[("(unpin)", "Reset to default model")],
            active_label="(pinned)",
        )
        flat = self._flatten_render(menu)
        joined = " | ".join(flat)

        # The sentinel description is rendered.
        assert "Reset to default model" in joined
        # The "(current)" marker is rendered for the sentinel.
        assert "(current)" in joined
        # The model "gpt-4" is rendered, but NOT with "(pinned)".
        assert "gpt-4" in joined
        assert "(pinned)" not in joined, (
            f"No line should contain '(pinned)' when no pin is set; got: {flat!r}"
        )

    def test_render_sentinel_value_coincides_with_model_name(self):
        """Edge case: a sentinel value that ALSO matches a real
        model name. Classification must be deterministic -- the
        sentinel value is the authority. A model row whose name
        matches a sentinel value is treated as a model row (not
        a sentinel) UNLESS its value is exactly the sentinel.
        In this test we put the sentinel value at index 0 and
        put a model with the same name. We assert no crash and
        that the visible rows are stable + the sentinel renders
        as a sentinel."""
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        # sentinel value = "(unpin)" -- also happens to be
        # the value of a model. Edge case: the model "claude-3"
        # doesn't match the sentinel, so classification is
        # unambiguous here. The regression we want is just
        # "no crash, deterministic output".
        menu = ModelSelectionMenu(
            model_names=["(unpin)", "claude-3"],
            current_model=None,  # falls back to get_active_model
            extra_options=[("(unpin)", "Reset to default model")],
            active_label="(pinned)",
        )
        # No filter -- both rows visible.
        flat = self._flatten_render(menu)
        joined = " | ".join(flat)

        # The sentinel row appears with its description.
        assert "Reset to default model" in joined
        # The model row appears.
        assert "claude-3" in joined
        # No crash, deterministic ordering: sentinel first.
        unpin_idx = next(
            i for i, line in enumerate(flat) if line.strip().endswith("(unpin)")
        )
        claude_idx = next(i for i, line in enumerate(flat) if "claude-3" in line)
        assert unpin_idx < claude_idx, (
            f"Sentinel row should be rendered before model row; "
            f"got sentinel at {unpin_idx}, claude at {claude_idx}"
        )

    def test_filter_only_matches_against_sentinel_value_not_description(self):
        """Sanity: the filter still matches against the sentinel
        VALUE (e.g. typing "un" should reveal "(unpin)"). This was
        already tested, but with the new value-membership
        classification we want to make sure filtering by a
        sentinel value works AND the surviving sentinel is
        rendered correctly (with description, not "(pinned)")."""
        from code_puppy.command_line.model_picker_completion import ModelSelectionMenu

        menu = ModelSelectionMenu(
            model_names=["gpt-4", "claude-3"],
            current_model="(unpin)",
            extra_options=[("(unpin)", "Reset to default model")],
            active_label="(pinned)",
        )
        menu._set_filter_text("un")
        flat = self._flatten_render(menu)
        joined = " | ".join(flat)

        # The sentinel is visible.
        assert "(unpin)" in joined
        # The sentinel description is visible.
        assert "Reset to default model" in joined
        # Models are hidden by the filter.
        assert "gpt-4" not in joined
        assert "claude-3" not in joined
        # "(current)" marker on the sentinel survives the filter.
        assert "(current)" in joined
        # No model "(pinned)" label appears.
        assert "(pinned)" not in joined


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
        assert mock_set.call_args_list[0].args == (True,)
        assert mock_set.call_args_list[-1].args == (False,)


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

    def test_model_idx_not_found(self):
        """Cover the return None when idx == -1 for /model."""
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
            # Create a case where text.find won't match the pattern
            # This happens when original text has different spacing
            result = update_model_in_input("  /model  gpt-4")
            # The cmd extracted is "/model", rest is "gpt-4"
            # Pattern is "/model gpt-4" but original has extra spaces
            # Actually let me trace: content = "/model  gpt-4" (stripped)
            # content.lower().startswith("/model ") -> True
            # model_cmd = "/model", rest = " gpt-4".strip() = "gpt-4"
            # pattern = "/model gpt-4", text = "  /model  gpt-4"
            # text.find("/model gpt-4") -> -1 because of double space
            assert result is None

    def test_m_idx_not_found(self):
        """Cover the return None when idx == -1 for /m."""
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
            result = update_model_in_input("  /m  gpt-4")
            assert result is None

    def test_m_with_trailing_text(self):
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
            result = update_model_in_input("/m gpt-4 tell me a joke")
            assert result is not None
            assert "tell me a joke" in result
