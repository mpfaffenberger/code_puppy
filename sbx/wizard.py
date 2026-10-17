#!/usr/bin/env python3
"""Host-side wizard: turn your local Code Puppy setup into a sandbox.

Stdlib-only; run with any Python 3.11+ (``uvx`` not required)::

    python sbx/wizard.py --name my-pup --provider meta
    python sbx/wizard.py --dry-run            # show every step, change nothing

What it does, per provider transport (see setup_cli providers.py):

- ``proxy-managed-env`` (meta, API-key providers): makes sure the key
  is in the sbx secret store (piped via stdin, never printed) and the
  kit's use of it is approved in sbx's credentials.yaml. The minted
  Meta key is read from ~/.code_puppy/meta_oauth.json when present.
- ``auth-in-sandbox`` (copilot): nothing to prepare; you run the
  device-flow login inside the sandbox after creation.
- ``token-file-sync`` (claude-code, codex, grok; experimental): with
  --sync-tokens, copies the host OAuth token file into the sandbox
  after creation. The host stays the refresh owner; re-run with an
  existing sandbox name and --sync-tokens to refresh.

It then personalizes the config mixin from your real setup via
``code-puppy --setup export --sbx`` (secret-free), creates the
sandbox, and optionally smoke-tests it.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SBX_DIR = Path(__file__).resolve().parent
PERSONAL_DIR = SBX_DIR / ".personal" / "code-puppy-config"

PROXY_PROVIDERS = {
    # provider id -> (sbx service, env var, inject domain)
    "meta": ("meta", "META_API_KEY", "api.meta.ai"),
    "anthropic": ("anthropic", "ANTHROPIC_API_KEY", "api.anthropic.com"),
    "openai": ("openai", "OPENAI_API_KEY", "api.openai.com"),
    "gemini": ("gemini", "GEMINI_API_KEY", "generativelanguage.googleapis.com"),
    "openrouter": ("openrouter", "OPENROUTER_API_KEY", "openrouter.ai"),
}
TOKEN_SYNC_PROVIDERS = {
    "claude-code": "claude_code_oauth.json",
    "codex": "chatgpt_oauth.json",
    "grok": "grok_oauth.json",
}
IN_SANDBOX_PROVIDERS = {"copilot": "/copilot-login"}


class WizardError(Exception):
    pass


def run(
    cmd: list[str], *, dry: bool, input_text: str | None = None, capture: bool = True
) -> subprocess.CompletedProcess:
    shown = " ".join(cmd)
    if dry:
        print(f"[dry-run] {shown}" + ("  (stdin: <secret>)" if input_text else ""))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    print(f"$ {shown}")
    return subprocess.run(
        cmd, input=input_text, text=True, capture_output=capture, check=False
    )


def check_prereqs(override: str | None = None) -> str:
    if not shutil.which("sbx"):
        raise WizardError(
            "sbx not found on PATH (https://docs.docker.com/ai/sandboxes/install/)"
        )
    probe = subprocess.run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        raise WizardError("Docker daemon not reachable; start Docker Desktop first")
    if override:
        return override
    # Prefer the project environment this interpreter belongs to (running
    # under .venv\Scripts\python.exe puts code-puppy right beside it),
    # then the repo's .venv, then PATH, then an ephemeral uvx install.
    script = "code-puppy.exe" if os.name == "nt" else "code-puppy"
    for candidate in (
        Path(sys.executable).parent / script,
        SBX_DIR.parent / ".venv" / ("Scripts" if os.name == "nt" else "bin") / script,
    ):
        if candidate.is_file():
            return str(candidate)
    exe = shutil.which("code-puppy")
    if exe:
        return exe
    if shutil.which("uvx"):
        return "uvx code-puppy"  # split by caller via shlex-like split below
    raise WizardError("code-puppy (or uvx) not found on PATH")


def code_puppy_cmd(exe: str) -> list[str]:
    return exe.split()


def ensure_setup_cli(exe: str) -> None:
    """Fail early (with the exact fix) if the setup_cli plugin is absent.

    ``uv run`` re-syncs the project .venv from uv.lock, which silently
    removes a local editable install of code-puppy-core-plugins; the
    resulting argparse usage dump is otherwise inscrutable.
    """
    probe = subprocess.run(
        code_puppy_cmd(exe) + ["--setup", "config", "path", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0:
        return
    sibling = SBX_DIR.parents[1] / "code_puppy_core_plugins"
    venv_python = (
        ".venv\\Scripts\\python.exe" if os.name == "nt" else ".venv/bin/python"
    )
    hint = (
        "the code-puppy on PATH has no --setup support (setup_cli plugin "
        "missing). If you just used `uv run`, it re-synced .venv from "
        "uv.lock and removed any editable core-plugins install."
    )
    if (sibling / "code_puppy_core_plugins" / "setup_cli").is_dir():
        hint += (
            f"\nFix (from the code_puppy repo root):\n"
            f"  uv pip install --python {venv_python} -e {Path('..') / 'code_puppy_core_plugins'}\n"
            f"  {venv_python} {Path('sbx') / 'wizard.py'} ...   (not `uv run`, which re-syncs)"
        )
    raise WizardError(hint)


def secret_stored(service: str) -> bool:
    out = subprocess.run(
        ["sbx", "secret", "ls"], capture_output=True, text=True, check=False
    )
    return any(
        line.split()[2] == service
        for line in out.stdout.splitlines()
        if len(line.split()) >= 3 and "service" in line
    )


def meta_key_from_disk() -> str | None:
    path = Path.home() / ".code_puppy" / "meta_oauth.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("api_key") or None
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def ensure_secret(provider: str, dry: bool) -> None:
    service, env_var, _domain = PROXY_PROVIDERS[provider]
    if secret_stored(service):
        print(f"sbx secret '{service}': already stored")
        return
    if provider == "meta":
        value = meta_key_from_disk()
        if not value:
            raise WizardError(
                "no Meta key found; run /meta-auth in a local Code Puppy "
                "session first (creates ~/.code_puppy/meta_oauth.json)"
            )
    else:
        value = os.environ.get(env_var) or getpass.getpass(f"Enter {env_var}: ")
        if not value:
            raise WizardError(f"no value provided for {env_var}")
    result = run(["sbx", "secret", "set", service], dry=dry, input_text=value)
    if result.returncode != 0:
        raise WizardError(
            f"sbx secret set {service} failed: {result.stderr.strip()[:300]}"
        )
    print(f"sbx secret '{service}': stored (value never printed)")


def bindings_path() -> Path:
    if os.name == "nt":
        return Path(os.environ["APPDATA"]) / "sbx" / "credentials.yaml"
    return Path.home() / ".config" / "sbx" / "credentials.yaml"


def ensure_binding(provider: str, dry: bool) -> None:
    service, _env, domain = PROXY_PROVIDERS[provider]
    path = bindings_path()
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if re.search(rf"(?m)^\s{{2}}{re.escape(service)}:", text):
        print(f"binding for '{service}': already approved")
        return
    block = f"  {service}:\n    apiKey:\n      domains: [{domain}]\n"
    if "bindings:" not in text:
        text = "bindings:\n" + block
    else:
        text = text.rstrip() + "\n" + block
    if dry:
        print(f"[dry-run] would write binding for {service} -> {domain} in {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"binding for '{service}' -> {domain}: written to {path}")


def build_personal_mixin(exe: str, dry: bool) -> Path:
    """Export the host setup (secret-free) into a personal mixin dir."""
    with tempfile.TemporaryDirectory(prefix="pup-export-") as tmp:
        result = run(
            code_puppy_cmd(exe) + ["--setup", "export", tmp, "--sbx", "--json"],
            dry=dry,
        )
        if dry:
            print(f"[dry-run] would copy export into {PERSONAL_DIR}")
            return PERSONAL_DIR
        if result.returncode != 0:
            raise WizardError(
                "`code-puppy --setup export` failed; is the setup_cli plugin "
                f"installed? {result.stderr.strip()[:300]}"
            )
        PERSONAL_DIR.mkdir(parents=True, exist_ok=True)
        stock = SBX_DIR / "code-puppy-config"
        # Personal descriptor = stock minus the lifecycle puppy.cfg
        # generator (the exported sanitized puppy.cfg replaces it).
        descriptor = (stock / "code-puppy-config.yaml").read_text(encoding="utf-8")
        descriptor = descriptor.split("capabilities:")[0].rstrip() + "\n"
        (PERSONAL_DIR / "code-puppy-config.yaml").write_text(
            descriptor, encoding="utf-8"
        )
        shutil.copy2(
            stock / "code-puppy-config.dockerfile",
            PERSONAL_DIR / "code-puppy-config.dockerfile",
        )
        files_dest = PERSONAL_DIR / "files"
        if files_dest.exists():
            shutil.rmtree(files_dest)
        shutil.copytree(Path(tmp) / "files", files_dest)
    print(f"personal mixin: {PERSONAL_DIR}")
    return PERSONAL_DIR


def sync_tokens(name: str, provider: str, dry: bool) -> None:
    filename = TOKEN_SYNC_PROVIDERS[provider]
    source = Path.home() / ".code_puppy" / filename
    if not source.is_file():
        raise WizardError(
            f"host token file {source} not found; authenticate on the host first"
        )
    run(
        ["sbx", "cp", str(source), f"{name}:/home/agent/.code_puppy/{filename}"],
        dry=dry,
    )
    print(
        "note: token synced into the guest (experimental). The host stays "
        "the refresh owner; re-sync if the sandbox reports an expired token."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="code-puppy-sandbox")
    providers_all = sorted(
        set(PROXY_PROVIDERS) | set(TOKEN_SYNC_PROVIDERS) | set(IN_SANDBOX_PROVIDERS)
    )
    parser.add_argument("--provider", default="meta", choices=providers_all)
    parser.add_argument("--model", help="default model key (stock mixin only)")
    parser.add_argument("--workspace", help="host directory to mount as workspace")
    parser.add_argument(
        "--stock-config",
        action="store_true",
        help="use the stock config mixin instead of a personal export",
    )
    parser.add_argument(
        "--sync-tokens",
        action="store_true",
        help="copy the host OAuth token file into the sandbox (experimental)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="run a headless smoke prompt after creation",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--code-puppy",
        metavar="EXE",
        help="code-puppy executable to drive (default: PATH, else uvx)",
    )
    args = parser.parse_args(argv)

    try:
        exe = check_prereqs(args.code_puppy)
        if not args.stock_config:
            ensure_setup_cli(exe)
        if args.provider in PROXY_PROVIDERS:
            ensure_secret(args.provider, args.dry_run)
            ensure_binding(args.provider, args.dry_run)
        elif args.provider in TOKEN_SYNC_PROVIDERS and not args.sync_tokens:
            print(
                f"warning: {args.provider} uses token-file auth; without "
                "--sync-tokens the sandbox starts unauthenticated"
            )

        if args.stock_config:
            mixin = SBX_DIR / "code-puppy-config"
        else:
            mixin = build_personal_mixin(exe, args.dry_run)

        create = [
            "sbx",
            "create",
            "--name",
            args.name,
            str(SBX_DIR / "code-puppy"),
            "--kit",
            str(mixin),
        ]
        if args.model and args.stock_config:
            create += ["--kit-arg", f"code-puppy-config.model={args.model}"]
        if args.workspace:
            create.append(args.workspace)
        result = run(create, dry=args.dry_run, capture=False)
        if result.returncode != 0:
            raise WizardError("sbx create failed")

        if args.provider in TOKEN_SYNC_PROVIDERS and args.sync_tokens:
            sync_tokens(args.name, args.provider, args.dry_run)
        if args.smoke:
            run(
                [
                    "sbx",
                    "exec",
                    args.name,
                    "--",
                    "bash",
                    "-lc",
                    'timeout 180 code-puppy-launch -p "Reply with exactly OK" </dev/null',
                ],
                dry=args.dry_run,
                capture=False,
            )
        if args.provider in IN_SANDBOX_PROVIDERS:
            print(
                f"next: attach and run {IN_SANDBOX_PROVIDERS[args.provider]} "
                "inside the sandbox to finish sign-in"
            )
        print(f"done. Attach with: sbx run --name {args.name}")
        return 0
    except WizardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
