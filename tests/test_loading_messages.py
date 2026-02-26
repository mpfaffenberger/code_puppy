"""Tests for loading_messages module."""

import code_puppy.messaging.loading_messages as _lm

from code_puppy.messaging.loading_messages import (
    _plugin_categories,
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
        """Two calls should (very likely) produce different orderings."""
        a = get_spinner_messages()
        b = get_spinner_messages()
        # Same contents
        assert sorted(a) == sorted(b)
        # Extremely unlikely to be in the same order with 100+ messages
        assert a != b or len(a) < 3  # tiny lists might match

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
        _plugin_categories.pop("test_cat", None)
        _plugin_categories.pop("test_cat2", None)
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
