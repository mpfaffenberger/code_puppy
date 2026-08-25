"""Tests for ``code_puppy.command_line.set_menu`` and the slash dispatcher.

This file covers:
* ``apply_setting`` validation + restart warnings + agent reload toggle
* edit flow: choice menus (Cancel keeps current, custom falls through
  to the text editor), typed TextInputs with masking for sensitive keys
* type coercion
* entry building / search
* reset bookkeeping (must record into ``changed_settings``)
* dispatcher correctly drains ``PickerResult.pending_messages`` and
  triggers exactly one coalesced agent reload
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from code_puppy.command_line.config_apply import ApplyResult, apply_setting
from code_puppy.command_line.set_menu import (
    PickerResult,
    _apply_and_record,
    _build_entries,
    _coerce_typed_input,
    _detect_dynamic_type,
    _edit_setting,
    _record_reset,
    build_choice_menu,
    build_settings_menu,
    run_text_editor,
)
from code_puppy.command_line.set_menu_settings import (
    SETTINGS_CATEGORIES,
    Setting,
)


def find_setting(key: str) -> Setting:
    """Locate a curated :class:`Setting` by key. Test helper."""
    for category in SETTINGS_CATEGORIES:
        for setting in category.settings:
            if setting.key == key:
                return setting
    raise AssertionError(f"Setting '{key}' not found in SETTINGS_CATEGORIES")


def test_dbos_effective_value_uses_plugin_capability():
    setting = find_setting("enable_dbos")
    with patch(
        "code_puppy.command_line.set_menu_catalog.get_feature_capability",
        return_value=False,
    ) as capability:
        assert setting.effective_getter() is False
    capability.assert_called_once_with("dbos_durable_exec")


def test_anthropic_native_editor_is_discoverable_and_off_by_default():
    """Regression: the Phase 3 native-editor flag was wired into
    model_capabilities.py/config.py's /set autocompletion but had no entry
    in the curated /set picker, so a user browsing Features would never
    find it. It must resolve through the real getter and read as False
    with no config override present."""
    setting = find_setting("enable_anthropic_native_editor")
    assert setting.type_hint == "bool"
    assert setting.effective_getter() is False


# ---------------------------------------------------------------------------
# apply_setting validation
# ---------------------------------------------------------------------------


class TestApplySetting:
    def test_missing_key_returns_error(self):
        result = apply_setting("", "anything")
        assert result.ok is False
        assert result.error and "key" in result.error.lower()

    @pytest.mark.parametrize("key", ["openai_reasoning_effort", "openai_verbosity"])
    def test_model_settings_only_keys_are_rejected(self, key):
        with patch("code_puppy.config.set_config_value") as mock_set:
            result = apply_setting(key, "high")
        assert result.ok is False
        assert "/model_settings" in (result.error or "")
        mock_set.assert_not_called()

    def test_cancel_agent_key_invalid_returns_error(self):
        with patch("code_puppy.config.set_config_value") as mock_set:
            result = apply_setting("cancel_agent_key", "ctrl+x")
        assert result.ok is False
        assert "Invalid cancel_agent_key" in (result.error or "")
        mock_set.assert_not_called()

    def test_cancel_agent_key_valid_warns_restart(self):
        with (
            patch("code_puppy.config.set_config_value") as mock_set,
            patch("code_puppy.agents.get_current_agent") as mock_agent,
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            result = apply_setting("cancel_agent_key", "CTRL+K")
        assert result.ok is True
        assert result.value_after == "ctrl+k"
        assert result.requires_restart is True
        assert "restart" in (result.warning or "").lower()
        mock_set.assert_called_once_with("cancel_agent_key", "ctrl+k")

    def test_enable_dbos_warns_restart(self):
        with (
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            result = apply_setting("enable_dbos", "false")
        assert result.ok is True
        assert result.requires_restart is True
        assert "restart" in (result.warning or "").lower()

    def test_yolo_mode_no_restart(self):
        with (
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            result = apply_setting("yolo_mode", "true")
        assert result.ok is True
        assert result.requires_restart is False
        assert result.warning is None

    def test_reload_agent_false_skips_reload(self):
        with (
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
        ):
            apply_setting("yolo_mode", "true", reload_agent=False)
        mock_agent.assert_not_called()

    def test_reload_failure_does_not_break_save(self):
        with (
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
        ):
            mock_agent.return_value.reload_code_generation_agent.side_effect = (
                RuntimeError("boom")
            )
            result = apply_setting("yolo_mode", "true")
        assert result.ok is True
        # Reload failure travels on its own field so a restart-required
        # warning (e.g. enable_dbos) can't be silently clobbered by it.
        assert "agent reload failed" in (result.reload_error or "").lower()
        assert result.warning is None

    def test_reload_failure_preserves_restart_warning(self):
        """Regression: restart notices must survive a reload failure on the
        same key. Original /set always emitted both the restart notice and
        the reload-failure warning; the split-field layout preserves that."""
        with (
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
        ):
            mock_agent.return_value.reload_code_generation_agent.side_effect = (
                RuntimeError("boom")
            )
            result = apply_setting("enable_dbos", "true")
        assert result.ok is True
        assert "restart" in (result.warning or "").lower()
        assert "agent reload failed" in (result.reload_error or "").lower()


# ---------------------------------------------------------------------------
# Edit flow (headless widget drives)
# ---------------------------------------------------------------------------


def _keys(*keys):
    from io import StringIO

    script = iter(keys)
    return {
        "key_source": lambda: next(script),
        "output": StringIO(),
        "size": lambda: (100, 24),
    }


def choice_setting() -> Setting:
    return Setting(
        key="message_history_strategy",
        display_name="History Strategy",
        description="How history is compacted.",
        type_hint="choice",
        valid_values=["summarization", "truncation"],
    )


class TestEditFlow:
    def test_choice_cancel_keeps_current(self):
        result = PickerResult()
        _edit_setting(
            result,
            choice_setting(),
            choice_menu_factory=lambda s, c, **kw: build_choice_menu(
                s,
                c,
                **_keys("end", "enter"),  # last item = Cancel
            ),
            text_editor=lambda *a, **kw: (_ for _ in ()).throw(AssertionError()),
        )
        assert result.changed_settings == {}

    def test_choice_real_value_applies(self):
        result = PickerResult()
        with patch(
            "code_puppy.command_line.set_menu.apply_setting",
            return_value=ApplyResult(ok=True, value_after="truncation"),
        ) as mock_apply:
            _edit_setting(
                result,
                choice_setting(),
                choice_menu_factory=lambda s, c, **kw: build_choice_menu(
                    s, c, **_keys("down", "enter")
                ),
            )
        mock_apply.assert_called_once_with(
            "message_history_strategy", "truncation", reload_agent=False
        )
        assert result.changed_settings["message_history_strategy"] == "truncation"

    def test_choice_custom_falls_through_to_text_editor(self):
        result = PickerResult()
        with patch(
            "code_puppy.command_line.set_menu.apply_setting",
            return_value=ApplyResult(ok=True, value_after="wild"),
        ):
            _edit_setting(
                result,
                choice_setting(),
                choice_menu_factory=lambda s, c, **kw: build_choice_menu(
                    # Options: 2 values, custom, cancel -- End then Up = custom.
                    s,
                    c,
                    **_keys("end", "up", "enter"),
                ),
                text_editor=lambda s, c, **kw: (True, "wild"),
            )
        assert result.changed_settings["message_history_strategy"] == "wild"

    def test_text_empty_value_resets(self):
        result = PickerResult()
        setting = Setting(
            key="some_key",
            display_name="Some Key",
            description="",
            type_hint="string",
        )
        with patch("code_puppy.command_line.set_menu.reset_value") as mock_reset:
            _edit_setting(
                result,
                setting,
                text_editor=lambda s, c, **kw: (True, ""),
            )
        mock_reset.assert_called_once_with("some_key")
        assert result.changed_settings["some_key"] is None


class TestRunTextEditor:
    def test_typed_value_committed(self):
        setting = Setting(key="k", display_name="K", description="", type_hint="int")
        edited, value = run_text_editor(setting, None, **_keys("4", "2", "enter"))
        assert (edited, value) == (True, "42")

    def test_invalid_typed_value_blocked_until_fixed(self):
        setting = Setting(key="k", display_name="K", description="", type_hint="int")
        edited, value = run_text_editor(
            setting, None, **_keys("x", "enter", "ctrl-u", "7", "enter")
        )
        assert (edited, value) == (True, "7")

    def test_escape_cancels(self):
        setting = Setting(key="k", display_name="K", description="", type_hint="string")
        edited, value = run_text_editor(setting, None, **_keys("escape"))
        assert edited is False

    def test_sensitive_setting_masks_output(self):
        from io import StringIO

        setting = Setting(
            key="token",
            display_name="Token",
            description="",
            type_hint="string",
            sensitive=True,
        )
        out = StringIO()
        script = iter(["s", "3", "k", "r", "i", "t", "enter"])
        edited, value = run_text_editor(
            setting,
            None,
            key_source=lambda: next(script),
            output=out,
            size=lambda: (100, 24),
        )
        assert value == "s3krit"
        assert "s3krit" not in out.getvalue()


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


class TestCoerceTypedInput:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("true", "true"),
            ("FALSE", "false"),
            ("YES", "yes"),
            ("", ""),
            ("nope", None),
        ],
    )
    def test_bool(self, value, expected):
        assert _coerce_typed_input("bool", value) == expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("42", "42"),
            ("-7", "-7"),
            ("", ""),
            ("not-a-number", None),
        ],
    )
    def test_int(self, value, expected):
        assert _coerce_typed_input("int", value) == expected

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("0.5", "0.5"),
            ("3", "3"),
            ("", ""),
            ("nan-like", None),
        ],
    )
    def test_float(self, value, expected):
        assert _coerce_typed_input("float", value) == expected

    def test_string_passthrough(self):
        assert _coerce_typed_input("string", "anything goes") == "anything goes"


# ---------------------------------------------------------------------------
# Entry building + filtering
# ---------------------------------------------------------------------------


class TestEntryBuilding:
    def test_curated_keys_land_in_their_categories(self):
        with patch(
            "code_puppy.command_line.set_menu.get_config_keys",
            return_value=[],
        ):
            entries = _build_entries()
        by_key = {e.setting.key: e for e in entries}
        assert by_key["yolo_mode"].category.name == "Behavior"
        assert by_key["puppy_name"].category.name == "Identity"

    def test_dynamic_keys_land_in_dynamic_category(self):
        with patch(
            "code_puppy.command_line.set_menu.get_config_keys",
            return_value=["custom_random_key"],
        ):
            entries = _build_entries()
        match = [e for e in entries if e.setting.key == "custom_random_key"]
        assert match
        assert match[0].category.name == "Dynamic"

    def test_model_settings_only_keys_are_absent(self):
        with patch(
            "code_puppy.command_line.set_menu.get_config_keys",
            return_value=["openai_reasoning_effort", "openai_verbosity"],
        ):
            entries = _build_entries()
        keys = {entry.setting.key for entry in entries}
        assert "openai_reasoning_effort" not in keys
        assert "openai_verbosity" not in keys

    def test_dynamic_does_not_double_curated_keys(self):
        with patch(
            "code_puppy.command_line.set_menu.get_config_keys",
            return_value=["yolo_mode"],
        ):
            entries = _build_entries()
        yolo_entries = [e for e in entries if e.setting.key == "yolo_mode"]
        assert len(yolo_entries) == 1
        assert yolo_entries[0].category.name == "Behavior"

    def test_settings_menu_search_filters_by_key(self):
        from io import StringIO

        with patch(
            "code_puppy.command_line.set_menu.get_config_keys",
            return_value=[],
        ):
            entries = _build_entries()
        keys = iter(list("yolo") + ["enter"])
        menu = build_settings_menu(
            entries,
            key_source=lambda: next(keys),
            output=StringIO(),
            size=lambda: (110, 30),
        )
        result = menu.run()
        assert result.item.value.setting.key == "yolo_mode"

    def test_detect_dynamic_type_bool_by_suffix(self):
        with patch("code_puppy.command_line.set_menu.get_value", return_value=None):
            assert _detect_dynamic_type("some_enabled") == "bool"
            assert _detect_dynamic_type("foo_mode") == "bool"

    def test_detect_dynamic_type_by_value(self):
        with patch("code_puppy.command_line.set_menu.get_value", return_value="42"):
            assert _detect_dynamic_type("random_key") == "int"
        with patch("code_puppy.command_line.set_menu.get_value", return_value="0.5"):
            assert _detect_dynamic_type("random_key") == "float"
        with patch("code_puppy.command_line.set_menu.get_value", return_value="true"):
            assert _detect_dynamic_type("random_key") == "bool"
        with patch("code_puppy.command_line.set_menu.get_value", return_value="hi"):
            assert _detect_dynamic_type("random_key") == "string"


# ---------------------------------------------------------------------------
# Reset / apply -- changed_settings bookkeeping and sensitive masking
# ---------------------------------------------------------------------------


class TestRecordResetAndApply:
    def test_record_reset_records_in_changed_settings(self):
        """Reset must enter ``changed_settings`` so the dispatcher's
        coalesced agent reload actually fires."""
        result = PickerResult()
        with patch("code_puppy.command_line.set_menu.reset_value") as mock_reset:
            _record_reset(result, "yolo_mode")
        mock_reset.assert_called_once_with("yolo_mode")
        assert "yolo_mode" in result.changed_settings
        assert result.changed_settings["yolo_mode"] is None
        assert (
            "success",
            "Reset 'yolo_mode' to default",
        ) in result.pending_messages

    def test_record_reset_invalidates_post_write_caches(self):
        """Regression: resetting the model key must clear ``_SESSION_MODEL``,
        otherwise the menu shows the stale pre-reset value until process exit.
        ``_record_reset`` must call ``invalidate_post_write_caches`` for every
        key (the helper itself decides which keys actually need clearing)."""
        result = PickerResult()
        with (
            patch("code_puppy.command_line.set_menu.reset_value"),
            patch(
                "code_puppy.command_line.config_apply.invalidate_post_write_caches"
            ) as mock_invalidate,
        ):
            _record_reset(result, "model")
        mock_invalidate.assert_called_once_with("model")

    def test_apply_and_record_masks_sensitive_value_in_message(self):
        result = PickerResult()
        token_setting = Setting(
            key="puppy_token",
            display_name="Puppy Token",
            description="",
            type_hint="string",
            sensitive=True,
        )
        with patch(
            "code_puppy.command_line.set_menu.apply_setting",
            return_value=ApplyResult(ok=True, value_after="abcd1234efgh"),
        ):
            _apply_and_record(result, token_setting, "abcd1234efgh")
        # The recorded *value* stays raw (for downstream reload bookkeeping)
        # but the user-facing message is masked.
        assert result.changed_settings["puppy_token"] == "abcd1234efgh"
        success_msgs = [
            text for level, text in result.pending_messages if level == "success"
        ]
        assert any("abcd...efgh" in m for m in success_msgs)
        assert not any("abcd1234efgh" in m for m in success_msgs)

    def test_apply_and_record_non_sensitive_leaves_value_visible(self):
        result = PickerResult()
        yolo = find_setting("yolo_mode")
        with patch(
            "code_puppy.command_line.set_menu.apply_setting",
            return_value=ApplyResult(ok=True, value_after="true"),
        ):
            _apply_and_record(result, yolo, "true")
        success_msgs = [
            text for level, text in result.pending_messages if level == "success"
        ]
        assert any('"true"' in m for m in success_msgs)


# ---------------------------------------------------------------------------
# Slash-command dispatcher integration
# ---------------------------------------------------------------------------


class TestHandleSetCommandDispatcher:
    def test_no_args_launches_picker_and_drains_messages(self):
        from code_puppy.command_line.config_commands import handle_set_command

        picker_result = PickerResult(
            changed_settings={"yolo_mode": "true"},
            pending_messages=[
                ("success", 'Set yolo_mode = "true"'),
                ("warning", "DBOS changes need restart."),
                ("info", "Exited config settings menu"),
            ],
        )
        with (
            patch(
                "code_puppy.command_line.set_menu.interactive_set_picker",
                new=AsyncMock(return_value=picker_result),
            ),
            patch("code_puppy.messaging.emit_success") as mock_success,
            patch("code_puppy.messaging.emit_warning") as mock_warning,
            patch("code_puppy.messaging.emit_info") as mock_info,
            patch("code_puppy.agents.get_current_agent") as mock_agent,
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            assert handle_set_command("/set") is True

        mock_success.assert_any_call('Set yolo_mode = "true"')
        mock_warning.assert_any_call("DBOS changes need restart.")
        mock_info.assert_any_call("Exited config settings menu")
        # Coalesced reload at end because changed_settings was non-empty.
        mock_agent.return_value.reload_code_generation_agent.assert_called_once()

    def test_no_args_picker_no_changes_no_reload(self):
        from code_puppy.command_line.config_commands import handle_set_command

        picker_result = PickerResult(
            changed_settings={},
            pending_messages=[("info", "Exited config settings menu")],
        )
        with (
            patch(
                "code_puppy.command_line.set_menu.interactive_set_picker",
                new=AsyncMock(return_value=picker_result),
            ),
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
        ):
            handle_set_command("/set")
        mock_agent.assert_not_called()

    def test_slash_set_puppy_token_masks_value_in_success(self):
        from code_puppy.command_line.config_commands import handle_set_command

        with (
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
            patch("code_puppy.messaging.emit_success") as mock_success,
            patch("code_puppy.messaging.emit_info"),
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            handle_set_command("/set puppy_token abcd1234efgh")

        recorded = [call.args[0] for call in mock_success.call_args_list]
        assert any("abcd...efgh" in m for m in recorded)
        assert not any("abcd1234efgh" in m for m in recorded)

    def test_slash_set_yolo_does_not_mask(self):
        from code_puppy.command_line.config_commands import handle_set_command

        with (
            patch("code_puppy.config.set_config_value"),
            patch("code_puppy.agents.get_current_agent") as mock_agent,
            patch("code_puppy.messaging.emit_success") as mock_success,
            patch("code_puppy.messaging.emit_info"),
        ):
            mock_agent.return_value.reload_code_generation_agent.return_value = None
            handle_set_command("/set yolo_mode true")

        recorded = [call.args[0] for call in mock_success.call_args_list]
        assert any('"true"' in m for m in recorded)
