"""Regression tests: /load_context completion must list what /load_context can load."""

from pathlib import Path
from unittest.mock import patch

from termflow.tui.completion import Document

from code_puppy.command_line.load_context_completion import LoadContextCompleter
from code_puppy.session_storage import save_session

_MODULE = "code_puppy.command_line.load_context_completion"


def _save(base_dir: Path, name: str) -> None:
    save_session(
        history=[],
        session_name=name,
        base_dir=base_dir,
        timestamp="2024-01-01T00:00:00",
        token_estimator=lambda _message: 0,
    )


def _complete(autosave_dir: Path, text: str) -> list[str]:
    """Complete ``text`` with AUTOSAVE_DIR pointed at ``autosave_dir``.

    The legacy ``CONFIG_DIR/contexts`` lookup is pointed at ``autosave_dir.parent``.
    ``create=True`` because the module no longer imports CONFIG_DIR: a regression to
    the legacy lookup then fails on wrong suggestions, not on a missing attribute.
    """
    document = Document(text, cursor_position=len(text))
    with (
        patch(f"{_MODULE}.AUTOSAVE_DIR", str(autosave_dir), create=True),
        patch(f"{_MODULE}.CONFIG_DIR", str(autosave_dir.parent), create=True),
    ):
        return [c.text for c in LoadContextCompleter().get_completions(document, None)]


# Scenario: a snapshot is saved where /dump_context writes (AUTOSAVE_DIR).
# Expected: /load_context <TAB> suggests it, since that is where it will load from.
def test_suggests_sessions_saved_in_autosave_dir(tmp_path: Path) -> None:
    autosave_dir = tmp_path / "autosaves"
    _save(autosave_dir, "my_snapshot")

    assert _complete(autosave_dir, "/load_context ") == ["my_snapshot"]


# Scenario: the user has typed a partial name.
# Expected: only snapshots starting with that prefix are suggested.
def test_filters_suggestions_by_typed_prefix(tmp_path: Path) -> None:
    autosave_dir = tmp_path / "autosaves"
    _save(autosave_dir, "alpha")
    _save(autosave_dir, "beta")

    assert _complete(autosave_dir, "/load_context al") == ["alpha"]


# Scenario: a session sits in the legacy CONFIG_DIR/contexts that /load_context ignores.
# Expected: it is not suggested, since selecting it would fail to load.
def test_does_not_suggest_sessions_from_legacy_contexts_dir(tmp_path: Path) -> None:
    autosave_dir = tmp_path / "autosaves"
    _save(autosave_dir, "my_snapshot")
    _save(tmp_path / "contexts", "stale_ghost")

    assert _complete(autosave_dir, "/load_context ") == ["my_snapshot"]
