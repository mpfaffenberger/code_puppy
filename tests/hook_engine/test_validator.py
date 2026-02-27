"""Tests for hook configuration validator."""

from code_puppy.hook_engine.validator import (
    format_validation_report,
    validate_hooks_config,
)


class TestValidateHooksConfig:
    def test_valid_pre_tool_use(self):
        config = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo test"}]}
            ]
        }
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is True
        assert errors == []

    def test_valid_post_tool_use(self):
        config = {
            "PostToolUse": [
                {
                    "matcher": "Edit",
                    "hooks": [{"type": "command", "command": "black ${file}"}],
                }
            ]
        }
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is True

    def test_invalid_event_type(self):
        config = {"BadEvent": []}
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is False
        assert any("BadEvent" in e for e in errors)

    def test_missing_matcher(self):
        config = {
            "PreToolUse": [{"hooks": [{"type": "command", "command": "echo test"}]}]
        }
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is False
        assert any("matcher" in e for e in errors)

    def test_missing_hooks(self):
        config = {"PreToolUse": [{"matcher": "*"}]}
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is False
        assert any("hooks" in e for e in errors)

    def test_invalid_hook_type(self):
        config = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "invalid", "command": "echo test"}]}
            ]
        }
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is False
        assert any("invalid" in e for e in errors)

    def test_missing_command(self):
        config = {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command"}]}]}
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is False
        assert any("command" in e for e in errors)

    def test_timeout_too_low(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "echo test", "timeout": 50}
                    ],
                }
            ]
        }
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is False
        assert any("timeout" in e for e in errors)

    def test_skip_comment_keys(self):
        config = {
            "_comment": "This is a comment",
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo test"}]}
            ],
        }
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is True

    def test_non_dict_config(self):
        is_valid, errors = validate_hooks_config([])
        assert is_valid is False

    def test_valid_prompt_hook(self):
        config = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "prompt", "prompt": "validate this"}],
                }
            ]
        }
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is True

    def test_multiple_event_types(self):
        config = {
            "PreToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "echo pre"}]}
            ],
            "PostToolUse": [
                {
                    "matcher": "Edit",
                    "hooks": [{"type": "command", "command": "echo post"}],
                }
            ],
        }
        is_valid, errors = validate_hooks_config(config)
        assert is_valid is True


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
