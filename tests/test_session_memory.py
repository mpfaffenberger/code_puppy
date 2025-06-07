import tempfile
from pathlib import Path
from code_puppy.session_memory import SessionMemory


def test_log_and_get_history():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = SessionMemory(storage_path=Path(tmpdir) / "test_mem.json", memory_limit=5)
        mem.clear()
        mem.log_task("foo")
        mem.log_task("bar", extras={"extra": "baz"})
        hist = mem.get_history()
        assert len(hist) == 2
        assert hist[-1]["description"] == "bar"
        assert hist[-1]["extra"] == "baz"


def test_history_limit():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = SessionMemory(
            storage_path=Path(tmpdir) / "test_mem2.json", memory_limit=3
        )
        for i in range(10):
            mem.log_task(f"task {i}")
        hist = mem.get_history()
        assert len(hist) == 3
        assert hist[0]["description"] == "task 7"
        assert hist[-1]["description"] == "task 9"


def test_preference():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = SessionMemory(storage_path=Path(tmpdir) / "prefs.json")
        mem.set_preference("theme", "dark-puppy")
        assert mem.get_preference("theme") == "dark-puppy"
        assert mem.get_preference("nonexistent", "zzz") == "zzz"


def test_watched_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = SessionMemory(storage_path=Path(tmpdir) / "watched.json")
        mem.add_watched_file("/foo/bar.py")
        mem.add_watched_file("/foo/bar.py")  # no dupes
        mem.add_watched_file("/magic/baz.py")
        assert set(mem.list_watched_files()) == {"/foo/bar.py", "/magic/baz.py"}


def test_clear():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = SessionMemory(storage_path=Path(tmpdir) / "wipe.json")
        mem.log_task("something")
        mem.set_preference("a", 1)
        mem.add_watched_file("x")
        mem.clear()
        assert mem.get_history() == []
        assert mem.get_preference("a") is None
        assert mem.list_watched_files() == []
