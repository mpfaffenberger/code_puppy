import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from acp.schema import InitializeRequest, NewSessionRequest, PromptRequest, SessionNotification
from acp import helpers
from code_puppy import __version__
from code_puppy.acp_server import CodePuppyAgent, acp_main


@pytest.mark.asyncio
async def test_code_puppy_agent_prompt():
    # Mock the agent loading functions
    with patch("code_puppy.acp_server.load_agent") as mock_load_agent, patch("code_puppy.acp_server.get_current_agent_name"):
        # Configure the mock agent that will be loaded
        mock_internal_agent = MagicMock()
        mock_internal_agent.run_with_mcp = AsyncMock(return_value=MagicMock(output="Test response"))
        mock_load_agent.return_value = mock_internal_agent

        # Mock the connection
        mock_conn = MagicMock()
        mock_conn.sessionUpdate = AsyncMock()

        # Instantiate the main ACP agent
        acp_agent = CodePuppyAgent(mock_conn)

        # 1. Create a new session
        new_session_request = NewSessionRequest(cwd="/", mcpServers=[])
        session_response = await acp_agent.newSession(new_session_request)
        session_id = session_response.sessionId

        # 2. Send a prompt to that session
        prompt_request = PromptRequest(
            sessionId=session_id,
            prompt=[helpers.text_block("Hello, world!")],
        )
        prompt_response = await acp_agent.prompt(prompt_request)

        # Assert that the correct agent's run_with_mcp was called
        mock_internal_agent.run_with_mcp.assert_called_once_with("Hello, world!")

        # Assert that sessionUpdate was called with the correct response
        mock_conn.sessionUpdate.assert_called_once()
        sent_notification = mock_conn.sessionUpdate.call_args[0][0]
        assert isinstance(sent_notification, SessionNotification)
        assert sent_notification.sessionId == session_id
        sent_update = sent_notification.update
        assert sent_update.sessionUpdate == "agent_message_chunk"
        assert sent_update.content.type == "text"
        assert sent_update.content.text == "Test response"

        # Assert that the prompt response has the correct stop reason
        assert prompt_response.stopReason == "end_turn"


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
    with patch("code_puppy.acp_server.load_agent") as mock_load_agent, patch("code_puppy.acp_server.get_current_agent_name"):
        # Configure the mock agent
        mock_internal_agent = MagicMock()
        mock_load_agent.return_value = mock_internal_agent

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
        # Assert that a new agent was created and stored
        assert response.sessionId in agent._sessions
        assert agent._sessions[response.sessionId] == mock_internal_agent
