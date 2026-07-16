"""Tests for the process-local ``--yolo`` override."""

import argparse
from unittest.mock import patch

import pytest

from code_puppy import config
from code_puppy.plugins.yolo_cli import register_callbacks as yolo_cli


@pytest.fixture(autouse=True)
def reset_cli_yolo_override():
    config.set_cli_yolo_override(None)
    yield
    config.set_cli_yolo_override(None)


def _parse(*arguments: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    yolo_cli._register_cli_args(parser)
    return parser.parse_args(arguments)


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("false", False)])
def test_cli_flag_sets_runtime_override_without_writing_config(raw, expected):
    args = _parse("--yolo", raw)

    with patch("code_puppy.config.set_config_value") as set_config:
        assert yolo_cli._handle_cli_args(args) is None

    assert config.get_cli_yolo_override() is expected
    set_config.assert_not_called()


def test_omitted_cli_flag_does_not_override_persisted_config():
    with patch("code_puppy.config.get_value", return_value="false"):
        yolo_cli._handle_cli_args(_parse())
        assert config.get_yolo_mode() is False


@pytest.mark.parametrize("raw", ["yes", "1", "maybe", ""])
def test_cli_flag_rejects_non_boolean_values(raw):
    with pytest.raises(SystemExit) as exc_info:
        _parse("--yolo", raw)

    assert exc_info.value.code == 2


@pytest.mark.parametrize(
    ("persisted", "cli_value", "expected"),
    [("false", True, True), ("true", False, False)],
)
def test_cli_override_takes_precedence_over_config(persisted, cli_value, expected):
    config.set_cli_yolo_override(cli_value)

    with patch("code_puppy.config.get_value", return_value=persisted):
        assert config.get_yolo_mode() is expected
