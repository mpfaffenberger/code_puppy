from pathlib import Path

import pytest

from code_puppy.plugins.tree_sessions.tree import SessionTree


def test_append_reload_and_history_round_trip(tmp_path: Path):
    path = tmp_path / "session.jsonl"
    tree = SessionTree(path)
    first = tree.append({"role": "user", "text": "hello"})
    second = tree.append({"role": "assistant", "text": "hi"})

    reloaded = SessionTree(path)

    assert reloaded.active_leaf == second.id
    assert reloaded.history() == [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "hi"},
    ]
    assert reloaded.path_entries()[0].id == first.id


def test_branch_preserves_both_children(tmp_path: Path):
    tree = SessionTree(tmp_path / "session.jsonl")
    root = tree.append("root")
    abandoned = tree.append("approach-a")
    tree.branch(root.id)
    chosen = tree.append("approach-b")

    assert tree.history() == ["root", "approach-b"]
    assert tree.children[root.id] == [abandoned.id, chosen.id]
    assert "├─" in tree.render()


def test_sync_history_branches_at_common_prefix(tmp_path: Path):
    tree = SessionTree(tmp_path / "session.jsonl")
    tree.sync_history(["one", "two", "three"])
    old_leaf = tree.active_leaf

    tree.sync_history(["one", "replacement"])

    assert tree.history() == ["one", "replacement"]
    assert old_leaf in tree.entries


def test_labels_are_append_only_and_reload(tmp_path: Path):
    path = tmp_path / "session.jsonl"
    tree = SessionTree(path)
    entry = tree.append("checkpoint")
    tree.set_label(entry.id, "before refactor")

    assert SessionTree(path).labels[entry.id] == "before refactor"


def test_fork_extracts_only_selected_path(tmp_path: Path):
    tree = SessionTree(tmp_path / "source.jsonl")
    root = tree.append("root")
    selected = tree.append("selected")
    tree.append("later")

    forked = tree.fork_to(tmp_path / "fork.jsonl", selected.id)

    assert forked.history() == ["root", "selected"]
    assert len(forked.entries) == 2
    assert root.id not in forked.entries


def test_dangling_branch_is_rejected(tmp_path: Path):
    tree = SessionTree(tmp_path / "session.jsonl")
    with pytest.raises(KeyError):
        tree.branch("missing")


def test_malformed_trailing_record_is_ignored(tmp_path: Path):
    path = tmp_path / "session.jsonl"
    tree = SessionTree(path)
    tree.append("valid")
    with path.open("a", encoding="utf-8") as stream:
        stream.write("{partial")

    assert SessionTree(path).history() == ["valid"]
