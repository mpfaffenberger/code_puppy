"""Regression tests: /load_context completion must list what /load_context can load."""

from unittest.mock import patch

from termflow.tui.completion import Document

from code_puppy.command_line.load_context_completion import LoadContextCompleter
from code_puppy.session_storage import save_session


def _save(base_dir, name):
    save_session(
        history=[],
        session_name=name,
        base_dir=base_dir,
        timestamp="2024-01-01T00:00:00",
        token_estimator=lambda _message: 0,
    )


def _complete(text):
    document = Document(text, cursor_position=len(text))
    return [c.text for c in LoadContextCompleter().get_completions(document, None)]


# Scenario: a snapshot is saved where /dump_context writes (AUTOSAVE_DIR).
# Expected: /load_context <TAB> suggests it, since that is where it will load from.
def test_suggests_sessions_saved_in_autosave_dir(tmp_path):
    autosave_dir = tmp_path / "autosaves"
    _save(autosave_dir, "my_snapshot")

    with patch(
        "code_puppy.command_line.load_context_completion.AUTOSAVE_DIR",
        str(autosave_dir),
    ):
        assert _complete("/load_context ") == ["my_snapshot"]


# Scenario: the user has typed a partial name.
# Expected: only snapshots starting with that prefix are suggested.
def test_filters_suggestions_by_typed_prefix(tmp_path):
    autosave_dir = tmp_path / "autosaves"
    _save(autosave_dir, "alpha")
    _save(autosave_dir, "beta")

    with patch(
        "code_puppy.command_line.load_context_completion.AUTOSAVE_DIR",
        str(autosave_dir),
    ):
        assert _complete("/load_context al") == ["alpha"]
