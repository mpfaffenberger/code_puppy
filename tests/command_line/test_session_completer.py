"""Tab completion for /session subcommands."""

import pytest
from termflow.tui.completion import Document

from code_puppy.command_line.completers import SessionCompleter, build_completer_stack


def _texts(completer, text: str) -> list[str]:
    document = Document(text=text, cursor_position=len(text))
    return [completion.text for completion in completer.get_completions(document, None)]


@pytest.mark.parametrize(
    ("trigger", "text", "expected"),
    [
        ("/session", "/session ", ["id", "new", "rename"]),
        ("/session", "/session re", ["rename"]),
        ("/session", "  /session n", ["new"]),
        ("/s", "/s re", ["rename"]),
        ("/session", "/session rename My", []),
        ("/session", "/session", []),
        ("/session", "/sessions ", []),
        ("/session", "/session Re", []),
    ],
)
def test_session_subcommand_completion(trigger, text, expected):
    assert _texts(SessionCompleter(trigger=trigger), text) == expected


def test_completion_replaces_only_the_partial_word():
    document = Document(text="/session ren", cursor_position=len("/session ren"))
    (completion,) = SessionCompleter().get_completions(document, None)
    assert completion.start_position == -3


def test_repl_stack_completes_session_rename():
    assert "rename" in _texts(build_completer_stack(), "/session re")
