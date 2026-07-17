from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.sandbox.backends import (
    BubblewrapBackend,
    ContainerBackend,
    MacOSSandboxBackend,
    NoneBackend,
    SandboxUnavailable,
    get_sandbox_backend,
    prepare_shell_command,
)
from code_puppy.plugins.sandbox_exec.register_callbacks import (
    sandbox_availability_policy,
)


def test_none_backend_uses_platform_shell_without_claiming_isolation(tmp_path: Path):
    prepared = NoneBackend().prepare("echo hi", str(tmp_path))
    assert prepared.sandboxed is False
    assert prepared.backend == "none"
    assert prepared.argv[-1] == "echo hi"


def test_bubblewrap_mounts_only_workspace_writable_and_disables_network(tmp_path: Path):
    prepared = BubblewrapBackend().prepare("pytest", str(tmp_path))
    assert prepared.sandboxed is True
    assert "--unshare-all" in prepared.argv
    assert (
        "--bind",
        str(tmp_path.resolve()),
        str(tmp_path.resolve()),
    ) == prepared.argv[
        prepared.argv.index("--bind") : prepared.argv.index("--bind") + 3
    ]


def test_macos_profile_denies_network_and_limits_writes(tmp_path: Path):
    prepared = MacOSSandboxBackend().prepare("git status", str(tmp_path))
    profile = prepared.argv[2]
    assert "(deny network*)" in profile
    assert str(tmp_path.resolve()) in profile


def test_container_backend_has_no_network_and_mounts_workspace(tmp_path: Path):
    backend = ContainerBackend(runtime="docker", image="test-image")
    prepared = backend.prepare("pytest", str(tmp_path))
    assert prepared.argv[:5] == ("docker", "run", "--rm", "--network", "none")
    assert "type=bind" in next(arg for arg in prepared.argv if "type=bind" in arg)
    assert "test-image" in prepared.argv


def test_backend_selection_is_explicit():
    assert get_sandbox_backend("none").name == "none"
    assert get_sandbox_backend("bubblewrap").name == "bubblewrap"
    assert get_sandbox_backend("sandbox_exec").name == "sandbox_exec"
    assert get_sandbox_backend("container").name == "container"
    with pytest.raises(ValueError):
        get_sandbox_backend("mystery")


def test_unavailable_backend_fails_closed_unless_approved(tmp_path: Path):
    backend = BubblewrapBackend()
    with (
        patch("code_puppy.sandbox.backends.get_sandbox_backend", return_value=backend),
        patch.object(backend, "available", return_value=False),
    ):
        with pytest.raises(SandboxUnavailable):
            prepare_shell_command("echo hi", str(tmp_path))
        fallback = prepare_shell_command(
            "echo hi", str(tmp_path), allow_unsandboxed_fallback=True
        )
    assert fallback.backend == "none"
    assert fallback.sandboxed is False


def test_unavailable_configured_backend_requests_explicit_fallback_approval():
    backend = BubblewrapBackend()
    with (
        patch(
            "code_puppy.plugins.sandbox_exec.register_callbacks.get_sandbox_backend",
            return_value=backend,
        ),
        patch.object(backend, "available", return_value=False),
    ):
        result = sandbox_availability_policy(None, "echo hi")
    assert result["requires_approval"] is True
    assert result["sandbox_fallback"] is True
