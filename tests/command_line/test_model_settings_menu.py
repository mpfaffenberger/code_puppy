"""Tests for the termflow-based model-settings menu.

Pure helpers, headless menu/editor drives, flow orchestration, and the
catalog-snapshot latency invariant (repaints must never reload the
model catalog: load_model_config callbacks may perform HTTP discovery).
"""

from io import StringIO
from unittest.mock import patch

from code_puppy.command_line import model_settings_menu as msm
from code_puppy.command_line.model_settings_defs import SETTING_DEFINITIONS
from code_puppy.config import CUSTOM_MODEL_SETTING

CATALOG = {
    "vizio-gpt": {
        "supported_settings": ["temperature", "reasoning_effort", "verbosity"]
    },
    "vizio-claude": {"supported_settings": ["extended_thinking", "budget_tokens"]},
}


def keys(*sequence):
    script = iter(sequence)
    return {
        "key_source": lambda: next(script),
        "output": StringIO(),
        "size": lambda: (110, 30),
    }


def scripted(factory, sequence):
    def build(*args, **kwargs):
        kwargs.update(keys(*sequence))
        return factory(*args, **kwargs)

    return build


# -- pure helpers -------------------------------------------------------------


class TestFormatValue:
    def test_boolean_and_numeric(self):
        assert msm.format_value("interleaved_thinking", True) == "Enabled"
        assert msm.format_value("temperature", 0.7) == "0.70"
        assert msm.format_value("seed", 42.0) == "42"

    def test_none_variants(self):
        assert msm.format_value("retry_main_strategy", None) == "(uses global)"
        assert "default" in msm.format_value("reasoning_effort", None)

    def test_custom_pairs(self):
        assert msm.format_value(CUSTOM_MODEL_SETTING, {"a": True}) == "a=true"
        assert msm.format_value(CUSTOM_MODEL_SETTING, {}) == "(none)"

    def test_unknown_setting(self):
        assert msm.format_value("stale_thing", "x") == "x"


class TestParseNumeric:
    def test_clamps_and_types(self):
        temp = SETTING_DEFINITIONS["temperature"]
        assert msm.parse_numeric("0.5", temp) == 0.5
        assert msm.parse_numeric("2.0", temp) is None
        assert msm.parse_numeric("nah", temp) is None
        seed = SETTING_DEFINITIONS["seed"]
        assert msm.parse_numeric("42", seed) == 42
        assert isinstance(msm.parse_numeric("42", seed), int)


class TestSupportedSettings:
    def test_always_includes_retry_and_custom(self):
        supported = msm.supported_settings("vizio-claude", CATALOG)
        assert CUSTOM_MODEL_SETTING in supported
        assert "retry_main_strategy" in supported
        assert "extended_thinking" in supported
        assert "verbosity" not in supported


# -- previews -----------------------------------------------------------------


class TestPreviews:
    def test_model_summary_lists_configured(self):
        with patch.object(
            msm,
            "_get_model_display_settings",
            return_value={"temperature": 0.5},
        ):
            text = msm.model_summary("vizio-gpt", CATALOG)
        assert "Temperature" in text and "0.50" in text

    def test_setting_details_shows_range_and_choices(self):
        text = msm.setting_details("temperature", "vizio-gpt", CATALOG, 0.5)
        assert "Range: 0.0 - 1.0" in text
        text = msm.setting_details("reasoning_effort", "vizio-gpt", CATALOG, None)
        assert "Choices:" in text


# -- menus / editors (headless) ----------------------------------------------


class TestMenus:
    def test_models_menu_preselects_current(self):
        menu = msm.build_models_menu(
            ["a-model", "b-model"], "b-model", CATALOG, **keys("enter")
        )
        assert menu.run().item.value == "b-model"

    def test_settings_menu_reset_sentinel(self):
        menu = msm.build_settings_menu("vizio-gpt", CATALOG, **keys("r"))
        result = menu.run()
        kind, setting = result.item.value
        assert kind == msm._RESET
        assert setting in msm.supported_settings("vizio-gpt", CATALOG)

    def test_choice_editor_boolean_labels(self):
        menu = msm.build_choice_editor(
            "interleaved_thinking", "vizio-gpt", CATALOG, True, **keys("down", "enter")
        )
        assert menu.run().item.value is False

    def test_choice_editor_starts_at_current(self):
        menu = msm.build_choice_editor(
            "reasoning_effort", "vizio-gpt", CATALOG, "high", **keys("enter")
        )
        assert menu.run().item.value == "high"


class TestNumericEditor:
    def test_typed_value_saves(self):
        changed, value = msm.run_numeric_editor(
            "temperature", "vizio-gpt", None, **keys("0", ".", "3", "enter")
        )
        assert (changed, value) == (True, 0.3)

    def test_empty_clears_override(self):
        changed, value = msm.run_numeric_editor(
            "temperature", "vizio-gpt", 0.7, **keys("ctrl-u", "enter")
        )
        assert (changed, value) == (True, None)

    def test_escape_cancels(self):
        changed, _ = msm.run_numeric_editor(
            "temperature", "vizio-gpt", None, **keys("escape")
        )
        assert changed is False

    def test_out_of_range_blocks_commit(self):
        changed, value = msm.run_numeric_editor(
            "temperature",
            "vizio-gpt",
            None,
            **keys("9", "enter", "ctrl-u", "1", "enter"),
        )
        assert (changed, value) == (True, 1.0)


class TestPairEditor:
    def test_parses_scalars(self):
        result = msm.run_pair_editor(
            "vizio-gpt", **keys("a", " ", "=", " ", "5", "enter")
        )
        assert result == ("a", 5)

    def test_validator_blocks_garbage(self):
        result = msm.run_pair_editor(
            "vizio-gpt", **keys("a", "enter", "=", "b", "enter")
        )
        assert result == ("a", "b")

    def test_cancel(self):
        assert msm.run_pair_editor("vizio-gpt", **keys("escape")) is None


# -- flows --------------------------------------------------------------------


class TestCustomParamsFlow:
    def test_add_edit_delete(self):
        store = {}

        def fake_get(model):
            return dict(store)

        def fake_set(model, key, value):
            if value is None:
                store.pop(key, None)
            else:
                store[key] = value

        menu_scripts = iter([["enter"], ["d"], ["escape"]])
        pair_results = iter([("k", 1)])
        with (
            patch.object(msm, "get_custom_model_settings", fake_get),
            patch.object(msm, "set_custom_model_setting", fake_set),
        ):
            changed = msm.run_custom_params_flow(
                "vizio-gpt",
                menu_factory=lambda pairs, model, **kw: msm.build_custom_menu(
                    pairs, model, **keys(*next(menu_scripts))
                ),
                pair_editor=lambda model, initial="": next(pair_results, None),
            )
        assert changed is True
        assert store == {}  # added then deleted


class TestSettingsFlow:
    def test_choice_edit_saves(self):
        saved = []
        settings_scripts = iter([["enter"], ["escape"]])

        def settings_factory(model, config, initial_index=0, **kw):
            return msm.build_settings_menu(
                model, config, initial_index, **keys(*next(settings_scripts))
            )

        with (
            patch.object(msm, "save_setting", lambda m, k, v: saved.append((k, v))),
            patch.object(msm, "_get_model_display_settings", return_value={}),
        ):
            changed = msm.run_settings_flow(
                "vizio-gpt",
                CATALOG,
                settings_menu_factory=settings_factory,
                choice_editor_factory=lambda *a, **kw: msm.build_choice_editor(
                    *a, **keys("enter")
                ),
                numeric_editor=lambda *a, **kw: (True, 0.5),
            )
        assert changed is True
        assert saved  # something was persisted

    def test_reset_sentinel_resets(self):
        resets = []
        settings_scripts = iter([["r"], ["escape"]])

        def settings_factory(model, config, initial_index=0, **kw):
            return msm.build_settings_menu(
                model, config, initial_index, **keys(*next(settings_scripts))
            )

        with patch.object(msm, "reset_setting", lambda m, k: resets.append(k)):
            changed = msm.run_settings_flow(
                "vizio-gpt", CATALOG, settings_menu_factory=settings_factory
            )
        assert changed is True and len(resets) == 1


class TestModelSettingsFlow:
    def test_model_pick_then_exit(self):
        model_scripts = iter([["enter"], ["escape"]])

        def models_factory(models, current, config, **kw):
            return msm.build_models_menu(
                models, current, config, **keys(*next(model_scripts))
            )

        flows = []
        with (
            patch.object(msm.ModelFactory, "load_config", return_value=CATALOG),
            patch.object(msm, "get_global_model_name", return_value="vizio-gpt"),
        ):
            changed = msm.run_model_settings_flow(
                models_menu_factory=models_factory,
                settings_flow=lambda model, config: flows.append(model) or True,
            )
        assert changed is True
        assert flows == ["vizio-gpt"]

    def test_empty_catalog(self):
        assert msm.run_model_settings_flow(models_config={}) is False


class TestCatalogSnapshotInvariant:
    def test_flow_loads_catalog_exactly_once(self):
        """Repaints and previews must reuse the snapshot -- the
        load_model_config callback may perform HTTP discovery."""
        model_scripts = iter([["down", "up", "enter"], ["escape"]])

        def models_factory(models, current, config, **kw):
            return msm.build_models_menu(
                models, current, config, **keys(*next(model_scripts))
            )

        with (
            patch.object(
                msm.ModelFactory, "load_config", return_value=CATALOG
            ) as load_config,
            patch.object(msm, "get_global_model_name", return_value="vizio-gpt"),
        ):
            msm.run_model_settings_flow(
                models_menu_factory=models_factory,
                settings_flow=lambda model, config: False,
            )
        assert load_config.call_count == 1
