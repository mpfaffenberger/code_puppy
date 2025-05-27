from unittest.mock import patch, mock_open, MagicMock
from code_puppy.tools.file_operations import read_file, create_file
from code_puppy.tools.command_runner import run_shell_command
from code_puppy.tools.file_modifications import modify_file


def test_read_file_nonexistent():
    with patch('os.path.exists', return_value=False):
        result = read_file({}, 'fake_path')
        assert 'error' in result
        assert "does not exist" in result['error']


def test_create_file_already_exists():
    with patch('os.path.exists', return_value=True):
        result = create_file({}, 'existing_file.txt')
        assert 'error' in result
        assert "already exists" in result['error']


def test_modify_file_no_change():
    with patch('os.path.isfile', return_value=True), \
         patch('builtins.open', mock_open(read_data='same content')):
        result = modify_file({}, 'file.txt', 'same content', 'same content')


def test_run_shell_command_success():
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ('output', '')
    mock_proc.returncode = 0

    with patch('subprocess.Popen', return_value=mock_proc):
        result = run_shell_command({}, 'echo Hello')
        assert result
        assert result['success']
        assert "output" in result['stdout']
