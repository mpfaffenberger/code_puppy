"""Tests for code_puppy.pydantic_patches loud-failure behavior.

The contract under test:
- Patches never raise (no-crash guarantee).
- Failure to patch a pydantic-ai internal logs a LOUD ``logging.ERROR``
  record naming the patch.
- A missing OPTIONAL third-party lib stays quiet (DEBUG at most).
- ``apply_all_patches`` returns a dict of patch name -> applied and logs
  one summary line listing real failures.
"""

import builtins
import logging

import pytest

from code_puppy import pydantic_patches

LOGGER_NAME = "code_puppy.pydantic_patches"


def _error_records(caplog):
    return [
        r
        for r in caplog.records
        if r.name == LOGGER_NAME and r.levelno >= logging.ERROR
    ]


# ---------------------------------------------------------------------------
# Success path: everything installed in the test env, so all patches apply
# cleanly and NO error records are emitted.
# ---------------------------------------------------------------------------


def test_apply_all_patches_success_no_errors(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        results = pydantic_patches.apply_all_patches()

    assert results == {p.__name__: True for p in pydantic_patches._ALL_PATCHES}
    assert _error_records(caplog) == []


def test_apply_all_patches_returns_all_patch_names():
    results = pydantic_patches.apply_all_patches()
    assert set(results) == {p.__name__ for p in pydantic_patches._ALL_PATCHES}


# ---------------------------------------------------------------------------
# Loud failures: a missing pydantic-ai internal must log ERROR, return False,
# and never raise.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "patch_fn_name,break_it",
    [
        (
            "patch_user_agent",
            lambda mp: mp.delattr("pydantic_ai.models.get_user_agent"),
        ),
        (
            "patch_message_history_cleaning",
            lambda mp: mp.delattr("pydantic_ai._agent_graph._clean_message_history"),
        ),
        (
            "patch_tool_call_callbacks",
            lambda mp: mp.delattr(
                "pydantic_ai.tool_manager.ToolManager.execute_tool_call"
            ),
        ),
        (
            "patch_tool_call_json_repair",
            lambda mp: mp.delattr(
                "pydantic_ai.tool_manager.ToolManager.validate_tool_call"
            ),
        ),
    ],
)
def test_missing_pydantic_internal_logs_error(
    monkeypatch, caplog, patch_fn_name, break_it
):
    break_it(monkeypatch)
    patch_fn = getattr(pydantic_patches, patch_fn_name)

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = patch_fn()  # must NOT raise

    assert result is False
    errors = _error_records(caplog)
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert patch_fn_name in message
    assert "FAILED to apply" in message


def test_tool_call_callbacks_failure_names_disabled_hooks(monkeypatch, caplog):
    """The security-critical patch must spell out the consequence."""
    monkeypatch.delattr("pydantic_ai.tool_manager.ToolManager.execute_tool_call")
    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        assert pydantic_patches.patch_tool_call_callbacks() is False
    message = _error_records(caplog)[0].getMessage()
    assert "pre/post tool hooks and hook-blocking are DISABLED" in message


# ---------------------------------------------------------------------------
# Optional dependencies: ImportError of json_repair/wcwidth/prompt_toolkit/
# termflow stays quiet (DEBUG at most, never ERROR).
# ---------------------------------------------------------------------------


def _block_import(monkeypatch, *names):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in names or any(name.startswith(f"{n}.") for n in names):
            raise ImportError(f"No module named {name!r} (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


@pytest.mark.parametrize(
    "patch_fn_name,blocked_libs",
    [
        ("patch_tool_call_json_repair", ("json_repair",)),
        ("patch_termflow_clipboard", ("termflow",)),
        ("patch_termflow_code_padding", ("termflow",)),
    ],
)
def test_missing_optional_lib_is_quiet(
    monkeypatch, caplog, patch_fn_name, blocked_libs
):
    _block_import(monkeypatch, *blocked_libs)
    patch_fn = getattr(pydantic_patches, patch_fn_name)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        result = patch_fn()  # must NOT raise

    assert result is False
    assert _error_records(caplog) == []
    debug_msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == LOGGER_NAME and r.levelno == logging.DEBUG
    ]
    assert any(patch_fn_name in m for m in debug_msgs)


# ---------------------------------------------------------------------------
# apply_all_patches summary behavior.
# ---------------------------------------------------------------------------


def test_apply_all_patches_summary_lists_loud_failures(monkeypatch, caplog):
    monkeypatch.delattr("pydantic_ai._agent_graph._clean_message_history")

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        results = pydantic_patches.apply_all_patches()  # must NOT raise

    assert results["patch_message_history_cleaning"] is False
    # Everything else still applies.
    assert all(
        ok for name, ok in results.items() if name != "patch_message_history_cleaning"
    )
    summary = [
        r.getMessage()
        for r in _error_records(caplog)
        if "FAILED to apply:" in r.getMessage()
    ]
    assert len(summary) == 1
    assert "patch_message_history_cleaning" in summary[0]


def test_apply_all_patches_no_summary_for_optional_skips(monkeypatch, caplog):
    """A skipped optional dep is False in the dict but NOT a loud failure."""
    _block_import(monkeypatch, "termflow")

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        results = pydantic_patches.apply_all_patches()

    assert results["patch_termflow_clipboard"] is False
    assert results["patch_termflow_code_padding"] is False
    assert _error_records(caplog) == []
