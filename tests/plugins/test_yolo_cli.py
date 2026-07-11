"""Tests for the runtime-only YOLO CLI override."""

import argparse
from types import SimpleNamespace

import pytest

from code_puppy import config
from code_puppy.plugins.yolo_cli.register_callbacks import (
    _handle_cli_args,
    _register_cli_args,
)


@pytest.fixture(autouse=True)
def clear_override():
    config.set_yolo_mode_override(None)
    yield
    config.set_yolo_mode_override(None)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    _register_cli_args(parser)
    return parser


@pytest.mark.parametrize(("text", "expected"), [("true", True), ("false", False)])
def test_explicit_boolean_values_override_config(monkeypatch, text, expected):
    monkeypatch.setattr(config, "get_value", lambda _key: not expected)

    args = _parser().parse_args(["--yolo", text])
    _handle_cli_args(args)

    assert config.get_yolo_mode() is expected


def test_omitted_option_preserves_config(monkeypatch):
    monkeypatch.setattr(config, "get_value", lambda _key: "false")

    _handle_cli_args(_parser().parse_args([]))

    assert config.get_yolo_mode() is False


def test_handler_tolerates_namespace_without_yolo(monkeypatch):
    monkeypatch.setattr(config, "get_value", lambda _key: "true")

    _handle_cli_args(SimpleNamespace())

    assert config.get_yolo_mode() is True


def test_invalid_boolean_has_useful_error(capsys):
    with pytest.raises(SystemExit):
        _parser().parse_args(["--yolo", "maybe"])

    assert "expected 'true' or 'false'" in capsys.readouterr().err


def test_help_documents_precedence():
    help_text = _parser().format_help()

    assert "--yolo {true,false}" in help_text
    assert "overrides" in help_text
    assert "puppy.cfg" in help_text
