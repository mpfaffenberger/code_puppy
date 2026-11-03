"""/session rename: validation, persistence, help, and lifecycle survival."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from code_puppy.command_line.session_browser_data import (
    _TITLE_MAX,
    build_entries,
    ensure_titles,
)
from code_puppy.command_line.session_commands import handle_session_command
from code_puppy.session_storage import has_user_title, save_session

NAME = "auto_session_rename_test"


def _history() -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content="fix the bug")]),
        ModelResponse(parts=[TextPart(content="done")]),
    ]


def _meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def autosave_dir(tmp_path):
    with (
        patch("code_puppy.command_line.session_commands.AUTOSAVE_DIR", str(tmp_path)),
        patch("code_puppy.config.get_current_session_name", return_value=NAME),
        patch(
            "code_puppy.command_line.session_commands.t",
            side_effect=lambda key, **params: f"{key}|{params}",
        ),
    ):
        yield tmp_path


@pytest.fixture
def sidecar_path(autosave_dir):
    save_session(
        history=_history(),
        session_name=NAME,
        base_dir=autosave_dir,
        timestamp="2026-01-02T00:00:00",
        token_estimator=lambda _m: 1,
        auto_saved=True,
    )
    return autosave_dir / f"{NAME}_meta.json"


@pytest.fixture
def emitted():
    with (
        patch("code_puppy.messaging.emit_success") as success,
        patch("code_puppy.messaging.emit_warning") as warning,
        patch("code_puppy.messaging.emit_error") as error,
    ):
        yield {"success": success, "warning": warning, "error": error}


@pytest.mark.parametrize(
    ("command", "title"),
    [
        ("/session rename Fix the login bug", "Fix the login bug"),
        ("/s rename   spaced    out  ", "spaced out"),
        ("/session rename line\none\ttab", "line one tab"),
        ("/session rename esc\x1b[31m red\x07", "esc[31m red"),
        ("/session rename bidi\u202eflip", "bidiflip"),
        (
            "/session rename family \U0001f468\u200d\U0001f469\u200d\U0001f467",
            "family \U0001f468\u200d\U0001f469\u200d\U0001f467",
        ),
        (
            "/session rename \u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",
            "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",
        ),
        ("/session rename [bold]markup[/bold]", "[bold]markup[/bold]"),
        ("/session rename " + "x" * _TITLE_MAX, "x" * _TITLE_MAX),
    ],
    ids=[
        "spaces",
        "alias-collapse",
        "newline-tab",
        "ansi",
        "bidi",
        "zwj-emoji",
        "zwnj-word",
        "markup",
        "max-length",
    ],
)
def test_rename_sets_clean_user_title(sidecar_path, emitted, command, title):
    assert handle_session_command(command) is True
    meta = _meta(sidecar_path)
    assert (meta["title"], has_user_title(meta), meta["message_count"]) == (
        title,
        True,
        2,
    )
    emitted["success"].assert_called_once_with(
        f"cmd.session.renamed|{ {'title': title} }"
    )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("/session rename", "cmd.session.rename_empty|{}"),
        ("/session rename    ", "cmd.session.rename_empty|{}"),
        ("/session rename \x1b\x07\u200b", "cmd.session.rename_empty|{}"),
        (
            "/session rename " + "x" * (_TITLE_MAX + 1),
            f"cmd.session.rename_too_long|{ {'length': _TITLE_MAX + 1, 'limit': _TITLE_MAX} }",
        ),
    ],
    ids=["missing", "whitespace", "only-controls", "too-long"],
)
def test_rename_rejects_invalid_titles(sidecar_path, emitted, command, expected):
    before = sidecar_path.read_bytes()
    assert handle_session_command(command) is True
    emitted["warning"].assert_called_once_with(expected)
    assert sidecar_path.read_bytes() == before


def test_rename_before_first_save_writes_nothing(autosave_dir, emitted):
    handle_session_command("/session rename Too early")
    emitted["warning"].assert_called_once_with("cmd.session.rename_unsaved|{}")
    assert list(autosave_dir.iterdir()) == []


def test_second_rename_replaces_first(sidecar_path, emitted):
    handle_session_command("/session rename First")
    handle_session_command("/session rename Second")
    assert _meta(sidecar_path)["title"] == "Second"


def test_rename_reports_unreadable_sidecar(sidecar_path, emitted):
    sidecar_path.write_text("{broken", encoding="utf-8")
    handle_session_command("/session rename Mine")
    emitted["error"].assert_called_once_with("cmd.session.rename_failed|{}")
    assert sidecar_path.read_text(encoding="utf-8") == "{broken"


def test_help_and_usage_list_rename():
    from code_puppy.command_line.command_registry import get_command
    from code_puppy.i18n import t

    info = get_command("session")
    assert info.usage == "/session [id|new|rename <title>]"
    assert "/session rename <title>" in info.detailed_help
    assert "rename <title>" in t("cmd.session.usage")


def test_user_title_survives_autosave_clear_new_resume_and_restart(tmp_path):
    from code_puppy import config

    agent = MagicMock()
    agent.get_message_history.return_value = _history()
    agent.estimate_tokens_for_message.return_value = 1
    with (
        patch.object(config, "_CURRENT_AUTOSAVE_ID", None),
        patch.object(config, "AUTOSAVE_DIR", str(tmp_path)),
        patch("code_puppy.command_line.session_commands.AUTOSAVE_DIR", str(tmp_path)),
        patch.object(config, "get_auto_save_session", return_value=True),
        patch("code_puppy.agents.agent_manager.get_current_agent", return_value=agent),
        patch.object(config, "record_quick_resume_sessions"),
        patch.object(config, "record_terminal_session"),
        patch("code_puppy.session_lifecycle.fire_post_autosave_callback"),
        patch("code_puppy.messaging.emit_success"),
    ):
        name = config.rotate_session_name()
        assert config.auto_save_session_if_enabled()
        handle_session_command("/session rename Pinned title")
        assert config.auto_save_session_if_enabled()  # next autosave turn
        assert config.finalize_autosave_session() != name  # /clear and agent switch
        handle_session_command("/session new")
        config.pin_current_session_name(name)  # resume the renamed session
        assert config.auto_save_session_if_enabled()
    entry = next(
        e for e in build_entries(tmp_path) if e.name == name
    )  # restart: fresh disk read
    assert entry.title == "Pinned title" and has_user_title(entry.meta)
    assert ensure_titles(tmp_path, entry) is False
