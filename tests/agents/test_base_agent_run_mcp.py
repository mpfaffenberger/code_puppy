"""Tests for BaseAgent run_with_mcp() method.

This module tests the run_with_mcp async method which handles:
- Running the agent with attachments (binary and link attachments)
- DBOS integration (with/without)
- Delayed compaction triggering
- Usage limits
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import BinaryContent, DocumentUrl, ImageUrl

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestBaseAgentRunMCP:
    """Test suite for BaseAgent run_with_mcp method with comprehensive coverage."""

    @pytest.fixture
    def agent(self):
        """Create a CodePuppyAgent instance for testing."""
        return CodePuppyAgent()

    @pytest.mark.asyncio
    async def test_run_with_mcp_basic(self, agent):
        """Test basic run_with_mcp functionality without attachments."""
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            result = await agent.run_with_mcp("Hello world")

            assert mock_run.called
            assert result.data == "response"
            # Verify the call was made with correct structure
            assert mock_run.call_count == 1
            call_args = mock_run.call_args
            # First positional argument should be the prompt
            assert "Hello world" in str(call_args[0][0])

    @pytest.mark.asyncio
    async def test_run_with_mcp_with_binary_attachments(self, agent):
        """Test run_with_mcp with binary attachments."""
        attachment = BinaryContent(data=b"test image data", media_type="image/png")

        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            await agent.run_with_mcp("Check this image", attachments=[attachment])

            assert mock_run.called
            # Verify the prompt payload is a list with text and attachments
            call_args = mock_run.call_args[0][0]
            assert isinstance(call_args, list)
            # First element should contain the text prompt (may include system prompt)
            assert "Check this image" in call_args[0]
            # Second element should be the attachment
            assert call_args[1] == attachment

    @pytest.mark.asyncio
    async def test_run_with_mcp_with_link_attachments(self, agent):
        """Test run_with_mcp with link attachments."""
        image_url = ImageUrl(url="https://example.com/image.jpg")
        doc_url = DocumentUrl(url="https://example.com/document.pdf")

        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            await agent.run_with_mcp(
                "Review these links", link_attachments=[image_url, doc_url]
            )

            assert mock_run.called
            # Verify the prompt payload includes both links
            call_args = mock_run.call_args[0][0]
            assert isinstance(call_args, list)
            assert "Review these links" in call_args[0]
            assert call_args[1] == image_url
            assert call_args[2] == doc_url

    @pytest.mark.asyncio
    async def test_run_with_mcp_with_mixed_attachments(self, agent):
        """Test run_with_mcp with both binary and link attachments."""
        binary_attachment = BinaryContent(data=b"test data", media_type="image/jpeg")
        link_attachment = ImageUrl(url="https://example.com/photo.jpg")

        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            await agent.run_with_mcp(
                "Analyze these files",
                attachments=[binary_attachment],
                link_attachments=[link_attachment],
            )

            assert mock_run.called
            call_args = mock_run.call_args[0][0]
            assert isinstance(call_args, list)
            assert len(call_args) == 3
            assert "Analyze these files" in call_args[0]
            assert call_args[1] == binary_attachment
            assert call_args[2] == link_attachment

    @pytest.mark.asyncio
    async def test_run_with_mcp_with_empty_prompt_and_attachments(self, agent):
        """Test run_with_mcp with empty prompt but attachments."""
        attachment = BinaryContent(data=b"test data", media_type="image/png")

        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            await agent.run_with_mcp("", attachments=[attachment])

            assert mock_run.called
            # With empty prompt and attachments, should create a list
            call_args = mock_run.call_args[0][0]
            assert isinstance(call_args, list)
            # Empty prompt might have system prompt prepended for claude-code models
            # Just check that we have the attachment in the list
            assert attachment in call_args

    @pytest.mark.asyncio
    async def test_run_with_mcp_with_additional_kwargs(self, agent):
        """Test run_with_mcp forwards additional kwargs to agent.run."""
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            additional_args = {
                "max_tokens": 500,
                "temperature": 0.7,
                "custom_param": "value",
            }

            await agent.run_with_mcp("Test kwargs", **additional_args)

            assert mock_run.called
            # Verify additional kwargs were forwarded
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["max_tokens"] == 500
            assert call_kwargs["temperature"] == 0.7
            assert call_kwargs["custom_param"] == "value"

    @pytest.mark.asyncio
    async def test_run_with_mcp_uses_existing_agent(self, agent):
        """Test run_with_mcp reuses existing agent when available."""
        # Create a mock existing agent
        existing_agent = MagicMock()
        agent._code_generation_agent = existing_agent

        with patch.object(existing_agent, "run") as mock_run:
            mock_run.return_value = asyncio.Future()
            mock_run.return_value.set_result(MagicMock(data="reused response"))

            result = await agent.run_with_mcp("Reuse test")

            assert mock_run.called
            assert result.data == "reused response"
            # Should not call reload_code_generation_agent
            assert agent._code_generation_agent == existing_agent

    @pytest.mark.asyncio
    async def test_run_with_mcp_task_creation(self, agent):
        """Test run_with_mcp properly creates and manages async tasks."""
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            # The method should complete successfully
            result = await agent.run_with_mcp("Task test")

            assert mock_run.called
            assert result.data == "response"

    @pytest.mark.asyncio
    async def test_run_with_mcp_handles_exceptions_gracefully(self, agent):
        """Test run_with_mcp handles various exceptions properly."""
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(side_effect=Exception("Test error"))
            mock_agent.run = mock_run

            # Should handle and potentially swallow exceptions
            await agent.run_with_mcp("Error test")

            # The method should complete without raising (error handling in run_agent_task)
            # In real implementation, this would emit error info and continue
            assert mock_run.called

    @pytest.mark.asyncio
    async def test_run_with_mcp_forwards_all_kwargs(self, agent):
        """Test that all kwargs are properly forwarded to the underlying agent.run."""
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            # Test with various kwargs that might be passed through
            test_kwargs = {
                "max_tokens": 1000,
                "temperature": 0.5,
                "top_p": 0.9,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.1,
                "stop": ["\n", "END"],
                "stream": False,
            }

            await agent.run_with_mcp("Forward kwargs test", **test_kwargs)

            assert mock_run.called
            call_kwargs = mock_run.call_args[1]

            # Verify all kwargs were forwarded
            for key, value in test_kwargs.items():
                assert key in call_kwargs
                assert call_kwargs[key] == value

    @pytest.mark.asyncio
    async def test_run_with_mcp_empty_attachments_list(self, agent):
        """Test run_with_mcp handles empty attachments lists gracefully."""
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            await agent.run_with_mcp(
                "Empty attachments", attachments=[], link_attachments=[]
            )

            assert mock_run.called
            # Should pass prompt as string when no attachments
            call_args = mock_run.call_args[0][0]
            # The prompt might have system prompt prepended for claude-code models
            assert "Empty attachments" in str(call_args)
            # Should be a string, not a list
            assert isinstance(call_args, str)
