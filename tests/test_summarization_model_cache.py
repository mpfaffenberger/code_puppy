"""Tests for P2-05/PERF-05: summarization and model config caching.

Covers:
- get_summarization_agent(force_reload=False) default: reused without reload
- get_summarization_agent reloads when model changes
- get_cached_models_config() returns same config on repeated calls
- invalidate_models_config_cache() forces reload
- Model config cache invalidates on file changes (mtime)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import code_puppy.summarization_agent as sa_mod


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Reset module-level caches between tests."""
    sa_mod._summarization_agent = None
    sa_mod._cached_model_name = None
    sa_mod._models_config_cache = (None, None)
    yield
    sa_mod._summarization_agent = None
    sa_mod._cached_model_name = None
    sa_mod._models_config_cache = (None, None)


class TestSummarizationAgentCache:
    """P2-05: get_summarization_agent defaults to reuse."""

    def test_default_force_reload_is_false(self):
        """The default argument for force_reload is now False."""
        import inspect

        sig = inspect.signature(sa_mod.get_summarization_agent)
        assert sig.parameters["force_reload"].default is False

    def test_agent_reused_without_force_reload(self):
        """Without force_reload, the same agent is returned on subsequent calls."""
        mock_agent = MagicMock()
        with patch.object(
            sa_mod, "reload_summarization_agent", return_value=mock_agent
        ) as mock_reload:
            with patch.object(
                sa_mod, "get_summarization_model_name", return_value="test-model"
            ):
                first = sa_mod.get_summarization_agent()
                second = sa_mod.get_summarization_agent()

        assert first is second
        # reload should have been called only once
        assert mock_reload.call_count == 1

    def test_agent_reloads_when_model_changes(self):
        """When the model name changes, the agent is rebuilt."""
        mock_agent1 = MagicMock()
        mock_agent2 = MagicMock()
        call_count = 0

        def fake_reload():
            nonlocal call_count
            call_count += 1
            return mock_agent1 if call_count == 1 else mock_agent2

        with patch.object(
            sa_mod, "reload_summarization_agent", side_effect=fake_reload
        ):
            with patch.object(
                sa_mod,
                "get_summarization_model_name",
                side_effect=["model-a", "model-b"],
            ):
                first = sa_mod.get_summarization_agent()
                second = sa_mod.get_summarization_agent()

        assert first is mock_agent1
        assert second is mock_agent2
        assert call_count == 2

    def test_force_reload_rebuilds_even_if_model_same(self):
        """force_reload=True always rebuilds, even with same model name."""
        mock_agent1 = MagicMock()
        mock_agent2 = MagicMock()
        call_count = 0

        def fake_reload():
            nonlocal call_count
            call_count += 1
            return mock_agent1 if call_count == 1 else mock_agent2

        with patch.object(
            sa_mod, "reload_summarization_agent", side_effect=fake_reload
        ):
            with patch.object(
                sa_mod, "get_summarization_model_name", return_value="same-model"
            ):
                first = sa_mod.get_summarization_agent()
                second = sa_mod.get_summarization_agent(force_reload=True)

        assert first is mock_agent1
        assert second is mock_agent2
        assert call_count == 2

    def test_first_call_always_builds(self):
        """First call with force_reload=False still builds the agent."""
        mock_agent = MagicMock()
        with patch.object(
            sa_mod, "reload_summarization_agent", return_value=mock_agent
        ) as mock_reload:
            with patch.object(
                sa_mod, "get_summarization_model_name", return_value="test-model"
            ):
                result = sa_mod.get_summarization_agent()

        assert result is mock_agent
        assert mock_reload.call_count == 1


class TestModelConfigCache:
    """P2-05/PERF-05: Model config caching with mtime invalidation."""

    def test_cached_config_returns_same_on_repeated_calls(self):
        """Repeated calls to get_cached_models_config return the same dict."""
        mock_config = {"gpt-4o": {"type": "openai", "name": "gpt-4o"}}
        with patch.object(sa_mod, "ModelFactory") as mock_factory:
            mock_factory.load_config.return_value = mock_config
            # Need to reset the fingerprint too
            with patch.object(
                sa_mod, "_models_config_fingerprint", return_value=(1.0, "abc")
            ):
                first = sa_mod.get_cached_models_config()
                second = sa_mod.get_cached_models_config()

        assert first is second
        # ModelFactory.load_config should only be called once
        assert mock_factory.load_config.call_count == 1

    def test_invalidate_forces_reload(self):
        """invalidate_models_config_cache forces the next call to reload."""
        mock_config = {"gpt-4o": {"type": "openai", "name": "gpt-4o"}}
        with patch.object(sa_mod, "ModelFactory") as mock_factory:
            mock_factory.load_config.return_value = mock_config
            with patch.object(
                sa_mod, "_models_config_fingerprint", return_value=(1.0, "abc")
            ):
                sa_mod.get_cached_models_config()
                sa_mod.invalidate_models_config_cache()
                sa_mod.get_cached_models_config()

        assert mock_factory.load_config.call_count == 2

    def test_config_invalidates_on_fingerprint_change(self):
        """When the fingerprint changes, the cache is invalidated."""
        mock_config = {"gpt-4o": {"type": "openai", "name": "gpt-4o"}}
        with patch.object(sa_mod, "ModelFactory") as mock_factory:
            mock_factory.load_config.return_value = mock_config
            with patch.object(
                sa_mod,
                "_models_config_fingerprint",
                side_effect=[(1.0, "abc"), (2.0, "def")],
            ):
                sa_mod.get_cached_models_config()
                sa_mod.get_cached_models_config()

        # Two different fingerprints => two loads
        assert mock_factory.load_config.call_count == 2

    def test_fingerprint_includes_bundled_models_json(self):
        """The fingerprint function should at least look at models.json."""
        # Just verify it doesn't crash
        fp = sa_mod._models_config_fingerprint()
        assert isinstance(fp, tuple)
        assert len(fp) == 2
        assert isinstance(fp[0], float)
        assert isinstance(fp[1], str)

    def test_cache_propagates_load_failure(self):
        """If ModelFactory.load_config() fails, the exception propagates."""
        with patch.object(sa_mod, "ModelFactory") as mock_factory:
            mock_factory.load_config.side_effect = RuntimeError("nope")
            with patch.object(
                sa_mod, "_models_config_fingerprint", return_value=(1.0, "abc")
            ):
                with pytest.raises(RuntimeError, match="nope"):
                    sa_mod.get_cached_models_config()
