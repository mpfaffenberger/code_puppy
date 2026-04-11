"""
Tests for task_models profile-sync behaviour.

Bug: when a named profile was active, calling set_model_for() wrote the new
value to puppy.cfg but the get_model() resolution chain checked the profile
JSON first (layer 1) and always returned the stale profile value.

Fix: TaskModelResolver.set_model() now calls _patch_active_profile() which
also updates the profile JSON on disk so the two sources stay in sync.
"""

import json
from unittest.mock import patch

import pytest


@pytest.fixture()
def tmp_profiles_dir(tmp_path):
    """Return a temporary directory usable as the profiles store."""
    return tmp_path / "profiles"


@pytest.fixture()
def dummy_profile(tmp_profiles_dir):
    """
    Write a minimal profile JSON and return its path.

    The profile has compaction=initial-compaction-model.
    """
    tmp_profiles_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "name": "test-profile",
        "description": "",
        "models": {
            "main": "initial-main-model",
            "compaction": "initial-compaction-model",
            "subagent": "initial-subagent-model",
        },
    }
    profile_path = tmp_profiles_dir / "test-profile.json"
    profile_path.write_text(json.dumps(data, indent=2))
    return profile_path


def _make_patches(tmp_profiles_dir, profile_name="test-profile"):
    """Return a list of patch objects that isolate task_models from real config."""
    return [
        # Make get_value("active_profile") return our profile name
        patch(
            "code_puppy.task_models.get_value",
            side_effect=lambda key: profile_name if key == "active_profile" else None,
        ),
        # Redirect profile directory to tmp
        patch(
            "code_puppy.task_models._get_profiles_dir",
            return_value=tmp_profiles_dir,
        ),
        # Stub out config writes (we only test the JSON patch)
        patch("code_puppy.task_models.set_value"),
        patch("code_puppy.task_models.reset_value"),
        patch("code_puppy.task_models.set_model_name"),
        patch(
            "code_puppy.task_models.get_global_model_name", return_value="global-model"
        ),
        patch("code_puppy.task_models.get_agent_pinned_model", return_value=None),
    ]


class TestSetModelPatchesActiveProfile:
    """set_model_for() must update the active profile JSON."""

    def test_compaction_model_written_to_profile_json(
        self, tmp_profiles_dir, dummy_profile
    ):
        from code_puppy.task_models import Task, set_model_for

        patches = _make_patches(tmp_profiles_dir)
        [p.start() for p in patches]
        try:
            set_model_for(Task.COMPACTION, "new-compaction-model")
        finally:
            for p in patches:
                p.stop()

        updated = json.loads(dummy_profile.read_text())
        assert updated["models"]["compaction"] == "new-compaction-model", (
            "Profile JSON should be updated with the new compaction model"
        )

    def test_subagent_model_written_to_profile_json(
        self, tmp_profiles_dir, dummy_profile
    ):
        from code_puppy.task_models import Task, set_model_for

        patches = _make_patches(tmp_profiles_dir)
        [p.start() for p in patches]
        try:
            set_model_for(Task.SUBAGENT, "new-subagent-model")
        finally:
            for p in patches:
                p.stop()

        updated = json.loads(dummy_profile.read_text())
        assert updated["models"]["subagent"] == "new-subagent-model"

    def test_get_model_returns_updated_value_after_set(
        self, tmp_profiles_dir, dummy_profile
    ):
        """
        After set_model_for() the subsequent get_model_for() must return the
        new value, not the stale profile value.
        """
        from code_puppy.task_models import Task, get_model_for, set_model_for

        patches = _make_patches(tmp_profiles_dir)
        [p.start() for p in patches]
        try:
            set_model_for(Task.COMPACTION, "fresh-model")
            resolved = get_model_for(Task.COMPACTION)
        finally:
            for p in patches:
                p.stop()

        assert resolved == "fresh-model", (
            "get_model_for() should return the model that was just set, "
            f"but got {resolved!r}"
        )


class TestClearModelRemovesFromActiveProfile:
    """clear_model_for() must remove the key from the active profile JSON."""

    def test_clear_removes_key_from_profile_json(self, tmp_profiles_dir, dummy_profile):
        from code_puppy.task_models import Task, clear_model_for

        patches = _make_patches(tmp_profiles_dir)
        [p.start() for p in patches]
        try:
            clear_model_for(Task.COMPACTION)
        finally:
            for p in patches:
                p.stop()

        updated = json.loads(dummy_profile.read_text())
        assert "compaction" not in updated["models"], (
            "After clear_model_for, the key should be removed from profile JSON"
        )

    def test_clear_does_not_touch_other_keys(self, tmp_profiles_dir, dummy_profile):
        from code_puppy.task_models import Task, clear_model_for

        patches = _make_patches(tmp_profiles_dir)
        [p.start() for p in patches]
        try:
            clear_model_for(Task.COMPACTION)
        finally:
            for p in patches:
                p.stop()

        updated = json.loads(dummy_profile.read_text())
        assert updated["models"]["subagent"] == "initial-subagent-model"
        assert updated["models"]["main"] == "initial-main-model"


class TestNoPatchWhenNoActiveProfile:
    """When no profile is active, set_model_for() must not touch any JSON."""

    def test_no_profile_no_json_written(self, tmp_profiles_dir):
        from code_puppy.task_models import Task, set_model_for

        # No profile is active (all get_value calls return None)
        no_profile_patches = [
            patch("code_puppy.task_models.get_value", return_value=None),
            patch(
                "code_puppy.task_models._get_profiles_dir",
                return_value=tmp_profiles_dir,
            ),
            patch("code_puppy.task_models.set_value"),
            patch("code_puppy.task_models.reset_value"),
            patch("code_puppy.task_models.set_model_name"),
            patch(
                "code_puppy.task_models.get_global_model_name", return_value="global"
            ),
            patch("code_puppy.task_models.get_agent_pinned_model", return_value=None),
        ]
        [p.start() for p in no_profile_patches]
        try:
            set_model_for(Task.COMPACTION, "whatever")
        finally:
            for p in no_profile_patches:
                p.stop()

        # No JSON files should have been created
        assert not any(tmp_profiles_dir.glob("*.json")), (
            "No profile JSON should be written when no profile is active"
        )
