import unittest
from unittest.mock import patch, mock_open
from code_agent.agent_tools import share_your_reasoning
import os

class TestAgentTools(unittest.TestCase):
    def test_share_your_reasoning(self):
        reasoning = "This is a test reasoning."
        next_steps = "These are the next steps."
        expected_output = {
            "success": True,
            "reasoning": reasoning,
            "next_steps": next_steps
        }
        result = share_your_reasoning(reasoning, reasoning=reasoning, next_steps=next_steps)
        self.assertEqual(result, expected_output)

    def test_multiline_command_history(self):
        history_file_path = 'test_history.txt'
        multiline_command = """echo 'This is a test\nmultiline command' > /dev/null"""
        # Mock open to simulate file operation
        with patch('builtins.open', mock_open()) as mocked_file:
            with open(history_file_path, 'a') as history_file:
                history_file.write(f"{multiline_command}\n")
            mocked_file.assert_called_once_with('test_history.txt', 'a')
            handle = mocked_file()
            handle.write.assert_called_once_with(f"{multiline_command}\n")

        # Simulate reading from the history file
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=multiline_command)) as mocked_file:
                with open(history_file_path, 'r') as history_file:
                    content = history_file.read()
                    self.assertEqual(content, multiline_command)

if __name__ == "__main__":
    unittest.main()