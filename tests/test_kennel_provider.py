"""Neutral provider seam for kennel memory recall."""

import code_puppy.kennel_provider as kennel_provider


def test_returns_empty_without_provider(monkeypatch):
    monkeypatch.setattr(kennel_provider, "on_register_kennel_memory", lambda: [])
    assert kennel_provider.get_kennel_recall_block() == ""


def test_returns_block_from_first_provider(monkeypatch):
    monkeypatch.setattr(
        kennel_provider,
        "on_register_kennel_memory",
        lambda: [lambda: "first", lambda: "second"],
    )
    assert kennel_provider.get_kennel_recall_block() == "first"


def test_swallows_provider_errors(monkeypatch):
    def first() -> str | None:
        raise RuntimeError("db on fire")

    monkeypatch.setattr(kennel_provider, "on_register_kennel_memory", lambda: [first])
    assert kennel_provider.get_kennel_recall_block() == ""
