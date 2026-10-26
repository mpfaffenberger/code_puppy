"""Startup failures in ``cli_runner`` reach ``errors.log`` exactly once.

Drives the real ``main()`` / ``main_entry()`` with the helpers of the existing
runner suites. Only failures that nothing else would record are written; the
user-facing output and exit codes of the fatal paths stay unchanged.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from code_puppy import callbacks, cli_runner, error_hooks, error_logging
from code_puppy.i18n import t
from tests.test_cli_runner_resume_render import _resume_patches, _run_main

CTX = "code_puppy.cli_runner::"
HOOK_CONTEXT = error_hooks._MAIN_CONTEXT


@pytest.fixture(autouse=True)
def isolated_log(tmp_path, monkeypatch):
    """Redirect errors.log, silence subscribers, and undo hook installs."""
    log_file = tmp_path / "errors.log"
    monkeypatch.setattr(error_logging, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(error_logging, "ERROR_LOG_FILE", str(log_file))
    monkeypatch.setattr(error_logging, "_fallback", OrderedDict())
    original = list(callbacks._callbacks.get("error_logged", []))
    callbacks._callbacks["error_logged"] = []
    error_hooks.uninstall_error_hooks()
    saved = (sys.excepthook, threading.excepthook)
    yield log_file
    error_hooks.uninstall_error_hooks()
    sys.excepthook, threading.excepthook = saved
    callbacks._callbacks["error_logged"] = original


def _contexts(log_file: Path) -> list[str]:
    if not log_file.exists():
        return []
    return re.findall(r"^Context: (.*)$", log_file.read_text(), flags=re.MULTILINE)


def _boom(message: str = "boom") -> RuntimeError:
    return RuntimeError(message)


def _quiet_sweeps(**overrides) -> dict:
    """Both migrations mocked so no test touches the real session directories."""
    patches = {
        "code_puppy.session_migration.sweep_contexts_to_autosaves": MagicMock(),
        "code_puppy.session_format_migration.sweep_legacy_pickle_sessions": MagicMock(),
    }
    patches.update(overrides)
    return patches


# --- (a) swallowed session-migration failures -------------------------------


@pytest.mark.parametrize(
    ("target", "phrase"),
    [
        (
            "code_puppy.session_migration.sweep_contexts_to_autosaves",
            "startup/session-migration: sweep legacy contexts into autosaves",
        ),
        (
            "code_puppy.session_format_migration.sweep_legacy_pickle_sessions",
            "startup/session-migration: migrate legacy pickle sessions to versioned JSON",
        ),
    ],
)
async def test_session_migration_failure_is_recorded_and_startup_continues(
    isolated_log, target, phrase
):
    execute = AsyncMock()
    extra = _quiet_sweeps(
        **{
            target: MagicMock(side_effect=_boom()),
            "code_puppy.cli_runner.execute_single_prompt": execute,
        }
    )

    await _run_main(["code-puppy", "-p", "hi"], extra)

    execute.assert_awaited_once()
    assert _contexts(isolated_log) == [f"{CTX}main: {phrase}"]


# --- (b) fatal model / agent failures ---------------------------------------


@pytest.mark.parametrize(
    ("argv", "extra", "expected_error", "phrase"),
    [
        (
            ["code-puppy", "-m", "bad", "-p", "hi"],
            {
                "code_puppy.config._validate_model_exists": MagicMock(
                    side_effect=_boom()
                )
            },
            t("cli.model.validate_error", error="boom"),
            "startup/model: validate the --model value against models.json",
        ),
        (
            ["code-puppy", "-a", "bad", "-p", "hi"],
            {
                "code_puppy.agents.agent_manager.get_available_agents": MagicMock(
                    side_effect=_boom()
                )
            },
            t("cli.agent.set_error", error="boom"),
            "startup/agent: resolve and set the --agent value",
        ),
    ],
)
async def test_model_and_agent_failure_recorded_with_unchanged_output(
    isolated_log, argv, extra, expected_error, phrase
):
    emit_error = MagicMock()
    patches = _quiet_sweeps(
        **{
            "code_puppy.config.set_model_name": MagicMock(),
            "code_puppy.messaging.emit_error": emit_error,
            **extra,
        }
    )

    with pytest.raises(SystemExit) as exit_info:
        await _run_main(argv, patches)

    assert exit_info.value.code == 1
    assert emit_error.call_args_list == [call(expected_error)]
    assert _contexts(isolated_log) == [f"{CTX}main: {phrase}"]


@pytest.mark.parametrize(
    ("argv", "extra"),
    [
        (
            ["code-puppy", "-m", "bad", "-p", "hi"],
            {
                "code_puppy.config._validate_model_exists": MagicMock(
                    return_value=False
                ),
                "code_puppy.model_factory.ModelFactory": MagicMock(),
            },
        ),
        (
            ["code-puppy", "-a", "bad", "-p", "hi"],
            {
                "code_puppy.agents.agent_manager.get_available_agents": MagicMock(
                    return_value={"code-puppy": {}}
                )
            },
        ),
    ],
)
async def test_unknown_model_or_agent_is_user_error_not_logged(
    isolated_log, argv, extra
):
    """``sys.exit`` raises SystemExit, which ``except Exception`` never catches."""
    patches = _quiet_sweeps(
        **{
            "code_puppy.config.set_model_name": MagicMock(),
            "code_puppy.messaging.emit_error": MagicMock(),
            **extra,
        }
    )

    with pytest.raises(SystemExit) as exit_info:
        await _run_main(argv, patches)

    assert exit_info.value.code == 1
    assert _contexts(isolated_log) == []


# --- (c) resume failures ----------------------------------------------------


def _resume_extra(**overrides) -> dict:
    agent = MagicMock()
    agent.estimate_tokens_for_message.return_value = 1
    stdout = MagicMock()
    stdout.isatty.return_value = True
    extra = _quiet_sweeps(
        **{
            "code_puppy.cli_runner.interactive_mode": AsyncMock(),
            "pyfiglet.figlet_format": MagicMock(return_value="LOGO\n\n"),
            "sys.stdout": stdout,
        }
    )
    extra.update(_resume_patches(MagicMock(), agent))
    extra.update(overrides)
    return extra


async def test_resumed_history_render_failure_is_recorded_and_startup_continues(
    isolated_log,
):
    interactive = AsyncMock()
    extra = _resume_extra(
        **{
            "code_puppy.command_line.autosave_menu.display_resumed_history": MagicMock(
                side_effect=_boom()
            ),
            "code_puppy.cli_runner.interactive_mode": interactive,
        }
    )

    await _run_main(["code-puppy", "-r", "my-session"], extra)

    interactive.assert_awaited_once()
    assert _contexts(isolated_log) == [
        f"{CTX}main: startup/resume: re-render resumed session history"
    ]


async def test_resume_load_failure_is_recorded_with_unchanged_output(isolated_log):
    emit_error = MagicMock()
    extra = _resume_extra(
        **{
            "code_puppy.session_storage.load_session": MagicMock(side_effect=_boom()),
            "code_puppy.messaging.emit_error": emit_error,
        }
    )

    with pytest.raises(SystemExit) as exit_info:
        await _run_main(["code-puppy", "-r", "my-session"], extra)

    assert exit_info.value.code == 1
    assert emit_error.call_args_list == [
        call(t("cli.resume.failed", target="my-session", error=_boom()))
    ]
    assert _contexts(isolated_log) == [
        f"{CTX}main: startup/resume: load and apply the resumed session history"
    ]


# --- (d) main_entry hooks ---------------------------------------------------


def _run_main_entry(run_side_effect, utf8_stdio=None) -> object:
    """Drive ``main_entry`` with ``asyncio.run`` replaced; returns its exit code."""
    with (
        pytest.raises(SystemExit) as exit_info,
        patch("code_puppy.cli_runner.main", MagicMock(return_value=None)),
        patch("code_puppy.cli_runner.asyncio.run", side_effect=run_side_effect),
        patch("code_puppy.cli_runner.install_malloc_noise_guard"),
        patch("code_puppy.cli_runner._force_utf8_stdio", utf8_stdio or MagicMock()),
        patch("code_puppy.cli_runner.reset_unix_terminal"),
    ):
        cli_runner.main_entry()
    return exit_info.value.code


def test_main_entry_installs_the_hooks_first():
    order: list[str] = []
    with (
        patch(
            "code_puppy.cli_runner.install_error_hooks",
            side_effect=lambda: order.append("hooks"),
        ),
    ):
        _run_main_entry(
            lambda *_: order.append("run") or 0,
            utf8_stdio=lambda: order.append("utf8"),
        )

    assert order == ["hooks", "utf8", "run"]


def test_main_entry_survives_a_failing_hook_install(caplog):
    with (
        patch(
            "code_puppy.cli_runner.install_error_hooks", side_effect=_boom("no hooks")
        ),
        caplog.at_level(logging.DEBUG, logger=cli_runner.logger.name),
    ):
        assert _run_main_entry(lambda *_: 0) == 0

    assert any(record.exc_info for record in caplog.records)


def test_uncaught_exception_from_the_run_loop_is_recorded_once(isolated_log):
    delegated: list[BaseException] = []
    sys.excepthook = lambda _type, exc, _tb: delegated.append(exc)
    exc = ValueError("escaped asyncio.run")

    with pytest.raises(ValueError) as raised:
        _run_main_entry(exc)
    assert raised.value is exc
    assert _contexts(isolated_log) == []

    # The interpreter hands the escaped exception to sys.excepthook.
    sys.excepthook(type(exc), exc, exc.__traceback__)
    sys.excepthook(type(exc), exc, exc.__traceback__)

    assert delegated == [exc, exc]
    assert _contexts(isolated_log) == [HOOK_CONTEXT]


# --- (e) control flow writes nothing ----------------------------------------


def test_version_flag_system_exit_writes_nothing(isolated_log):
    with (
        patch("sys.argv", ["code-puppy", "--version"]),
        patch("code_puppy.cli_runner.install_malloc_noise_guard"),
        patch("code_puppy.cli_runner.reset_unix_terminal"),
        pytest.raises(SystemExit) as exit_info,
    ):
        cli_runner.main_entry()

    assert exit_info.value.code == 0
    assert _contexts(isolated_log) == []


# --- expected degradations and pins -----------------------------------------


def test_utf8_reconfigure_failure_is_debug_only(isolated_log, caplog):
    stream = MagicMock()
    stream.reconfigure.side_effect = _boom()
    with (
        patch("sys.stdout", stream),
        patch("sys.stderr", stream),
        caplog.at_level(logging.DEBUG, logger=cli_runner.logger.name),
    ):
        cli_runner._force_utf8_stdio()

    messages = [r.getMessage() for r in caplog.records if r.exc_info]
    assert (
        messages
        == [
            f"{CTX}_force_utf8_stdio: startup/stdio: reconfigure stdout/stderr to UTF-8"
        ]
        * 2
    )
    assert _contexts(isolated_log) == []


def test_cli_runner_startup_context_count_is_pinned():
    source = Path(cli_runner.__file__).read_text()
    startup = re.findall(rf'"({re.escape(CTX)}[^"]*startup/[^"]+)"', source)

    assert len(startup) == 10, (
        "cli_runner has 6 ERROR + 4 DEBUG startup sites pinned in "
        "tests/data/error_pipeline_sites.tsv; add or remove the TSV row with the site"
    )
