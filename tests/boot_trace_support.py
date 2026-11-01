"""Shared fakes and helpers for the boot-trace recorder tests."""

import importlib
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import code_puppy.boot_trace as bt
from code_puppy import _boot_trace_sink as sink_mod

ENV = "CODE_PUPPY_BOOT_TRACE"
HEX32 = re.compile(r"[0-9a-f]{32}")
HASHED = re.compile(r"h:[0-9a-f]{16}")
REPO_ROOT = Path(__file__).resolve().parents[1]
ABS_TARGET = str(REPO_ROOT / "boot-trace.jsonl")
TIMEOUT = 10.0
# Safety ceiling only (cold imports take 10-30 s on loaded hosts); never an assertion.
SUBPROCESS_TIMEOUT_S = 180

# Pinned from the reviewed official plugin list (70 names, one per line).
OFFICIAL = (
    "acp",
    "agent_skills",
    "agent_creator_skill",
    "attachment_references",
    "aws_bedrock",
    "background_agents",
    "azure_foundry",
    "auto_continue",
    "btw",
    "chatgpt_oauth",
    "claude_code_hooks",
    "claude_code_oauth",
    "code_puppy_agent",
    "computer_use",
    "completion_notification",
    "context_indicator",
    "copilot_auth",
    "customizable_commands",
    "dbos_durable_exec",
    "destructive_command_guard",
    "emoji_filter",
    "empty_html_comment_filter",
    "example_custom_command",
    "execution_environment",
    "file_permission_handler",
    "flux_bootstrap",
    "force_push_guard",
    "fork",
    "frontend_emitter",
    "grok_oauth",
    "herdr",
    "hook_creator",
    "hook_manager",
    "jev_grep",
    "logfire_oauth",
    "logfire_sessions",
    "mcp_binding_prompt",
    "meta_oauth",
    "namespace_skill_search",
    "no_tools",
    "obsidian_agent",
    "ollama",
    "ollama_setup",
    "openrouter_oauth",
    "plugin_list",
    "pop_command",
    "profiles",
    "prompt_newline",
    "prune",
    "puppy_kennel",
    "pstack",
    "puppy_spinner",
    "qa_kitten_skill",
    "quick_resume",
    "resume_hint",
    "review_pr",
    "session_namer",
    "setup_cli",
    "spill",
    "stack_dump",
    "statusline",
    "steer_queue",
    "subagent_panel",
    "switch_agent_resume",
    "theme",
    "timestamp_heartbeat",
    "universal_constructor",
    "web_retriever_skill",
    "wiggum",
    "yolo_cli",
)

EXTRA_NAMES = tuple(f"extra_plugin_{i:02d}" for i in range(1, 19))


class FakeSink:
    """Records what the recorder offers; ``created`` is set per test subclass."""

    created: list = []

    def __init__(self, target, *, boot_id, t0_ns):
        self.target, self.boot_id, self.t0_ns = target, boot_id, t0_ns
        self.events, self.drops, self.stops = [], 0, 0
        self._lock = threading.Lock()
        self._span = 0
        type(self).created.append(self)

    def next_span_id(self):
        with self._lock:
            self._span += 1
            return format(self._span, "x")

    def offer(self, event):
        with self._lock:
            self.events.append({"seq": len(self.events) + 1, **event})

    def record_drop(self):
        with self._lock:
            self.drops += 1

    def request_stop(self):
        with self._lock:
            self.stops += 1


class _Clock:
    def __init__(self):
        self.mono = 1_000_000_000
        self.wall = 1_700_000_000_000_000_000


def make_clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(time, "monotonic_ns", lambda: c.mono)
    monkeypatch.setattr(time, "time_ns", lambda: c.wall)
    return c


def traced_loader():
    """Yield a loader that reloads the recorder with a fake sink.

    Teardown reloads with the env var unset so the module is disabled for other tests.
    """

    def load(target=ABS_TARGET, sink_cls=FakeSink):
        cls = type("Fake", (sink_cls,), {"created": []})
        with pytest.MonkeyPatch.context() as mp:
            if target is None:
                mp.delenv(ENV, raising=False)
            else:
                mp.setenv(ENV, target)
            mp.setattr(sink_mod, "Sink", cls)
            importlib.reload(bt)
        return cls.created[-1] if cls.created else None

    yield load
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv(ENV, raising=False)
        importlib.reload(bt)


def _e(sink, seq, **fields):
    return {"v": 1, "bootId": sink.boot_id, "seq": seq, **fields}


def _shape(sink):
    """Events without clock values; clocks are checked by type here."""
    shaped = []
    for event in sink.events:
        assert isinstance(event["tMonoMs"], float) and event["tMonoMs"] >= 0
        assert type(event["tWallMs"]) is int
        shaped.append(
            {k: v for k, v in event.items() if k not in ("tMonoMs", "tWallMs")}
        )
    return shaped


def _run_py(code, value, tmp_path, *args):
    """Run ``code`` in a child with an isolated cwd/HOME and the given trace env value."""
    home, cwd = tmp_path / "home", tmp_path / "cwd"
    cwd.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != ENV}
    env.update({"PYTHONPATH": str(REPO_ROOT), "HOME": str(home)})
    if value is not None:
        env[ENV] = value
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
        check=False,
    )
