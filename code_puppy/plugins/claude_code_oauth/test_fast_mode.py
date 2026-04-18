"""Tests for the fast_mode submodule.

These tests don't touch the network or config file - they exercise pure
helpers for beta-header merging and payload injection.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_puppy.plugins.claude_code_oauth.fast_mode import (
    FAST_MODE_BETA,
    FAST_SETTING_KEY,
    ensure_fast_beta_header,
    is_fast_mode_enabled,
    make_fast_mode_wrapper,
)


class TestEnsureFastBetaHeader:
    def test_adds_marker_when_enabled_and_absent(self):
        headers = {}
        ensure_fast_beta_header(headers, enabled=True)
        assert headers["anthropic-beta"] == FAST_MODE_BETA

    def test_appends_marker_to_existing(self):
        headers = {"anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14"}
        ensure_fast_beta_header(headers, enabled=True)
        parts = headers["anthropic-beta"].split(",")
        assert FAST_MODE_BETA in parts
        assert "oauth-2025-04-20" in parts
        assert "interleaved-thinking-2025-05-14" in parts

    def test_no_duplicate_when_already_present(self):
        headers = {"anthropic-beta": f"oauth-2025-04-20,{FAST_MODE_BETA}"}
        ensure_fast_beta_header(headers, enabled=True)
        assert headers["anthropic-beta"].count(FAST_MODE_BETA) == 1

    def test_removes_marker_when_disabled(self):
        headers = {"anthropic-beta": f"oauth-2025-04-20,{FAST_MODE_BETA}"}
        ensure_fast_beta_header(headers, enabled=False)
        assert FAST_MODE_BETA not in headers["anthropic-beta"]
        assert "oauth-2025-04-20" in headers["anthropic-beta"]

    def test_drops_header_when_only_marker_removed(self):
        headers = {"anthropic-beta": FAST_MODE_BETA}
        ensure_fast_beta_header(headers, enabled=False)
        assert "anthropic-beta" not in headers

    def test_noop_when_disabled_and_absent(self):
        headers = {"anthropic-beta": "oauth-2025-04-20"}
        ensure_fast_beta_header(headers, enabled=False)
        assert headers == {"anthropic-beta": "oauth-2025-04-20"}


class TestIsFastModeEnabled:
    def test_returns_false_when_setting_absent(self):
        with patch(
            "code_puppy.config.get_all_model_settings",
            return_value={},
        ):
            assert is_fast_mode_enabled("claude-code-foo") is False

    def test_returns_true_when_setting_true(self):
        with patch(
            "code_puppy.config.get_all_model_settings",
            return_value={FAST_SETTING_KEY: True},
        ):
            assert is_fast_mode_enabled("claude-code-foo") is True

    def test_returns_false_when_setting_false(self):
        with patch(
            "code_puppy.config.get_all_model_settings",
            return_value={FAST_SETTING_KEY: False},
        ):
            assert is_fast_mode_enabled("claude-code-foo") is False


class TestMakeFastModeWrapper:
    @pytest.mark.asyncio
    async def test_injects_speed_when_enabled(self):
        captured = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            return "ok"

        wrapped = make_fast_mode_wrapper(fake_create, "claude-code-foo")

        with patch(
            "code_puppy.config.get_all_model_settings",
            return_value={FAST_SETTING_KEY: True},
        ):
            await wrapped(model="foo", messages=[])

        assert captured.get("speed") == "fast"

    @pytest.mark.asyncio
    async def test_does_not_inject_when_disabled(self):
        captured = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            return "ok"

        wrapped = make_fast_mode_wrapper(fake_create, "claude-code-foo")

        with patch(
            "code_puppy.config.get_all_model_settings",
            return_value={FAST_SETTING_KEY: False},
        ):
            await wrapped(model="foo", messages=[])

        assert "speed" not in captured

    @pytest.mark.asyncio
    async def test_does_not_clobber_explicit_speed(self):
        captured = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            return "ok"

        wrapped = make_fast_mode_wrapper(fake_create, "claude-code-foo")

        with patch(
            "code_puppy.config.get_all_model_settings",
            return_value={FAST_SETTING_KEY: True},
        ):
            await wrapped(model="foo", messages=[], speed="slow")

        # Caller-provided speed wins
        assert captured.get("speed") == "slow"


class TestIsFastModeEnabledRealConfigRoundTrip:
    """End-to-end regression test: set_model_setting -> is_fast_mode_enabled.

    This would have caught the original bug where get_effective_model_settings
    silently filtered the 'fast' key out because it wasn't in the core
    supported_settings allowlist for claude-* models.
    """

    def test_real_roundtrip_with_claude_code_model(self, tmp_path, monkeypatch):
        # Point config at a throwaway file so we don't clobber user config.
        cfg = tmp_path / "puppy.cfg"
        monkeypatch.setattr("code_puppy.config.CONFIG_FILE", str(cfg))

        from code_puppy.config import set_model_setting

        model = "claude-code-claude-opus-4-7"

        # Initially off.
        assert is_fast_mode_enabled(model) is False

        # Flip it on via the same path /claude-code-fast uses.
        set_model_setting(model, FAST_SETTING_KEY, "true")
        assert is_fast_mode_enabled(model) is True, (
            "Regression: fast setting written to config but read as False. "
            "Likely the reader is filtering through the supported_settings allowlist."
        )

        # Flip it back off.
        set_model_setting(model, FAST_SETTING_KEY, "false")
        assert is_fast_mode_enabled(model) is False
