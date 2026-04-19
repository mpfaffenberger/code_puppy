"""Tests for item_visibility module.

Tests the generic VisibilityStore class and model-specific convenience functions.
"""

import json
import os
from unittest.mock import patch

import pytest

from code_puppy.config import DATA_DIR
from code_puppy.item_visibility import (
    VisibilityStore,
    clear_visibility_config,
    is_model_hidden,
    load_hidden_models,
    prune_stale_entries,
    save_hidden_models,
    toggle_model_hidden,
)

MODEL_VISIBILITY_CONFIG = os.path.join(DATA_DIR, "model_visibility.json")


class TestVisibilityStore:
    """Tests for the generic VisibilityStore class."""

    @pytest.fixture(autouse=True)
    def cleanup(self, tmp_path):
        """Clean up test files after each test."""
        yield
        # Clean up any test visibility files
        for f in tmp_path.glob("test_visibility*.json"):
            f.unlink()

    @pytest.fixture
    def store(self, tmp_path):
        """Create a VisibilityStore with a temporary file path."""
        return VisibilityStore("test_visibility")

    def test_file_path_follows_naming_convention(self, store, tmp_path):
        """Store name 'test_visibility' creates file 'test_visibility_visibility.json'."""
        assert store.name == "test_visibility"
        # File path uses DATA_DIR, not tmp_path
        assert "test_visibility_visibility.json" in store.file_path

    def test_load_hidden_returns_empty_when_missing(self, store):
        """No file → empty set."""
        assert store.load_hidden() == set()

    def test_load_hidden_returns_empty_when_corrupt(self, store):
        """Bad JSON → empty set + warning log."""
        with open(store.file_path, "w") as f:
            f.write("not valid json {")

        with patch("code_puppy.item_visibility.logger") as mock_logger:
            result = store.load_hidden()
            assert result == set()
            mock_logger.warning.assert_called()

    def test_load_hidden_returns_empty_when_key_missing(self, store):
        """Valid JSON but wrong key → empty set."""
        with open(store.file_path, "w") as f:
            json.dump({"wrong_key": ["item1"]}, f)

        result = store.load_hidden()
        assert result == set()

    def test_load_hidden_returns_empty_when_wrong_type(self, store):
        """Valid JSON but wrong value type → empty set."""
        with open(store.file_path, "w") as f:
            json.dump({"hidden_test_visibilitys": "not a list"}, f)

        result = store.load_hidden()
        assert result == set()

    def test_save_and_load_hidden_round_trip(self, store):
        """Write set, read back, matches."""
        test_set = {"model-a", "model-b", "model-c"}
        store.save_hidden(test_set)

        result = store.load_hidden()
        assert result == test_set

    def test_save_creates_data_dir(self, tmp_path):
        """DATA_DIR doesn't exist → creates it."""
        # Use a subdir that doesn't exist
        test_store = VisibilityStore("test_visibility")
        # Override file path to a non-existent directory
        test_store._file_path = os.path.join(
            tmp_path, "nonexistent", "deep", "test_visibility_visibility.json"
        )

        test_set = {"item1", "item2"}
        test_store.save_hidden(test_set)

        assert os.path.exists(test_store.file_path)
        assert test_store.load_hidden() == test_set

    def test_toggle_first_call_hides(self, store):
        """Toggle visible → hidden, returns True."""
        result = store.toggle("model-x")
        assert result is True
        assert "model-x" in store.load_hidden()

    def test_toggle_second_call_restores(self, store):
        """Toggle hidden → visible, returns False."""
        store.save_hidden({"model-y"})
        result = store.toggle("model-y")
        assert result is False
        assert "model-y" not in store.load_hidden()

    def test_is_hidden_true_and_false(self, store):
        """Both hidden states verified."""
        store.save_hidden({"hidden-model"})
        assert store.is_hidden("hidden-model") is True
        assert store.is_hidden("visible-model") is False

    def test_prune_stale_removes_gone_items(self, store):
        """Item removed from config → pruned."""
        store.save_hidden({"stale-model", "valid-model"})

        # Only 'valid-model' exists in current config
        pruned = store.prune_stale(["valid-model", "another-valid"])

        assert pruned == {"stale-model"}
        assert store.load_hidden() == {"valid-model"}

    def test_prune_stale_noop_when_all_valid(self, store):
        """No stale → returns empty set, no write."""
        store.save_hidden({"model-a", "model-b"})

        # Track if save was called
        with patch.object(store, "save_hidden") as mock_save:
            pruned = store.prune_stale(["model-a", "model-b", "model-c"])
            assert pruned == set()
            mock_save.assert_not_called()

    def test_clear_removes_file(self, store):
        """File deleted, idempotent."""
        store.save_hidden({"model-x"})
        assert os.path.exists(store.file_path)

        store.clear()

        assert not os.path.exists(store.file_path)
        # Calling again should not raise
        store.clear()

    def test_save_empty_set_writes_valid_json(self, store):
        """Saving empty set produces valid JSON."""
        store.save_hidden(set())

        with open(store.file_path) as f:
            data = json.load(f)

        assert data == {"hidden_test_visibilitys": []}


class TestModelVisibilityAliases:
    """Tests for model-specific convenience functions."""

    @pytest.fixture(autouse=True)
    def clean_slate_restore(self):
        """Clear before tests (clean slate), restore user's config after."""
        original_hidden = load_hidden_models()
        clear_visibility_config()  # Start with clean slate

        yield

        # Restore user's config after tests
        if original_hidden:
            save_hidden_models(original_hidden)
        else:
            clear_visibility_config()

    def test_load_hidden_models_returns_empty_when_missing(self):
        """No file → empty set."""
        assert load_hidden_models() == set()

    def test_toggle_model_hidden_hides(self):
        """toggle_model_hidden adds to hidden set."""
        result = toggle_model_hidden("test-model-xyz")
        assert result is True
        assert "test-model-xyz" in load_hidden_models()

    def test_toggle_model_hidden_restores(self):
        """Second toggle removes from hidden set."""
        toggle_model_hidden("test-model-abc")
        result = toggle_model_hidden("test-model-abc")
        assert result is False
        assert "test-model-abc" not in load_hidden_models()

    def test_is_model_hidden(self):
        """is_model_hidden checks hidden state."""
        assert is_model_hidden("nonexistent") is False
        toggle_model_hidden("hidden-test")
        assert is_model_hidden("hidden-test") is True

    def test_prune_stale_entries(self):
        """prune_stale_entries removes stale entries."""
        toggle_model_hidden("stale-entry")
        toggle_model_hidden("keep-entry")

        pruned = prune_stale_entries(["keep-entry", "another-valid"])

        assert pruned == {"stale-entry"}
        assert load_hidden_models() == {"keep-entry"}

    def test_save_hidden_models(self):
        """save_hidden_models persists a set."""
        test_set = {"model-a", "model-b"}
        save_hidden_models(test_set)

        assert load_hidden_models() == test_set

    def test_clear_visibility_config(self):
        """clear_visibility_config removes file."""
        toggle_model_hidden("test-model")
        assert os.path.exists(os.path.join(DATA_DIR, "model_visibility.json"))

        clear_visibility_config()

        assert not os.path.exists(os.path.join(DATA_DIR, "model_visibility.json"))


class TestPersistence:
    """Tests for cross-process persistence."""

    @pytest.fixture(autouse=True)
    def clean_slate_restore(self):
        """Clear before tests (clean slate), restore user's config after."""
        original_hidden = load_hidden_models()
        clear_visibility_config()  # Start with clean slate

        yield

        # Restore user's config after tests
        if original_hidden:
            save_hidden_models(original_hidden)
        else:
            clear_visibility_config()

    def test_visibility_persists_across_process_restart(self):
        """Write hidden set → new process reads same state."""
        # Simulate first "process" writing hidden models
        hidden = {"persist-test-1", "persist-test-2"}
        save_hidden_models(hidden)

        # Simulate second "process" reading
        # (We can't actually spawn a new process, but we can verify the file)
        config_path = os.path.join(DATA_DIR, "model_visibility.json")
        assert os.path.exists(config_path)

        with open(config_path) as f:
            data = json.load(f)

        assert set(data["hidden_models"]) == hidden
