from code_agent.tools.file_operations import should_ignore_path, list_files


class FakeContext:
    pass


def test_list_files(tmpdir):
    """Test listing files in a directory"""
    temp_dir = tmpdir.mkdir("test_dir")
    temp_file = temp_dir.join("test_file.py")
    temp_file.write("print('hello world')")

    context = FakeContext()
    results = list_files(context=context, directory=str(temp_dir))

    assert len(results) == 1
    assert results[0]["path"] == "test_file.py"
    assert results[0]["type"] == "file"
    assert results[0]["size"] == len("print('hello world')")


def test_should_ignore_path():
    assert should_ignore_path("temp.py") == False
    assert should_ignore_path("/some/path/__pycache__/") == True
    assert should_ignore_path(".gitignore") == False
    assert should_ignore_path("/another/path/.git/") == True
