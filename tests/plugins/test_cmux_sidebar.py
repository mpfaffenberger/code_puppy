"""Tests for the builtin ``cmux_sidebar`` plugin.

Exercise gating, command construction, arg-summary extraction, context
buckets, file tracking, and the streaming narration -- all without a real
cmux instance (the ``cmux`` CLI is mocked).
"""

from __future__ import annotations

import importlib

import pytest

import code_puppy.plugins.cmux_sidebar.register_callbacks as rc


@pytest.fixture()
def mod(monkeypatch):
    """Reload the plugin module fresh with a clean in_cmux cache each test."""
    importlib.reload(rc)
    rc.in_cmux.cache_clear()
    return rc


def _capture(mod, monkeypatch):
    calls: list = []
    monkeypatch.setattr(mod.subprocess, "Popen", lambda args, **k: calls.append(list(args)))
    return calls


def test_no_op_outside_cmux(mod, monkeypatch):
    monkeypatch.delenv("CMUX_WORKSPACE_ID", raising=False)
    mod.in_cmux.cache_clear()
    assert mod.in_cmux() is False
    calls = _capture(mod, monkeypatch)
    mod._status("k", "v", "sparkle", "#fff")
    mod._log("nope")
    assert calls == []


def test_disabled_env_wins(mod, monkeypatch):
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "ws")
    monkeypatch.setenv("CMUX_SIDEBAR_DISABLED", "1")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/cmux")
    mod.in_cmux.cache_clear()
    assert mod.in_cmux() is False


def test_runs_inside_cmux(mod, monkeypatch):
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "ws-123")
    monkeypatch.delenv("CMUX_SIDEBAR_DISABLED", raising=False)
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/cmux")
    mod.in_cmux.cache_clear()
    assert mod.in_cmux() is True
    calls = _capture(mod, monkeypatch)
    mod._progress(0.5, label="half")
    assert calls and calls[0][0] == "cmux"
    assert "set-progress" in calls[0] and "0.50" in calls[0]


def test_progress_clamped(mod, monkeypatch):
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "ws")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/cmux")
    mod.in_cmux.cache_clear()
    calls = _capture(mod, monkeypatch)
    mod._progress(5.0)
    assert "1.00" in calls[0]


def test_arg_summary_basename(mod):
    assert mod._arg_summary("edit_file", {"file_path": "/a/b/c/foo.py"}) == "foo.py"
    assert mod._arg_summary("run_shell_command", {"command": "ls -la"}) == "ls -la"
    assert mod._arg_summary("grep", {"search_string": "needle"}) == "needle"
    assert mod._arg_summary("read_file", {}) == ""


def test_arg_summary_truncates(mod):
    out = mod._arg_summary("run_shell_command", {"command": "x" * 200})
    assert len(out) <= 44 and out.endswith("\u2026")


def test_ctx_color_buckets(mod):
    assert mod._ctx_color(10) == mod.CTX_GREEN
    assert mod._ctx_color(50) == mod.CTX_YELLOW
    assert mod._ctx_color(90) == mod.CTX_RED


def test_human_tokens(mod):
    assert mod._human_tokens(500) == "500"
    assert mod._human_tokens(1500) == "1.5k"


def test_breakdown_and_counts(mod):
    mod._cats.clear()
    mod._cats.update({"read": 2, "edit": 1, "shell": 1})
    assert mod._fmt_breakdown() == "2 read \u00b7 1 edit \u00b7 1 shell"


def test_category_counting(mod, monkeypatch):
    monkeypatch.delenv("CMUX_WORKSPACE_ID", raising=False)
    mod.in_cmux.cache_clear()
    mod._on_agent_run_start("B", "m")
    mod._on_pre_tool_call("read_file", {"file_path": "a.py"})
    mod._on_pre_tool_call("grep", {"search_string": "x"})
    mod._on_pre_tool_call("edit_file", {"file_path": "a.py"})
    mod._on_pre_tool_call("weird_unknown_tool", {})
    assert mod._cats == {"read": 1, "search": 1, "edit": 1, "other": 1}


def test_files_touched(mod, monkeypatch):
    monkeypatch.delenv("CMUX_WORKSPACE_ID", raising=False)
    mod.in_cmux.cache_clear()
    mod._on_agent_run_start("B", "m")
    mod._on_pre_tool_call("read_file", {"file_path": "/x/read_only.py"})
    mod._on_pre_tool_call("create_file", {"file_path": "/x/a.py"})
    mod._on_pre_tool_call("edit_file", {"file_path": "/x/b.py"})
    mod._on_pre_tool_call("edit_file", {"file_path": "/x/b.py"})
    mod._on_pre_tool_call("delete_file", {"file_path": "/x/c.py"})
    assert mod._files == ["a.py", "b.py", "c.py"]
    assert mod._fmt_files() == "a.py, b.py, c.py"


def test_files_overflow(mod):
    mod._files.clear()
    mod._files.extend(["a", "b", "c", "d", "e", "f"])
    assert mod._fmt_files(limit=4) == "a, b, c, d (+2 more)"


def test_task_handler_returns_none(mod, monkeypatch):
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "ws")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/cmux")
    mod.in_cmux.cache_clear()
    calls = _capture(mod, monkeypatch)
    assert mod._on_user_prompt_submit("build me a thing") is None
    assert any("set-status" in c and mod.KEY_TASK in c for c in calls)


def test_stream_text_extract(mod):
    class P:
        content = "hello world"

    class D:
        content_delta = " more"

    assert mod._stream_text("part_start", {"part": P()}) == "hello world"
    assert mod._stream_text("part_delta", {"delta": D()}) == " more"
    assert mod._stream_text("other", {"x": 1}) == ""
    assert mod._stream_text("part_start", "not-a-dict") == ""


def test_narration_pill_throttled(mod, monkeypatch):
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "ws")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/cmux")
    mod.in_cmux.cache_clear()
    mod._say["buf"] = ""
    mod._say["last_push"] = 0.0
    mod._say["last_text"] = ""
    calls = _capture(mod, monkeypatch)

    class D:
        content_delta = "analyzing the codebase now"

    mod._on_stream_event("part_delta", {"delta": D()})
    assert any("set-status" in c and mod.KEY_SAY in c for c in calls)
    calls.clear()
    mod._on_stream_event("part_delta", {"delta": D()})
    assert not any(mod.KEY_SAY in c for c in calls)


def test_register_survives_unsupported_phase(mod, monkeypatch):
    # If a build rejects one phase, the rest must still register.
    registered = []

    def fake_register(phase, fn):
        if phase == "stream_event":
            raise ValueError("Unsupported phase: stream_event")
        registered.append(phase)

    monkeypatch.setattr(rc, "register_callback", fake_register)
    mod._REGISTERED = False
    mod.register()  # must not raise
    assert "startup" in registered
    assert "agent_run_end" in registered
    assert "stream_event" not in registered


def test_handlers_never_raise(mod, monkeypatch):
    monkeypatch.delenv("CMUX_WORKSPACE_ID", raising=False)
    mod.in_cmux.cache_clear()
    mod._on_startup()
    mod._on_user_prompt_submit("do the thing")
    mod._on_agent_run_start("B", "some-model")
    mod._on_stream_event("part_delta", {"delta": object()})
    mod._on_pre_tool_call("edit_file", {"file_path": "/x/y.py"})
    mod._on_post_tool_call("edit_file", {}, None, 12.0)
    mod._on_agent_run_end("B", "some-model", success=True)
    mod._on_agent_run_cancel("group-1")
    mod._on_shutdown()
