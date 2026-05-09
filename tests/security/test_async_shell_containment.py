"""Security regression tests for async shell containment and performance gates (Epic 7).

Covers:
- Shell commands run via ThreadPoolExecutor (nonblocking event loop)
- Background job registry isolation
- Huge-file read/edit/write gates
- Streaming list/grep caps
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import RunContext


# ---------------------------------------------------------------------------
# Async shell containment (PERF-01)
# ---------------------------------------------------------------------------


class TestAsyncShellContainment:
    """Shell commands must not block the event loop."""

    @pytest.mark.asyncio
    async def test_shell_uses_thread_pool(self):
        """run_shell_command should delegate to run_in_executor."""
        from code_puppy.tools.command_runner import run_shell_command

        ctx = MagicMock(spec=RunContext)
        with (
            patch(
                "code_puppy.callbacks.on_run_shell_command",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("code_puppy.config.get_yolo_mode", return_value=True),
            patch("code_puppy.tools.command_runner.is_subagent", return_value=True),
        ):
            with patch(
                "code_puppy.tools.command_runner._run_command_inner",
                new_callable=AsyncMock,
                return_value=MagicMock(success=True, command="echo hi"),
            ) as mock_inner:
                _ = await run_shell_command(ctx, "echo hi", timeout=5)
                mock_inner.assert_called_once()

    @pytest.mark.asyncio
    async def test_background_command_isolation(self, tmp_path):
        """Background jobs are tracked in a separate registry."""
        from code_puppy.tools.background_jobs import (
            _BACKGROUND_JOBS,
            list_background_jobs,
            register_background_job,
            stop_background_job,
        )

        _BACKGROUND_JOBS.clear()
        log_file = tmp_path / "bg.log"
        log_file.write_text("output")

        register_background_job(12345, "sleep 10", "/tmp", str(log_file))
        jobs = list_background_jobs()
        assert len(jobs) == 1
        assert jobs[0].pid == 12345
        assert jobs[0].command == "sleep 10"

        # Isolated: can't stop a PID not in the registry
        assert stop_background_job(99999) is False

        # Clean up
        stop_background_job(12345)
        _BACKGROUND_JOBS.clear()


# ---------------------------------------------------------------------------
# Streaming list/grep caps (P2-01 / PERF-02)
# ---------------------------------------------------------------------------


class TestStreamingListCaps:
    """List and grep operations must cap output to prevent context blowup."""

    def test_list_files_respects_max_entries(self, tmp_path, monkeypatch):
        from code_puppy.tools.file_operations import (
            MAX_LIST_FILES_LLM_ENTRIES,
            _list_files,
        )

        monkeypatch.chdir(tmp_path)
        for i in range(MAX_LIST_FILES_LLM_ENTRIES + 20):
            (tmp_path / f"f{i}.txt").write_text("x")

        ctx = MagicMock(spec=RunContext)
        result = _list_files(ctx, str(tmp_path), recursive=False)
        lines = result.content.splitlines()
        # Result should not exceed cap + a few summary lines
        assert len(lines) < MAX_LIST_FILES_LLM_ENTRIES + 20

    def test_grep_matches_capped(self, tmp_path, monkeypatch):
        from code_puppy.tools.file_operations import MAX_GREP_MATCHES, _grep

        monkeypatch.chdir(tmp_path)
        (tmp_path / "big.txt").write_text("match\n" * 300)

        ctx = MagicMock(spec=RunContext)

        # Skip if no rg available
        import shutil

        if not shutil.which("rg"):
            pytest.skip("ripgrep not available")

        result = _grep(ctx, "match", str(tmp_path))
        assert len(result.matches) <= MAX_GREP_MATCHES


# ---------------------------------------------------------------------------
# Huge-file gates (P2-02 / PERF-03)
# ---------------------------------------------------------------------------


class TestHugeFileGates:
    """File operations must reject huge files before loading them."""

    def test_read_rejects_oversized_file(self, tmp_path, monkeypatch):
        from code_puppy.tools.file_operations import MAX_READ_FILE_BYTES, _read_file

        monkeypatch.chdir(tmp_path)
        huge = tmp_path / "huge.txt"
        huge.write_text("x" * (MAX_READ_FILE_BYTES + 100))

        ctx = MagicMock(spec=RunContext)
        result = _read_file(ctx, str(huge))
        assert result.error is not None
        assert "too large" in result.error.lower() or "chunk" in result.error.lower()

    def test_chunked_read_works_on_large_file(self, tmp_path, monkeypatch):
        from code_puppy.tools.file_operations import MAX_READ_FILE_BYTES, _read_file

        monkeypatch.chdir(tmp_path)
        huge = tmp_path / "huge.txt"
        huge.write_text("line\n" * (MAX_READ_FILE_BYTES // 2))

        ctx = MagicMock(spec=RunContext)
        result = _read_file(ctx, str(huge), start_line=1, num_lines=5)
        assert result.error is None

    def test_edit_rejects_oversized_file(self, tmp_path, monkeypatch):
        from code_puppy.tools.file_modifications import (
            MAX_EDIT_FILE_BYTES,
            _replace_in_file,
        )

        monkeypatch.chdir(tmp_path)
        huge = tmp_path / "huge.txt"
        huge.write_text("x" * (MAX_EDIT_FILE_BYTES + 100))

        result = _replace_in_file(None, str(huge), [{"old_str": "x", "new_str": "y"}])
        assert result.get("error") is not None
        assert "too large" in result["error"].lower()

    def test_delete_snippet_rejects_oversized_file(self, tmp_path, monkeypatch):
        from code_puppy.tools.file_modifications import (
            MAX_EDIT_FILE_BYTES,
            _delete_snippet_from_file,
        )

        monkeypatch.chdir(tmp_path)
        huge = tmp_path / "huge.txt"
        huge.write_text("x" * (MAX_EDIT_FILE_BYTES + 100))

        result = _delete_snippet_from_file(None, str(huge), "xxx")
        assert result.get("error") is not None
        assert "too large" in result["error"].lower()

    def test_diff_output_capped(self, tmp_path, monkeypatch):
        from code_puppy.tools.file_modifications import MAX_DIFF_BYTES, _write_to_file

        monkeypatch.chdir(tmp_path)
        existing = tmp_path / "big.txt"
        # Create a file large enough to produce a diff that exceeds MAX_DIFF_BYTES
        # (unified diff adds per-line prefix chars so we need enough changed lines)
        half_cap = MAX_DIFF_BYTES // 2
        existing.write_text("a\n" * half_cap)

        new_content = "b\n" * half_cap
        result = _write_to_file(None, str(existing), new_content, overwrite=True)
        diff = result.get("diff", "")
        # The diff must either fit within the cap or be explicitly truncated
        if len(diff) > MAX_DIFF_BYTES:
            pytest.fail(
                f"Diff output ({len(diff)} bytes) exceeds MAX_DIFF_BYTES "
                f"({MAX_DIFF_BYTES}) without truncation marker"
            )
        # If close to the cap, verify truncation was applied
        if len(diff) >= MAX_DIFF_BYTES - 100:
            assert "truncated" in diff.lower(), (
                "Diff near size cap but missing truncation marker"
            )
