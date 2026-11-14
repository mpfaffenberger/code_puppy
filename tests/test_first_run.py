"""The first-launch naming ritual: asked once, of a person, before the session."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from code_puppy import first_run
from code_puppy.personality import FACTORY, PLUGIN_ID, PersonalitySettings


@pytest.fixture
def store(home: Path, installed_distribution: None) -> Any:
    from pydantic_clai2.config.settings_store import SettingsStore

    return SettingsStore()


def scripted(*lines: str | None) -> tuple[Callable[[str], str | None], list[str]]:
    """A reader that answers from ``lines``, and the questions it was shown."""
    answers: Iterator[str | None] = iter(lines)
    asked: list[str] = []

    def read(question: str) -> str | None:
        asked.append(question)
        return next(answers)

    return read, asked


def saved_names(store: Any) -> dict[str, Any]:
    (declaration,) = [p for p in store.plugins() if p.id == PLUGIN_ID]
    return dict(declaration.settings)


def declare(store: Any, **fields: Any) -> None:
    from pydantic_clai2.config import PluginSettings

    store.save_plugin(PluginSettings(id=PLUGIN_ID, factory=FACTORY, **fields))


def test_a_fresh_install_is_asked_both_0_0_x_questions(store: Any) -> None:
    read, asked = scripted("Boodler\n", "  Mike  \n")
    said: list[str] = []

    names = first_run.welcome(store, read=read, write=said.append)

    assert asked == [
        "What should we name the puppy? [Puppy]",
        "What's your name (so Code Puppy knows its owner)? [Master]",
    ]
    assert names == PersonalitySettings(puppy_name="Boodler", owner_name="Mike")
    assert saved_names(store) == {"puppy_name": "Boodler", "owner_name": "Mike"}
    assert said[0] == first_run.INTRO
    assert said[-1] == (
        "Meet Boodler, Mike's puppy. "
        "Change either name any time with /plugins configure personality."
    )


def test_it_only_asks_once(store: Any) -> None:
    read, _ = scripted("Boodler\n", "Mike\n")
    first_run.welcome(store, read=read, write=lambda _: None)

    never, asked = scripted()
    assert first_run.welcome(store, read=never, write=lambda _: None) is None
    assert asked == []


def test_enter_keeps_a_default_and_still_counts_as_answered(store: Any) -> None:
    read, _ = scripted("\n", "Mike\n")
    first_run.welcome(store, read=read, write=lambda _: None)

    assert saved_names(store) == {"puppy_name": "Puppy", "owner_name": "Mike"}
    assert first_run.unanswered(store) == ()


def test_backing_out_keeps_the_defaults_and_is_not_asked_again(store: Any) -> None:
    read, asked = scripted(None)
    first_run.welcome(store, read=read, write=lambda _: None)

    assert len(asked) == 1, "the second question is not put to someone who backed out"
    assert saved_names(store) == {"puppy_name": "Puppy", "owner_name": "Master"}
    assert first_run.unanswered(store) == ()


def test_a_name_the_settings_reject_is_asked_again(store: Any) -> None:
    read, asked = scripted("x" * 81 + "\n", "Boodler\n", "Mike\n")
    said: list[str] = []

    first_run.welcome(store, read=read, write=said.append)

    assert len(asked) == 3
    assert any(line.startswith("That will not work: ") for line in said)
    assert saved_names(store)["puppy_name"] == "Boodler"


def test_names_carried_over_from_0_0_x_are_not_asked_for(store: Any) -> None:
    declare(store, settings={"puppy_name": "Boodler", "owner_name": "Mike"})

    assert first_run.unanswered(store) == ()


def test_only_the_missing_name_is_asked_for(store: Any) -> None:
    declare(store, settings={"puppy_name": "Boodler"})
    read, asked = scripted("Mike\n")

    first_run.welcome(store, read=read, write=lambda _: None)

    assert asked == ["What's your name (so Code Puppy knows its owner)? [Master]"]
    assert saved_names(store) == {"puppy_name": "Boodler", "owner_name": "Mike"}


def test_a_disabled_personality_is_left_alone(store: Any) -> None:
    declare(store, enabled=False)
    never, asked = scripted()

    assert first_run.welcome(store, read=never, write=lambda _: None) is None
    assert asked == []
    assert saved_names(store) == {}


@pytest.mark.parametrize(
    ("typed", "expected"), [("Boodler\n", "Boodler\n"), ("", None), ("Boo", None)]
)
def test_read_line_asks_on_stdout_and_reports_end_of_input(
    typed: str,
    expected: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(typed))

    assert first_run.read_line("Name?") == expected

    captured = capsys.readouterr()
    assert captured.out.startswith("Name? ")
    assert captured.err == "", "stderr is relayed elsewhere while a session starts"


def test_ctrl_c_at_a_question_backs_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Interrupted(io.StringIO):
        def readline(self, *args: Any) -> str:
            raise KeyboardInterrupt

    monkeypatch.setattr("sys.stdin", Interrupted())

    assert first_run.read_line("Name?") is None
    assert capsys.readouterr().out == "Name? \n"


# --- wired into the launch -------------------------------------------------


@pytest.fixture
def launch(
    store: Any, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., dict[str, Any]]:
    """Start a session through the installed ``chat``, with clai2's own stubbed out.

    ``Rex`` and ``Sam`` are waiting on stdin. Returns what clai2's ``chat`` was given.
    """
    from pydantic_clai2 import app

    from code_puppy import distribution

    given: dict[str, Any] = {}
    monkeypatch.setattr(
        app, "chat", lambda agent, **kw: given.update(agent=agent, **kw)
    )
    distribution._install_first_run()  # wraps the stub; monkeypatch restores `app.chat`
    monkeypatch.setattr("sys.stdin", io.StringIO("Rex\nSam\n"))

    def start(*, terminal: bool, **options: Any) -> dict[str, Any]:
        monkeypatch.setattr(first_run, "at_a_terminal", lambda: terminal)
        app.chat("the agent", store=store, **options)
        return given

    return start


def test_an_interactive_launch_names_the_puppy_then_starts_the_session(
    launch: Callable[..., dict[str, Any]],
    store: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    given = launch(terminal=True, resume="abc")

    assert given == {"agent": "the agent", "store": store, "resume": "abc"}
    assert saved_names(store) == {"puppy_name": "Rex", "owner_name": "Sam"}
    assert "Meet Rex, Sam's puppy." in capsys.readouterr().out


def test_piped_input_is_not_asked_and_is_asked_next_time(
    launch: Callable[..., dict[str, Any]],
    store: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    given = launch(terminal=False)

    assert given["agent"] == "the agent"
    assert capsys.readouterr().out == ""
    assert first_run.unanswered(store) == tuple(first_run.QUESTIONS)


def test_a_caller_supplied_agent_is_not_asked(
    launch: Callable[..., dict[str, Any]],
    store: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    given = launch(terminal=True, load_plugins=False)

    assert given["load_plugins"] is False
    assert capsys.readouterr().out == ""


def test_a_failure_while_naming_does_not_stop_the_launch(
    launch: Callable[..., dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken(store: Any) -> None:
        raise OSError("database is locked")

    monkeypatch.setattr(first_run, "welcome", broken)

    given = launch(terminal=True)

    assert given["agent"] == "the agent"
    assert capsys.readouterr().err == (
        "Skipped naming the puppy (OSError: database is locked). "
        "Use /plugins configure personality instead.\n"
    )
