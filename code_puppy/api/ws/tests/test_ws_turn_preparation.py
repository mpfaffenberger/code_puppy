from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from code_puppy.api.ws.ws_turn_preparation import prepare_turn_input


def test_prepare_turn_input_injects_directory_and_collects_attachments(
    monkeypatch,
    tmp_path,
):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello world", encoding="utf-8")

    monkeypatch.setattr(
        "code_puppy.api.ws.ws_turn_preparation.build_file_context_and_attachments",
        lambda msg: ("FILE CONTEXT", ["binary-1"]),
    )

    agent = MagicMock()
    prepared = prepare_turn_input(
        agent=agent,
        user_message="Analyze this",
        msg={"attachments": [str(text_file), "", None, str(tmp_path / "missing.txt")]},
        session_working_directory="/tmp/project",
        last_context_sent_directory="",
    )

    assert agent.append_to_message_history.call_count == 1
    assert prepared.last_context_sent_directory == "/tmp/project"
    assert prepared.message_to_send == "FILE CONTEXT\n\nAnalyze this"
    assert prepared.run_kwargs == {"attachments": ["binary-1"]}
    assert prepared.attachment_metadata == [
        {
            "name": "notes.txt",
            "path": str(Path(text_file).absolute()),
            "sizeBytes": text_file.stat().st_size,
        }
    ]


def test_prepare_turn_input_is_noop_when_directory_unchanged(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.api.ws.ws_turn_preparation.build_file_context_and_attachments",
        lambda msg: ("", []),
    )

    agent = MagicMock()
    prepared = prepare_turn_input(
        agent=agent,
        user_message="Hello",
        msg={},
        session_working_directory="/tmp/project",
        last_context_sent_directory="/tmp/project",
    )

    agent.append_to_message_history.assert_not_called()
    assert prepared.last_context_sent_directory == "/tmp/project"
    assert prepared.message_to_send == "Hello"
    assert prepared.run_kwargs == {}
    assert prepared.attachment_metadata == []
