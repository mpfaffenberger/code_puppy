#!/usr/bin/env python3
"""Host-side wizard: turn your local Code Puppy setup into a sandbox.

Stdlib-only; run it with the project environment's Python (NOT
``uv run``, which re-syncs .venv from uv.lock -- see sbx/README.md)::

    .venv\\Scripts\\python.exe sbx\\wizard.py --name my-pup --smoke
    .venv\\Scripts\\python.exe sbx\\wizard.py --dry-run

The sandbox's credentials are *derived from your configured models*
(``code-puppy --setup sbx plan``), never hand-enumerated: the wizard
generates a personal credentials mixin declaring exactly the keys and
egress your catalog needs (Meta, ZAI Coding Plan, custom endpoints,
...), ensures each key is in the sbx secret store (piped via stdin,
never printed) with an approved binding, exports your configuration
secret-free into a personal config mixin, then creates the sandbox
from workload + both mixins. OAuth token-file providers can opt into
--sync-tokens (experimental); device-flow providers sign in inside
the sandbox.
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
PERSONAL_CONFIG_DIR = SBX_DIR / ".personal" / "code-puppy-config"
PERSONAL_CREDS_DIR = SBX_DIR / ".personal" / "code-puppy-creds"

# OAuth providers whose token file can be synced into the guest.
TOKEN_FILES = {
    "claude-code": "claude_code_oauth.json",
    "codex": "chatgpt_oauth.json",
    "grok": "grok_oauth.json",
}
LOGIN_HINTS = {
    "copilot": "/copilot-login",
    "claude-code": "/claude-code-auth",
    "codex": "/chatgpt-auth",
    "grok": "/grok-auth",
}


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
        return "uvx code-puppy"  # split by caller via code_puppy_cmd
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
            "\nFix (from the code_puppy repo root):\n"
            f"  uv pip install --python {venv_python} -e {Path('..') / 'code_puppy_core_plugins'}\n"
            f"  {venv_python} {Path('sbx') / 'wizard.py'} ...   (not `uv run`, which re-syncs)"
        )
    raise WizardError(hint)


def fetch_plan(exe: str, dry: bool) -> dict:
    """Derive the credential/egress plan from the host model catalog."""
    result = run(code_puppy_cmd(exe) + ["--setup", "sbx", "plan", "--json"], dry=dry)
    if dry:
        return {"credentials": [], "oauth": [], "egress": [], "unsupported": []}
    if result.returncode != 0:
        raise WizardError(
            f"`code-puppy --setup sbx plan` failed: {result.stderr.strip()[:300]}"
        )
    text = result.stdout
    try:
        return json.loads(text[text.index("{") : text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as exc:
        raise WizardError(f"could not parse sbx plan output: {exc}") from exc


def filter_plan(plan: dict, provider: str | None) -> dict:
    if not provider:
        return plan
    plan = {
        **plan,
        "credentials": [c for c in plan["credentials"] if c["service"] == provider],
        "oauth": [o for o in plan["oauth"] if o["id"] == provider],
    }
    plan["egress"] = sorted(
        {c["domain"] for c in plan["credentials"]}
        | {d for o in plan["oauth"] for d in o["domains"]}
    )
    return plan


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


def ensure_secret(service: str, env_var: str, dry: bool) -> None:
    if secret_stored(service):
        print(f"sbx secret '{service}': already stored")
        return
    value: str | None = None
    if service == "meta":
        value = meta_key_from_disk()
        if not value:
            raise WizardError(
                "no Meta key found; run /meta-auth in a local Code Puppy "
                "session first (creates ~/.code_puppy/meta_oauth.json)"
            )
    if not value:
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


def ensure_binding(service: str, domain: str, dry: bool) -> None:
    path = bindings_path()
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if re.search(rf"(?m)^\s{{2}}{re.escape(service)}:", text):
        print(f"binding for '{service}': already approved")
        return
    block = f"  {service}:\n    apiKey:\n      domains: [{domain}]\n"
    text = (
        ("bindings:\n" + block)
        if "bindings:" not in text
        else text.rstrip() + "\n" + block
    )
    if dry:
        print(f"[dry-run] would write binding for {service} -> {domain} in {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"binding for '{service}' -> {domain}: written to {path}")


def build_creds_mixin(plan: dict, dry: bool) -> Path | None:
    """Generate the personal credentials mixin from the derived plan."""
    if not plan["credentials"] and not plan["egress"]:
        return None
    lines = [
        "# syntax=docker/sandbox-kit:3",
        'schemaVersion: "3"',
        "kind: mixin",
        "displayName: Code Puppy credentials (generated)",
        (
            "description: Generated by sbx/wizard.py from the host model "
            "catalog; regenerated on every wizard run. Do not edit."
        ),
        "",
        "capabilities:",
    ]
    if plan["egress"]:
        lines.append("  - type: com.docker.sandbox/network-policy@1")
        lines.append("    config:")
        lines.append("      runtime:")
        lines.append("        allow:")
        lines += [f"          - {domain}:443" for domain in plan["egress"]]
    for cred in plan["credentials"]:
        fmt = cred["format"].replace('"', '\\"')
        lines += [
            "  - type: com.docker.sandbox/credential@1",
            "    optional: true",
            f"    description: {cred['service']} access (derived from host models)",
            "    config:",
            f"      service: {cred['service']}",
            "      phase: runtime",
            "      apiKey:",
            f"        name: {cred['env_var']}",
            "        proxyManaged: true",
            "        inject:",
            f"          - domain: {cred['domain']}",
            f"            header: {cred['header']}",
            f'            format: "{fmt}"',
        ]
    if dry:
        print(f"[dry-run] would generate credentials mixin in {PERSONAL_CREDS_DIR}:")
        print("\n".join(lines))
        return PERSONAL_CREDS_DIR
    PERSONAL_CREDS_DIR.mkdir(parents=True, exist_ok=True)
    (PERSONAL_CREDS_DIR / "code-puppy-creds.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    (PERSONAL_CREDS_DIR / "code-puppy-creds.dockerfile").write_text(
        "# Capability-only mixin: credentials/egress, no files to overlay.\n"
        "FROM scratch\n",
        encoding="utf-8",
    )
    print(f"personal credentials mixin: {PERSONAL_CREDS_DIR}")
    return PERSONAL_CREDS_DIR


def build_personal_mixin(exe: str, dry: bool) -> Path:
    """Export the host setup (secret-free) into a personal config mixin."""
    with tempfile.TemporaryDirectory(prefix="pup-export-") as tmp:
        result = run(
            code_puppy_cmd(exe) + ["--setup", "export", tmp, "--sbx", "--json"],
            dry=dry,
        )
        if dry:
            print(f"[dry-run] would copy export into {PERSONAL_CONFIG_DIR}")
            return PERSONAL_CONFIG_DIR
        if result.returncode != 0:
            raise WizardError(
                "`code-puppy --setup export` failed; is the setup_cli plugin "
                f"installed? {result.stderr.strip()[:300]}"
            )
        PERSONAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        stock = SBX_DIR / "code-puppy-config"
        # Personal descriptor = stock minus the lifecycle puppy.cfg
        # generator (the exported sanitized puppy.cfg replaces it).
        descriptor = (stock / "code-puppy-config.yaml").read_text(encoding="utf-8")
        descriptor = descriptor.split("capabilities:")[0].rstrip() + "\n"
        (PERSONAL_CONFIG_DIR / "code-puppy-config.yaml").write_text(
            descriptor, encoding="utf-8"
        )
        shutil.copy2(
            stock / "code-puppy-config.dockerfile",
            PERSONAL_CONFIG_DIR / "code-puppy-config.dockerfile",
        )
        files_dest = PERSONAL_CONFIG_DIR / "files"
        if files_dest.exists():
            shutil.rmtree(files_dest)
        shutil.copytree(Path(tmp) / "files", files_dest)
    print(f"personal config mixin: {PERSONAL_CONFIG_DIR}")
    return PERSONAL_CONFIG_DIR


def sync_tokens(name: str, plan: dict, dry: bool) -> None:
    for entry in plan["oauth"]:
        filename = TOKEN_FILES.get(entry["id"])
        if not filename or entry["transport"] != "token-file-sync":
            continue
        source = Path.home() / ".code_puppy" / filename
        if not source.is_file():
            print(f"warning: no host token file {source} for {entry['id']}; skipped")
            continue
        run(
            ["sbx", "cp", str(source), f"{name}:/home/agent/.code_puppy/{filename}"],
            dry=dry,
        )
        print(
            f"note: {entry['id']} token synced into the guest (experimental). "
            "The host stays the refresh owner; re-sync on expiry."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="code-puppy-sandbox")
    parser.add_argument(
        "--provider",
        help="only include this service/provider from the derived plan "
        "(default: everything your configured models need)",
    )
    parser.add_argument("--model", help="default model key (stock config mixin only)")
    parser.add_argument("--workspace", help="host directory to mount as workspace")
    parser.add_argument(
        "--stock-config",
        action="store_true",
        help="use the stock config mixin instead of a personal export",
    )
    parser.add_argument(
        "--no-creds",
        action="store_true",
        help="skip the generated credentials mixin entirely",
    )
    parser.add_argument(
        "--sync-tokens",
        action="store_true",
        help="copy host OAuth token files into the sandbox (experimental)",
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
        help="code-puppy executable to drive (default: project .venv, else PATH/uvx)",
    )
    args = parser.parse_args(argv)

    try:
        exe = check_prereqs(args.code_puppy)
        needs_setup_cli = not (args.stock_config and args.no_creds)
        if needs_setup_cli:
            ensure_setup_cli(exe)

        plan: dict = {"credentials": [], "oauth": [], "egress": [], "unsupported": []}
        creds_mixin: Path | None = None
        if not args.no_creds:
            plan = filter_plan(fetch_plan(exe, args.dry_run), args.provider)
            for entry in plan["unsupported"]:
                print(
                    f"warning: no sandbox credential for {entry['model']} "
                    f"[{entry['type']}]: {entry['reason']}"
                )
            for cred in plan["credentials"]:
                ensure_secret(cred["service"], cred["env_var"], args.dry_run)
                ensure_binding(cred["service"], cred["domain"], args.dry_run)
            creds_mixin = build_creds_mixin(plan, args.dry_run)
        mixin = (
            SBX_DIR / "code-puppy-config"
            if args.stock_config
            else build_personal_mixin(exe, args.dry_run)
        )

        create = [
            "sbx",
            "create",
            "--name",
            args.name,
            str(SBX_DIR / "code-puppy"),
            "--kit",
            str(mixin),
        ]
        if creds_mixin:
            create += ["--kit", str(creds_mixin)]
        if args.model and args.stock_config:
            create += ["--kit-arg", f"code-puppy-config.model={args.model}"]
        if args.workspace:
            create.append(args.workspace)
        result = run(create, dry=args.dry_run, capture=False)
        if result.returncode != 0:
            raise WizardError("sbx create failed")

        if args.sync_tokens:
            sync_tokens(args.name, plan, args.dry_run)
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
        for entry in plan["oauth"]:
            if entry["transport"] == "auth-in-sandbox":
                hint = LOGIN_HINTS.get(entry["id"], "/login")
                print(f"next: attach and run {hint} inside the sandbox to sign in")
            elif entry["transport"] == "token-file-sync" and not args.sync_tokens:
                print(
                    f"note: {entry['id']} models start unauthenticated; rerun "
                    "with --sync-tokens to copy the host token file in"
                )
        print(f"done. Attach with: sbx run --name {args.name}")
        return 0
    except WizardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
