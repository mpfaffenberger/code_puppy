"""Tests for ``code_puppy.command_line.config_apply`` cache invalidation.

These exist because of a bug where changing the model via ``/set`` (or
via the interactive menu) silently left the in-memory ``_SESSION_MODEL``
cache stale. The user would see the OLD model in the menu for the rest
of the process lifetime even though the new value was correctly
persisted to ``puppy.cfg``. Regression test: ensure both the set path
and the reset path go through ``invalidate_post_write_caches`` for the
``model`` key.
"""

from __future__ import annotations

from unittest.mock import patch

from code_puppy.command_line.config_apply import (
    apply_setting,
    invalidate_post_write_caches,
)


class TestInvalidatePostWriteCaches:
    def test_model_key_clears_both_caches(self):
        with (
            patch("code_puppy.config.reset_session_model") as mock_reset,
            patch("code_puppy.config.clear_model_cache") as mock_clear,
        ):
            invalidate_post_write_caches("model")
        mock_reset.assert_called_once()
        mock_clear.assert_called_once()

    def test_non_model_key_is_noop(self):
        with (
            patch("code_puppy.config.reset_session_model") as mock_reset,
            patch("code_puppy.config.clear_model_cache") as mock_clear,
        ):
            invalidate_post_write_caches("yolo_mode")
            invalidate_post_write_caches("puppy_name")
            invalidate_post_write_caches("temperature")
        mock_reset.assert_not_called()
        mock_clear.assert_not_called()


class TestApplySettingInvalidatesModelCache:
    def test_setting_model_clears_session_cache(self):
        """The original bug: changing model didn't invalidate ``_SESSION_MODEL``."""
        with (
            patch("code_puppy.config.set_config_value"),
            patch(
                "code_puppy.command_line.config_apply.invalidate_post_write_caches"
            ) as mock_invalidate,
        ):
            result = apply_setting("model", "claude-opus-4-7", reload_agent=False)
        assert result.ok
        mock_invalidate.assert_called_once_with("model")

    def test_setting_non_model_still_calls_invalidator_as_noop(self):
        """The invalidator is called for every key; it's the helper's job
        to decide whether to actually clear anything. Ensures the wire-up
        stays uniform and the model-specific knowledge stays in one place."""
        with (
            patch("code_puppy.config.set_config_value"),
            patch(
                "code_puppy.command_line.config_apply.invalidate_post_write_caches"
            ) as mock_invalidate,
        ):
            apply_setting("yolo_mode", "true", reload_agent=False)
        mock_invalidate.assert_called_once_with("yolo_mode")
