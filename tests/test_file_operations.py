import os
from unittest.mock import patch
from code_agent.tools.file_operations import list_files, create_file, read_file

def test_create_file():
    test_file = "test_create.txt"
    with patch('os.path.exists') as mock_exists, patch('os.makedirs') as mock_makedirs, patch('builtins.open', new_callable=lambda *args, **kwargs: open(os.devnull, 'w')) as mock_file:
        mock_exists.return_value = False
        result = create_file(None, test_file, "content")
        assert result["success"]
        assert result["path"].endswith(test_file)

def test_read_file():
    test_file = "test_read.txt"
    with patch('os.path.exists') as mock_exists, patch('os.path.isfile') as mock_isfile, patch('builtins.open', new_callable=lambda *args, **kwargs: open(os.devnull, 'r')) as mock_file:
        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_file.return_value.read.return_value = "line1\nline2\nline3"
        result = read_file(None, test_file)
        assert "content" in result

def test_list_files():
    with patch('os.path.abspath') as mock_abspath, patch('os.path.exists') as mock_exists, patch('os.path.isdir') as mock_isdir, patch('os.walk') as mock_walk:
        mock_abspath.return_value = '/test'
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_walk.return_value = [('/test', ('dir',), ('file.txt',))]
        result = list_files(None, directory="/test", recursive=True)
        assert len(result) > 0
import os
from unittest.mock import patch, mock_open
from code_agent.tools.file_operations import list_files, create_file, read_file

def test_create_file():
    test_file = "test_create.txt"
    with patch('os.path.exists') as mock_exists, \
         patch('os.makedirs') as mock_makedirs, \
         patch('builtins.open', mock_open()) as mock_file:
        mock_exists.return_value = False
        result = create_file(None, test_file, "content")
        assert "success" in result
        assert result["path"].endswith(test_file)

def test_read_file():
    test_file = "test_read.txt"
    mock_file_content = "line1\nline2\nline3"
    with patch('os.path.exists') as mock_exists, \
         patch('os.path.isfile') as mock_isfile, \
         patch('builtins.open', mock_open(read_data=mock_file_content)) as mock_file:
        mock_exists.return_value = True
        mock_isfile.return_value = True
        result = read_file(None, test_file)
        assert "content" in result

def test_list_files():
    with patch('os.path.abspath') as mock_abspath, \
         patch('os.path.exists') as mock_exists, \
         patch('os.path.isdir') as mock_isdir, \
         patch('os.walk') as mock_walk:
        mock_abspath.return_value = '/test'
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_walk.return_value = [('/test', ['dir'], ['file.txt'])]
        result = list_files(None, directory="/test", recursive=True)
        assert len(result) > 0
def test_list_files():
    with patch('os.path.abspath') as mock_abspath, \
         patch('os.path.exists') as mock_exists, \
         patch('os.path.isdir') as mock_isdir, \
         patch('os.walk') as mock_walk, \
         patch('os.path.getsize') as mock_getsize:
        mock_abspath.return_value = '/test'
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_walk.return_value = [('/test', ['dir'], ['file.txt'])]
        mock_getsize.return_value = 123
        result = list_files(None, directory="/test", recursive=True)
        assert len(result) > 0