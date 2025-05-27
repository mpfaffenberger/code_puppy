import pytest
from code_agent.main import main, interactive_mode
import asyncio
import sys

# Setup test for command arguments
def test_command_args(monkeypatch):
    """Test command argument execution"""
    async def mock_run(*args, **kwargs):
        return UserCodeMock()

    class UserCodeMock:
        output_message = 'Test command executed'
        awaiting_user_input = False

    # Mock the run method
    monkeypatch.setattr("code_agent.agent.code_generation_agent.run", mock_run)
    
    # Capture the output of the main function
    mock_return = UserCodeMock()
    monkeypatch.setattr(main, 'run', lambda x: mock_return)
    monkeypatch.setattr(sys, 'argv', ['main', 'echo', 'Hello'])

    response = asyncio.run(main())
    assert hasattr(response, 'output_message')
    assert "Test command executed" in response.output_message
    assert response.awaiting_user_input == False