"""Tests for hook configuration validator."""

import pytest

from code_puppy.hook_engine.validator import (
    format_validation_report,
    validate_hooks_config,
)

_CMD = {"type": "command", "command": "echo test"}


def _cfg(**event_map):
    """Event map of {event: rules}; each rule may be a dict or list of hook dicts."""
    out = {}
    for event, rules in event_map.items():
        if isinstance(rules, list) and rules and isinstance(rules[0], dict):
            out[event] = [{"matcher": "*", "hooks": rules}]
        else:
            out[event] = rules
    return out


# (name, config, expected_valid, error-substring when invalid)
_VALIDATION_CASES = [
    ("valid_pre_tool_use", _cfg(PreToolUse=[_CMD]), True, None),
    (
        "valid_post_tool_use",
        {
            "PostToolUse": [
                {
                    "matcher": "Edit",
                    "hooks": [{"type": "command", "command": "black ${file}"}],
                }
            ]
        },
        True,
        None,
    ),
    ("invalid_event_type", {"BadEvent": []}, False, "BadEvent"),
    ("missing_matcher", {"PreToolUse": [{"hooks": [_CMD]}]}, False, "matcher"),
    ("missing_hooks", {"PreToolUse": [{"matcher": "*"}]}, False, "hooks"),
    (
        "invalid_hook_type",
        {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "invalid", "command": "echo test"}]}]},
        False,
        "invalid",
    ),
    (
        "missing_command",
        {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command"}]}]},
        False,
        "command",
    ),
    (
        "timeout_too_low",
        {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo test", "timeout": 50}]}
            ]
        },
        False,
        "timeout",
    ),
    # A _comment key is skipped, the rest still validates.
    ("skip_comment_keys", {"_comment": "This is a comment", **_cfg(PreToolUse=[_CMD])}, True, None),
    ("non_dict_config", [], False, None),
    (
        "valid_prompt_hook",
        {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "prompt", "prompt": "validate this"}]}
            ]
        },
        True,
        None,
    ),
    (
        "multiple_event_types",
        {
            "PreToolUse": [{"matcher": "*", "hooks": [_CMD]}],
            "PostToolUse": [
                {"matcher": "Edit", "hooks": [{"type": "command", "command": "echo post"}]}
            ],
        },
        True,
        None,
    ),
]


@pytest.mark.parametrize(
    "name,config,expected_valid,keyword",
    _VALIDATION_CASES,
    ids=[c[0] for c in _VALIDATION_CASES],
)
def test_validate_hooks_config(name, config, expected_valid, keyword):
    is_valid, errors = validate_hooks_config(config)
    assert is_valid is expected_valid
    if keyword is not None:
        assert any(keyword in e for e in errors)


class TestFormatValidationReport:
    def test_valid_report(self):
        report = format_validation_report(True, [])
        assert "valid" in report.lower()

    def test_invalid_report(self):
        report = format_validation_report(False, ["error 1", "error 2"])
        assert "error 1" in report
        assert "error 2" in report

    def test_report_with_suggestions(self):
        report = format_validation_report(False, ["error"], ["try this"])
        assert "try this" in report
