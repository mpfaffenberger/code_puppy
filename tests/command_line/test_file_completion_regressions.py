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


@pytest.mark.parametrize(
    "text",
    [
        "don't change @target",
        "it's in @target",
        "can't @",
        "they're @a.py",
        "isn't @~/Documents",
    ],
)
def test_contraction_prose_does_not_hide_active_reference(text):
    # Issue #915: an apostrophe in preceding prose must not open quote state;
    # the later @token still completes.
    token = text[text.rfind("@") :]
    decoded, raw_len = active_reference(text)
    assert decoded == token[1:]
    assert raw_len == len(token) - 1


@pytest.mark.parametrize(
    "text,expected",
    [
        ('he said "hi" @target', "target"),
        ('read @"my file.txt" done', None),
        ("@'unfinished", "unfinished"),
        ('@"my file.txt', "my file.txt"),
    ],
)
def test_quotes_still_group_attachment_tokens(text, expected):
    # Word-boundary quotes keep grouping spaces (filenames with spaces), and
    # a closed quote still ends completion so later prose is not replaced.
    result = active_reference(text)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert result[0] == expected


@pytest.mark.parametrize(
    "text,symbol",
    [
        ('@dir/"my fi', "@"),
        ("@dir/'my fi", "@"),
        ("don't change @dir/\"my fi", "@"),
        ("it's in @dir/'my fi", "@"),
        ('read @@dir/"my fi', "@@"),
    ],
)
def test_partial_path_quotes_preserve_decoded_path_and_raw_length(text, symbol):
    raw = text[text.rfind(symbol) + len(symbol) :]
    assert active_reference(text, symbol) == ("dir/my fi", len(raw))


@pytest.mark.parametrize("quote", ['"', "'"])
def test_closed_partial_path_quotes_end_completion(quote):
    assert active_reference(f"@dir/{quote}my file.txt{quote}") is None
    assert active_reference(f"read @dir/{quote}my file.txt{quote} done") is None


@pytest.mark.parametrize("quote", ['"', "'"])
def test_partial_path_completion_preserves_prose_and_replaces_raw_path(
    quote, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "my file.txt").touch()
    monkeypatch.setattr(fi, "reindex", lambda *a, **kw: None)
    raw = f"dir/{quote}my fi"
    prefix = "don't change @"
    text = prefix + raw
    results = list(FilePathCompleter().get_completions(Document(text, len(text)), None))
    assert len(results) == 1
    result = results[0]
    assert result.start_position == -len(raw)
    assert shlex.split(result.text) == ["dir/my file.txt"]
    inserted = text[: len(text) + result.start_position] + result.text
    assert inserted == prefix + shlex.quote("dir/my file.txt")


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
