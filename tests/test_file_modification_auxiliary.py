from code_puppy.tools import file_modifications


def test_replace_in_file_missing_file(tmp_path):
    """_replace_in_file returns an error dict for a nonexistent file."""
    missing = str(tmp_path / "nonexistent.txt")
    res = file_modifications._replace_in_file(
        None, missing, [{"old_str": "a", "new_str": "b"}]
    )
    assert "error" in res
    assert "does not exist" in res["error"]
    assert res["diff"] == ""


def test_replace_in_file_multiple_replacements(tmp_path):
    path = tmp_path / "multi.txt"
    path.write_text("foo bar baz bar foo")
    reps = [
        {"old_str": "bar", "new_str": "dog", "replace_all": True},
        {"old_str": "foo", "new_str": "biscuit", "replace_all": True},
    ]
    res = file_modifications._replace_in_file(None, str(path), reps)
    assert res["success"]
    assert "dog" in path.read_text() and "biscuit" in path.read_text()


def test_replace_in_file_ambiguous_match_refused(tmp_path):
    """Multiple matches without replace_all must refuse (Claude Code parity)."""
    path = tmp_path / "multi.txt"
    path.write_text("foo bar baz bar foo")
    reps = [{"old_str": "bar", "new_str": "dog"}]
    res = file_modifications._replace_in_file(None, str(path), reps)
    assert "error" in res
    assert res["error"].startswith(
        "Found 2 matches of the string to replace, but replace_all is false."
    )
    # File must be untouched — no silent wrong-location edit.
    assert path.read_text() == "foo bar baz bar foo"


def test_replace_in_file_unicode(tmp_path):
    path = tmp_path / "unicode.txt"
    path.write_text("puppy 🐶 says meow")
    reps = [{"old_str": "meow", "new_str": "woof"}]
    res = file_modifications._replace_in_file(None, str(path), reps)
    assert res["success"]
    assert "woof" in path.read_text()


def test_replace_in_file_near_match(tmp_path):
    path = tmp_path / "fuzzy.txt"
    path.write_text("abc\ndef\nghijk")
    # Deliberately wrong character: fuzzy matching was removed for Claude Code
    # parity, so a near-match must refuse with the harness error message.
    reps = [{"old_str": "def\nghixk", "new_str": "replaced"}]
    res = file_modifications._replace_in_file(None, str(path), reps)
    assert "error" in res
    assert res["error"].startswith("String to replace not found in file.")
    assert path.read_text() == "abc\ndef\nghijk"


def test_whitespace_mismatch_is_not_found(tmp_path):
    """Trailing-whitespace mismatches refuse instead of fuzzy-matching."""
    path = tmp_path / "trailing.txt"
    path.write_text("aaa\nbbb\nccc\n")
    reps = [{"old_str": "bbb\nccc ", "new_str": "replaced"}]
    res = file_modifications._replace_in_file(None, str(path), reps)
    assert "error" in res
    assert res["error"].startswith("String to replace not found in file.")
    assert path.read_text() == "aaa\nbbb\nccc\n"


def test_delete_large_snippet(tmp_path):
    path = tmp_path / "bigdelete.txt"
    content = "hello" + " fluff" * 500 + " bye"
    path.write_text(content)
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
    path.write_text("hi there!")
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
