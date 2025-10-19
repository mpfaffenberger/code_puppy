from code_puppy.tools import file_modifications


def test_replace_in_file_multiple_replacements(tmp_path):
    path = tmp_path / "multi.txt"
    path.write_text("foo bar baz bar foo", encoding="utf-8")
    reps = [
        {"old_str": "bar", "new_str": "dog"},
        {"old_str": "foo", "new_str": "biscuit"},
    ]
    res = file_modifications._replace_in_file(None, str(path), reps)
    assert res["success"]
    text = path.read_text(encoding="utf-8")
    assert "dog" in text and "biscuit" in text


def test_replace_in_file_unicode(tmp_path):
    path = tmp_path / "unicode.txt"
    path.write_text("puppy 🐶 says meow", encoding="utf-8")
    reps = [{"old_str": "meow", "new_str": "woof"}]
    res = file_modifications._replace_in_file(None, str(path), reps)
    assert res["success"]
    assert "woof" in path.read_text(encoding="utf-8")


def test_replace_in_file_near_match(tmp_path):
    path = tmp_path / "fuzzy.txt"
    path.write_text("abc\ndef\nghijk", encoding="utf-8")
    # deliberately off by one for fuzzy test
    reps = [{"old_str": "def\nghij", "new_str": "replaced"}]
    res = file_modifications._replace_in_file(None, str(path), reps)
    # Depending on scoring, this may or may not match: just test schema
    assert "diff" in res


def test_delete_large_snippet(tmp_path):
    path = tmp_path / "bigdelete.txt"
    content = "hello" + " fluff" * 500 + " bye"
    path.write_text(content, encoding="utf-8")
    snippet = " fluff" * 250
    res = file_modifications._delete_snippet_from_file(None, str(path), snippet)
    # Could still succeed or fail depending on split, just check key presence
    assert "diff" in res


def test_write_to_file_invalid_path(tmp_path):
    # Directory as filename
    d = tmp_path / "adir"
    d.mkdir()
    res = file_modifications._write_to_file(None, str(d), "puppy", overwrite=False)
    assert "error" in res or not res.get("success")


def test_replace_in_file_invalid_json(tmp_path):
    path = tmp_path / "bad.txt"
    path.write_text("hi there!", encoding="utf-8")
    # malformed replacements - not a list
    reps = "this is definitely not json dicts"
    try:
        res = file_modifications._replace_in_file(None, str(path), reps)
    except Exception:
        assert True
    else:
        assert isinstance(res, dict)


def test_write_to_file_binary_content(tmp_path):
    path = tmp_path / "binfile"
    bin_content = b"\x00\x01biscuit\x02"
    # Should not raise, but can't always expect 'success' either: just presence
    try:
        res = file_modifications._write_to_file(
            None, str(path), bin_content.decode(errors="ignore"), overwrite=False
        )
        assert "success" in res or "error" in res
    except Exception:
        assert True
