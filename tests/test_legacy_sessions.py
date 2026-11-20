"""Code Puppy 0.0.x sessions in the runtime's ``/resume``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from code_puppy import legacy_sessions as legacy

HISTORY: list[ModelMessage] = [
    ModelRequest(
        parts=[
            SystemPromptPart("You are Boodler. Use agent_run_shell_command."),
            UserPromptPart("list the files"),
        ],
        instructions="0.0.x instructions",
    ),
    ModelResponse(
        parts=[ToolCallPart("list_files", {"directory": "."}, tool_call_id="call-1")]
    ),
    ModelRequest(parts=[ToolReturnPart("list_files", "a.py", tool_call_id="call-1")]),
    ModelResponse(parts=[TextPart("There is one file: a.py")]),
    ModelRequest(
        parts=[UserPromptPart("now delete it")], instructions="0.0.x instructions"
    ),
    # Interrupted here: this call never got a result.
    ModelResponse(
        parts=[
            ToolCallPart("delete_file", {"file_path": "a.py"}, tool_call_id="call-2")
        ]
    ),
]


def write_session(
    root: Path,
    name: str,
    history: list[ModelMessage] | None = None,
    *,
    encoding: str = "pydantic-ai-messages",
    **meta: Any,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    messages = ModelMessagesTypeAdapter.dump_python(
        HISTORY if history is None else history, mode="json"
    )
    envelope = {
        "format": 2,
        "code_puppy": "0.0.969",
        "pydantic_ai": "2.64.0",
        "encoding": encoding,
        "messages": messages,
    }
    path = root / f"{name}.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    sidecar = {
        "session_name": name,
        "timestamp": "2026-11-01T09:30:00",
        "message_count": len(messages),
        **meta,
    }
    (root / f"{name}_meta.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return path


@pytest.fixture
def autosaves(home: Path) -> Path:
    return home / ".code_puppy" / "autosaves"


def texts(history: list[ModelMessage]) -> list[str]:
    """Every user and assistant text in order, for reading a history at a glance."""
    found: list[str] = []
    for message in history:
        for part in message.parts:
            if isinstance(part, TextPart):
                found.append(part.content)
            elif isinstance(part, UserPromptPart):
                content = part.content
                found.append(
                    content
                    if isinstance(content, str)
                    else str(getattr(content[0], "content", ""))
                )
    return found


# --- the files ---------------------------------------------------------------


def test_sessions_are_found_and_sidecars_are_not(autosaves: Path) -> None:
    write_session(autosaves, "auto_session_1")
    write_session(autosaves, "auto_session_2")
    (autosaves / "auto_session_2_acp.json").write_text("{}", encoding="utf-8")
    (autosaves / ".contexts_sweep_done").write_text("", encoding="utf-8")

    assert legacy.home() == autosaves
    assert sorted(path.stem for path in legacy.files(autosaves)) == [
        "auto_session_1",
        "auto_session_2",
    ]
    assert legacy.files(autosaves / "missing") == []


def test_find_takes_a_session_name_and_nothing_else(autosaves: Path) -> None:
    path = write_session(autosaves, "auto_session_1")
    assert legacy.find(autosaves, "auto_session_1") == path
    assert legacy.find(autosaves, "auto_session_1_meta") is None
    assert legacy.find(autosaves, "nope") is None
    assert legacy.find(autosaves, "../autosaves/auto_session_1") is None
    assert legacy.find(autosaves, "") is None


def test_header_comes_from_the_sidecar(autosaves: Path, tmp_path: Path) -> None:
    project = str(tmp_path / "project")
    named = legacy.header(
        write_session(autosaves, "s1", title="Fix the  parser\n", scope_key=project)
    )
    assert named is not None
    assert (named.native_id, named.title, named.cwd, named.named) == (
        "s1",
        "Fix the parser",
        project,
        True,
    )

    unnamed = legacy.header(write_session(autosaves, "s2"))
    assert unnamed is not None
    assert (unnamed.title, unnamed.named, unnamed.listed) == (
        "Session from 2026-11-01 09:30",
        False,
        True,
    )
    assert unnamed.cwd == str(Path.home())

    empty = legacy.header(write_session(autosaves, "s3", history=[]))
    assert empty is not None and empty.listed is False

    orphan = legacy.header(autosaves / "no_sidecar.json")
    assert orphan is not None and orphan.title == "no_sidecar"


# --- the history ---------------------------------------------------------------


def test_history_is_cleaned_and_framed(autosaves: Path) -> None:
    history = legacy.messages(write_session(autosaves, "auto_session_1"))

    kinds = [part.part_kind for message in history for part in message.parts]
    assert "system-prompt" not in kinds
    assert all(m.instructions is None for m in history if isinstance(m, ModelRequest))
    # The call that never got a result is gone; the answered one stays with its result.
    calls = [
        part.tool_name
        for m in history
        for part in m.parts
        if isinstance(part, ToolCallPart)
    ]
    assert calls == ["list_files"]

    said = texts(history)
    assert said[0].startswith(
        "This conversation was imported from Code Puppy 0.0.x session auto_session_1."
    )
    assert said[1:4] == ["list the files", "There is one file: a.py", "now delete it"]
    assert said[-1].startswith(
        "The conversation above was imported from Code Puppy 0.0.x"
    )
    assert isinstance(history[-1], ModelRequest)


def test_unreadable_or_foreign_envelopes_import_nothing(autosaves: Path) -> None:
    assert legacy.messages(write_session(autosaves, "s1", encoding="json")) == []
    assert legacy.messages(write_session(autosaves, "s2", history=[])) == []
    broken = autosaves / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert legacy.messages(broken) == []
    assert legacy.tasks(broken, "id") == []


def test_clean_drops_only_a_trailing_unanswered_call() -> None:
    answered = legacy.clean(HISTORY[:4])
    assert [part.part_kind for part in answered[0].parts] == ["user-prompt"]
    assert answered[1:] == HISTORY[1:4]  # an answered call and its result are kept
    assert len(legacy.clean(HISTORY)) == 5  # the trailing unanswered call is dropped
    assert legacy.clean([]) == []


# --- inside the runtime --------------------------------------------------------


def test_puppy_is_an_import_source_beside_claude_and_codex(
    installed_distribution: None,
) -> None:
    from pydantic_ai_pax.runtime import imported_sessions, sessions
    from pydantic_ai_pax.ui.menus import session_browser

    assert imported_sessions.IMPORT_SOURCES == ("claude", "codex", "puppy")
    assert sessions.IMPORT_SOURCES is imported_sessions.IMPORT_SOURCES
    assert imported_sessions.import_source("puppy") == "puppy"
    assert imported_sessions.source_label("puppy") == "Code Puppy 0.0.x"
    assert session_browser._FILTERS == (None, "clai", "claude", "codex", "puppy")


async def test_a_session_is_listed_then_copied_into_the_store_when_picked(
    installed_distribution: None, autosaves: Path, tmp_path: Path
) -> None:
    from pydantic_ai_harness.step_persistence.conversations import (
        SqliteConversationStore,
    )
    from pydantic_ai_pax.runtime.imported_sessions import (
        ImportCatalog,
        save_import,
        source_of,
    )

    project = tmp_path / "project"
    project.mkdir()
    write_session(
        autosaves, "auto_session_1", title="Delete a file", scope_key=str(project)
    )
    write_session(autosaves, "auto_session_empty", history=[])

    catalog = ImportCatalog(("puppy",))
    (summary,) = catalog.listing()
    assert summary.title == "Delete a file"
    assert summary.subtitle == "Code Puppy 0.0.x session auto_session_1"
    assert summary.workspace == str(project.resolve())
    assert summary.tags == ("puppy",) and source_of(summary) == "puppy"

    store = SqliteConversationStore(database=tmp_path / "sessions.db")
    imported = catalog.get(summary.id)
    assert imported is not None
    conversation_id = await save_import(store, imported)
    saved = await store.get(conversation_id=conversation_id)
    assert texts(list(saved.messages))[1] == "list the files"
    # Picking it again refreshes the same copy instead of adding another.
    assert await save_import(store, imported) == conversation_id
    assert len(await store.listing()) == 1
