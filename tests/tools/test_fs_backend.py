"""Reference in-memory FileSystemBackend + contract/coherence tests.

The in-memory backend here is the canonical *reference implementation* of
``code_puppy.tools.io_backends.FileSystemBackend``: it is not the local disk and
not ACP, so it proves the seam stands on its own -- any host that implements the
protocol gets a single coherent filesystem across every file tool.

Two layers of tests:

* **contract** -- each protocol method behaves + raises per the documented
  contract, exercised through the ``fs_access`` facade so the dispatch is real.
* **coherence** -- with the backend installed, metadata / listing / traversal
  agree with content (the property whose absence was the old "split-brain" bug).
"""

from __future__ import annotations

import os
import posixpath
import sys
from typing import Dict, List, Optional

import pytest

from code_puppy.tools import fs_access
from code_puppy.tools.io_backends import (
    DirEntry,
    FileSystemBackend,
    get_filesystem_backend,
    set_filesystem_backend,
)


class InMemoryFileSystemBackend:
    """A dict-backed filesystem. Paths are absolute, POSIX-style keys.

    Directories are implicit (any prefix of a file path). This is deliberately
    tiny -- it exists to demonstrate the contract, not to be efficient.
    """

    def __init__(self, files: Optional[Dict[str, str]] = None) -> None:
        self._files: Dict[str, str] = dict(files or {})

    # --- content ---
    def read_text_file(
        self, path: str, line: Optional[int] = None, limit: Optional[int] = None
    ) -> str:
        if path not in self._files:
            raise FileNotFoundError(path)
        text = self._files[path]
        if line is None or limit is None:
            return text
        rows = text.splitlines(keepends=True)
        return "".join(rows[line - 1 : line - 1 + limit])

    def write_text_file(self, path: str, content: str) -> None:
        self._files[path] = content

    # --- metadata ---
    def exists(self, path: str) -> bool:
        return self.is_file(path) or self.is_dir(path)

    def is_file(self, path: str) -> bool:
        return path in self._files

    def is_dir(self, path: str) -> bool:
        prefix = path.rstrip("/") + "/"
        return any(f.startswith(prefix) for f in self._files)

    def list_dir(self, path: str) -> List[DirEntry]:
        if self.is_file(path):
            raise NotADirectoryError(path)
        prefix = path.rstrip("/") + "/"
        if not self.is_dir(path):
            raise FileNotFoundError(path)
        names_seen = set()
        entries: List[DirEntry] = []
        for f, content in self._files.items():
            if not f.startswith(prefix):
                continue
            rest = f[len(prefix) :]
            head, sep, _tail = rest.partition("/")
            if head in names_seen:
                continue
            names_seen.add(head)
            if sep:  # there was a "/", so head is a subdirectory
                entries.append(DirEntry(name=head, is_dir=True, size=0))
            else:
                entries.append(
                    DirEntry(name=head, is_dir=False, size=len(content.encode()))
                )
        return entries

    # --- mutation ---
    def delete_file(self, path: str) -> None:
        if path not in self._files:
            raise FileNotFoundError(path)
        del self._files[path]

    def make_dirs(self, path: str) -> None:
        # Directories are implicit; nothing to materialize.
        return None


@pytest.fixture
def backend():
    fs = InMemoryFileSystemBackend(
        {
            "/ws/a.py": "print('a')\nx = 1\n",
            "/ws/pkg/b.py": "import os\nNEEDLE = 42\n",
            "/ws/pkg/c.txt": "no match here\n",
        }
    )
    set_filesystem_backend(fs)
    try:
        yield fs
    finally:
        set_filesystem_backend(None)


def test_reference_backend_satisfies_protocol(backend):
    # runtime_checkable structural check + it is actually installed.
    assert isinstance(backend, FileSystemBackend)
    assert get_filesystem_backend() is backend


# --- contract (through the facade) ------------------------------------------
def test_read_whole_and_slice(backend):
    assert fs_access.read_text("/ws/a.py") == "print('a')\nx = 1\n"
    assert fs_access.read_text("/ws/a.py", line=2, limit=1) == "x = 1\n"


def test_metadata(backend):
    assert fs_access.exists("/ws/a.py")
    assert fs_access.is_file("/ws/a.py")
    assert not fs_access.is_dir("/ws/a.py")
    assert fs_access.is_dir("/ws/pkg")
    assert not fs_access.exists("/ws/nope.py")


def test_list_dir_one_level(backend):
    names = {e.name: e.is_dir for e in fs_access.list_dir("/ws")}
    assert names == {"a.py": False, "pkg": True}


def test_missing_read_raises_file_not_found(backend):
    with pytest.raises(FileNotFoundError):
        fs_access.read_text("/ws/ghost.py")


def test_list_dir_errors(backend):
    with pytest.raises(FileNotFoundError):
        fs_access.list_dir("/ws/ghost")
    with pytest.raises(NotADirectoryError):
        fs_access.list_dir("/ws/a.py")


def test_delete_and_make_dirs(backend):
    fs_access.delete_file("/ws/pkg/c.txt")
    assert not fs_access.exists("/ws/pkg/c.txt")
    with pytest.raises(FileNotFoundError):
        fs_access.delete_file("/ws/pkg/c.txt")
    fs_access.make_dirs("/ws/new")  # idempotent no-op for this backend


# --- coherence (the anti-split-brain property) ------------------------------
def test_walk_sees_every_file_no_local_disk(backend):
    found = {full for full, entry in fs_access.walk("/ws") if not entry.is_dir}
    assert found == {"/ws/a.py", "/ws/pkg/b.py", "/ws/pkg/c.txt"}


def test_write_is_immediately_visible_to_metadata_list_and_walk(backend):
    # Write through the backend, then confirm EVERY other operation agrees --
    # this is exactly what split-brain (list local, read host) got wrong.
    backend.write_text_file("/ws/pkg/new.py", "value = 'created'\n")

    assert fs_access.exists("/ws/pkg/new.py")
    assert fs_access.is_file("/ws/pkg/new.py")
    assert "new.py" in {e.name for e in fs_access.list_dir("/ws/pkg")}
    walked = {full for full, e in fs_access.walk("/ws") if not e.is_dir}
    assert "/ws/pkg/new.py" in walked
    assert fs_access.read_text("/ws/pkg/new.py") == "value = 'created'\n"


def test_walk_prune_skips_directory(backend):
    walked = {
        full
        for full, e in fs_access.walk("/ws", skip_dir=lambda p: p.endswith("/pkg"))
        if not e.is_dir
    }
    assert walked == {"/ws/a.py"}  # pkg pruned entirely


def test_paths_are_posix_join(backend):
    # sanity: facade uses os.path.join; on POSIX CI this equals posixpath.
    assert posixpath.join("/ws", "a.py") == "/ws/a.py"


# --- tool-level coherence: the real list_files / grep tools ------------------
def test_list_files_tool_uses_backend(backend):
    """``_list_files`` composes its listing from the backend, not local disk."""
    from code_puppy.tools.file_operations import _list_files

    out = _list_files(None, "/ws", recursive=True)
    assert out.error is None
    # Every backend file shows up; nothing from the real local disk leaks in.
    assert "a.py" in out.content
    assert "b.py" in out.content
    assert "pkg" in out.content
    assert "c.txt" in out.content


def test_grep_tool_searches_backend(backend):
    """``_grep`` searches the backend's files (walk + read), not local ripgrep."""
    from code_puppy.tools.file_operations import _grep

    out = _grep(None, "NEEDLE", "/ws")
    assert out.error is None
    hits = {(m.file_path, m.line_content) for m in out.matches}
    assert ("/ws/pkg/b.py", "NEEDLE = 42") in hits
    # c.txt has no match -> not present
    assert all(m.file_path != "/ws/pkg/c.txt" for m in out.matches)


def test_created_file_is_listable_and_greppable(backend):
    """End-to-end anti-split-brain: write via backend, then the *tools* agree."""
    from code_puppy.tools.file_operations import _grep, _list_files

    backend.write_text_file("/ws/pkg/fresh.py", "MARKER = 'x'\n")

    listing = _list_files(None, "/ws", recursive=True)
    assert "fresh.py" in listing.content

    grep_out = _grep(None, "MARKER", "/ws")
    assert any(m.file_path == "/ws/pkg/fresh.py" for m in grep_out.matches)


# --- backend grep flag-mode parity ------------------------------------------
def test_grep_ignore_case_flag(backend):
    from code_puppy.tools.file_operations import _grep

    # 'needle' lower-case only matches NEEDLE with -i.
    assert _grep(None, "needle", "/ws").matches == []
    hits = _grep(None, "-i needle", "/ws").matches
    assert any(m.file_path == "/ws/pkg/b.py" for m in hits)


def test_grep_fixed_string_flag(backend):
    from code_puppy.tools.file_operations import _grep

    backend.write_text_file("/ws/dots.py", "a=b.c.d\naXbYcZd\n")
    # As regex, 'b.c.d' matches 'aXbYcZd'? No -- but 'b.c.d' regex matches
    # 'b.c.d' literally too. Use -F to force literal: only the real 'b.c.d'.
    literal = _grep(None, "-F b.c.d", "/ws").matches
    assert {m.line_content for m in literal} == {"a=b.c.d"}


def test_grep_word_flag(backend):
    from code_puppy.tools.file_operations import _grep

    backend.write_text_file("/ws/w.py", "cat\ncategory\nscatter\n")
    words = {m.line_content for m in _grep(None, "-w cat", "/ws").matches}
    assert words == {"cat"}


def test_grep_type_filter(backend):
    from code_puppy.tools.file_operations import _grep

    # b.py and c.txt both contain 'no match'? Put a common token in both.
    backend.write_text_file("/ws/pkg/b.py", "import os\nTOKEN = 42\n")
    backend.write_text_file("/ws/pkg/c.txt", "TOKEN in text\n")
    py_only = _grep(None, "--type py TOKEN", "/ws").matches
    assert {m.file_path for m in py_only} == {"/ws/pkg/b.py"}


def test_grep_unsupported_flag_errors_loudly(backend):
    from code_puppy.tools.file_operations import _grep

    out = _grep(None, "-z foo", "/ws")
    assert out.matches == []
    assert out.error is not None and "-z" in out.error


def test_grep_unknown_type_errors(backend):
    from code_puppy.tools.file_operations import _grep

    out = _grep(None, "--type cobol foo", "/ws")
    assert out.matches == []
    assert out.error is not None and "cobol" in out.error


def test_grep_nonexistent_directory_errors(backend):
    """A missing directory reports an error, not zero silent matches.

    Parity with the local ripgrep path (which errors on a bad directory) so a
    typo'd path isn't mistaken for "searched, found nothing".
    """
    from code_puppy.tools.file_operations import _grep

    out = _grep(None, "NEEDLE", "/ws/does_not_exist")
    assert out.matches == []
    assert out.error is not None and "does not exist" in out.error


def test_grep_skips_binary_files(backend):
    from code_puppy.tools.file_operations import _grep

    backend.write_text_file("/ws/bin.dat", "MARK\x00MARK\n")
    out = _grep(None, "MARK", "/ws")
    assert all(m.file_path != "/ws/bin.dat" for m in out.matches)


# --- adversarial: hostile / degenerate backends -----------------------------
class _CyclicBackend:
    """list_dir always returns one subdir -> an infinite chain of distinct paths."""

    def read_text_file(self, p, line=None, limit=None):
        return ""

    def write_text_file(self, p, c):
        pass

    def exists(self, p):
        return True

    def is_file(self, p):
        return False

    def is_dir(self, p):
        return True

    def list_dir(self, p):
        return [DirEntry("sub", True, 0)]

    def delete_file(self, p):
        pass

    def make_dirs(self, p):
        pass


class _DeepBackend(_CyclicBackend):
    def __init__(self, depth):
        self.depth = depth

    def is_dir(self, p):
        return p.count("/") <= self.depth

    def list_dir(self, p):
        return [DirEntry("d", True, 0)] if p.count("/") < self.depth else []


def test_walk_survives_cyclic_backend():
    """A cyclic list_dir must not blow the stack (no OS ELOOP to save us)."""
    from code_puppy.tools import fs_access

    set_filesystem_backend(_CyclicBackend())
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(400)
    try:
        n = sum(1 for _ in fs_access.walk("/r"))
        assert n <= fs_access.MAX_WALK_DEPTH  # capped, not infinite / crashed
    finally:
        sys.setrecursionlimit(old)
        set_filesystem_backend(None)


def test_walk_survives_deep_tree():
    """A legitimately very deep tree must not overflow the recursive stack."""
    from code_puppy.tools import fs_access

    set_filesystem_backend(_DeepBackend(5000))
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(400)
    try:
        n = sum(1 for _ in fs_access.walk("/r"))
        assert n == fs_access.MAX_WALK_DEPTH
    finally:
        sys.setrecursionlimit(old)
        set_filesystem_backend(None)


def test_list_files_degrades_when_backend_raises():
    """A backend raising must become a tool error, never a crash."""
    from code_puppy.tools.file_operations import _list_files

    class _Boom:
        def read_text_file(self, p, line=None, limit=None):
            return ""

        def write_text_file(self, p, c):
            pass

        def exists(self, p):
            return True

        def is_file(self, p):
            return False

        def is_dir(self, p):
            return True

        def list_dir(self, p):
            raise RuntimeError("host exploded")

        def delete_file(self, p):
            pass

        def make_dirs(self, p):
            pass

    set_filesystem_backend(_Boom())
    try:
        out = _list_files(None, "/ws", recursive=False)
        assert out.error is not None and "host exploded" in out.error
    finally:
        set_filesystem_backend(None)


def test_grep_skips_unreadable_file(backend):
    """One file whose read raises must not abort the whole search."""
    from code_puppy.tools.file_operations import _grep

    real_read = backend.read_text_file

    def flaky(path, line=None, limit=None):
        if path == "/ws/pkg/b.py":
            raise RuntimeError("cannot read this one")
        return real_read(path, line, limit)

    backend.read_text_file = flaky
    backend.write_text_file("/ws/ok.py", "FINDME = 1\n")
    out = _grep(None, "FINDME", "/ws")
    assert any(m.file_path == "/ws/ok.py" for m in out.matches)
    assert out.error is None


# --- gap A: the facade's LOCAL (no-backend) branches ------------------------
def test_facade_local_disk_roundtrip(tmp_path):
    """With no backend, the facade operates on real local disk."""
    from code_puppy.tools import fs_access

    assert get_filesystem_backend() is None
    d = tmp_path / "proj"
    fs_access.make_dirs(str(d / "pkg"))
    assert fs_access.is_dir(str(d / "pkg"))
    f = d / "pkg" / "m.py"
    fs_access.write_text(str(f), "l1\nl2\nl3\n")
    assert fs_access.exists(str(f)) and fs_access.is_file(str(f))
    # whole-file + slice reads via the local branch
    assert fs_access.read_text(str(f)) == "l1\nl2\nl3\n"
    assert fs_access.read_text(str(f), line=2, limit=1) == "l2\n"
    names = {e.name for e in fs_access.list_dir(str(d / "pkg"))}
    assert names == {"m.py"}
    fs_access.delete_file(str(f))
    assert not fs_access.exists(str(f))


def test_facade_local_list_dir_errors(tmp_path):
    from code_puppy.tools import fs_access

    with pytest.raises(FileNotFoundError):
        fs_access.list_dir(str(tmp_path / "nope"))
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        fs_access.list_dir(str(f))


def test_facade_local_walk_and_symlink_cycle(tmp_path):
    """Local walk traverses real disk and survives a real symlink cycle."""
    from code_puppy.tools import fs_access

    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.py").write_text("hi\n")
    files = {full for full, e in fs_access.walk(str(tmp_path)) if not e.is_dir}
    assert str(tmp_path / "a" / "f.py") in files
    try:
        os.symlink(str(tmp_path), str(tmp_path / "a" / "loop"))
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    # Must terminate (visited-set on realpath breaks the cycle).
    n = sum(1 for _ in fs_access.walk(str(tmp_path)))
    assert n < 1000


# --- gap B: the ACP adapter's topology methods (pure local os) --------------
def test_acp_backend_topology(tmp_path):
    from code_puppy.plugins.acp.io_delegation import DelegatedFileSystemBackend

    be = DelegatedFileSystemBackend()
    be.make_dirs(str(tmp_path / "sub"))
    assert be.is_dir(str(tmp_path / "sub"))
    f = tmp_path / "sub" / "x.txt"
    f.write_text("data")
    (tmp_path / "sub" / "nested").mkdir()  # a directory entry too
    assert be.exists(str(f)) and be.is_file(str(f)) and not be.is_dir(str(f))
    entries = {e.name: (e.is_dir, e.size) for e in be.list_dir(str(tmp_path / "sub"))}
    assert entries == {"x.txt": (False, 4), "nested": (True, 0)}
    be.delete_file(str(f))
    assert not be.exists(str(f))


def test_acp_backend_list_dir_errors(tmp_path):
    from code_puppy.plugins.acp.io_delegation import DelegatedFileSystemBackend

    be = DelegatedFileSystemBackend()
    with pytest.raises(FileNotFoundError):
        be.list_dir(str(tmp_path / "ghost"))
    f = tmp_path / "f"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        be.list_dir(str(f))


# --- gap C: file-mod tools + undo, WITH a backend installed -----------------
def test_file_mod_tools_hit_backend(backend):
    from code_puppy.tools.file_modifications import (
        _delete_file,
        delete_snippet_from_file,
        replace_in_file,
        write_to_file,
    )

    write_to_file(None, "/ws/pkg/new.py", "V = 1\nKEEP = 2\n", True)
    assert backend.is_file("/ws/pkg/new.py")
    assert backend.read_text_file("/ws/pkg/new.py") == "V = 1\nKEEP = 2\n"
    # write must NOT have touched the real local disk
    assert not os.path.exists("/ws/pkg/new.py")

    replace_in_file(None, "/ws/pkg/new.py", [{"old_str": "V = 1", "new_str": "V = 9"}])
    assert "V = 9" in backend.read_text_file("/ws/pkg/new.py")

    delete_snippet_from_file(None, "/ws/pkg/new.py", "KEEP = 2\n")
    assert "KEEP" not in backend.read_text_file("/ws/pkg/new.py")

    _delete_file(None, "/ws/pkg/c.txt")
    assert not backend.exists("/ws/pkg/c.txt")


def test_undo_is_backend_coherent(backend):
    """Undo must snapshot/restore through the backend, not local disk."""
    from code_puppy.tools.file_modifications import write_to_file
    from code_puppy.undo_manager import UndoManager

    UndoManager()._instance.history.clear()
    write_to_file(None, "/ws/created.py", "NEW = 1\n", True)
    assert backend.is_file("/ws/created.py")
    msg = UndoManager().undo_last()
    # created file -> undo deletes it FROM THE BACKEND
    assert "deleted" in msg
    assert not backend.exists("/ws/created.py")
