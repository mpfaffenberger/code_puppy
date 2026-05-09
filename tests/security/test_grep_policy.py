"""Tests for grep option injection fix and path policy (Epic 3 / P1-01)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import RunContext


def test_grep_search_string_cannot_inject_flags(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import _grep

    monkeypatch.chdir(tmp_path)
    # Create a file that contains a real word
    (tmp_path / "foo.txt").write_text("hello world\n")

    ctx = MagicMock(spec=RunContext)

    # Try to inject a flag via search_string
    with patch("shutil.which", return_value="rg"):
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdout = []
            mock_proc.poll.return_value = 0
            mock_popen.return_value = mock_proc
            _grep(ctx, "-h", str(tmp_path))

    # The command should include '--' before the pattern
    called_args = mock_popen.call_args[0][0]
    assert "--" in called_args
    # The pattern should be the literal string '-h', not parsed as a flag
    dash_h_index = called_args.index("-h")
    dash_index = called_args.index("--")
    assert dash_h_index > dash_index


def test_grep_pattern_starting_dash_is_data(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import _grep

    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.txt").write_text("-help\n")
    ctx = MagicMock(spec=RunContext)

    with patch("shutil.which", return_value="rg"):
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdout = []
            mock_proc.poll.return_value = 0
            mock_popen.return_value = mock_proc
            _grep(ctx, "-help", str(tmp_path))

    called_args = mock_popen.call_args[0][0]
    assert "--" in called_args
    assert "-help" in called_args


def test_grep_uses_double_dash_before_pattern(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import _grep

    monkeypatch.chdir(tmp_path)
    (tmp_path / "bar.txt").write_text("test\n")
    ctx = MagicMock(spec=RunContext)

    with patch("shutil.which", return_value="rg"):
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdout = []
            mock_proc.poll.return_value = 0
            mock_popen.return_value = mock_proc
            _grep(ctx, "pattern", str(tmp_path))

    called_args = mock_popen.call_args[0][0]
    assert "--" in called_args


def test_grep_stops_after_match_cap(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import MAX_GREP_MATCHES, _grep

    monkeypatch.chdir(tmp_path)
    # Create a file with many matches
    (tmp_path / "many.txt").write_text("match\n" * 200)
    ctx = MagicMock(spec=RunContext)

    # Use real rg if available, otherwise skip
    rg = Path("/usr/bin/rg")
    if not rg.exists():
        rg = Path("/bin/rg")
    if not rg.exists():
        pytest.skip("ripgrep not available")

    result = _grep(ctx, "match", str(tmp_path))
    assert len(result.matches) <= MAX_GREP_MATCHES


def test_grep_denies_sensitive_directory_without_approval(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import _grep

    monkeypatch.chdir(tmp_path)
    ctx = MagicMock(spec=RunContext)

    result = _grep(ctx, "secret", str(tmp_path / ".ssh"))
    assert result.error is not None
    assert "sensitive" in result.error.lower() or "policy" in result.error.lower()


def test_grep_temp_ignore_file_deleted_in_finally(tmp_path, monkeypatch):
    from code_puppy.tools.file_operations import _grep

    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.txt").write_text("hello\n")
    ctx = MagicMock(spec=RunContext)

    with patch("shutil.which", return_value="rg"):
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.stdout = []
            mock_proc.poll.return_value = 0
            mock_popen.return_value = mock_proc
            _grep(ctx, "hello", str(tmp_path))

    # Verify no leftover ignore files in tmp_path
    leftovers = list(tmp_path.glob("*.ignore"))
    assert not leftovers
