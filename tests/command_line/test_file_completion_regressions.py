"""Regression coverage for the @file audit."""

import os
import shlex
import shutil
import threading

import pytest
from termflow.tui.completion import Document

from code_puppy.command_line import file_index as fi
from code_puppy.command_line.file_path_completion import FilePathCompleter
from code_puppy.file_completion_io import read_paths
from code_puppy.file_completion_tokens import active_reference


@pytest.mark.parametrize(
    "text", ["user@example", "read @a.py explain", "@a.py ", '@"a b"']
)
def test_not_an_active_reference(text):
    assert active_reference(text) is None


@pytest.mark.parametrize("raw", ['@"space fi', "@'space fi", r"@space\ fi"])
def test_quoted_completion_replaces_entire_raw_path(raw, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fi, "reindex", lambda *a, **kw: None)
    monkeypatch.setattr(
        fi, "get_index", lambda: fi._make_index(str(tmp_path), ["space file.py"])
    )
    result = list(FilePathCompleter().get_completions(Document(raw, len(raw)), None))[0]
    inserted = raw[: len(raw) + result.start_position] + result.text
    assert shlex.split(inserted) == ["@space file.py"]


def test_wrong_root_never_used(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fi, "reindex", lambda *a, **kw: None)
    monkeypatch.setattr(fi, "get_index", lambda: fi._make_index("/old", ["target.py"]))
    assert list(FilePathCompleter().get_completions(Document("@target", 7), None)) == []


def test_tilde_and_literal_glob_characters(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(fi, "reindex", lambda *a, **kw: None)
    (tmp_path / "Documents").mkdir()
    (tmp_path / "[literal].py").touch()
    for query, expected in [("@~/Doc", "~/Documents"), ("@~/[", "~/[literal].py")]:
        results = list(
            FilePathCompleter().get_completions(Document(query, len(query)), None)
        )
        assert shlex.split(results[0].text) == [expected]


def test_root_switch_during_build_is_queued_and_duplicates_coalesced(
    monkeypatch, tmp_path
):
    entered, release = threading.Event(), threading.Event()
    calls = []
    first, second = str(tmp_path / "one"), str(tmp_path / "two")

    def build(root):
        calls.append(root)
        if root == first:
            entered.set()
            assert release.wait(5)
        return [root + ".py"]

    monkeypatch.setattr(fi, "_run_ripgrep", build)
    index = fi.FileIndex()
    index.reindex(first)
    assert entered.wait(5)
    for _ in range(20):
        index.reindex(first)
    index.reindex(second)
    thread = index._build_thread
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert calls == [first, second]
    assert index.current.root == second


def test_refresh_and_failure_backoff(monkeypatch, tmp_path):
    calls = []
    clock = [10.0]
    monkeypatch.setattr(fi.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fi, "_run_ripgrep", lambda root: calls.append(root))
    index = fi.FileIndex()
    index.reindex(str(tmp_path), blocking=True)
    for _ in range(10):
        index.reindex(str(tmp_path))
    assert len(calls) == 1
    clock[0] += 6
    monkeypatch.setattr(fi, "_run_ripgrep", lambda root: ["new/nested.py"])
    index.reindex(str(tmp_path))
    with index._lock:
        thread = index._build_thread
    if thread:
        thread.join(5)
    assert index.current.paths == ("new/nested.py",)


def test_rg_null_records_ignore_rules_and_path_cap(tmp_path):
    rg = shutil.which("rg")
    if not rg:
        pytest.skip("ripgrep unavailable")
    (tmp_path / ".ignore").write_text("ignored\n")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "x").touch()
    (tmp_path / "a\nb.py").touch()
    (tmp_path / "normal.py").touch()
    result = read_paths(rg, str(tmp_path), 100, 5)
    assert "a\nb.py" in result
    assert not any("ignored" in p for p in result)
    assert len(read_paths(rg, str(tmp_path), 1, 5)) == 1


def test_top_results_are_bounded_and_ranked(monkeypatch, tmp_path):
    from code_puppy.command_line.file_path_completion import _fuzzy_completions

    monkeypatch.chdir(tmp_path)
    paths = [f"src/{i}/target.py" for i in range(1000)] + ["target"]
    snapshot = fi._make_index(os.getcwd(), paths)
    monkeypatch.setattr(fi, "get_index", lambda: snapshot)
    monkeypatch.setattr(fi, "reindex", lambda *a, **kw: None)
    results = _fuzzy_completions("target", -6)
    assert len(results) == 20
    assert results[0].text == "target"


def test_byte_cap_and_timeout(monkeypatch, tmp_path):
    import sys
    from code_puppy import file_completion_io as io

    if os.name == "nt":
        pytest.skip("executable-script fixture is POSIX only")
    fake = tmp_path / "fake-rg"
    fake.write_text(
        f"#!{sys.executable}\nimport os, time\nos.write(1, b'valid\\0' + b'x'*10000)\ntime.sleep(10)\n"
    )
    fake.chmod(0o700)
    monkeypatch.setattr(io, "MAX_OUTPUT_BYTES", 100)
    assert io.read_paths(str(fake), str(tmp_path), 100, 3) == ["valid"]
    monkeypatch.setattr(io, "MAX_OUTPUT_BYTES", 100000)
    assert io.read_paths(str(fake), str(tmp_path), 100, 0.1) is None
