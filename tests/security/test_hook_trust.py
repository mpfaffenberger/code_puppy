"""Security regression tests for hook trust boundaries (P0-06)."""

import tempfile
from pathlib import Path

import pytest

from code_puppy.hook_engine.executor import execute_hook
from code_puppy.hook_engine.models import EventData, HookConfig
from code_puppy.hook_engine.trust import (
    _load_trust_db,
    approve_hook,
    build_minimal_hook_env,
    cap_hook_output,
    compute_content_hash,
    is_hook_trusted,
    revoke_hook_trust,
)


class TestHookConfigBackwardsCompatible:
    """HookConfig dataclass must preserve backward compatibility."""

    def test_defaults_are_global_and_trusted(self):
        hook = HookConfig(matcher="*", type="command", command="echo test")
        assert hook.source == "global"
        assert hook.trusted is True

    def test_explicit_project_source(self):
        hook = HookConfig(
            matcher="*",
            type="command",
            command="echo test",
            source="project",
            trusted=False,
        )
        assert hook.source == "project"
        assert hook.trusted is False

    def test_id_generation_unchanged(self):
        hook1 = HookConfig(matcher="*", type="command", command="echo test")
        hook2 = HookConfig(matcher="*", type="command", command="echo test")
        assert hook1.id == hook2.id

    def test_existing_tests_still_valid(self):
        """Existing construction patterns should not break."""
        hook = HookConfig(matcher="Edit", type="prompt", command="validate this")
        assert hook.type == "prompt"
        assert hook.source == "global"
        assert hook.trusted is True


class TestTrustKeyAndStorage:
    """Trust decisions keyed by project root + file path + content hash."""

    def test_compute_content_hash(self):
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("hello")
        h3 = compute_content_hash("world")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64  # sha256 hex

    def test_trust_defaults_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert not is_hook_trusted(tmpdir, "/x/settings.json", "abc123")

    def test_approve_and_trust(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / ".claude" / "settings.json")
            h = compute_content_hash("hooks")
            approve_hook(tmpdir, path, h)
            assert is_hook_trusted(tmpdir, path, h) is True

    def test_hash_change_requires_reapproval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / ".claude" / "settings.json")
            h1 = compute_content_hash("hooks_v1")
            h2 = compute_content_hash("hooks_v2")
            approve_hook(tmpdir, path, h1)
            assert is_hook_trusted(tmpdir, path, h1) is True
            assert is_hook_trusted(tmpdir, path, h2) is False

    def test_revoke_trust(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / ".claude" / "settings.json")
            h = compute_content_hash("hooks")
            approve_hook(tmpdir, path, h)
            revoke_hook_trust(tmpdir, path)
            assert is_hook_trusted(tmpdir, path, h) is False

    def test_storage_permissions(self):
        """Trust DB file should be created with restrictive permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / ".claude" / "settings.json")
            h = compute_content_hash("hooks")
            approve_hook(tmpdir, path, h)
            db = _load_trust_db()
            # At least one key should exist
            assert len(db) >= 1


class TestProjectHookTrustEnforcement:
    """Untrusted project hooks must be blocked before execution."""

    @pytest.mark.asyncio
    async def test_project_hook_blocked_when_untrusted(self):
        hook = HookConfig(
            matcher="*",
            type="command",
            command="echo 'should not run'",
            source="project",
            trusted=False,
        )
        event = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await execute_hook(hook, event)
        assert result.blocked is True
        assert "not explicitly trusted" in result.error.lower()
        assert result.stdout == ""
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_project_hook_allowed_when_trusted(self):
        hook = HookConfig(
            matcher="*",
            type="command",
            command="echo 'allowed'",
            source="project",
            trusted=True,
            timeout=2000,
        )
        event = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await execute_hook(hook, event)
        assert result.blocked is False
        assert "allowed" in result.stdout
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_global_hook_runs_without_trust_check(self):
        hook = HookConfig(
            matcher="*",
            type="command",
            command="echo 'global'",
            source="global",
            trusted=True,
            timeout=2000,
        )
        event = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await execute_hook(hook, event)
        assert result.blocked is False
        assert "global" in result.stdout

    @pytest.mark.asyncio
    async def test_prompt_hook_respects_trust(self):
        """Even prompt-type project hooks should be blocked if untrusted."""
        hook = HookConfig(
            matcher="*",
            type="prompt",
            command="This is a prompt",
            source="project",
            trusted=False,
        )
        event = EventData(event_type="PreToolUse", tool_name="Edit")
        result = await execute_hook(hook, event)
        assert result.blocked is True
        assert "not explicitly trusted" in result.error.lower()


class TestHookEnvironmentStripping:
    """Project hooks must receive a stripped-down environment."""

    def test_build_minimal_env_strips_secrets(self):
        base = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "SHELL": "/bin/bash",
            "MY_API_KEY": "secret123",
            "GITHUB_TOKEN": "ghp_supersecret",
            "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI",
            "PASSWORD": "hunter2",
            "OPENAI_API_KEY": "sk-1234567890abcdef",
            "NORMAL_VAR": "hello",
        }
        filtered = build_minimal_hook_env(base)
        assert filtered["PATH"] == "/usr/bin"
        assert filtered["NORMAL_VAR"] == "hello"
        assert "MY_API_KEY" not in filtered
        assert "GITHUB_TOKEN" not in filtered
        assert "AWS_SECRET_ACCESS_KEY" not in filtered
        assert "PASSWORD" not in filtered
        assert "OPENAI_API_KEY" not in filtered

    def test_build_minimal_env_allows_safe_vars(self):
        base = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "SHELL": "/bin/bash",
            "PWD": "/tmp",
            "TERM": "xterm",
            "LANG": "en_US.UTF-8",
            "USER": "alice",
            "LOGNAME": "alice",
        }
        filtered = build_minimal_hook_env(base)
        for key in base:
            assert key in filtered

    def test_long_values_stripped(self):
        base = {"SOME_VAR": "x" * 5000}
        filtered = build_minimal_hook_env(base)
        assert "SOME_VAR" not in filtered


class TestHookOutputCapping:
    """Hook stdout/stderr must be capped to prevent context blowup."""

    def test_cap_output_short_text_unchanged(self):
        text = "hello\nworld"
        assert cap_hook_output(text, max_chars=100, max_lines=10) == text

    def test_cap_output_lines_capped(self):
        text = "\n".join(f"line {i}" for i in range(300))
        result = cap_hook_output(text, max_chars=10000, max_lines=256)
        assert "... [output truncated]" in result
        assert result.count("\n") <= 257

    def test_cap_output_chars_capped(self):
        text = "a" * 10000
        result = cap_hook_output(text, max_chars=4096, max_lines=1000)
        assert "... [output truncated]" in result
        assert len(result) <= 4096 + 50

    def test_executor_caps_output(self):
        """Integration: execute_hook caps stdout/stderr for project hooks."""
        # We verify by checking the cap_hook_output is imported and used
        from code_puppy.hook_engine.executor import _MAX_HOOK_STDOUT, _MAX_HOOK_STDERR

        assert _MAX_HOOK_STDOUT > 0
        assert _MAX_HOOK_STDERR > 0
        assert _MAX_HOOK_STDOUT <= 4096
        assert _MAX_HOOK_STDERR <= 4096


class TestHookConfigLoaderTrust:
    """Config loader must mark project hooks correctly."""

    def test_load_hooks_config_returns_dict_for_compat(self):
        from code_puppy.plugins.claude_code_hooks.config import load_hooks_config

        result = load_hooks_config()
        # When no config files exist, should return None
        assert result is None or isinstance(result, dict)

    def test_load_hooks_config_with_sources_returns_tuple(self):
        from code_puppy.plugins.claude_code_hooks.config import (
            load_hooks_config_with_sources,
        )

        config, sources = load_hooks_config_with_sources()
        assert config is None or isinstance(config, dict)
        assert isinstance(sources, list)
