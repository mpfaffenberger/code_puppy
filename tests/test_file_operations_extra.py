from code_agent.tools.file_operations import list_files
import os
from unittest.mock import patch
import pytest

def test_list_files_default_dir():
    # Should not error when the current directory exists
    with patch('os.path.exists', return_value=True), \
         patch('os.path.isdir', return_value=True), \
         patch('os.walk', return_value=[('.', [], ['foo.py', 'bar.md'])]), \
         patch('code_agent.tools.file_operations.should_ignore_path', return_value=False), \
         patch('os.path.getsize', return_value=32):
        results = list_files(None)
        assert any(f for f in results if f['path'].endswith('.py'))

def test_list_files_hidden_and_ignored():
    # It should skip ignored files
    with patch('os.path.exists', return_value=True), \
         patch('os.path.isdir', return_value=True), \
         patch('os.walk', return_value=[('.', [], ['__pycache__', 'ok.pyc', 'baz.txt', 'good.py'])]), \
         patch('code_agent.tools.file_operations.should_ignore_path', side_effect=lambda x: x.endswith('.pyc') or x=='__pycache__'), \
         patch('os.path.getsize', return_value=4):
        results = list_files(None)
        assert all(not f['path'].endswith('.pyc') for f in results)

# Tree/summary printout edge cases not covered by mocks (as they're console side-effects)
# We'll make sure some format/size helpers behave fine:
def test_list_files_large_file():
    hugefile = 'huge.iso'
    with patch('os.path.exists', return_value=True), \
         patch('os.path.isdir', return_value=True), \
         patch('os.walk', return_value=[('.', [], [hugefile])]), \
         patch('code_agent.tools.file_operations.should_ignore_path', return_value=False), \
         patch('os.path.getsize', return_value=10**9 + 4096):
        results = list_files(None)
        # No crash and large file entry present
        assert any(f for f in results if f['path'] == hugefile)
