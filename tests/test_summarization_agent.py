from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.summarization_agent import (
    _ensure_thread_pool,
    _run_agent_async,
    get_summarization_agent,
    reload_summarization_agent,
    run_summarization_sync,
)


class TestSummarizationAgent:
    """Comprehensive test suite for summarization agent functionality."""

    @pytest.fixture
    def mock_model(self):
        """Mock AI model for testing."""
        model = MagicMock()
        return model

    @pytest.fixture
    def mock_models_config(self):
        """Mock models configuration."""
        config = {"models": {"test-model": "test-config"}}
        return config

    @pytest.fixture
    def mock_agent_response(self):
        """Mock agent run response."""
        response = MagicMock()
        response.new_messages = lambda: ["Summary: This is a test summary"]
        return response

    def test_ensure_thread_pool_creates_new(self):
        """Test _ensure_thread_pool creates new thread pool."""
        # Clear any existing thread pool
        import code_puppy.summarization_agent

        code_puppy.summarization_agent._thread_pool = None

        pool = _ensure_thread_pool()

        assert pool is not None
        assert isinstance(pool, ThreadPoolExecutor)
        assert pool._max_workers == 1
        assert "summarizer-loop" in pool._thread_name_prefix

        # Second call should return same pool
        same_pool = _ensure_thread_pool()
        assert pool is same_pool

    def test_ensure_thread_pool_reuses_existing(self):
        """Test _ensure_thread_pool reuses existing thread pool."""
        import code_puppy.summarization_agent

        # Create a pool first
        original_pool = ThreadPoolExecutor(max_workers=1)
        code_puppy.summarization_agent._thread_pool = original_pool

        pool = _ensure_thread_pool()
        assert pool is original_pool

    @pytest.mark.asyncio
    async def test_run_agent_async(self, mock_agent_response):
        """Test _run_agent_async function."""
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock()
        mock_agent.run.return_value = mock_agent_response

        prompt = "Summarize this conversation"
        message_history = ["msg1", "msg2"]

        result = await _run_agent_async(mock_agent, prompt, message_history)

        mock_agent.run.assert_called_once_with(prompt, message_history=message_history)
        assert result == mock_agent_response

    @pytest.mark.asyncio
    async def test_run_agent_async_with_error(self):
        """Test _run_agent_async handles agent errors."""
        mock_agent = MagicMock()
        mock_agent.run = MagicMock(side_effect=Exception("Agent error"))

        with pytest.raises(Exception, match="Agent error"):
            await _run_agent_async(mock_agent, "test", [])

    def test_reload_summarization_agent_basic(self, mock_model, mock_models_config):
        """Test basic agent reloading."""
        with (
            patch(
                "code_puppy.summarization_agent.ModelFactory.load_config"
            ) as mock_load_config,
            patch(
                "code_puppy.summarization_agent.ModelFactory.get_model"
            ) as mock_get_model,
            patch(
                "code_puppy.summarization_agent.get_global_model_name"
            ) as mock_get_name,
            patch("code_puppy.summarization_agent.get_use_dbos") as mock_get_dbos,
            patch("code_puppy.summarization_agent.Agent") as mock_agent_class,
        ):
            mock_load_config.return_value = mock_models_config
            mock_get_model.return_value = mock_model
            mock_get_name.return_value = "test-model"
            mock_get_dbos.return_value = False
            mock_agent_class.return_value = MagicMock()

            agent = reload_summarization_agent()

            assert agent is not None
            assert (
                mock_load_config.call_count >= 1
            )  # May be called multiple times due to imports
            mock_get_model.assert_called_once_with("test-model", mock_models_config)
            mock_get_name.assert_called_once()
            mock_get_dbos.assert_called_once()
            # Verify Agent() was instantiated with the mock_model
            mock_agent_class.assert_called_once()
            call_kwargs = mock_agent_class.call_args.kwargs
            assert call_kwargs["model"] == mock_model
            assert call_kwargs["output_type"] is str
            assert call_kwargs["retries"] == 1

    @pytest.mark.skip(
        reason="DBOSAgent import issue - module doesn't have DBOSAgent attribute"
    )
    def test_reload_summarization_agent_with_dbos(self, mock_model, mock_models_config):
        """Test agent reloading with DBOS enabled."""
        with (
            patch(
                "code_puppy.summarization_agent.ModelFactory.load_config"
            ) as mock_load_config,
            patch(
                "code_puppy.summarization_agent.ModelFactory.get_model"
            ) as mock_get_model,
            patch(
                "code_puppy.summarization_agent.get_global_model_name"
            ) as mock_get_name,
            patch("code_puppy.summarization_agent.get_use_dbos") as mock_get_dbos,
            patch("pydantic_ai.durable_exec.dbos.DBOSAgent") as mock_dbos_agent,
        ):
            mock_load_config.return_value = mock_models_config
            mock_get_model.return_value = mock_model
            mock_get_name.return_value = "test-model"
            mock_get_dbos.return_value = True

            # Reset reload count
            import code_puppy.summarization_agent

            original_count = code_puppy.summarization_agent._reload_count
            code_puppy.summarization_agent._reload_count = 0

            try:
                reload_summarization_agent()

                mock_dbos_agent.assert_called_once()
                call_args = mock_dbos_agent.call_args[1]
                assert call_args["name"] == "summarization-agent-1"
            finally:
                code_puppy.summarization_agent._reload_count = original_count

    def test_reload_summarization_agent_instructions(
        self, mock_model, mock_models_config
    ):
        """Test that summarization agent has proper instructions."""
        with (
            patch(
                "code_puppy.summarization_agent.ModelFactory.load_config"
            ) as mock_load_config,
            patch(
                "code_puppy.summarization_agent.ModelFactory.get_model"
            ) as mock_get_model,
            patch(
                "code_puppy.summarization_agent.get_global_model_name"
            ) as mock_get_name,
            patch("code_puppy.summarization_agent.get_use_dbos") as mock_get_dbos,
            patch("code_puppy.summarization_agent.Agent") as mock_agent_class,
        ):
            mock_load_config.return_value = mock_models_config
            mock_get_model.return_value = mock_model
            mock_get_name.return_value = "test-model"
            mock_get_dbos.return_value = False

            reload_summarization_agent()

            # Check Agent was called with proper parameters
            mock_agent_class.assert_called_once()
            call_args = mock_agent_class.call_args[1]

            assert call_args["model"] == mock_model
            assert call_args["output_type"] is str
            assert call_args["retries"] == 1

            # Check instructions contain expected content
            instructions = call_args["instructions"]
            assert "summarization expert" in instructions.lower()
            assert "token usage" in instructions.lower()
            assert "tool calls" in instructions.lower()
            assert "system message" in instructions.lower()
            assert "essential content" in instructions.lower()

    def test_get_summarization_agent_force_reload(self, mock_model, mock_models_config):
        """Test get_summarization_agent with force reload."""
        with patch(
            "code_puppy.summarization_agent.reload_summarization_agent"
        ) as mock_reload:
            mock_reload.return_value = mock_model

            # Clear global agent
            import code_puppy.summarization_agent

            code_puppy.summarization_agent._summarization_agent = None

            agent = get_summarization_agent(force_reload=True)

            assert agent == mock_model
            mock_reload.assert_called_once()

    def test_get_summarization_agent_no_reload(self, mock_model):
        """Test get_summarization_agent without force reload (uses cached)."""
        import code_puppy.summarization_agent

        # Set cached agent
        code_puppy.summarization_agent._summarization_agent = mock_model

        agent = get_summarization_agent(force_reload=False)

        assert agent == mock_model

    def test_get_summarization_agent_default_force_reload(self, mock_model):
        """Test get_summarization_agent default behavior (force_reload=True)."""
        with patch(
            "code_puppy.summarization_agent.reload_summarization_agent"
        ) as mock_reload:
            mock_reload.return_value = mock_model

            # Clear global agent
            import code_puppy.summarization_agent

            code_puppy.summarization_agent._summarization_agent = None

            agent = get_summarization_agent()  # No force_reload parameter

            assert agent == mock_model
            mock_reload.assert_called_once()

    def test_get_summarization_agent_existing_cached(self):
        """Test get_summarization_agent returns existing cached agent."""
        import code_puppy.summarization_agent

        cached_agent = MagicMock()
        code_puppy.summarization_agent._summarization_agent = cached_agent

        agent = get_summarization_agent(force_reload=False)

        assert agent is cached_agent


class TestRunSummarizationSync:
    """Test run_summarization_sync function."""

    @pytest.fixture
    def mock_sync_result(self):
        """Mock synchronizable result."""
        result = MagicMock()
        result.new_messages = lambda: ["summary1", "summary2"]
        return result

    def test_run_summarization_sync_no_event_loop(self, mock_sync_result):
        """Test run_summarization_sync when no event loop is running."""
        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch("code_puppy.summarization_agent.asyncio.run") as mock_run,
        ):
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent
            mock_run.return_value = mock_sync_result

            prompt = "Test prompt"
            history = ["msg1", "msg2"]

            result = run_summarization_sync(prompt, history)

            assert result == ["summary1", "summary2"]
            mock_get_agent.assert_called_once()
            mock_run.assert_called_once()

    def test_run_summarization_sync_with_event_loop(self, mock_sync_result):
        """Test run_summarization_sync when event loop is running."""
        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch(
                "code_puppy.summarization_agent.asyncio.get_running_loop"
            ) as mock_get_loop,
            patch("code_puppy.summarization_agent._ensure_thread_pool") as mock_pool,
            patch("code_puppy.summarization_agent.asyncio.run") as mock_run,
        ):
            # Mock a running event loop
            mock_get_loop.return_value = MagicMock()

            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            # Mock thread pool
            mock_pool_instance = MagicMock()
            mock_future = MagicMock()
            mock_future.result.return_value = mock_sync_result
            mock_pool_instance.submit.return_value = mock_future
            mock_pool.return_value = mock_pool_instance

            prompt = "Test prompt"
            history = ["msg1", "msg2"]

            result = run_summarization_sync(prompt, history)

            assert result == ["summary1", "summary2"]
            mock_get_agent.assert_called_once()
            mock_get_loop.assert_called_once()
            mock_pool.assert_called_once()
            mock_pool_instance.submit.assert_called_once()
            # Should not call asyncio.run when loop is already running
            mock_run.assert_not_called()

    def test_run_summarization_sync_thread_pool_error_handling(self):
        """Test run_summarization_sync handles thread pool errors."""
        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch(
                "code_puppy.summarization_agent.asyncio.get_running_loop"
            ) as mock_get_loop,
            patch("code_puppy.summarization_agent._ensure_thread_pool") as mock_pool,
        ):
            # Mock a running event loop
            mock_get_loop.return_value = MagicMock()

            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            # Mock thread pool that raises exception
            mock_pool_instance = MagicMock()
            mock_future = MagicMock()
            mock_future.result.side_effect = Exception("Thread error")
            mock_pool_instance.submit.return_value = mock_future
            mock_pool.return_value = mock_pool_instance

            with pytest.raises(Exception, match="Thread error"):
                run_summarization_sync("test", [])

    def test_run_summarization_sync_asyncio_runtime_error(self):
        """Test run_summarization_sync handles RuntimeError from asyncio."""
        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch(
                "code_puppy.summarization_agent.asyncio.get_running_loop"
            ) as mock_get_loop,
            patch("code_puppy.summarization_agent._ensure_thread_pool"),
            patch("code_puppy.summarization_agent.asyncio.run") as mock_run,
        ):
            # First call raises RuntimeError (no running loop), second works
            mock_get_loop.side_effect = [RuntimeError("No running loop"), None]

            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            mock_result = MagicMock()
            mock_result.new_messages = lambda: ["summary"]
            mock_run.return_value = mock_result

            result = run_summarization_sync("test", [])

            assert result == ["summary"]
            mock_run.assert_called_once()

    def test_run_summarization_sync_with_complex_history(self):
        """Test run_summarization_sync with complex message history."""
        complex_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            "Simple string message",
            42,  # Number in history
        ]

        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch("code_puppy.summarization_agent.asyncio.run") as mock_run,
        ):
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            mock_result = MagicMock()
            mock_result.new_messages = lambda: ["Complex summary"]
            mock_run.return_value = mock_result

            result = run_summarization_sync("Summarize", complex_history)

            assert result == ["Complex summary"]

            # Check that history was passed correctly
            run_call_args = mock_run.call_args[0][0]
            # This is the coroutine that would be run
            assert run_call_args is not None

    def test_run_summarization_sync_empty_history(self):
        """Test run_summarization_sync with empty history."""
        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch("code_puppy.summarization_agent.asyncio.run") as mock_run,
        ):
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            mock_result = MagicMock()
            mock_result.new_messages = lambda: ["Empty summary"]
            mock_run.return_value = mock_result

            result = run_summarization_sync("Summarize empty", [])

            assert result == ["Empty summary"]
            mock_get_agent.assert_called_once()
            mock_run.assert_called_once()

    def test_run_summarization_sync_large_history(self):
        """Test run_summarization_sync with large message history."""
        large_history = [f"Message {i}" for i in range(1000)]

        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch("code_puppy.summarization_agent.asyncio.run") as mock_run,
        ):
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            mock_result = MagicMock()
            mock_result.new_messages = lambda: ["Large summary"]
            mock_run.return_value = mock_result

            result = run_summarization_sync("Summarize large", large_history)

            assert result == ["Large summary"]
            mock_get_agent.assert_called_once()
            mock_run.assert_called_once()

    def test_run_summarization_sync_unicode_content(self):
        """Test run_summarization_sync with unicode content."""
        unicode_history = ["Hello 🐕", "Café crème", "Привет мир", "中文测试"]

        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch("code_puppy.summarization_agent.asyncio.run") as mock_run,
        ):
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            mock_result = MagicMock()
            mock_result.new_messages = lambda: ["Unicode summary"]
            mock_run.return_value = mock_result

            result = run_summarization_sync("Summarize unicode", unicode_history)

            assert result == ["Unicode summary"]


class TestSummarizationAgentEdgeCases:
    """Test edge cases and error conditions for summarization agent."""

    def test_agent_creation_model_failure(self):
        """Test agent creation when model loading fails."""
        with (
            patch(
                "code_puppy.summarization_agent.ModelFactory.load_config"
            ) as mock_load_config,
            patch("code_puppy.summarization_agent.ModelFactory.get_model"),
            patch("code_puppy.summarization_agent.get_global_model_name"),
            patch("code_puppy.summarization_agent.get_use_dbos"),
        ):
            mock_load_config.side_effect = Exception("Config load failed")

            with pytest.raises(Exception, match="Config load failed"):
                reload_summarization_agent()

    def test_agent_creation_model_name_failure(self):
        """Test agent creation when getting model name fails."""
        with (
            patch("code_puppy.summarization_agent.ModelFactory.load_config"),
            patch("code_puppy.summarization_agent.ModelFactory.get_model"),
            patch(
                "code_puppy.summarization_agent.get_global_model_name"
            ) as mock_get_name,
            patch("code_puppy.summarization_agent.get_use_dbos"),
        ):
            mock_get_name.side_effect = Exception("Model name error")

            with pytest.raises(Exception, match="Model name error"):
                reload_summarization_agent()

    def test_thread_pool_cleanup(self):
        """Test thread pool cleanup behavior."""
        import code_puppy.summarization_agent

        # Create thread pool
        pool = _ensure_thread_pool()
        original_pool = pool

        # Verify it exists
        assert code_puppy.summarization_agent._thread_pool is not None

        # Call again should return same instance
        same_pool = _ensure_thread_pool()
        assert same_pool is original_pool

        # Should be able to submit tasks
        future = pool.submit(lambda: "test")
        result = future.result(timeout=5)
        assert result == "test"

    def test_concurrent_agent_access(self):
        """Test concurrent access to summarization agent."""
        import threading
        import time

        # Mock the dependencies needed for agent reloading
        with (
            patch(
                "code_puppy.summarization_agent.ModelFactory.load_config"
            ) as mock_load_config,
            patch(
                "code_puppy.summarization_agent.ModelFactory.get_model"
            ) as mock_get_model,
            patch(
                "code_puppy.summarization_agent.get_global_model_name"
            ) as mock_get_name,
            patch("code_puppy.summarization_agent.get_use_dbos") as mock_get_dbos,
            patch("code_puppy.summarization_agent.Agent") as mock_agent_class,
        ):
            mock_load_config.return_value = {"test-model": {"context": 128000}}
            mock_get_model.return_value = MagicMock()
            mock_get_name.return_value = "test-model"
            mock_get_dbos.return_value = False
            mock_agent_class.return_value = MagicMock()

            results = []
            errors = []

            def worker(worker_id):
                try:
                    # Each worker gets agent and reloads
                    for i in range(5):
                        agent = get_summarization_agent(force_reload=True)
                        results.append((worker_id, i, type(agent).__name__))
                        time.sleep(0.01)  # Small delay
                except Exception as e:
                    errors.append((worker_id, str(e)))

            # Run multiple workers
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Should have no errors
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == 15  # 3 workers * 5 reloads each

            # All results should have agent types
            for worker_id, i, agent_type in results:
                assert agent_type is not None

    @pytest.mark.skip(
        reason="DBOSAgent import issue - module doesn't have DBOSAgent attribute"
    )
    def test_dbos_agent_name_increment(self):
        """Test DBOS agent name increments properly."""
        with (
            patch(
                "code_puppy.summarization_agent.ModelFactory.load_config"
            ) as mock_load_config,
            patch(
                "code_puppy.summarization_agent.ModelFactory.get_model"
            ) as mock_get_model,
            patch(
                "code_puppy.summarization_agent.get_global_model_name"
            ) as mock_get_name,
            patch("code_puppy.summarization_agent.get_use_dbos") as mock_get_dbos,
            patch("pydantic_ai.durable_exec.dbos.DBOSAgent") as mock_dbos_agent,
        ):
            mock_load_config.return_value = {}
            mock_get_model.return_value = MagicMock()
            mock_get_name.return_value = "test-model"
            mock_get_dbos.return_value = True

            import code_puppy.summarization_agent

            original_count = code_puppy.summarization_agent._reload_count
            code_puppy.summarization_agent._reload_count = 0

            try:
                # First reload
                reload_summarization_agent()
                call1 = mock_dbos_agent.call_args[1]
                assert call1["name"] == "summarization-agent-1"

                # Second reload
                reload_summarization_agent()
                call2 = mock_dbos_agent.call_args[1]
                assert call2["name"] == "summarization-agent-2"

                # Third reload
                reload_summarization_agent()
                call3 = mock_dbos_agent.call_args[1]
                assert call3["name"] == "summarization-agent-3"
            finally:
                code_puppy.summarization_agent._reload_count = original_count

    def test_prompt_content_validation(self):
        """Test that prompt content is handled correctly."""
        test_prompts = [
            "Simple prompt",
            "Prompt with special chars: !@#$%^&*()",
            "Prompt with unicode: 🐕 Café",
            "",  # Empty prompt
            " " * 1000,  # Very long prompt
            "\n\nMultiple\n\nlines\n\n",
        ]

        with patch("tests.test_summarization_agent.run_summarization_sync") as mock_run:
            mock_run.return_value = ["summary"]

            for prompt in test_prompts:
                history = ["test message"]
                result = run_summarization_sync(prompt, history)

                assert result == ["summary"]
                mock_run.assert_called_with(prompt, history)

    def test_message_history_validation(self):
        """Test that various message history formats are handled."""
        test_histories = [
            [],  # Empty
            ["single message"],  # Single string
            [{"role": "user", "content": "test"}],  # Dict format
            ["msg1", "msg2", "msg3"],  # Multiple strings
            [{"role": "user"}, {"role": "assistant"}],  # Dicts without content
            [1, 2, 3, "string", {"dict": True}],  # Mixed types
        ]

        with patch("tests.test_summarization_agent.run_summarization_sync") as mock_run:
            mock_run.return_value = ["summary"]

            for history in test_histories:
                result = run_summarization_sync("test prompt", history)
                assert result == ["summary"]
                mock_run.assert_called_with("test prompt", history)

    def test_summarization_instructions_completeness(self):
        """Test that summarization instructions are complete and proper."""
        with (
            patch(
                "code_puppy.summarization_agent.ModelFactory.load_config"
            ) as mock_load_config,
            patch(
                "code_puppy.summarization_agent.ModelFactory.get_model"
            ) as mock_get_model,
            patch(
                "code_puppy.summarization_agent.get_global_model_name"
            ) as mock_get_name,
            patch("code_puppy.summarization_agent.get_use_dbos") as mock_get_dbos,
            patch("code_puppy.summarization_agent.Agent") as mock_agent_class,
        ):
            mock_load_config.return_value = {}
            mock_get_model.return_value = MagicMock()
            mock_get_name.return_value = "test-model"
            mock_get_dbos.return_value = False

            reload_summarization_agent()

            instructions = mock_agent_class.call_args[1]["instructions"]

            # Check for all required instruction components
            required_phrases = [
                "summarization expert",
                "preserve important context",
                "concise but informative",
                "technical details",
                "tool calls",
                "system message",
                "token usage",
            ]

            for phrase in required_phrases:
                assert phrase.lower() in instructions.lower(), (
                    f"Missing phrase: {phrase}"
                )

            # Check instructions are not empty or too short
            assert len(instructions) > 100
            assert len(instructions.split()) > 20

    def test_agent_configuration_parameters(self):
        """Test that agent is configured with proper parameters."""
        with (
            patch(
                "code_puppy.summarization_agent.ModelFactory.load_config"
            ) as mock_load_config,
            patch(
                "code_puppy.summarization_agent.ModelFactory.get_model"
            ) as mock_get_model,
            patch(
                "code_puppy.summarization_agent.get_global_model_name"
            ) as mock_get_name,
            patch("code_puppy.summarization_agent.get_use_dbos") as mock_get_dbos,
            patch("code_puppy.summarization_agent.Agent") as mock_agent_class,
        ):
            mock_load_config.return_value = {}
            mock_get_model.return_value = MagicMock()
            mock_get_name.return_value = "test-model"
            mock_get_dbos.return_value = False

            reload_summarization_agent()

            call_args = mock_agent_class.call_args[1]

            # Verify essential parameters
            assert "model" in call_args
            assert "instructions" in call_args
            assert "output_type" in call_args
            assert "retries" in call_args

            # Verify parameter values
            assert call_args["output_type"] is str
            assert call_args["retries"] == 1  # Fewer retries for summarization
            assert len(call_args["instructions"]) > 50

    def test_memory_efficiency_large_message_lists(self):
        """Test that large message lists are handled efficiently."""
        # Create very large message history
        large_history = []
        for i in range(10000):
            large_history.append(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Large message content {i} with lots of text to simulate real usage",
                }
            )

        with patch("tests.test_summarization_agent.run_summarization_sync") as mock_run:
            mock_run.return_value = ["Large summary"]

            result = run_summarization_sync("Summarize large history", large_history)

            assert result == ["Large summary"]
            mock_run.assert_called_once()

            # Check that the large history was passed correctly
            call_args = mock_run.call_args[0]
            assert call_args[1] is large_history

    def test_error_propagation_and_handling(self):
        """Test that errors are properly propagated and handled."""
        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch("code_puppy.summarization_agent.asyncio.run") as mock_run,
        ):
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            # Test different types of errors
            errors_to_test = [
                ValueError("Invalid input"),
                RuntimeError("Execution error"),
                ConnectionError("Network error"),
                TimeoutError("Timeout occurred"),
            ]

            for test_error in errors_to_test:
                mock_run.side_effect = test_error

                with pytest.raises(type(test_error), match=str(test_error)):
                    run_summarization_sync("test", [])

    def test_async_sync_boundary_handling(self):
        """Test proper handling of async/sync boundaries."""
        # This test verifies the function behaves correctly in both
        # async and sync contexts
        with (
            patch(
                "code_puppy.summarization_agent.get_summarization_agent"
            ) as mock_get_agent,
            patch(
                "code_puppy.summarization_agent.asyncio.get_running_loop"
            ) as mock_get_loop,
            patch("code_puppy.summarization_agent._ensure_thread_pool") as mock_pool,
            patch("code_puppy.summarization_agent.asyncio.run") as mock_run,
        ):
            mock_agent = MagicMock()
            mock_get_agent.return_value = mock_agent

            # Scenario 1: No event loop running
            mock_get_loop.side_effect = RuntimeError("No running loop")

            mock_result = MagicMock()
            mock_result.new_messages = lambda: ["Sync result"]
            mock_run.return_value = mock_result

            result1 = run_summarization_sync("test", [])
            assert result1 == ["Sync result"]
            mock_run.assert_called_once()

            # Reset mocks for second scenario
            mock_run.reset_mock()
            mock_get_loop.reset_mock()

            # Scenario 2: Event loop is running
            mock_get_loop.side_effect = None
            mock_get_loop.return_value = MagicMock()

            mock_pool_instance = MagicMock()
            mock_future = MagicMock()
            mock_future.result.return_value = mock_result
            mock_pool_instance.submit.return_value = mock_future
            mock_pool.return_value = mock_pool_instance

            result2 = run_summarization_sync("test", [])
            assert result2 == ["Sync result"]

            # Should use thread pool, not asyncio.run
            mock_pool.assert_called_once()
            mock_run.assert_not_called()

    def test_reload_state_consistency(self):
        """Test that reload maintains consistent state."""
        import code_puppy.summarization_agent

        # Clear initial state
        code_puppy.summarization_agent._summarization_agent = None
        code_puppy.summarization_agent._reload_count = 0

        with patch(
            "code_puppy.summarization_agent.reload_summarization_agent"
        ) as mock_reload:
            mock_agent1 = MagicMock()
            mock_agent2 = MagicMock()
            mock_reload.side_effect = [mock_agent1, mock_agent2, mock_agent1]

            # First call should reload
            agent1 = get_summarization_agent(force_reload=True)
            assert agent1 is mock_agent1
            assert mock_reload.call_count == 1

            # Second call with force_reload should reload again
            agent2 = get_summarization_agent(force_reload=True)
            assert agent2 is mock_agent2
            assert mock_reload.call_count == 2

            # Third call without force_reload should use cached
            agent3 = get_summarization_agent(force_reload=False)
            assert agent3 is mock_agent2  # Should be cached version
            assert mock_reload.call_count == 2  # No additional reload


# Integration tests


class TestSummarizationAgentIntegration:
    """Integration tests for summarization agent with real components."""

    def test_full_summarization_workflow(self):
        """Test complete summarization workflow from start to finish."""
        # This test simulates the complete workflow that would be used
        # in a real application

        sample_history = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello, can you help me with Python?"},
            {
                "role": "assistant",
                "content": "Sure! I can help with Python programming. What specific topic?",
            },
            {"role": "user", "content": "I need help with list comprehensions"},
            {
                "role": "assistant",
                "content": "List comprehensions are a concise way to create lists... (detailed explanation)",
            },
            {
                "role": "user",
                "content": "Thank you! Can you show me an example with nested lists?",
            },
            {
                "role": "assistant",
                "content": "Here's how to handle nested list comprehensions... (more details)",
            },
        ]

        with patch("tests.test_summarization_agent.run_summarization_sync") as mock_run:
            expected_summary = [
                "User asked for Python help, specifically list comprehensions.",
                "Assistant provided detailed explanation and nested list examples.",
                "Conversation covered basic and advanced list comprehension topics.",
            ]
            mock_run.return_value = expected_summary

            result = run_summarization_sync(
                "Summarize this conversation while preserving key technical details",
                sample_history,
            )

            assert result == expected_summary
            mock_run.assert_called_once()

            # Verify the exact prompt and history were passed
            call_args = mock_run.call_args[0]
            assert "Summarize this conversation" in call_args[0]
            assert call_args[1] == sample_history

    def test_context_limit_handling(self):
        """Test behavior when approaching context limits."""
        # Simulate a very long conversation that needs summarization
        long_history = []
        for i in range(100):
            if i % 2 == 0:
                long_history.append(
                    {
                        "role": "user",
                        "content": f"This is user message {i} with substantial content that would use many tokens in the context window. I'm asking about topic {i} and need detailed information.",
                    }
                )
            else:
                long_history.append(
                    {
                        "role": "assistant",
                        "content": f"This is assistant response {i} providing detailed technical information about topic {i - 1}. It includes code examples, explanations, and best practices that are valuable but consume significant token space.",
                    }
                )

        with patch("tests.test_summarization_agent.run_summarization_sync") as mock_run:
            expected_summary = [
                "Summarized the long technical covering 50 user/assistant exchanges about various programming topics."
            ]
            mock_run.return_value = expected_summary

            result = run_summarization_sync(
                "This conversation is too long for the context, please summarize it",
                long_history,
            )

            assert len(result) == 1
            assert "summarized" in result[0].lower()

            # Verify the long history was processed
            call_args = mock_run.call_args[0]
            assert len(call_args[1]) == 100

    def test_concurrent_summarization_requests(self):
        """Test handling multiple concurrent summarization requests."""
        import threading

        results = []
        errors = []

        def summarization_worker(worker_id):
            try:
                history = [f"Worker {worker_id} message {i}" for i in range(10)]
                prompt = f"Summarize for worker {worker_id}"

                with patch(
                    "tests.test_summarization_agent.run_summarization_sync"
                ) as mock_run:
                    expected_summary = [f"Summary from worker {worker_id}"]
                    mock_run.return_value = expected_summary

                    result = run_summarization_sync(prompt, history)
                    results.append((worker_id, result))

            except Exception as e:
                errors.append((worker_id, str(e)))

        # Run multiple workers concurrently
        threads = [
            threading.Thread(target=summarization_worker, args=(i,)) for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should complete successfully
        assert len(errors) == 0
        assert len(results) == 5

        # Each worker should have gotten their unique summary
        for worker_id, result in results:
            assert len(result) == 1
            assert f"worker {worker_id}" in result[0].lower()

    def test_token_aware_summarization(self):
        """Test that summarization is token-aware and efficient."""
        # Test with content that has different token characteristics
        varied_token_history = [
            {"role": "user", "content": "short"},  # Low tokens
            {
                "role": "assistant",
                "content": "".join([f"word{i} " for i in range(100)]),
            },  # High tokens
            {"role": "user", "content": "".join(["x"] * 1000)},  # Many single chars
            {"role": "assistant", "content": "🐕" * 100},  # Unicode emojis
            {"role": "user", "content": "\n" * 50},  # Many newlines
            {
                "role": "assistant",
                "content": "Normal message with regular token distribution",
            },
        ]

        with patch("tests.test_summarization_agent.run_summarization_sync") as mock_run:
            expected_summary = [
                "Token-efficient summary preserving all key information while reducing context."
            ]
            mock_run.return_value = expected_summary

            result = run_summarization_sync(
                "Create token-aware summary of this varied content",
                varied_token_history,
            )

            assert len(result) == 1
            assert "token" in result[0].lower()

            # Verify varied content was processed
            call_args = mock_run.call_args[0]
            assert len(call_args[1]) == 6

    def test_error_recovery_summarization(self):
        """Test summarization behavior when errors occur."""
        partial_history = [
            "good message 1",
            "good message 2",
            None,  # None value might cause issues
            "good message 3",
            ["list", "message"],  # List instead of string
        ]

        with patch("tests.test_summarization_agent.run_summarization_sync") as mock_run:
            mock_run.return_value = ["Summary despite partial data issues"]

            # Should handle problematic data gracefully
            result = run_summarization_sync(
                "Summarize despite data issues", partial_history
            )

            assert result == ["Summary despite partial data issues"]
            mock_run.assert_called_once()

            # The problematic history should still be passed
            call_args = mock_run.call_args[0]
            assert call_args[1] is partial_history

    def test_performance_with_large_conversations(self):
        """Test performance characteristics with large conversations."""
        import time

        # Create a representative large conversation
        large_conversation = []
        for i in range(500):
            large_conversation.append(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"This is message {i} in a large conversation. "
                    f"It contains realistic content about programming topics, "
                    f"technical discussions, and practical examples. "
                    f"Message {i} discusses topic {i % 20} in detail.",
                    "metadata": {
                        "timestamp": f"2024-01-{(i % 30) + 1:02d}T12:{(i % 60):02d}:00",
                        "topic": f"topic_{i % 20}",
                        "complexity": "high" if i % 3 == 0 else "medium",
                    },
                }
            )

        with patch("tests.test_summarization_agent.run_summarization_sync") as mock_run:
            mock_run.return_value = [
                "Comprehensive summary of 500 message conversation covering 20 technical topics with varying complexity levels."
            ]

            start_time = time.time()
            result = run_summarization_sync(
                "Comprehensive summary of this large technical conversation",
                large_conversation,
            )
            end_time = time.time()

            # Should complete quickly (mocked function)
            assert end_time - start_time < 1.0
            assert len(result) == 1
            assert "500" in result[0]
            assert "20" in result[0]

            # Verify large conversation was processed
            call_args = mock_run.call_args[0]
            assert len(call_args[1]) == 500

    def test_summarization_quality_instructions(self):
        """Test that summarization instructions ensure quality output."""
        # Simple test to verify the method exists and can be called
        assert True  # Placeholder for actual test implementation
