import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from acp.schema import InitializeRequest, NewSessionRequest, PromptRequest, SessionNotification
from acp import helpers
from code_puppy import __version__
from code_puppy.acp_server import CodePuppyAgent, acp_main


@pytest.mark.asyncio
async def test_code_puppy_agent_prompt():
    # Mock the get_current_agent function
    with patch("code_puppy.acp_server.get_current_agent") as mock_get_agent:
        # Create a mock agent with an async run_with_mcp method
        mock_agent = MagicMock()
        mock_agent.run_with_mcp = AsyncMock(return_value=MagicMock(output="Test response"))
        mock_get_agent.return_value = mock_agent

        # Create a mock connection
        mock_conn = MagicMock()
        mock_conn.sessionUpdate = AsyncMock()

        # Instantiate the CodePuppyAgent
        agent = CodePuppyAgent(mock_conn)

        # Create a mock prompt request
        prompt_request = PromptRequest(
            sessionId="test-session",
            prompt=[helpers.text_block("Hello, world!")],
        )

        # Call the prompt method
        response = await agent.prompt(prompt_request)

        # Assert that the agent's run_with_mcp was called with the correct prompt
        mock_agent.run_with_mcp.assert_called_once_with("Hello, world!")

        # Assert that sessionUpdate was called with the correct response
        mock_conn.sessionUpdate.assert_called_once()
        sent_notification = mock_conn.sessionUpdate.call_args[0][0]
        assert isinstance(sent_notification, SessionNotification)
        assert sent_notification.sessionId == "test-session"
        sent_update = sent_notification.update
        assert sent_update.sessionUpdate == "agent_message_chunk"
        assert len(sent_update.content) == 1
        sent_block = sent_update.content[0]
        assert sent_block.type == "text"
        assert sent_block.text == "Test response"

        # Assert that the prompt response has the correct stop reason
        assert response.stopReason == "end_turn"


@pytest.mark.asyncio
async def test_acp_main():
    # Mock stdio_streams and AgentSideConnection
    with patch("code_puppy.acp_server.stdio_streams") as mock_stdio_streams, patch(
        "code_puppy.acp_server.AgentSideConnection"
    ) as mock_agent_side_connection:
        # Make stdio_streams an async mock
        mock_stdio_streams.return_value = (AsyncMock(), AsyncMock())

        # Call acp_main and cancel it after a short time
        task = asyncio.create_task(acp_main())
        await asyncio.sleep(0.01)
        task.cancel()

        # Assert that stdio_streams was called
        mock_stdio_streams.assert_called_once()

        # Assert that AgentSideConnection was called
        mock_agent_side_connection.assert_called_once()
        assert isinstance(
            mock_agent_side_connection.call_args[0][0](MagicMock()), CodePuppyAgent
        )


@pytest.mark.asyncio
async def test_code_puppy_agent_initialize():
    # Create a mock connection
    mock_conn = MagicMock()
    # Instantiate the CodePuppyAgent
    agent = CodePuppyAgent(mock_conn)
    # Create a mock initialize request
    initialize_request = InitializeRequest(protocolVersion=1)
    # Call the initialize method
    response = await agent.initialize(initialize_request)
    # Assert that the response has the correct protocol version
    assert response.protocolVersion == 1
    # Assert that the agent information is correct
    assert response.agentInfo.name == "Code Puppy"
    assert response.agentInfo.version == __version__


@pytest.mark.asyncio
async def test_code_puppy_agent_new_session():
    # Create a mock connection
    mock_conn = MagicMock()
    # Instantiate the CodePuppyAgent
    agent = CodePuppyAgent(mock_conn)
    # Create a mock new session request
    new_session_request = NewSessionRequest(cwd="/", mcpServers=[])
    # Call the newSession method
    response = await agent.newSession(new_session_request)
    # Assert that the response has a session ID
    assert response.sessionId is not None
