"""Completion-provider seam and Ollama plugin registration tests."""

from termflow.tui.completion import Completer, Completion, Document

from code_puppy import callbacks
from code_puppy.messaging.editor_completion import build_completer


class PluginCompleter(Completer):
    def get_completions(self, document, complete_event):
        if document.text_before_cursor == "/plugin":
            yield Completion("-command", start_position=0)


def _completion_texts(completer, text):
    return {
        item.text
        for item in completer.get_completions(
            Document(text, cursor_position=len(text)), None
        )
    }


def test_build_completer_works_without_plugin_providers(monkeypatch):
    monkeypatch.setitem(callbacks._callbacks, "register_completion_provider", [])

    completer = build_completer()

    assert "-command" not in _completion_texts(completer, "/plugin")


def test_build_completer_includes_registered_provider(monkeypatch):
    monkeypatch.setitem(callbacks._callbacks, "register_completion_provider", [])
    callbacks.register_callback("register_completion_provider", PluginCompleter)

    completer = build_completer()

    assert "-command" in _completion_texts(completer, "/plugin")


def test_ollama_plugin_registers_completion_provider(monkeypatch):
    monkeypatch.setitem(callbacks._callbacks, "register_completion_provider", [])
    from code_puppy_core_plugins.ollama_setup.register_callbacks import (
        _completion_provider,
    )

    callbacks.register_callback("register_completion_provider", _completion_provider)

    assert "glm-5:cloud" in _completion_texts(
        callbacks.get_completion_providers()[0], "/ollama-setup g"
    )
