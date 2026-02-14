from __future__ import annotations

from prompt_toolkit.document import Document

from code_puppy.command_line.skills_completion import SkillsCompleter


def test_skills_completer_does_not_trigger_without_space() -> None:
    completer = SkillsCompleter()
    doc = Document("/skills")
    completions = list(completer.get_completions(doc, None))
    assert completions == []


def test_skills_completer_shows_subcommands_on_space() -> None:
    completer = SkillsCompleter()
    doc = Document("/skills ")
    completions = list(completer.get_completions(doc, None))

    values = {c.text for c in completions}
    assert values == {"list", "install", "enable", "disable", "tui"}


def test_skills_completer_filters_partial_subcommand() -> None:
    completer = SkillsCompleter()
    doc = Document("/skills en")
    completions = list(completer.get_completions(doc, None))

    assert [c.text for c in completions] == ["enable"]


def test_skills_completer_install_completes_bundled_skill_ids(monkeypatch) -> None:
    # Mock catalog load so tests don't depend on filesystem.
    monkeypatch.setattr(
        "code_puppy.command_line.skills_completion.load_bundled_skill_ids",
        lambda: ["data-exploration", "pdf", "contract-review"],
    )

    completer = SkillsCompleter()

    # `/skills install ` -> show all ids
    doc = Document("/skills install ")
    completions = list(completer.get_completions(doc, None))
    values = {c.text for c in completions}
    assert values == {"data-exploration", "pdf", "contract-review"}

    # `/skills install da` -> filtered
    doc = Document("/skills install da")
    completions = list(completer.get_completions(doc, None))
    assert [c.text for c in completions] == ["data-exploration"]
