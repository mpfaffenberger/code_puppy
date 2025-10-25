"""Comprehensive unit tests for code_puppy.summarization_agent.

Tests agent creation, thread pool management, and summarization execution.
"""
import asyncio
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from code_puppy.summarization_agent import (
    get_summarization_agent,
    reload_summarization_agent,
    run_summarization_sync,
    _ensure_thread_pool,
)


class TestThreadPoolManagement:
    """Test thread pool initialization and management."""
    
    def test_ensure_thread_pool_creates_pool(self):
        """Test _ensure_thread_pool creates thread pool on first call."""
        with patch('code_puppy.summarization_agent._thread_pool', None):
            pool = _ensure_thread_pool()
            
            assert pool is not None
            assert pool._max_workers == 1
    
    def test_ensure_thread_pool_reuses_existing(self):
        """Test _ensure_thread_pool reuses existing pool."""
        pool1 = _ensure_thread_pool()
        pool2 = _ensure_thread_pool()
        
        assert pool1 is pool2


class TestAgentReload:
    """Test agent reload functionality."""
    
    @patch('code_puppy.summarization_agent.ModelFactory')
    @patch('code_puppy.summarization_agent.get_global_model_name')
    @patch('code_puppy.summarization_agent.get_use_dbos')
    def test_reload_agent_without_dbos(self, mock_dbos, mock_model_name, mock_factory):
        """Test reload_summarization_agent without DBOS."""
        mock_dbos.return_value = False
        mock_model_name.return_value = "gpt-4"
        mock_model = Mock()
        mock_factory.get_model.return_value = mock_model
        mock_factory.load_config.return_value = {}
        
        with patch('code_puppy.summarization_agent.Agent') as mock_agent_class:
            mock_agent = Mock()
            mock_agent_class.return_value = mock_agent
            
            agent = reload_summarization_agent()
            
            # Should return the agent directly (not DBOSAgent)
            assert agent is mock_agent
            mock_agent_class.assert_called_once()
            
            # Verify agent was created with correct params
            call_kwargs = mock_agent_class.call_args[1]
            assert call_kwargs['model'] is mock_model
            assert 'summarization expert' in call_kwargs['instructions']
            assert call_kwargs['output_type'] is str
            assert call_kwargs['retries'] == 1
    
    @patch('code_puppy.summarization_agent.ModelFactory')
    @patch('code_puppy.summarization_agent.get_global_model_name')
    @patch('code_puppy.summarization_agent.get_use_dbos')
    def test_reload_agent_with_dbos(self, mock_dbos, mock_model_name, mock_factory):
        """Test reload_summarization_agent with DBOS enabled."""
        mock_dbos.return_value = True
        mock_model_name.return_value = "gpt-4"
        mock_model = Mock()
        mock_factory.get_model.return_value = mock_model
        mock_factory.load_config.return_value = {}
        
        with patch('code_puppy.summarization_agent.Agent') as mock_agent_class:
            # Patch the DBOSAgent import dynamically
            with patch('pydantic_ai.durable_exec.dbos.DBOSAgent') as mock_dbos_class:
                mock_agent = Mock()
                mock_dbos_agent = Mock()
                mock_agent_class.return_value = mock_agent
                mock_dbos_class.return_value = mock_dbos_agent
                
                agent = reload_summarization_agent()
                
                # Should return DBOSAgent wrapper
                assert agent is mock_dbos_agent
                mock_dbos_class.assert_called_once()
    
    @patch('code_puppy.summarization_agent.reload_summarization_agent')
    def test_get_agent_force_reload(self, mock_reload):
        """Test get_summarization_agent with force_reload=True."""
        mock_agent = Mock()
        mock_reload.return_value = mock_agent
        
        agent = get_summarization_agent(force_reload=True)
        
        assert agent is mock_agent
        mock_reload.assert_called_once()
    
    @patch('code_puppy.summarization_agent.reload_summarization_agent')
    @patch('code_puppy.summarization_agent._summarization_agent', None)
    def test_get_agent_creates_if_none(self, mock_reload):
        """Test get_summarization_agent creates agent if none exists."""
        mock_agent = Mock()
        mock_reload.return_value = mock_agent
        
        agent = get_summarization_agent(force_reload=False)
        
        assert agent is mock_agent
        mock_reload.assert_called_once()


class TestSummarizationExecution:
    """Test summarization execution logic."""
    
    @pytest.mark.asyncio
    @patch('code_puppy.summarization_agent.get_summarization_agent')
    async def test_run_sync_outside_event_loop(self, mock_get_agent):
        """Test run_summarization_sync when not in an event loop."""
        mock_agent = Mock()
        mock_result = Mock()
        mock_result.new_messages.return_value = ["summary1", "summary2"]
        
        # Mock the agent.run to be async
        async def mock_run(*args, **kwargs):
            return mock_result
        
        mock_agent.run = mock_run
        mock_get_agent.return_value = mock_agent
        
        # Run in a thread to simulate no event loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                run_summarization_sync,
                "summarize this",
                ["msg1", "msg2"]
            )
            result = future.result()
        
        assert result == ["summary1", "summary2"]
    
    @patch('code_puppy.summarization_agent.get_summarization_agent')
    @patch('code_puppy.summarization_agent._ensure_thread_pool')
    def test_run_sync_inside_event_loop(self, mock_pool, mock_get_agent):
        """Test run_summarization_sync when already in an event loop."""
        mock_agent = Mock()
        mock_result = Mock()
        mock_result.new_messages.return_value = ["summary"]
        
        async def mock_run(*args, **kwargs):
            return mock_result
        
        mock_agent.run = mock_run
        mock_get_agent.return_value = mock_agent
        
        # Mock thread pool submit
        mock_executor = Mock()
        mock_future = Mock()
        mock_future.result.return_value = mock_result
        mock_executor.submit.return_value = mock_future
        mock_pool.return_value = mock_executor
        
        # This simulates being inside an event loop
        async def test_in_loop():
            result = run_summarization_sync("test", ["msg"])
            return result
        
        result = asyncio.run(test_in_loop())
        
        assert result == ["summary"]
        # Should have used thread pool since we're in a loop
        mock_pool.assert_called_once()


class TestAgentInstructions:
    """Test agent instructions and configuration."""
    
    @patch('code_puppy.summarization_agent.ModelFactory')
    @patch('code_puppy.summarization_agent.get_global_model_name')
    @patch('code_puppy.summarization_agent.get_use_dbos')
    def test_agent_has_summarization_instructions(self, mock_dbos, mock_model_name, mock_factory):
        """Test agent is created with summarization-specific instructions."""
        mock_dbos.return_value = False
        mock_model_name.return_value = "gpt-4"
        mock_factory.get_model.return_value = Mock()
        mock_factory.load_config.return_value = {}
        
        with patch('code_puppy.summarization_agent.Agent') as mock_agent_class:
            reload_summarization_agent()
            
            call_kwargs = mock_agent_class.call_args[1]
            instructions = call_kwargs['instructions']
            
            # Verify key instruction components
            assert 'summarization expert' in instructions
            assert 'concise' in instructions.lower()
            assert 'tool calls' in instructions.lower()
    
    @patch('code_puppy.summarization_agent.ModelFactory')
    @patch('code_puppy.summarization_agent.get_global_model_name')
    @patch('code_puppy.summarization_agent.get_use_dbos')
    def test_agent_has_retry_limit(self, mock_dbos, mock_model_name, mock_factory):
        """Test agent is configured with retry limit."""
        mock_dbos.return_value = False
        mock_model_name.return_value = "gpt-4"
        mock_factory.get_model.return_value = Mock()
        mock_factory.load_config.return_value = {}
        
        with patch('code_puppy.summarization_agent.Agent') as mock_agent_class:
            reload_summarization_agent()
            
            call_kwargs = mock_agent_class.call_args[1]
            assert call_kwargs['retries'] == 1


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @patch('code_puppy.summarization_agent.ModelFactory')
    @patch('code_puppy.summarization_agent.get_global_model_name')
    @patch('code_puppy.summarization_agent.get_use_dbos')
    def test_multiple_reloads_increment_counter(self, mock_dbos, mock_model_name, mock_factory):
        """Test multiple reloads with DBOS increment the reload counter."""
        mock_dbos.return_value = True
        mock_model_name.return_value = "gpt-4"
        mock_factory.get_model.return_value = Mock()
        mock_factory.load_config.return_value = {}
        
        with patch('code_puppy.summarization_agent.Agent'):
            with patch('pydantic_ai.durable_exec.dbos.DBOSAgent') as mock_dbos_agent:
                # Reset counter
                import code_puppy.summarization_agent as sa_module
                sa_module._reload_count = 0
                
                reload_summarization_agent()
                reload_summarization_agent()
                reload_summarization_agent()
                
                # Counter should have incremented
                assert sa_module._reload_count == 3
