"""Tests for path policy (Epic 3 / P0-05)."""

import pytest

from code_puppy.tools.path_policy import (
    Operation,
    check_path_allowed,
    classify_path,
    resolve_user_path,
)


class TestPathPolicyBasics:
    def test_resolve_user_path_expands_tilde(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        resolved = resolve_user_path("~/foo.txt")
        assert resolved == tmp_path / "foo.txt"

    def test_classify_path_inside_workspace(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert classify_path(tmp_path / "foo.py")["inside_workspace"] is True

    def test_classify_path_outside_workspace(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "outside" / "foo.py"
        assert classify_path(outside)["inside_workspace"] is False

    def test_classify_path_sensitive_by_basename(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert classify_path(tmp_path / ".env")["sensitive"] is True
        assert classify_path(tmp_path / "id_rsa")["sensitive"] is True

    def test_classify_path_not_sensitive(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert classify_path(tmp_path / "main.py")["sensitive"] is False


class TestCheckPathAllowed:
    def test_normal_workspace_read_allowed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "foo.py").write_text("hello")
        decision = check_path_allowed("foo.py", Operation.READ)
        assert decision.allowed is True

    def test_read_sensitive_file_denied_without_approval(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("secret")
        decision = check_path_allowed(".env", Operation.READ)
        assert decision.allowed is False
        assert "sensitive" in (decision.reason or "").lower()

    def test_grep_sensitive_directory_denied_without_approval(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        decision = check_path_allowed(str(tmp_path / ".ssh"), Operation.SEARCH)
        assert decision.allowed is False
        assert "sensitive" in (decision.reason or "").lower()

    def test_write_outside_workspace_denied_without_approval(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "outside.txt"
        decision = check_path_allowed(str(outside), Operation.WRITE)
        assert decision.allowed is False
        assert "outside" in (decision.reason or "").lower()

    def test_delete_outside_workspace_denied_without_approval(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        outside = tmp_path.parent / "outside.txt"
        decision = check_path_allowed(str(outside), Operation.DELETE)
        assert decision.allowed is False
        assert "outside" in (decision.reason or "").lower()

    def test_approved_sensitive_read_allowed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        env_path = tmp_path / ".env"
        env_path.write_text("secret")
        decision = check_path_allowed(
            str(env_path), Operation.READ, approved_sensitive=[str(env_path.resolve())]
        )
        assert decision.allowed is True

    def test_symlink_escape_detected_for_write(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path.parent / "escapes.txt"
        target.write_text("target")
        link = tmp_path / "link.txt"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlink creation not supported")
        decision = check_path_allowed(str(link), Operation.WRITE)
        # symlink outside workspace should be denied for writes
        assert decision.allowed is False

    def test_policy_denial_does_not_read_file_content(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        secret = tmp_path / ".env"
        secret.write_text("SECRET_CONTENT_12345")
        decision = check_path_allowed(str(secret), Operation.READ)
        assert decision.allowed is False
        assert "SECRET_CONTENT" not in (decision.reason or "")
