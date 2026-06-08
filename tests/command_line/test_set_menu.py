"""Tests for ``code_puppy.command_line.set_menu`` and the slash dispatcher.

Value resolution + masking tests live in ``test_set_menu_values.py``.

This file covers:
* ``apply_setting`` validation + restart warnings + agent reload toggle
* ``_prompt_for_value`` control flow: Cancel returns None without
  falling into the free-text prompt, real choices return cleaned strings,
  ``is_password`` is wired through for sensitive settings
* type coercion
* entry building / search
* reset bookkeeping (must record into ``changed_settings``)
* dispatcher correctly drains ``PickerResult.pending_messages`` and
  triggers exactly one coalesced agent reload
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.command_line.config_apply import ApplyResult, apply_setting
from code_puppy.command_line.set_menu import (
    PickerResult,
    _apply_and_record,
    _coerce_typed_input,
    _detect_dynamic_type,
    _entry_matches,
    _Entry,
    _prompt_for_value,
    _build_entries,
    _record_reset,
)
from code_puppy.command_line.set_menu_settings import (
    Setting,
    SettingsCategory,
)
from tests.command_line.test_set_menu_values import find_setting


# ---------------------------------------------------------------------------
# apply_setting validation
# ---------------------------------------------------------------------------


class TestApplySetting:
    def test_missing_key_returns_error(self):
        result = apply_setting("", "anything")
        assert result.ok is False
        assert result.error and "key" in result.error.lower()

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
# _prompt_for_value control flow
# ---------------------------------------------------------------------------


class TestPromptForValue:
    @pytest.mark.asyncio
    async def test_choice_cancel_returns_none_no_prompt(self):
        setting = find_setting("compaction_strategy")
        prompt_session = MagicMock()
        prompt_session.prompt_async = AsyncMock(return_value="never-called")
        with (
            patch(
                "code_puppy.tools.common.arrow_select_async",
                new=AsyncMock(return_value="Cancel (keep current)"),
            ),
            patch(
                "prompt_toolkit.PromptSession",
                return_value=prompt_session,
            ) as ps_class,
        ):
            result = await _prompt_for_value(setting, current_val="summarization")
        assert result is None
        prompt_session.prompt_async.assert_not_awaited()
        ps_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_choice_real_value_returns_cleaned_string(self):
        setting = find_setting("compaction_strategy")
        with patch(
            "code_puppy.tools.common.arrow_select_async",
            new=AsyncMock(return_value="  summarization (current)"),
        ):
            result = await _prompt_for_value(setting, current_val="summarization")
        assert result == "summarization"

    @pytest.mark.asyncio
    async def test_choice_type_custom_falls_through_to_prompt(self):
        setting = find_setting("compaction_strategy")
        prompt_session = MagicMock()
        prompt_session.prompt_async = AsyncMock(return_value="my-custom-value")
        with (
            patch(
                "code_puppy.tools.common.arrow_select_async",
                new=AsyncMock(return_value="Type custom value..."),
            ),
            patch(
                "prompt_toolkit.PromptSession",
                return_value=prompt_session,
            ),
        ):
            result = await _prompt_for_value(setting, current_val="summarization")
        # 'choice' falls through to string passthrough -> returned unchanged.
        assert result == "my-custom-value"

    @pytest.mark.asyncio
    async def test_prompt_passes_is_password_for_sensitive(self):
        sensitive_setting = Setting(
            key="puppy_token",
            display_name="Puppy Token",
            description="",
            type_hint="string",
            sensitive=True,
        )
        captured = {}

        class _FakeSession:
            def __init__(self, message, **kwargs):
                captured["is_password"] = kwargs.get("is_password")

            async def prompt_async(self):
                return "secret"

        with patch("prompt_toolkit.PromptSession", _FakeSession):
            result = await _prompt_for_value(sensitive_setting, current_val=None)
        assert result == "secret"
        assert captured["is_password"] is True

    @pytest.mark.asyncio
    async def test_prompt_no_password_for_non_sensitive(self):
        normal_setting = Setting(
            key="owner_name",
            display_name="Owner",
            description="",
            type_hint="string",
        )
        captured = {}

        class _FakeSession:
            def __init__(self, message, **kwargs):
                captured["is_password"] = kwargs.get("is_password")

            async def prompt_async(self):
                return "Andrew"

        with patch("prompt_toolkit.PromptSession", _FakeSession):
            result = await _prompt_for_value(normal_setting, current_val=None)
        assert result == "Andrew"
        assert captured["is_password"] is False


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

    def test_dynamic_does_not_double_curated_keys(self):
        with patch(
            "code_puppy.command_line.set_menu.get_config_keys",
            return_value=["yolo_mode"],
        ):
            entries = _build_entries()
        yolo_entries = [e for e in entries if e.setting.key == "yolo_mode"]
        assert len(yolo_entries) == 1
        assert yolo_entries[0].category.name == "Behavior"

    def test_entry_matches_searches_all_fields(self):
        category = SettingsCategory(name="Behavior")
        setting = Setting(
            key="yolo_mode",
            display_name="YOLO",
            description="Skip prompts.",
            type_hint="bool",
        )
        entry = _Entry(category=category, setting=setting)
        assert _entry_matches(entry, "yolo")
        assert _entry_matches(entry, "skip")
        assert _entry_matches(entry, "behavior")
        assert not _entry_matches(entry, "nope")

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


@dataclass
class _StubState:
    """Just enough of ``_PickerState`` to drive the helpers under test."""

    result: PickerResult


class TestRecordResetAndApply:
    def test_record_reset_records_in_changed_settings(self):
        """Reset must enter ``changed_settings`` so the dispatcher's
        coalesced agent reload actually fires."""
        state = _StubState(result=PickerResult())
        with patch("code_puppy.command_line.set_menu.reset_value") as mock_reset:
            _record_reset(state, "yolo_mode")
        mock_reset.assert_called_once_with("yolo_mode")
        assert "yolo_mode" in state.result.changed_settings
        assert state.result.changed_settings["yolo_mode"] is None
        assert (
            "success",
            "Reset 'yolo_mode' to default",
        ) in state.result.pending_messages

    def test_record_reset_invalidates_post_write_caches(self):
        """Regression: resetting the model key must clear ``_SESSION_MODEL``,
        otherwise the menu shows the stale pre-reset value until process exit.
        ``_record_reset`` must call ``invalidate_post_write_caches`` for every
        key (the helper itself decides which keys actually need clearing)."""
        state = _StubState(result=PickerResult())
        with (
            patch("code_puppy.command_line.set_menu.reset_value"),
            patch(
                "code_puppy.command_line.config_apply.invalidate_post_write_caches"
            ) as mock_invalidate,
        ):
            _record_reset(state, "model")
        mock_invalidate.assert_called_once_with("model")

    def test_apply_and_record_masks_sensitive_value_in_message(self):
        state = _StubState(result=PickerResult())
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
            _apply_and_record(state, token_setting, "abcd1234efgh")
        # The recorded *value* stays raw (for downstream reload bookkeeping)
        # but the user-facing message is masked.
        assert state.result.changed_settings["puppy_token"] == "abcd1234efgh"
        success_msgs = [
            text for level, text in state.result.pending_messages if level == "success"
        ]
        assert any("abcd...efgh" in m for m in success_msgs)
        assert not any("abcd1234efgh" in m for m in success_msgs)

    def test_apply_and_record_non_sensitive_leaves_value_visible(self):
        state = _StubState(result=PickerResult())
        yolo = find_setting("yolo_mode")
        with patch(
            "code_puppy.command_line.set_menu.apply_setting",
            return_value=ApplyResult(ok=True, value_after="true"),
        ):
            _apply_and_record(state, yolo, "true")
        success_msgs = [
            text for level, text in state.result.pending_messages if level == "success"
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
