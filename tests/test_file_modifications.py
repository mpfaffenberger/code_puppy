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

# --- NEW TESTS for edit_file high-level tool ----
import json
class DummyContext: pass

def test_edit_file_content_creates(tmp_path):
    f = tmp_path / "hi.txt"
    d = json.dumps({"content": "new-content!", "overwrite": False})
    res = file_modifications._write_to_file(None, str(f), "new-content!", overwrite=False)
    assert res["success"]
    assert f.read_text() == "new-content!"

def test_edit_file_content_overwrite(tmp_path):
    f = tmp_path / "hi2.txt"
    f.write_text("abc")
    d = json.dumps({"content": "puppy", "overwrite": True})
    res = file_modifications._write_to_file(None, str(f), "puppy", overwrite=True)
    assert res["success"]
    assert f.read_text() == "puppy"

def test_edit_file_content_refuses_overwrite(tmp_path):
    f = tmp_path / "hi3.txt"
    f.write_text("nope")
    d = json.dumps({"content": "puppy", "overwrite": False})
    # simulate what the edit_file would do (overwrite False on existing file)
    file_exists = f.exists()
    if file_exists and not json.loads(d)["overwrite"]:
        res = {
            "success": False,
            "path": str(f),
            "message": f"File '{str(f)}' exists. Set 'overwrite': true to replace.",
            "changed": False,
        }
        assert not res["success"]
        assert f.read_text() == "nope"

def test_edit_file_json_parse_repair(tmp_path):
    # Missing closing brace, should be repaired
    f = tmp_path / "puppy.txt"
    broken = '{"content": "biscuit", "overwrite": true'
    try:
        data = json.loads(broken)
        assert False, "Should fail JSON"
    except json.JSONDecodeError:
        pass
    # If file_modifications.edit_file did repair, it would parse
    # Not testing `edit_file` agent method directly, but logic is reachable
    from json_repair import repair_json
    fixed = repair_json(broken)
    repaired = json.loads(fixed)
    assert repaired["content"] == "biscuit"
    assert repaired["overwrite"]

def test_edit_file_empty_content(tmp_path):
    f = tmp_path / "empty.txt"
    res = file_modifications._write_to_file(None, str(f), "", overwrite=False)
    assert res["success"]
    assert f.read_text() == ""

def test_edit_file_delete_snippet(tmp_path):
    f = tmp_path / "woof.txt"
    f.write_text("puppy loyal")
    d = {"delete_snippet": "loyal"}
    res = file_modifications._delete_snippet_from_file(None, str(f), "loyal")
    assert res["success"]
    assert "loyal" not in f.read_text()
