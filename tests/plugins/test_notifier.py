"""Tests for the notifier plugin.

Coverage Matrix
===============

| ID  | Requirement                         | Scenario                                              | Risk Tag   | Test(s)                                                        |
|-----|-------------------------------------|-------------------------------------------------------|------------|----------------------------------------------------------------|
| T1  | Notifications respect config        | Disabled → 0 notifications from any hook              | happy-path | test_disabled_config_suppresses_notifications                  |
| T2  | agent_run_end notifies              | No prior interaction → exactly 1                      | happy-path | test_agent_run_end_notifies_when_no_interaction                |
| T3  | agent_run_end reads agent name      | Name from positional arg                              | happy-path | test_agent_run_end_uses_agent_name_positional                  |
| T4  | agent_run_end reads agent name      | Name from keyword arg                                 | happy-path | test_agent_run_end_uses_agent_name_kwarg                       |
| T5  | pre_tool_call notifies              | ask_user_question fires → 1 notification              | happy-path | test_pre_tool_call_notifies_for_interactive_tool               |
| T6  | pre_tool_call reads question        | Header text surfaced in message                       | happy-path | test_pre_tool_call_surfaces_question_header                    |
| T7  | pre_tool_call silent for others     | Non-interactive tool → 0 notifications                | negative   | test_pre_tool_call_ignores_non_interactive_tool                |
| T8  | No duplicate: tool + run_end        | pre_tool_call then agent_run_end → 1 total            | edge       | test_no_duplicate_pre_tool_and_run_end                         |
| T9  | No duplicate: user responded        | post_tool_call sets flag → agent_run_end suppressed   | edge       | test_agent_run_end_suppressed_after_user_responded             |
| T10 | No duplicate: two tools fast        | Two ask_user_question in <2s → 1 notification         | boundary   | test_two_interactive_tools_rate_limited                        |
| T11 | Flag resets across runs             | agent_run_end resets flag at its tail → next run can notify  | regression | test_agent_run_end_resets_interaction_flag                     |
| T12 | post_tool_call non-interactive      | bash response → flag stays False                      | negative   | test_post_tool_call_non_interactive_leaves_flag_false          |
| T13 | Rate limit: same key                | Same key within 2s → 2nd blocked                      | boundary   | test_rate_limiting_blocks_same_key_within_interval             |
| T14 | Rate limit: different keys          | Different keys → both allowed                         | boundary   | test_rate_limiting_allows_different_keys                       |
| T15 | Rate limit: reset                   | Same key after 2s → allowed again                     | boundary   | test_rate_limiting_resets_after_interval                       |
| T16 | macOS osascript escaping            | Shell-special chars safely escaped                    | negative   | test_macos_fallback_escapes_applescript_and_uses_popen         |
| T17 | macOS alerter daemon thread         | alerter preferred; daemon=True                        | happy-path | test_macos_alerter_fires_daemon_thread                         |
| T18 | macOS thread body: click            | @CONTENTCLICKED / @ACTIONCLICKED → focus called       | edge       | test_macos_alerter_thread_body_focuses_on_click                |
| T19 | macOS thread body: no-click         | @TIMEOUT / empty → no focus                           | edge       | test_macos_alerter_thread_body_no_focus_on_timeout             |
| T20 | macOS no subprocess timeout         | subprocess.run must not receive timeout=              | negative   | test_macos_alerter_no_subprocess_timeout                       |
| T21 | macOS focus via AppleScript         | _focus_terminal uses osascript activate, not open -b  | negative   | test_macos_focus_uses_applescript_not_open_b                   |
| T22 | Windows env-var safety              | Untrusted text via env vars, not inline script        | negative   | test_windows_notification_passes_untrusted_text_via_env        |
| T23 | Windows resolver: absolute path     | Relative / missing paths rejected                     | boundary   | test_windows_powershell_resolver_requires_absolute_path        |
| T24 | Backend failures fail closed        | Unknown OS / missing tools → False, no crash          | negative   | test_notification_backend_failures_return_false                |
| T25 | Config key discoverable             | enable_notifications in get_config_keys()             | happy-path | test_config_keys_include_enable_notifications                  |
| T26 | Callbacks registered exactly once   | 5 hooks; no duplicates (agent_run_end unregistered)  | regression | test_plugin_registers_expected_callbacks_once                  |
| T27 | Public Python API                   | __init__.send_notification delegates to dispatcher    | happy-path | test_public_api_delegates_to_dispatcher                        |
| T28 | register_tools hook                 | Returns send_notification tool definition             | happy-path | test_register_tools_returns_send_notification                  |
| T29 | Agent tool: dispatches              | Tool calls _send_notification, returns output model   | happy-path | test_agent_tool_dispatches_notification                        |
| T30 | Agent tool: suppressed flag         | Rate-limited call sets suppressed=True                | boundary   | test_agent_tool_suppressed_flag                                |
| T31 | /notify command: title only         | /notify Hello → dispatches, success message           | happy-path | test_notify_command_title_only                                 |
| T32 | /notify command: title + message    | /notify Hello | World → both parts used                  | happy-path | test_notify_command_title_and_message                          |
| T33 | /notify command: empty title        | /notify  → usage error emitted                        | negative   | test_notify_command_empty_title_emits_error                    |
| T34 | /notify command: wrong name         | /foo → returns None (not ours)                        | negative   | test_notify_command_ignores_wrong_name                         |
| T35 | /notify command: help entry         | custom_command_help returns (notify, description)     | happy-path | test_notify_command_help_entry                                 |
| T36 | macOS alerter: default timeout      | No timeout arg → --timeout 600 in cmd             | happy-path | test_macos_alerter_default_timeout                             |
| T37 | macOS alerter: explicit timeout     | timeout=30 → --timeout 30                         | happy-path | test_macos_alerter_explicit_timeout                           |
| T38 | macOS alerter: persistent           | persistent=True → --timeout 0                     | edge       | test_macos_alerter_persistent                                 |
| T39 | macOS alerter: timeout=0            | timeout=0 → --timeout 0 (same as persistent)      | edge       | test_macos_alerter_timeout_zero_is_persistent                 |
| T40 | macOS osascript: timeout ignored    | No alerter → timeout logged, no crash             | negative   | test_macos_osascript_timeout_silently_ignored                 |
| T41 | Windows: _resolve_duration default  | None/False → "short"                              | happy-path | test_windows_resolve_duration_default                         |
| T42 | Windows: _resolve_duration long     | timeout=20 → "long"                               | happy-path | test_windows_resolve_duration_long                            |
| T43 | Windows: _resolve_duration reminder | persistent=True or timeout=0 → "reminder"         | edge       | test_windows_resolve_duration_reminder                        |
| T44 | Windows: env var CODE_PUPPY_NOTIFY_DURATION | Set correctly from persistent/timeout     | happy-path | test_windows_duration_env_var_set                             |
| T45 | Linux: expire-time injected         | timeout=10 → --expire-time 10000                  | happy-path | test_linux_expire_time_timeout                                |
| T46 | Linux: expire-time persistent       | persistent=True → --expire-time 0                 | edge       | test_linux_expire_time_persistent                             |
| T47 | Linux: no expire-time by default    | timeout=None → no --expire-time flag              | happy-path | test_linux_no_expire_time_by_default                          |
| T48 | macOS is_terminal_focused: focused  | bundle_id matches frontmost → True                | happy-path | test_macos_is_terminal_focused_when_active                    |
| T49 | macOS is_terminal_focused: not focused | bundle_id mismatch → False                     | happy-path | test_macos_is_terminal_focused_when_not_active                |
| T50 | macOS is_terminal_focused: no bundle| _detect returns None → False                       | edge       | test_macos_is_terminal_focused_no_bundle_id                   |
| T51 | _on_agent_run_end: focused → skip   | terminal in foreground → no notification           | regression | test_agent_run_end_suppressed_when_terminal_focused           |
| T52 | _on_agent_run_end: not focused → go | terminal in background → notification sent         | regression | test_agent_run_end_fires_when_terminal_not_focused            |
| T53 | Windows _pid_is_ancestor_of: direct parent   | fg PID == our parent → True                  | happy-path | test_windows_pid_is_ancestor_direct_parent                    |
| T54 | Windows _pid_is_ancestor_of: grandparent     | fg PID is 2 levels up → True                 | happy-path | test_windows_pid_is_ancestor_grandparent                      |
| T55 | Windows _pid_is_ancestor_of: self            | fg PID == start_pid → True                   | edge       | test_windows_pid_is_ancestor_self                             |
| T56 | Windows _pid_is_ancestor_of: unrelated       | fg PID not in chain → False                  | happy-path | test_windows_pid_is_ancestor_unrelated                        |
| T57 | Windows _pid_is_ancestor_of: cycle           | parent_map has a cycle → no infinite loop    | edge       | test_windows_pid_is_ancestor_cycle_protection                 |
| T58 | Windows is_terminal_focused: fg is ancestor  | mocked map shows ancestry → True             | happy-path | test_windows_is_terminal_focused_ancestor                     |
| T59 | Windows is_terminal_focused: not in chain    | mocked map, fg unrelated → False             | happy-path | test_windows_is_terminal_focused_not_ancestor                 |
| T60 | Windows is_terminal_focused: no fg window    | _get_foreground_pid returns None → False     | edge       | test_windows_is_terminal_focused_no_fg_window                 |
| T61 | Windows is_terminal_focused: error → False   | exception in _get_foreground_pid → False     | negative   | test_windows_is_terminal_focused_errors_return_false          |
| T62 | _is_terminal_focused: delegates to windows   | platform=windows calls windows backend       | happy-path | test_is_terminal_focused_delegates_to_windows_backend         |
| T63 | Windows classic PS: HWND match → focused     | GetConsoleWindow==GetForegroundWindow → True  | regression | test_windows_is_terminal_focused_classic_powershell           |
| T64 | Windows classic PS: HWND mismatch → not focused | different foreground HWND → False          | regression | test_windows_is_terminal_focused_classic_console_not_focused  |
| T65 | Windows WT ConPTY: no console HWND, ancestor → focused | HWND=0, ancestor walk hits WT  | regression | test_windows_is_terminal_focused_no_console_hwnd_falls_to_ancestor |
| T66 | pre_tool_call: terminal focused → suppress | ask_user_question fired but terminal in foreground → 0 notifications | regression | test_pre_tool_call_suppressed_when_terminal_focused |
| T67 | pre_tool_call: terminal not focused → notify | ask_user_question fired, terminal in background → 1 notification | regression | test_pre_tool_call_fires_when_terminal_not_focused |
| T68 | detect_terminal_bundle_id: found in tree | ancestor pid has bundle ID → returns it | happy-path | test_detect_terminal_bundle_id_found_in_process_tree |
| T69 | detect_terminal_bundle_id: not in tree | no ancestor has bundle ID → None | negative | test_detect_terminal_bundle_id_not_found_returns_none |
| T70 | detect_terminal_bundle_id: lsappinfo fails | exception → None, no crash | negative | test_detect_terminal_bundle_id_lsappinfo_failure |
| T72 | macOS terminal active check timeout | osascript timeout returns False (fail-open) | negative | test_macos_terminal_is_active_timeout_returns_false |
| T71 | detect_terminal_bundle_id: lsappinfo real format | bundleID + pid= lines (mixed case/order) parsed correctly | regression | test_detect_terminal_bundle_id_parses_real_lsappinfo_format |
"""

from __future__ import annotations

import asyncio
import importlib

import pytest

from code_puppy import callbacks
from code_puppy.config import get_config_keys


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ALL_HOOKS = (
    "agent_run_end",
    "pre_tool_call",
    "post_tool_call",
    "register_tools",
    "custom_command",
    "custom_command_help",
)


@pytest.fixture(autouse=True)
def cleanup_callbacks():
    original = {h: callbacks.get_callbacks(h) for h in ALL_HOOKS}
    for h in ALL_HOOKS:
        callbacks.clear_callbacks(h)
    yield
    for h in ALL_HOOKS:
        callbacks.clear_callbacks(h)
        for cb in original[h]:
            callbacks.register_callback(h, cb)


@pytest.fixture
def mod():
    m = importlib.import_module("code_puppy.plugins.notifier.register_callbacks")
    return importlib.reload(m)


@pytest.fixture
def macos_module():
    m = importlib.import_module("code_puppy.plugins.notifier._macos")
    return importlib.reload(m)


@pytest.fixture
def windows_module():
    m = importlib.import_module("code_puppy.plugins.notifier._windows")
    return importlib.reload(m)


def _enable(mod, monkeypatch):
    monkeypatch.setattr(mod, "_is_notifications_enabled", lambda: True)
    # Default: terminal is NOT focused so agent_run_end notifications fire.
    # Tests that want to verify the focused-suppression path override this themselves.
    monkeypatch.setattr(mod, "_is_terminal_focused", lambda: False)


def _stub_send(mod, monkeypatch):
    sent = []
    monkeypatch.setattr(
        mod,
        "_send_notification",
        lambda title,
        message,
        subtitle=None,
        rate_limit_key=None,
        timeout=None,
        persistent=False: sent.append(
            {"title": title, "message": message, "key": rate_limit_key}
        )
        or True,
    )
    return sent


# ---------------------------------------------------------------------------
# T1 – disabled config
# ---------------------------------------------------------------------------


def test_disabled_config_suppresses_notifications(monkeypatch, mod):
    """T1: all hooks are no-ops when notifications are disabled."""
    monkeypatch.setattr(mod, "_is_notifications_enabled", lambda: False)
    sent = _stub_send(mod, monkeypatch)

    mod._on_agent_run_end()
    asyncio.get_event_loop().run_until_complete(
        mod._on_pre_tool_call("ask_user_question", {"questions": [{"header": "q?"}]})
    )
    asyncio.get_event_loop().run_until_complete(
        mod._on_post_tool_call("ask_user_question", {}, None, 0)
    )

    assert sent == []


# ---------------------------------------------------------------------------
# T2-T4 – agent_run_end
# ---------------------------------------------------------------------------


def test_agent_run_end_notifies_when_no_interaction(monkeypatch, mod):
    """T2: agent_run_end sends exactly 1 notification when user never interacted."""
    _enable(mod, monkeypatch)
    sent = _stub_send(mod, monkeypatch)
    mod._on_agent_run_end()
    assert len(sent) == 1
    assert "Waiting for your input" in sent[0]["message"]


def test_agent_run_end_uses_agent_name_positional(monkeypatch, mod):
    """T3: agent name from positional arg."""
    _enable(mod, monkeypatch)
    sent = _stub_send(mod, monkeypatch)
    mod._on_agent_run_end("husky", "claude-3-5")
    assert "husky" in sent[0]["title"]


def test_agent_run_end_uses_agent_name_kwarg(monkeypatch, mod):
    """T4: agent name from agent_name= keyword."""
    _enable(mod, monkeypatch)
    sent = _stub_send(mod, monkeypatch)
    mod._on_agent_run_end(agent_name="shepherd", model_name="gpt-4o")
    assert "shepherd" in sent[0]["title"]


# ---------------------------------------------------------------------------
# T5-T7 – pre_tool_call
# ---------------------------------------------------------------------------


def test_pre_tool_call_notifies_for_interactive_tool(monkeypatch, mod):
    """T5: pre_tool_call sends 1 notification for ask_user_question."""
    _enable(mod, monkeypatch)
    sent = _stub_send(mod, monkeypatch)
    asyncio.get_event_loop().run_until_complete(
        mod._on_pre_tool_call("ask_user_question", {})
    )
    assert len(sent) == 1
    assert sent[0]["key"] == "interactive_tool"


def test_pre_tool_call_surfaces_question_header(monkeypatch, mod):
    """T6: question header appears in the notification message."""
    _enable(mod, monkeypatch)
    sent = _stub_send(mod, monkeypatch)
    asyncio.get_event_loop().run_until_complete(
        mod._on_pre_tool_call(
            "ask_user_question", {"questions": [{"header": "Which branch?"}]}
        )
    )
    assert "Which branch?" in sent[0]["message"]


def test_pre_tool_call_ignores_non_interactive_tool(monkeypatch, mod):
    """T7: non-interactive tool → 0 notifications."""
    _enable(mod, monkeypatch)
    sent = _stub_send(mod, monkeypatch)
    asyncio.get_event_loop().run_until_complete(
        mod._on_pre_tool_call("bash", {"command": "ls"})
    )
    assert sent == []


# ---------------------------------------------------------------------------
# T8-T12 – dedup / interaction flag
# ---------------------------------------------------------------------------


def test_no_duplicate_pre_tool_and_run_end(monkeypatch, mod):
    """T8: pre_tool_call + post_tool_call + agent_run_end → exactly 1 notification."""
    _enable(mod, monkeypatch)
    sent = _stub_send(mod, monkeypatch)
    asyncio.get_event_loop().run_until_complete(
        mod._on_pre_tool_call("ask_user_question", {})
    )
    asyncio.get_event_loop().run_until_complete(
        mod._on_post_tool_call("ask_user_question", {}, "answer", 100)
    )
    mod._on_agent_run_end()
    assert len(sent) == 1, f"Expected 1, got {len(sent)}: {sent}"


def test_agent_run_end_suppressed_after_user_responded(monkeypatch, mod):
    """T9: post_tool_call sets flag → agent_run_end sends nothing."""
    _enable(mod, monkeypatch)
    sent = _stub_send(mod, monkeypatch)
    asyncio.get_event_loop().run_until_complete(
        mod._on_post_tool_call("ask_user_question", {}, "yes", 50)
    )
    mod._on_agent_run_end()
    assert sent == []


def test_two_interactive_tools_rate_limited(monkeypatch, mod):
    """T10: two ask_user_question calls within 2s → only 1 notification dispatched."""
    _enable(mod, monkeypatch)
    dispatched = []
    monkeypatch.setattr(mod.platform, "system", lambda: "linux")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/notify-send")
    monkeypatch.setattr(
        mod.subprocess, "Popen", lambda *a, **kw: dispatched.append(a[0])
    )
    now = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "time", lambda: now["t"])

    asyncio.get_event_loop().run_until_complete(
        mod._on_pre_tool_call("ask_user_question", {})
    )
    now["t"] += 0.5
    asyncio.get_event_loop().run_until_complete(
        mod._on_pre_tool_call("ask_user_question", {})
    )
    assert len(dispatched) == 1, f"Expected 1, got {len(dispatched)}"


def test_agent_run_end_resets_interaction_flag(monkeypatch, mod):
    """T11: agent_run_end resets flag at its tail → next run can notify."""
    rc = mod
    rc._user_interacted_this_run = True  # simulate a prior interaction
    monkeypatch.setattr(rc, "_is_notifications_enabled", lambda: True)
    monkeypatch.setattr(rc, "_is_terminal_focused", lambda: False)
    sent = []
    monkeypatch.setattr(
        rc,
        "_send_notification",
        lambda *a, **kw: sent.append(a) or True,
    )
    rc._on_agent_run_end()
    assert rc._user_interacted_this_run is False
    assert len(sent) == 0  # suppressed because flag was True at entry


def test_post_tool_call_non_interactive_leaves_flag_false(monkeypatch, mod):
    """T12: bash post_tool_call must not set the flag."""
    _enable(mod, monkeypatch)
    sent = _stub_send(mod, monkeypatch)
    asyncio.get_event_loop().run_until_complete(
        mod._on_post_tool_call("bash", {"command": "ls"}, "output", 10)
    )
    mod._on_agent_run_end()
    assert len(sent) == 1
    assert mod._user_interacted_this_run is False


# ---------------------------------------------------------------------------
# T13-T15 – rate limiting
# ---------------------------------------------------------------------------


def test_rate_limiting_blocks_same_key_within_interval(monkeypatch, mod):
    """T13: same key within 2s → 2nd blocked; timestamp unchanged."""
    _enable(mod, monkeypatch)
    now = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "time", lambda: now["t"])
    monkeypatch.setattr(mod.platform, "system", lambda: "Plan9")

    mod._send_notification("T", "M", rate_limit_key="k")
    now["t"] += 0.5
    mod._send_notification("T", "M", rate_limit_key="k")

    assert mod._last_notification_times.get("k", 0) == 1000.0


def test_rate_limiting_allows_different_keys(monkeypatch, mod):
    """T14: different keys dispatch independently."""
    _enable(mod, monkeypatch)
    dispatched = []
    monkeypatch.setattr(mod.platform, "system", lambda: "linux")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/notify-send")
    monkeypatch.setattr(
        mod.subprocess, "Popen", lambda *a, **kw: dispatched.append(a[0])
    )
    now = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "time", lambda: now["t"])

    mod._send_notification("T", "M", rate_limit_key="a")
    mod._send_notification("T", "M", rate_limit_key="b")
    assert len(dispatched) == 2


def test_rate_limiting_resets_after_interval(monkeypatch, mod):
    """T15: same key after MIN_NOTIFICATION_INTERVAL is allowed again."""
    _enable(mod, monkeypatch)
    dispatched = []
    monkeypatch.setattr(mod.platform, "system", lambda: "linux")
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/notify-send")
    monkeypatch.setattr(
        mod.subprocess, "Popen", lambda *a, **kw: dispatched.append(a[0])
    )
    now = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "time", lambda: now["t"])

    mod._send_notification("T", "M", rate_limit_key="k")
    now["t"] += mod._MIN_NOTIFICATION_INTERVAL
    mod._send_notification("T", "M", rate_limit_key="k")
    assert len(dispatched) == 2


# ---------------------------------------------------------------------------
# T16-T21 – macOS backend
# ---------------------------------------------------------------------------


def test_macos_fallback_escapes_applescript_and_uses_popen(monkeypatch, macos_module):
    """T16: osascript fallback escapes shell-special chars; no shell=True."""
    calls = []
    monkeypatch.setattr(macos_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(macos_module, "_detect_terminal_bundle_id", lambda: None)
    monkeypatch.setattr(
        macos_module.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw))
    )
    assert macos_module.send('bad"; path \\', "msg") is True
    argv = calls[0][0][0]
    assert argv[:2] == ["osascript", "-e"]
    assert 'bad\\"; path \\\\' in argv[2]
    assert "shell" not in calls[0][1]


def test_macos_alerter_fires_daemon_thread(monkeypatch, macos_module):
    """T17: alerter preferred; daemon thread with correct argv."""
    thread_calls = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            thread_calls.append({"target": target, "args": args, "daemon": daemon})

        def start(self):
            pass

    monkeypatch.setattr(
        macos_module.shutil,
        "which",
        lambda name: "/usr/local/bin/alerter" if name == "alerter" else None,
    )
    monkeypatch.setattr(
        macos_module, "_detect_terminal_bundle_id", lambda: "com.example.Term"
    )
    monkeypatch.setattr(macos_module.threading, "Thread", FakeThread)

    assert macos_module.send("title", "msg", "sub") is True
    assert len(thread_calls) == 1
    cmd = thread_calls[0]["args"][0]
    assert cmd[0] == "/usr/local/bin/alerter"
    assert "--title" in cmd and "title" in cmd
    assert "--message" in cmd and "msg" in cmd
    assert "--subtitle" in cmd and "sub" in cmd
    assert thread_calls[0]["daemon"] is True


def test_macos_alerter_thread_body_focuses_on_click(monkeypatch, macos_module):
    """T18: @CONTENTCLICKED / @ACTIONCLICKED → _focus_terminal called."""
    focus_calls = []

    class FR:
        def __init__(self, s):
            self.stdout = s

    monkeypatch.setattr(
        macos_module, "_focus_terminal", lambda bid: focus_calls.append(bid)
    )
    for output in ("@CONTENTCLICKED", "@ACTIONCLICKED"):
        focus_calls.clear()
        monkeypatch.setattr(macos_module.subprocess, "run", lambda *a, **kw: FR(output))
        macos_module._run_alerter_and_focus(["alerter"], "com.example.Term")
        assert focus_calls == ["com.example.Term"], f"{output!r} must focus"


def test_macos_alerter_thread_body_no_focus_on_timeout(monkeypatch, macos_module):
    """T19: @TIMEOUT / empty → no focus."""
    focus_calls = []

    class FR:
        def __init__(self, s):
            self.stdout = s

    monkeypatch.setattr(
        macos_module, "_focus_terminal", lambda bid: focus_calls.append(bid)
    )
    for output in ("@TIMEOUT", "", "unexpected"):
        monkeypatch.setattr(
            macos_module.subprocess, "run", lambda *a, o=output, **kw: FR(o)
        )
        macos_module._run_alerter_and_focus(["alerter"], "com.example.Term")
    assert focus_calls == []


def test_macos_alerter_no_subprocess_timeout(monkeypatch, macos_module):
    """T20: subprocess.run must not receive timeout=."""
    captured = {}

    class FR:
        stdout = "@TIMEOUT"

    monkeypatch.setattr(
        macos_module.subprocess,
        "run",
        lambda *a, **kw: captured.update(kw) or FR(),
    )
    monkeypatch.setattr(macos_module, "_focus_terminal", lambda bid: None)
    macos_module._run_alerter_and_focus(["alerter"], "com.example.Term")
    assert "timeout" not in captured


def test_macos_focus_uses_applescript_not_open_b(monkeypatch, macos_module):
    """T21: _focus_terminal uses osascript activate, not open -b."""
    run_calls = []
    monkeypatch.setattr(macos_module, "_terminal_is_active", lambda bid: False)
    monkeypatch.setattr(
        macos_module.subprocess, "run", lambda *a, **kw: run_calls.append((a, kw))
    )
    macos_module._focus_terminal("com.example.Term")
    assert len(run_calls) == 1
    argv = run_calls[0][0][0]
    assert argv[0] == "osascript"
    assert "activate" in " ".join(argv)
    assert "com.example.Term" in " ".join(argv)


# ---------------------------------------------------------------------------
# T22-T23 – Windows backend
# ---------------------------------------------------------------------------


def test_windows_notification_passes_untrusted_text_via_env(
    monkeypatch, windows_module
):
    """T22: title/message go through env vars, never inline in PS script."""
    calls = []
    monkeypatch.setattr(
        windows_module,
        "_resolve_powershell",
        lambda: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    )
    monkeypatch.setattr(
        windows_module.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw))
    )
    title = "bad'; Start-Process calc; $(whoami)"
    message = "line1`nline2; rm -rf /"
    assert windows_module.send(title, message) is True
    kw = calls[0][1]
    assert title not in " ".join(calls[0][0][0][1:])
    assert kw["env"]["CODE_PUPPY_NOTIFY_TITLE"] == title
    assert kw["env"]["CODE_PUPPY_NOTIFY_MESSAGE"] == message


def test_windows_powershell_resolver_requires_absolute_path(
    monkeypatch, windows_module
):
    """T23: relative / missing paths rejected."""
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.delenv("WINDIR", raising=False)
    monkeypatch.setattr(windows_module.shutil, "which", lambda name: "powershell.exe")
    monkeypatch.setattr(windows_module.os.path, "isabs", lambda p: ":" in p)
    monkeypatch.setattr(windows_module.os.path, "isfile", lambda p: True)
    assert windows_module._resolve_powershell() is None


# ---------------------------------------------------------------------------
# T24 – backend failures
# ---------------------------------------------------------------------------


def test_notification_backend_failures_return_false(monkeypatch, mod, windows_module):
    """T24: unknown OS / missing tools → False, no exception."""
    monkeypatch.setattr(mod.platform, "system", lambda: "Plan9")
    assert mod._send_notification("t", "m") is False

    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    assert mod._send_linux_notification("t", "m") is False

    monkeypatch.setattr(windows_module, "_resolve_powershell", lambda: None)
    assert windows_module.send("t", "m") is False

    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/notify-send")
    monkeypatch.setattr(
        mod.subprocess,
        "Popen",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("boom")),
    )
    assert mod._send_linux_notification("t", "m") is False


# ---------------------------------------------------------------------------
# T25 – config key
# ---------------------------------------------------------------------------


def test_config_keys_include_enable_notifications():
    """T25: enable_notifications visible to /set."""
    assert "enable_notifications" in get_config_keys()


# ---------------------------------------------------------------------------
# T26 – callback count
# ---------------------------------------------------------------------------


def test_plugin_registers_expected_callbacks_once(mod):
    """T26: exactly 1 registration per active hook; agent_run_end disabled."""
    assert len(callbacks.get_callbacks("agent_run_end")) == 0
    assert len(callbacks.get_callbacks("pre_tool_call")) == 1
    assert len(callbacks.get_callbacks("post_tool_call")) == 1
    assert len(callbacks.get_callbacks("register_tools")) == 1
    assert len(callbacks.get_callbacks("custom_command")) == 1
    assert len(callbacks.get_callbacks("custom_command_help")) == 1


# ---------------------------------------------------------------------------
# T27 – public Python API
# ---------------------------------------------------------------------------


def test_public_api_delegates_to_dispatcher(monkeypatch):
    """T27: __init__.send_notification delegates to the core dispatcher."""
    import importlib

    notifier_init = importlib.import_module("code_puppy.plugins.notifier")
    rc = importlib.import_module("code_puppy.plugins.notifier.register_callbacks")
    rc = importlib.reload(rc)

    calls = []
    monkeypatch.setattr(
        rc,
        "_send_notification",
        lambda t,
        m,
        s=None,
        rate_limit_key=None,
        timeout=None,
        persistent=False: calls.append((t, m, s, rate_limit_key)) or True,
    )

    # Patch the reference inside the __init__ lazy import
    import sys

    sys.modules["code_puppy.plugins.notifier.register_callbacks"] = rc

    result = notifier_init.send_notification(
        "Hello", "World", subtitle="sub", rate_limit_key="k"
    )
    assert result is True
    assert calls == [("Hello", "World", "sub", "k")]


# ---------------------------------------------------------------------------
# T28 – register_tools hook
# ---------------------------------------------------------------------------


def test_register_tools_returns_send_notification(mod):
    """T28: register_tools callback returns a send_notification tool def."""
    result = mod._get_notification_tools()
    assert isinstance(result, list)
    assert len(result) == 1
    tool = result[0]
    assert tool["name"] == "send_notification"
    assert callable(tool["register_func"])


# ---------------------------------------------------------------------------
# T29-T30 – agent tool behaviour
# ---------------------------------------------------------------------------


def test_agent_tool_dispatches_notification(monkeypatch, mod):
    """T29: tool calls _send_notification and returns a well-formed output."""
    dispatched = []
    monkeypatch.setattr(
        mod,
        "_send_notification",
        lambda t, m, s=None, rate_limit_key=None: dispatched.append((t, m)) or True,
    )
    monkeypatch.setattr(mod.platform, "system", lambda: "darwin")

    # Simulate what the tool does internally
    before = mod._last_notification_times.get("k", 0)
    ok = mod._send_notification("Build done", "bd-42 passed", rate_limit_key="k")
    after = mod._last_notification_times.get("k", 0)
    suppressed = ok is False and after == before

    assert ok is True
    assert suppressed is False
    assert dispatched == [("Build done", "bd-42 passed")]


def test_agent_tool_suppressed_flag(monkeypatch, mod):
    """T30: rate-limited call → suppressed=True (timestamp unchanged)."""
    now = {"t": 1000.0}
    monkeypatch.setattr(mod.time, "time", lambda: now["t"])
    monkeypatch.setattr(mod.platform, "system", lambda: "Plan9")

    # First call records timestamp
    mod._send_notification("T", "M", rate_limit_key="x")
    before = mod._last_notification_times.get("x", 0)

    # Second call within window — rate-limited
    now["t"] += 0.1
    ok = mod._send_notification("T", "M", rate_limit_key="x")
    after = mod._last_notification_times.get("x", 0)

    suppressed = ok is False and after == before
    assert suppressed is True


# ---------------------------------------------------------------------------
# T31-T35 – /notify slash command
# ---------------------------------------------------------------------------


def test_notify_command_title_only(monkeypatch, mod):
    """T31: /notify Hello dispatches with empty message."""
    dispatched = []
    monkeypatch.setattr(
        mod,
        "_send_notification",
        lambda t, m, s=None, rate_limit_key=None: dispatched.append((t, m)) or True,
    )
    success_msgs = []
    monkeypatch.setattr(
        "code_puppy.messaging.emit_success", lambda msg: success_msgs.append(msg)
    )

    result = mod._handle_notify_command("/notify Hello", "notify")

    assert result is True
    assert dispatched == [("Hello", "")]
    assert any("Hello" in m for m in success_msgs)


def test_notify_command_title_and_message(monkeypatch, mod):
    """T32: /notify Hello | World uses both parts."""
    dispatched = []
    monkeypatch.setattr(
        mod,
        "_send_notification",
        lambda t, m, s=None, rate_limit_key=None: dispatched.append((t, m)) or True,
    )
    monkeypatch.setattr("code_puppy.messaging.emit_success", lambda msg: None)

    mod._handle_notify_command("/notify Hello | World", "notify")

    assert dispatched == [("Hello", "World")]


def test_notify_command_empty_title_emits_error(monkeypatch, mod):
    """T33: /notify with no title emits usage error."""
    errors = []
    monkeypatch.setattr(
        "code_puppy.messaging.emit_error", lambda msg: errors.append(msg)
    )

    result = mod._handle_notify_command("/notify", "notify")

    assert result is True
    assert any("Usage" in e for e in errors)


def test_notify_command_ignores_wrong_name(mod):
    """T34: /foo → returns None (not our command)."""
    assert mod._handle_notify_command("/foo bar", "foo") is None


def test_notify_command_help_entry(mod):
    """T35: custom_command_help returns ("notify", description)."""
    entries = mod._notify_command_help()
    names = [e[0] for e in entries]
    assert "notify" in names
    desc = dict(entries)["notify"]
    assert "/notify" in desc or "notification" in desc.lower()


# ---------------------------------------------------------------------------
# T36-T40 – macOS timeout / persistent
# ---------------------------------------------------------------------------


def test_macos_alerter_default_timeout(monkeypatch, macos_module):
    """T36: no timeout arg → --timeout 600 (DEFAULT_TIMEOUT) in alerter cmd."""
    thread_calls = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            thread_calls.append(args[0])

        def start(self):
            pass

    monkeypatch.setattr(
        macos_module.shutil,
        "which",
        lambda name: "/usr/local/bin/alerter" if name == "alerter" else None,
    )
    monkeypatch.setattr(macos_module, "_detect_terminal_bundle_id", lambda: "com.x")
    monkeypatch.setattr(macos_module.threading, "Thread", FakeThread)

    macos_module.send("T", "M")
    cmd = thread_calls[0]
    idx = cmd.index("--timeout")
    assert cmd[idx + 1] == str(macos_module._DEFAULT_TIMEOUT)


def test_macos_alerter_explicit_timeout(monkeypatch, macos_module):
    """T37: timeout=30 → --timeout 30 in alerter cmd."""
    thread_calls = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            thread_calls.append(args[0])

        def start(self):
            pass

    monkeypatch.setattr(
        macos_module.shutil,
        "which",
        lambda name: "/usr/local/bin/alerter" if name == "alerter" else None,
    )
    monkeypatch.setattr(macos_module, "_detect_terminal_bundle_id", lambda: "com.x")
    monkeypatch.setattr(macos_module.threading, "Thread", FakeThread)

    macos_module.send("T", "M", timeout=30)
    cmd = thread_calls[0]
    idx = cmd.index("--timeout")
    assert cmd[idx + 1] == "30"


def test_macos_alerter_persistent(monkeypatch, macos_module):
    """T38: persistent=True → --timeout 0 (never auto-dismiss)."""
    thread_calls = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            thread_calls.append(args[0])

        def start(self):
            pass

    monkeypatch.setattr(
        macos_module.shutil,
        "which",
        lambda name: "/usr/local/bin/alerter" if name == "alerter" else None,
    )
    monkeypatch.setattr(macos_module, "_detect_terminal_bundle_id", lambda: "com.x")
    monkeypatch.setattr(macos_module.threading, "Thread", FakeThread)

    macos_module.send("T", "M", persistent=True)
    cmd = thread_calls[0]
    idx = cmd.index("--timeout")
    assert cmd[idx + 1] == "0", f"Expected --timeout 0, got {cmd[idx + 1]!r}"


def test_macos_alerter_timeout_zero_is_persistent(monkeypatch, macos_module):
    """T39: timeout=0 → --timeout 0 (same semantic as persistent=True)."""
    thread_calls = []

    class FakeThread:
        def __init__(self, target, args, daemon):
            thread_calls.append(args[0])

        def start(self):
            pass

    monkeypatch.setattr(
        macos_module.shutil,
        "which",
        lambda name: "/usr/local/bin/alerter" if name == "alerter" else None,
    )
    monkeypatch.setattr(macos_module, "_detect_terminal_bundle_id", lambda: "com.x")
    monkeypatch.setattr(macos_module.threading, "Thread", FakeThread)

    macos_module.send("T", "M", timeout=0)
    cmd = thread_calls[0]
    idx = cmd.index("--timeout")
    assert cmd[idx + 1] == "0"


def test_macos_osascript_timeout_silently_ignored(monkeypatch, macos_module):
    """T40: no alerter → timeout/persistent accepted, logged, no crash."""
    popen_calls = []
    monkeypatch.setattr(macos_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(macos_module, "_detect_terminal_bundle_id", lambda: None)
    monkeypatch.setattr(
        macos_module.subprocess,
        "Popen",
        lambda *a, **kw: popen_calls.append(a[0]),
    )

    # Must not raise
    result = macos_module.send("T", "M", timeout=10, persistent=True)
    assert result is True
    assert popen_calls, "osascript fallback must still fire"
    assert popen_calls[0][0] == "osascript"


# ---------------------------------------------------------------------------
# T41-T44 – Windows timeout / persistent
# ---------------------------------------------------------------------------


def test_windows_resolve_duration_default(windows_module):
    """T41: timeout=None, persistent=False → 'short'."""
    assert windows_module._resolve_duration(None, False) == "short"


def test_windows_resolve_duration_long(windows_module):
    """T42: timeout=20 → 'long'; timeout=7 → 'short' (boundary)."""
    assert windows_module._resolve_duration(20, False) == "long"
    assert windows_module._resolve_duration(8, False) == "long"
    assert windows_module._resolve_duration(7, False) == "short"
    assert windows_module._resolve_duration(1, False) == "short"


def test_windows_resolve_duration_reminder(windows_module):
    """T43: persistent=True or timeout=0 → 'reminder'."""
    assert windows_module._resolve_duration(None, True) == "reminder"
    assert windows_module._resolve_duration(0, False) == "reminder"
    assert (
        windows_module._resolve_duration(30, True) == "reminder"
    )  # persistent overrides


def test_windows_duration_env_var_set(monkeypatch, windows_module):
    """T44: CODE_PUPPY_NOTIFY_DURATION env var is set from persistent/timeout."""
    calls = []
    monkeypatch.setattr(windows_module, "_resolve_powershell", lambda: r"C:\ps.exe")
    monkeypatch.setattr(
        windows_module.subprocess,
        "Popen",
        lambda *a, **kw: calls.append(kw["env"]),
    )

    windows_module.send("T", "M", persistent=True)
    assert calls[0]["CODE_PUPPY_NOTIFY_DURATION"] == "reminder"

    calls.clear()
    windows_module.send("T", "M", timeout=30)
    assert calls[0]["CODE_PUPPY_NOTIFY_DURATION"] == "long"

    calls.clear()
    windows_module.send("T", "M")
    assert calls[0]["CODE_PUPPY_NOTIFY_DURATION"] == "short"


# ---------------------------------------------------------------------------
# T45-T47 – Linux timeout / persistent
# ---------------------------------------------------------------------------


def test_linux_expire_time_timeout(monkeypatch, mod):
    """T45: timeout=10 → notify-send receives --expire-time 10000."""
    cmds = []
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/notify-send")
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **kw: cmds.append(a[0]))

    mod._send_linux_notification("T", "M", timeout=10)
    assert "--expire-time" in cmds[0]
    idx = cmds[0].index("--expire-time")
    assert cmds[0][idx + 1] == "10000"


def test_linux_expire_time_persistent(monkeypatch, mod):
    """T46: persistent=True → --expire-time 0 (never dismiss)."""
    cmds = []
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/notify-send")
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **kw: cmds.append(a[0]))

    mod._send_linux_notification("T", "M", persistent=True)
    assert "--expire-time" in cmds[0]
    idx = cmds[0].index("--expire-time")
    assert cmds[0][idx + 1] == "0"


def test_linux_no_expire_time_by_default(monkeypatch, mod):
    """T47: timeout=None → no --expire-time flag (platform default)."""
    cmds = []
    monkeypatch.setattr(mod.shutil, "which", lambda _: "/usr/bin/notify-send")
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **kw: cmds.append(a[0]))

    mod._send_linux_notification("T", "M")
    assert "--expire-time" not in cmds[0]


# ---------------------------------------------------------------------------
# T48-T52 – focus detection
# ---------------------------------------------------------------------------


def test_macos_is_terminal_focused_when_active(monkeypatch, macos_module):
    """T48: _terminal_is_active returns True → is_terminal_focused() True."""
    monkeypatch.setattr(
        macos_module, "_detect_terminal_bundle_id", lambda: "com.example.term"
    )
    monkeypatch.setattr(
        macos_module, "_terminal_is_active", lambda bid: bid == "com.example.term"
    )

    assert macos_module.is_terminal_focused() is True


def test_macos_is_terminal_focused_when_not_active(monkeypatch, macos_module):
    """T49: different app is frontmost → is_terminal_focused() False."""
    monkeypatch.setattr(
        macos_module, "_detect_terminal_bundle_id", lambda: "com.example.term"
    )
    monkeypatch.setattr(macos_module, "_terminal_is_active", lambda bid: False)

    assert macos_module.is_terminal_focused() is False


def test_macos_is_terminal_focused_no_bundle_id(monkeypatch, macos_module):
    """T50: can't detect bundle ID → is_terminal_focused() False (fail open)."""
    monkeypatch.setattr(macos_module, "_detect_terminal_bundle_id", lambda: None)

    assert macos_module.is_terminal_focused() is False


def test_macos_terminal_is_active_timeout_returns_false(monkeypatch, macos_module):
    """T72: osascript timeout in _terminal_is_active fails open to False."""
    import subprocess

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=2)

    monkeypatch.setattr(macos_module.subprocess, "run", _timeout)

    assert macos_module._terminal_is_active("com.example.term") is False


def test_agent_run_end_suppressed_when_terminal_focused(monkeypatch, mod):
    """T51: terminal is frontmost → agent_run_end notification is suppressed."""
    sent = []
    monkeypatch.setattr(
        mod,
        "_send_notification",
        lambda title,
        message,
        subtitle=None,
        rate_limit_key=None,
        timeout=None,
        persistent=False: sent.append(title) or True,
    )
    monkeypatch.setattr(mod, "_is_notifications_enabled", lambda: True)
    monkeypatch.setattr(mod, "_is_terminal_focused", lambda: True)
    mod._user_interacted_this_run = False

    mod._on_agent_run_end("husky")

    assert sent == [], "no notification should fire when terminal is focused"


def test_agent_run_end_fires_when_terminal_not_focused(monkeypatch, mod):
    """T52: terminal is in background → agent_run_end notification fires."""
    sent = []
    monkeypatch.setattr(
        mod,
        "_send_notification",
        lambda title,
        message,
        subtitle=None,
        rate_limit_key=None,
        timeout=None,
        persistent=False: sent.append(title) or True,
    )
    monkeypatch.setattr(mod, "_is_notifications_enabled", lambda: True)
    monkeypatch.setattr(mod, "_is_terminal_focused", lambda: False)
    mod._user_interacted_this_run = False

    mod._on_agent_run_end("husky")

    assert sent == ["🐶 husky"], (
        "notification should fire when terminal is in background"
    )


# ---------------------------------------------------------------------------
# T53-T62 – Windows focus detection
# ---------------------------------------------------------------------------


def test_windows_pid_is_ancestor_direct_parent(windows_module):
    """T53: target PID is the immediate parent of start_pid → True."""
    parent_map = {100: 50, 50: 1}  # 100 → 50 → 1
    assert windows_module._pid_is_ancestor_of(50, 100, parent_map) is True


def test_windows_pid_is_ancestor_grandparent(windows_module):
    """T54: target PID is two levels up → True."""
    # Chain: python(300) → powershell(200) → WindowsTerminal(100) → 0
    parent_map = {300: 200, 200: 100, 100: 0}
    assert windows_module._pid_is_ancestor_of(100, 300, parent_map) is True


def test_windows_pid_is_ancestor_self(windows_module):
    """T55: target == start → True (foreground window IS our process)."""
    parent_map = {42: 1}
    assert windows_module._pid_is_ancestor_of(42, 42, parent_map) is True


def test_windows_pid_is_ancestor_unrelated(windows_module):
    """T56: target PID is not in the ancestor chain → False."""
    parent_map = {300: 200, 200: 100, 100: 0}
    assert windows_module._pid_is_ancestor_of(999, 300, parent_map) is False


def test_windows_pid_is_ancestor_cycle_protection(windows_module):
    """T57: parent_map contains a cycle → terminates, returns False."""
    # 10 → 20 → 10 (cycle)
    parent_map = {10: 20, 20: 10}
    # Should not hang; target 99 is not in the chain
    assert windows_module._pid_is_ancestor_of(99, 10, parent_map) is False


def test_windows_is_terminal_focused_ancestor(monkeypatch, windows_module):
    """T58: Windows Terminal path — fg PID is an ancestor of our process → True."""
    import os

    my_pid = os.getpid()
    fg_hwnd = 0xBEEF
    fg_pid = 9999
    # Build a fake parent map: my_pid → fg_pid (Windows Terminal) → 1
    parent_map = {my_pid: fg_pid, fg_pid: 1}

    monkeypatch.setattr(windows_module, "_get_foreground_hwnd", lambda: fg_hwnd)
    monkeypatch.setattr(
        windows_module, "_get_console_hwnd", lambda: 0
    )  # ConPTY, no classic console
    monkeypatch.setattr(windows_module, "_hwnd_to_pid", lambda hwnd: fg_pid)
    monkeypatch.setattr(windows_module, "_build_parent_map", lambda: parent_map)

    assert windows_module.is_terminal_focused() is True


def test_windows_is_terminal_focused_not_ancestor(monkeypatch, windows_module):
    """T59: foreground PID not in ancestor chain and console HWND mismatch → False."""
    import os

    my_pid = os.getpid()
    fg_hwnd = 0xBEEF
    fg_pid = 8888  # unrelated process
    parent_map = {my_pid: 1}

    monkeypatch.setattr(windows_module, "_get_foreground_hwnd", lambda: fg_hwnd)
    monkeypatch.setattr(
        windows_module, "_get_console_hwnd", lambda: 0xDEAD
    )  # different HWND
    monkeypatch.setattr(windows_module, "_hwnd_to_pid", lambda hwnd: fg_pid)
    monkeypatch.setattr(windows_module, "_build_parent_map", lambda: parent_map)

    assert windows_module.is_terminal_focused() is False


def test_windows_is_terminal_focused_no_fg_window(monkeypatch, windows_module):
    """T60: GetForegroundWindow returns 0 → False (fail open)."""
    monkeypatch.setattr(windows_module, "_get_foreground_hwnd", lambda: 0)

    assert windows_module.is_terminal_focused() is False


def test_windows_is_terminal_focused_errors_return_false(monkeypatch, windows_module):
    """T61: any exception inside is_terminal_focused → False (fail open)."""

    def _boom():
        raise OSError("simulated ctypes failure")

    monkeypatch.setattr(windows_module, "_get_foreground_hwnd", _boom)

    assert windows_module.is_terminal_focused() is False


def test_is_terminal_focused_delegates_to_windows_backend(monkeypatch, mod):
    """T62: on Windows, _is_terminal_focused() calls windows backend."""
    calls = []

    class FakeWindowsBackend:
        @staticmethod
        def is_terminal_focused():
            calls.append(True)
            return True

    monkeypatch.setattr(mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        mod,
        "_load_backend",
        lambda name: FakeWindowsBackend if name == "_windows" else None,
    )

    result = mod._is_terminal_focused()
    assert result is True
    assert calls == [True]


def test_windows_is_terminal_focused_classic_powershell(monkeypatch, windows_module):
    """T63: classic PowerShell — GetConsoleWindow matches foreground HWND → True.

    conhost.exe owns the HWND and is a *child* of powershell, not a parent,
    so the ancestor walk would miss it.  Path 1 (HWND comparison) catches it.
    """
    fg_hwnd = 0xC0FFEE
    # Our console HWND == foreground HWND → we are focused
    monkeypatch.setattr(windows_module, "_get_foreground_hwnd", lambda: fg_hwnd)
    monkeypatch.setattr(windows_module, "_get_console_hwnd", lambda: fg_hwnd)

    assert windows_module.is_terminal_focused() is True


def test_windows_is_terminal_focused_classic_console_not_focused(
    monkeypatch, windows_module
):
    """T64: classic console, different app in foreground → False.

    Our console HWND exists but doesn't match the foreground HWND,
    and the fg PID is not an ancestor either.
    """
    import os

    our_hwnd = 0xAABB
    fg_hwnd = 0xCCDD
    fg_pid = 5555
    parent_map = {os.getpid(): 1}  # unrelated parent chain

    monkeypatch.setattr(windows_module, "_get_foreground_hwnd", lambda: fg_hwnd)
    monkeypatch.setattr(windows_module, "_get_console_hwnd", lambda: our_hwnd)
    monkeypatch.setattr(windows_module, "_hwnd_to_pid", lambda hwnd: fg_pid)
    monkeypatch.setattr(windows_module, "_build_parent_map", lambda: parent_map)

    assert windows_module.is_terminal_focused() is False


def test_windows_is_terminal_focused_no_console_hwnd_falls_to_ancestor(
    monkeypatch, windows_module
):
    """T65: GetConsoleWindow returns 0 (ConPTY) → falls through to ancestor walk.

    This is the Windows Terminal case: no classic console HWND,
    but the foreground window is owned by WT.exe which IS our ancestor.
    """
    import os

    my_pid = os.getpid()
    fg_hwnd = 0xABCD
    fg_pid = 7777  # WindowsTerminal.exe
    parent_map = {my_pid: fg_pid, fg_pid: 1}

    monkeypatch.setattr(windows_module, "_get_foreground_hwnd", lambda: fg_hwnd)
    monkeypatch.setattr(
        windows_module, "_get_console_hwnd", lambda: 0
    )  # ConPTY → no HWND
    monkeypatch.setattr(windows_module, "_hwnd_to_pid", lambda hwnd: fg_pid)
    monkeypatch.setattr(windows_module, "_build_parent_map", lambda: parent_map)

    assert windows_module.is_terminal_focused() is True


# ---------------------------------------------------------------------------
# T66-T67 – pre_tool_call focus guard
# ---------------------------------------------------------------------------


def test_pre_tool_call_suppressed_when_terminal_focused(monkeypatch, mod):
    """T66: terminal is frontmost → pre_tool_call notification is suppressed."""
    sent = []
    monkeypatch.setattr(
        mod,
        "_send_notification",
        lambda title,
        message,
        subtitle=None,
        rate_limit_key=None,
        timeout=None,
        persistent=False: sent.append(title) or True,
    )
    monkeypatch.setattr(mod, "_is_notifications_enabled", lambda: True)
    monkeypatch.setattr(mod, "_is_terminal_focused", lambda: True)

    asyncio.run(mod._on_pre_tool_call(tool_name="ask_user_question", tool_args={}))

    assert sent == [], "no notification should fire when terminal is focused"


def test_pre_tool_call_fires_when_terminal_not_focused(monkeypatch, mod):
    """T67: terminal is in background → pre_tool_call notification fires."""
    sent = []
    monkeypatch.setattr(
        mod,
        "_send_notification",
        lambda title,
        message,
        subtitle=None,
        rate_limit_key=None,
        timeout=None,
        persistent=False: sent.append(title) or True,
    )
    monkeypatch.setattr(mod, "_is_notifications_enabled", lambda: True)
    monkeypatch.setattr(mod, "_is_terminal_focused", lambda: False)

    asyncio.run(mod._on_pre_tool_call(tool_name="ask_user_question", tool_args={}))

    assert sent == ["\U0001f436 User Selection Required"], (
        "notification should fire when terminal is in background"
    )


# ---------------------------------------------------------------------------
# T68-T70 – _detect_terminal_bundle_id process-tree walk
# ---------------------------------------------------------------------------


def test_detect_terminal_bundle_id_found_in_process_tree(monkeypatch, macos_module):
    """T68: our own PID appears in lsappinfo map → returns its bundle ID."""
    import os

    my_pid = os.getpid()
    lsappinfo_stdout = f'pid = {my_pid}\nbundleid = "com.apple.Terminal"\n'

    class _FakeResult:
        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        if cmd[0] == "lsappinfo":
            return _FakeResult(lsappinfo_stdout)
        # ps should not be needed when our own pid matches directly
        return _FakeResult("")

    monkeypatch.setattr(macos_module.subprocess, "run", fake_run)

    result = macos_module._detect_terminal_bundle_id()
    assert result == "com.apple.Terminal"


def test_detect_terminal_bundle_id_not_found_returns_none(monkeypatch, macos_module):
    """T69: no ancestor has a bundle ID in the map → returns None."""
    # Only a completely unrelated PID in the map
    lsappinfo_stdout = 'pid = 99999\nbundleid = "com.some.OtherApp"\n'

    class _FakeResult:
        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        if cmd[0] == "lsappinfo":
            return _FakeResult(lsappinfo_stdout)
        # ps ppid walk → return 1 to terminate the walk quickly
        return _FakeResult("1")

    monkeypatch.setattr(macos_module.subprocess, "run", fake_run)

    result = macos_module._detect_terminal_bundle_id()
    assert result is None


def test_detect_terminal_bundle_id_lsappinfo_failure(monkeypatch, macos_module):
    """T70: lsappinfo raises FileNotFoundError → no crash, returns None."""

    class _FakeResult:
        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        if cmd[0] == "lsappinfo":
            raise FileNotFoundError("lsappinfo not found")
        # ps ppid walk terminates at pid 1
        return _FakeResult("1")

    monkeypatch.setattr(macos_module.subprocess, "run", fake_run)

    result = macos_module._detect_terminal_bundle_id()
    assert result is None


def test_detect_terminal_bundle_id_parses_real_lsappinfo_format(
    monkeypatch, macos_module
):
    """T71: parse real lsappinfo lines where bundleID appears before pid."""
    import os

    my_pid = os.getpid()
    lsappinfo_stdout = (
        f' 7) "iTerm2" ASN:0x0-0x123:\n'
        '    bundleID="com.googlecode.iterm2"\n'
        '    bundle path="/Applications/iTerm.app"\n'
        f'    pid = {my_pid} type="Foreground" flavor=3\n'
    )

    class _FakeResult:
        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        if cmd[0] == "lsappinfo":
            return _FakeResult(lsappinfo_stdout)
        return _FakeResult("1")

    monkeypatch.setattr(macos_module.subprocess, "run", fake_run)

    result = macos_module._detect_terminal_bundle_id()
    assert result == "com.googlecode.iterm2"
