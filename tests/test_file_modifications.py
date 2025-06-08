from code_puppy.tools import file_modifications


def test_write_to_file_new(tmp_path):
    path = tmp_path / "a.txt"
    result = file_modifications._write_to_file(
        None, str(path), "hi puppy", overwrite=False
    )
    assert result["success"]
    assert path.exists()
    assert path.read_text() == "hi puppy"


def test_write_to_file_no_overwrite(tmp_path):
    path = tmp_path / "b.txt"
    path.write_text("old")
    result = file_modifications._write_to_file(None, str(path), "new", overwrite=False)
    assert not result["success"]
    assert path.read_text() == "old"


def test_write_to_file_overwrite(tmp_path):
    path = tmp_path / "c.txt"
    path.write_text("old")
    result = file_modifications._write_to_file(None, str(path), "new", overwrite=True)
    assert result["success"]
    assert path.read_text() == "new"


def test_replace_in_file_simple(tmp_path):
    path = tmp_path / "d.txt"
    path.write_text("foo bar baz")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "bar", "new_str": "biscuit"}]
    )
    assert res["success"]
    assert path.read_text() == "foo biscuit baz"


def test_replace_in_file_no_match(tmp_path):
    path = tmp_path / "e.txt"
    path.write_text("abcdefg")
    res = file_modifications._replace_in_file(
        None, str(path), [{"old_str": "xxxyyy", "new_str": "puppy"}]
    )
    assert "error" in res


def test_delete_snippet_success(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("i am a biscuit. delete me! woof woof")
    res = file_modifications._delete_snippet_from_file(None, str(path), "delete me!")
    assert res["success"]
    assert "delete me!" not in path.read_text()


def test_delete_snippet_no_file(tmp_path):
    path = tmp_path / "nope.txt"
    res = file_modifications._delete_snippet_from_file(
        None, str(path), "does not matter"
    )
    assert "error" in res


def test_delete_snippet_not_found(tmp_path):
    path = tmp_path / "g.txt"
    path.write_text("i am loyal.")
    res = file_modifications._delete_snippet_from_file(None, str(path), "NEVER here!")
    assert "error" in res
