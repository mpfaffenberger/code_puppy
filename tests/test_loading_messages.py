"""Tests for loading_messages module."""

from unittest.mock import patch

import code_puppy.messaging.loading_messages as _lm

from code_puppy.messaging.loading_messages import (
    get_all_messages,
    get_messages_by_category,
    get_spinner_messages,
    register_messages,
    unregister_messages,
)


class TestGetSpinnerMessages:
    """Tests for get_spinner_messages."""

    def test_returns_list(self):
        result = get_spinner_messages()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_returns_shuffled_copy(self):
        """Returns a shuffled copy without mutating source semantics."""
        with patch(
            "code_puppy.messaging.loading_messages.random.shuffle"
        ) as mock_shuffle:
            a = get_spinner_messages()
        b = get_spinner_messages()
        # shuffle was called on the returned list
        mock_shuffle.assert_called_once()
        # Same contents regardless of order
        assert sorted(a) == sorted(b)

    def test_does_not_include_standalone(self):
        """Spinner messages should not include standalone messages."""
        cats = get_messages_by_category()
        spinner = get_spinner_messages()
        for standalone_msg in cats["standalone"]:
            assert standalone_msg not in spinner


class TestGetAllMessages:
    def test_includes_standalone(self):
        all_msgs = get_all_messages()
        cats = get_messages_by_category()
        for msg in cats["standalone"]:
            assert msg in all_msgs

    def test_includes_spinner_messages(self):
        all_msgs = get_all_messages()
        cats = get_messages_by_category()
        # Verify spinner messages contribute to the combined list
        assert len(all_msgs) > len(cats["standalone"])


class TestGetMessagesByCategory:
    def test_has_expected_categories(self):
        cats = get_messages_by_category()
        for key in ("puppy", "dev", "fun", "action", "standalone"):
            assert key in cats
            assert len(cats[key]) > 0


class TestPluginRegistry:
    """Tests for register_messages / unregister_messages."""

    def teardown_method(self):
        """Clean up any test categories."""
        unregister_messages("test_cat")
        unregister_messages("test_cat2")
        _lm._plugins_initialized = False

    def test_register_new_category(self):
        register_messages("test_cat", ["zipping...", "zapping..."])
        msgs = get_spinner_messages()
        assert "zipping..." in msgs
        assert "zapping..." in msgs

    def test_register_appends_to_existing(self):
        register_messages("test_cat", ["alpha..."])
        register_messages("test_cat", ["beta..."])
        cats = get_messages_by_category()
        assert "alpha..." in cats["test_cat"]
        assert "beta..." in cats["test_cat"]

    def test_unregister_removes_category(self):
        register_messages("test_cat2", ["gone..."])
        unregister_messages("test_cat2")
        cats = get_messages_by_category()
        assert "test_cat2" not in cats

    def test_unregister_nonexistent_is_noop(self):
        unregister_messages("does_not_exist")  # should not raise

    def test_register_reserved_category_raises(self):
        """Registering a reserved core category name should raise ValueError."""
        import pytest

        for reserved in ("puppy", "dev", "fun", "action", "standalone"):
            with pytest.raises(ValueError, match="reserved core category"):
                register_messages(reserved, ["should fail..."])

    def test_register_empty_category_raises(self):
        """Registering an empty category name should raise ValueError."""
        import pytest

        with pytest.raises(ValueError, match="non-empty string"):
            register_messages("", ["should fail..."])
        with pytest.raises(ValueError, match="non-empty string"):
            register_messages("   ", ["should fail..."])
