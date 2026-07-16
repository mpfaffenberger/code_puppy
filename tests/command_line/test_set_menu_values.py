"""Tests for ``code_puppy.command_line.set_menu_values``.

Focused on value resolution + masking. Picker / dispatcher behavior
lives in ``test_set_menu.py``.
"""

from __future__ import annotations

from unittest.mock import patch

from code_puppy.command_line.set_menu_settings import (
    SETTINGS_CATEGORIES,
    Setting,
    iter_curated_settings,
)
from code_puppy.command_line.set_menu_values import (
    display_value,
    get_effective_setting_value,
    is_default_value,
    is_sensitive_key,
    mask_value,
)


# ---------------------------------------------------------------------------
# Effective-value regression sweep -- the core bug fix for PUP-298
# ---------------------------------------------------------------------------


class TestEffectiveSettingValue:
    def test_every_curated_setting_with_getter_resolves_to_non_none(self):
        """If a curated setting wires up an ``effective_getter`` it must
        return something, even when puppy.cfg is empty.

        Exceptions are keys whose semantics are explicitly "optional with
        no documented default" -- e.g. ``temperature`` means "use the
        model's own default" when unset, and ``puppy_token`` is simply
        not configured for most users. Add to ``OPTIONAL_KEYS`` only
        when you've confirmed the unset value is meaningful.
        """
        OPTIONAL_KEYS = {"temperature", "puppy_token"}
        failures = []
        for _, setting in iter_curated_settings():
            if setting.effective_getter is None:
                continue
            if setting.key in OPTIONAL_KEYS:
                continue
            value = get_effective_setting_value(setting)
            if value is None:
                failures.append(setting.key)
        assert not failures, (
            f"Curated settings returned None for effective value: {failures}"
        )

    def test_yolo_mode_defaults_to_true(self):
        s = Setting(
            key="yolo_mode",
            display_name="YOLO",
            description="",
            type_hint="bool",
            effective_getter=lambda: True,
        )
        assert get_effective_setting_value(s) == "true"

    def test_compaction_strategy_default_truncation(self):
        s = Setting(
            key="compaction_strategy",
            display_name="",
            description="",
            type_hint="choice",
            effective_getter=lambda: "truncation",
        )
        assert get_effective_setting_value(s) == "truncation"

    def test_protected_token_count_returns_int_as_string(self):
        s = Setting(
            key="protected_token_count",
            display_name="",
            description="",
            type_hint="int",
            effective_getter=lambda: 50000,
        )
        assert get_effective_setting_value(s) == "50000"

    def test_compaction_threshold_formats_float(self):
        s = Setting(
            key="compaction_threshold",
            display_name="",
            description="",
            type_hint="float",
            effective_getter=lambda: 0.85,
        )
        assert get_effective_setting_value(s) == "0.85"

    def test_getter_exception_yields_none_not_crash(self):
        """A misbehaving getter must not crash the menu."""
        bad_setting = Setting(
            key="bad",
            display_name="bad",
            description="bad",
            type_hint="string",
            effective_getter=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        assert get_effective_setting_value(bad_setting) is None

    def test_no_getter_falls_back_to_get_value(self):
        s = Setting(
            key="some_unknown_key",
            display_name="x",
            description="x",
            type_hint="string",
        )
        with patch(
            "code_puppy.command_line.set_menu_values.get_value",
            return_value="hello",
        ):
            assert get_effective_setting_value(s) == "hello"

    def test_no_getter_and_no_config_value_returns_none(self):
        s = Setting(
            key="some_unknown_key",
            display_name="x",
            description="x",
            type_hint="string",
        )
        with patch(
            "code_puppy.command_line.set_menu_values.get_value",
            return_value=None,
        ):
            assert get_effective_setting_value(s) is None

    def test_allow_recursion_is_curated(self):
        """Regression: ``allow_recursion`` was briefly dropped from curation
        despite still being consumed by ``file_operations``."""
        keys = {s.key for _, s in iter_curated_settings()}
        assert "allow_recursion" in keys

    def test_is_sensitive_key_for_puppy_token(self):
        assert is_sensitive_key("puppy_token") is True
        assert is_sensitive_key("yolo_mode") is False
        assert is_sensitive_key("") is False
        assert is_sensitive_key("nonexistent") is False


# ---------------------------------------------------------------------------
# is_default_value -- the (Default) prefix feature
# ---------------------------------------------------------------------------


class TestIsDefaultValue:
    def _setting_with(self, getter_result):
        return Setting(
            key="some_curated_key",
            display_name="",
            description="",
            type_hint="bool",
            effective_getter=lambda: getter_result,
        )

    def test_true_when_config_unset_and_getter_returns_value(self):
        s = self._setting_with(True)
        with patch(
            "code_puppy.command_line.set_menu_values.get_value",
            return_value=None,
        ):
            assert is_default_value(s) is True

    def test_true_when_config_is_empty_string(self):
        s = self._setting_with("foo")
        with patch(
            "code_puppy.command_line.set_menu_values.get_value",
            return_value="",
        ):
            assert is_default_value(s) is True

    def test_false_when_user_has_explicit_value(self):
        s = self._setting_with(True)
        with patch(
            "code_puppy.command_line.set_menu_values.get_value",
            return_value="false",
        ):
            assert is_default_value(s) is False

    def test_false_when_no_getter_wired(self):
        s = Setting(
            key="dynamic_key",
            display_name="",
            description="",
            type_hint="string",
        )
        assert is_default_value(s) is False

    def test_false_when_getter_returns_none(self):
        # e.g. temperature with no override anywhere -- there is no
        # default value to flag.
        s = self._setting_with(None)
        with patch(
            "code_puppy.command_line.set_menu_values.get_value",
            return_value=None,
        ):
            assert is_default_value(s) is False


# ---------------------------------------------------------------------------
# Sensitive value masking
# ---------------------------------------------------------------------------


class TestMaskValue:
    def test_empty(self):
        assert mask_value("") == ""

    def test_short_value_all_stars(self):
        assert mask_value("short") == "*****"

    def test_exactly_eight_chars_all_stars(self):
        assert mask_value("abcd1234") == "********"

    def test_long_value_keeps_edges(self):
        assert mask_value("abcd1234efgh") == "abcd...efgh"

    def test_very_long_value(self):
        long = "x" * 64
        masked = mask_value(long)
        assert masked.startswith("xxxx")
        assert masked.endswith("xxxx")
        assert "..." in masked

    def test_display_value_masks_when_sensitive(self):
        s = Setting(
            key="puppy_token",
            display_name="Puppy Token",
            description="",
            type_hint="string",
            effective_getter=lambda: "abcd1234efgh",
            sensitive=True,
        )
        assert display_value(s) == "abcd...efgh"

    def test_display_value_does_not_mask_when_not_sensitive(self):
        s = Setting(
            key="owner_name",
            display_name="Owner",
            description="",
            type_hint="string",
            effective_getter=lambda: "Andrew Tilson Owner",
        )
        assert display_value(s) == "Andrew Tilson Owner"


# ---------------------------------------------------------------------------
# Shared helper used across the test suite
# ---------------------------------------------------------------------------


def find_setting(key: str) -> Setting:
    """Locate a curated :class:`Setting` by key. Test helper."""
    for category in SETTINGS_CATEGORIES:
        for setting in category.settings:
            if setting.key == key:
                return setting
    raise AssertionError(f"Setting '{key}' not found in SETTINGS_CATEGORIES")
