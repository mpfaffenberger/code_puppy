"""Tests for the prompt_ready SDK prewarm plugin."""

import importlib
import sys
import threading
import uuid

import pytest

from code_puppy import callbacks
from code_puppy.agents import agent_manager
from code_puppy.model_factory import ModelFactory
from code_puppy.plugins.prewarm_sdks import prewarm, register_callbacks


class _FakeAgent:
    def __init__(self, model_name):
        self._model_name = model_name

    def get_model_name(self):
        return self._model_name


@pytest.fixture(autouse=True)
def _reset_prewarm_state(monkeypatch):
    monkeypatch.setattr(prewarm, "_families", list(prewarm._families))
    monkeypatch.setattr(prewarm, "_requested", set())
    monkeypatch.delenv(prewarm.OPT_OUT_ENV, raising=False)


def _use_active_model(monkeypatch, model_name):
    monkeypatch.setattr(
        agent_manager, "get_current_agent", lambda: _FakeAgent(model_name)
    )


def _wait_for_prewarm_thread():
    for thread in threading.enumerate():
        if thread.name == prewarm.THREAD_NAME:
            thread.join(timeout=10)
            assert not thread.is_alive()


def test_prompt_ready_is_a_callback_phase():
    assert "prompt_ready" in callbacks.PhaseType.__args__


def test_prompt_ready_hook_dispatches_to_plugin(monkeypatch):
    calls = []
    monkeypatch.setattr(
        register_callbacks,
        "start_prewarm_for_active_model",
        lambda: calls.append("prompt_ready"),
    )
    callbacks.on_prompt_ready()
    assert calls == ["prompt_ready"]


def test_prewarm_is_not_a_startup_callback():
    assert register_callbacks._on_prompt_ready not in callbacks.get_callbacks("startup")


def test_prewarm_thread_is_daemon_and_named(monkeypatch):
    spawned = []

    class _RecordingThread:
        def __init__(self, *, target, args, name, daemon):
            spawned.append((name, daemon, args))

        def start(self):
            pass

    monkeypatch.setattr(prewarm.threading, "Thread", _RecordingThread)
    _use_active_model(monkeypatch, "claude-sonnet-4-5")

    assert prewarm.start_prewarm_for_active_model() is True
    assert spawned == [(prewarm.THREAD_NAME, True, (("anthropic",),))]


def test_repeated_prompts_do_not_respawn_thread(monkeypatch):
    spawned = []

    class _RecordingThread:
        def __init__(self, **kwargs):
            spawned.append(kwargs)

        def start(self):
            pass

    monkeypatch.setattr(prewarm.threading, "Thread", _RecordingThread)
    _use_active_model(monkeypatch, "gpt-5")

    assert prewarm.start_prewarm_for_active_model() is True
    assert prewarm.start_prewarm_for_active_model() is False
    assert len(spawned) == 1


def test_thread_start_failure_rolls_back_requested_modules(monkeypatch):
    class _BrokenThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("cannot start thread")

    monkeypatch.setattr(prewarm.threading, "Thread", _BrokenThread)

    assert prewarm.start_prewarm("claude-sonnet-4-5") is False
    assert prewarm._requested == set()


def test_worker_swallows_import_errors_and_continues(monkeypatch):
    attempted = []

    def _fake_import(name):
        attempted.append(name)
        if name == "pup_broken_sdk":
            raise ImportError("broken install")

    monkeypatch.setattr(prewarm.importlib, "import_module", _fake_import)

    prewarm._import_all(("pup_broken_sdk", "pup_healthy_sdk"))

    assert attempted == ["pup_broken_sdk", "pup_healthy_sdk"]


def test_worker_reraises_memory_error(monkeypatch):
    def _exhausted(name):
        raise MemoryError

    monkeypatch.setattr(prewarm.importlib, "import_module", _exhausted)

    with pytest.raises(MemoryError):
        prewarm._import_all(("pup_any_sdk",))


@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_opt_out_creates_no_thread(monkeypatch, value):
    monkeypatch.setenv(prewarm.OPT_OUT_ENV, value)

    def _forbidden(**kwargs):
        raise AssertionError("prewarm thread must not be created")

    monkeypatch.setattr(prewarm.threading, "Thread", _forbidden)

    assert prewarm.start_prewarm_for_active_model() is False


@pytest.mark.parametrize("value", ["", "0", "no"])
def test_opt_out_flag_off_values_keep_prewarm_enabled(monkeypatch, value):
    monkeypatch.setenv(prewarm.OPT_OUT_ENV, value)
    assert prewarm.is_opted_out() is False


@pytest.mark.parametrize(
    "model_name, expected",
    [
        ("claude-sonnet-4-5", ("anthropic",)),
        ("anthropic-beta", ("anthropic",)),
        ("GPT-5", ("openai",)),
        ("o3-mini", ("openai",)),
        ("chatgpt-5.5", ("openai",)),
        ("gemini-2.5-pro", ()),
        ("my-custom-model", ()),
        ("", ()),
        (None, ()),
    ],
)
def test_family_table_maps_known_prefixes_only(model_name, expected):
    assert prewarm.modules_for_model(model_name) == expected


def test_registered_families_extend_the_table():
    prewarm.register_prewarm_families([("vendor-private-", ("vendor_private_sdk",))])
    assert prewarm.modules_for_model("Vendor-Private-model") == ("vendor_private_sdk",)


def test_main_and_worker_import_same_module_without_deadlock(tmp_path, monkeypatch):
    name = f"pup_prewarm_slow_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text("import time\ntime.sleep(0.2)\nVALUE = 42\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    prefix = f"{name}-"
    prewarm.register_prewarm_families([(prefix, (name,))])
    try:
        assert prewarm.start_prewarm(f"{prefix}model") is True
        main_result = {}

        def _main_import():
            main_result["module"] = importlib.import_module(name)

        main_thread = threading.Thread(target=_main_import)
        main_thread.start()
        main_thread.join(timeout=10)
        assert not main_thread.is_alive(), "main-thread import deadlocked"
        _wait_for_prewarm_thread()
        assert main_result["module"].VALUE == 42
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize(
    "model_name, model_type, api_key_env",
    [
        ("claude-sonnet-4-5", "anthropic", "ANTHROPIC_API_KEY"),
        ("gpt-5", "openai", "OPENAI_API_KEY"),
    ],
)
@pytest.mark.parametrize("prewarm_on", [True, False])
def test_first_request_model_builds_with_prewarm_on_and_off(
    monkeypatch, model_name, model_type, api_key_env, prewarm_on
):
    monkeypatch.setenv(api_key_env, "test-key-not-used-offline")
    if prewarm_on:
        _use_active_model(monkeypatch, model_name)
        assert prewarm.start_prewarm_for_active_model() is True
        _wait_for_prewarm_thread()

    config = {
        model_name: {"name": model_name, "type": model_type, "context_length": 200000}
    }
    model = ModelFactory.get_model(model_name, config)

    assert model is not None
