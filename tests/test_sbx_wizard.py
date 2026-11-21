"""Tests for sbx/wizard.py (stdlib-only script, imported by path)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

WIZARD_PATH = Path(__file__).resolve().parents[1] / "sbx" / "wizard.py"


@pytest.fixture
def wizard(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("sbx_wizard", WIZARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "OWNED_FILE", tmp_path / "owned-secrets.json")
    bindings = tmp_path / "credentials.yaml"
    monkeypatch.setattr(module, "bindings_path", lambda: bindings)
    return module


class FakeRun:
    def __init__(self, stdout: str = "", returncode: int = 0):
        self.calls: list[tuple[list[str], bool]] = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, cmd, *, dry, input_text=None, capture=True):
        self.calls.append((cmd, dry))
        if dry:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, "")

    def rm_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[:3] == ["sbx", "secret", "rm"]]


def _plan(**extra) -> dict:
    plan = {
        "credentials": [
            {
                "service": "anthropic",
                "env_var": "ANTHROPIC_API_KEY",
                "domain": "api.anthropic.com",
            }
        ],
        "oauth": [],
        "egress": ["api.anthropic.com"],
        "unsupported": [],
    }
    plan.update(extra)
    return plan


def test_fetch_plan_is_read_only(wizard, monkeypatch, capsys):
    fake = FakeRun(stdout=json.dumps(_plan(stale_sbx_secrets=["oldkey"])))
    monkeypatch.setattr(wizard, "run", fake)

    plan = wizard.fetch_plan("code-puppy", False)

    assert fake.calls == [(["code-puppy", "--setup", "sbx", "plan", "--json"], False)]
    assert plan["stale_sbx_secrets"] == ["oldkey"]
    assert "pruned" not in capsys.readouterr().out


def test_fetch_plan_dry_run_returns_empty_plan(wizard, monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(wizard, "run", fake)

    plan = wizard.fetch_plan("code-puppy", True)

    assert fake.calls[0][1] is True
    assert plan == {"credentials": [], "oauth": [], "egress": [], "unsupported": []}


def test_fetch_plan_without_stale_key(wizard, monkeypatch):
    monkeypatch.setattr(wizard, "run", FakeRun(stdout=json.dumps(_plan())))
    assert "stale_sbx_secrets" not in wizard.fetch_plan("code-puppy", False)


def test_prune_removes_only_owned_secrets(wizard, monkeypatch, capsys):
    wizard.save_owned({"secrets": ["oldkey"], "bindings": []})
    fake = FakeRun()
    monkeypatch.setattr(wizard, "run", fake)

    wizard.prune_owned_secrets(
        _plan(stale_sbx_secrets=["oldkey", "groq"]), dry=False, assume_yes=True
    )

    assert fake.rm_calls() == [["sbx", "secret", "rm", "oldkey", "-f"]]
    out = capsys.readouterr().out
    assert "sbx secret 'oldkey': pruned" in out
    assert "sbx secret 'groq': stale but not created by the wizard; kept" in out
    assert wizard.load_owned()["secrets"] == []


def test_prune_dry_run_previews_without_deleting(wizard, monkeypatch, capsys):
    wizard.save_owned({"secrets": ["oldkey"], "bindings": ["oldkey"]})
    fake = FakeRun()
    monkeypatch.setattr(wizard, "run", fake)

    wizard.prune_owned_secrets(
        _plan(stale_sbx_secrets=["oldkey"]), dry=True, assume_yes=True
    )

    assert fake.calls == []
    out = capsys.readouterr().out
    assert "[dry-run] sbx secret rm oldkey -f" in out
    assert "[dry-run] would remove binding for oldkey" in out
    assert wizard.load_owned()["secrets"] == ["oldkey"]


def test_prune_refuses_degenerate_plan(wizard, monkeypatch):
    wizard.save_owned({"secrets": ["oldkey"], "bindings": []})
    fake = FakeRun()
    monkeypatch.setattr(wizard, "run", fake)

    empty = {"credentials": [], "oauth": [], "egress": [], "unsupported": []}
    wizard.prune_owned_secrets(
        {**empty, "stale_sbx_secrets": ["oldkey"]}, dry=False, assume_yes=True
    )

    assert fake.rm_calls() == []


def test_prune_skips_when_plugin_reports_no_stale_key(wizard, monkeypatch):
    wizard.save_owned({"secrets": ["oldkey"], "bindings": []})
    fake = FakeRun()
    monkeypatch.setattr(wizard, "run", fake)

    wizard.prune_owned_secrets(_plan(), dry=False, assume_yes=True)

    assert fake.rm_calls() == []


def test_prune_declined_confirmation(wizard, monkeypatch):
    wizard.save_owned({"secrets": ["oldkey"], "bindings": []})
    fake = FakeRun()
    monkeypatch.setattr(wizard, "run", fake)
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    wizard.prune_owned_secrets(
        _plan(stale_sbx_secrets=["oldkey"]), dry=False, assume_yes=False
    )

    assert fake.rm_calls() == []
    assert wizard.load_owned()["secrets"] == ["oldkey"]


def test_binding_written_by_wizard_is_recorded_and_removed(wizard, monkeypatch):
    path = wizard.bindings_path()
    path.write_text(
        "bindings:\n  groq:\n    apiKey:\n      domains: [api.groq.com]\n",
        encoding="utf-8",
    )
    wizard.ensure_binding("oldkey", "api.old.example", dry=False)
    assert wizard.load_owned()["bindings"] == ["oldkey"]

    wizard.save_owned({"secrets": ["oldkey"], "bindings": ["oldkey"]})
    monkeypatch.setattr(wizard, "run", FakeRun())
    wizard.prune_owned_secrets(
        _plan(stale_sbx_secrets=["oldkey"]), dry=False, assume_yes=True
    )

    text = path.read_text(encoding="utf-8")
    assert "oldkey" not in text
    assert "  groq:\n    apiKey:\n      domains: [api.groq.com]\n" in text
    assert wizard.load_owned() == {"secrets": [], "bindings": []}


def test_ensure_secret_records_ownership_only_when_stored(wizard, monkeypatch):
    monkeypatch.setattr(wizard, "run", FakeRun())
    monkeypatch.setattr(wizard, "secret_stored", lambda _s: False)
    monkeypatch.setenv("FOO_API_KEY", "value")

    wizard.ensure_secret("foo", "FOO_API_KEY", dry=True)
    assert wizard.load_owned()["secrets"] == []

    wizard.ensure_secret("foo", "FOO_API_KEY", dry=False)
    assert wizard.load_owned()["secrets"] == ["foo"]

    monkeypatch.setattr(wizard, "secret_stored", lambda _s: True)
    wizard.ensure_secret("bar", "BAR_API_KEY", dry=False)
    assert "bar" not in wizard.load_owned()["secrets"]


def _stub_main_env(wizard, monkeypatch, fake):
    monkeypatch.setattr(wizard, "check_prereqs", lambda _o: "code-puppy")
    monkeypatch.setattr(wizard, "ensure_setup_cli", lambda _e: None)
    monkeypatch.setattr(wizard, "run", fake)
    monkeypatch.setattr(wizard, "ensure_secret", lambda *a: None)
    monkeypatch.setattr(wizard, "ensure_binding", lambda *a: None)
    monkeypatch.setattr(wizard, "build_creds_mixin", lambda *a: None)


def test_main_without_prune_never_deletes(wizard, monkeypatch):
    wizard.save_owned({"secrets": ["oldkey"], "bindings": []})
    fake = FakeRun(stdout=json.dumps(_plan(stale_sbx_secrets=["oldkey"])))
    _stub_main_env(wizard, monkeypatch, fake)

    assert wizard.main(["--stock-config"]) == 0
    assert fake.rm_calls() == []
    assert ["code-puppy", "--setup", "sbx", "plan", "--json"] in [
        c for c, _ in fake.calls
    ]


def test_main_dry_run_prune_reads_plan_to_preview(wizard, monkeypatch, capsys):
    wizard.save_owned({"secrets": ["oldkey"], "bindings": []})
    fake = FakeRun(stdout=json.dumps(_plan(stale_sbx_secrets=["oldkey"])))
    _stub_main_env(wizard, monkeypatch, fake)

    assert wizard.main(["--stock-config", "--prune", "--dry-run"]) == 0

    plan_calls = [
        c for c in fake.calls if c[0][:4] == ["code-puppy", "--setup", "sbx", "plan"]
    ]
    assert plan_calls == [(["code-puppy", "--setup", "sbx", "plan", "--json"], False)]
    assert fake.rm_calls() == []
    assert "[dry-run] sbx secret rm oldkey -f" in capsys.readouterr().out


def test_main_rejects_prune_with_no_creds(wizard):
    with pytest.raises(SystemExit):
        wizard.main(["--prune", "--no-creds"])
