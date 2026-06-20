"""Persisted trust decisions for project-local executable resources."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

_LOCK = threading.RLock()
_ENV_OVERRIDES = ("MIST_TRUST_PROJECT", "CODE_PUPPY_TRUST_PROJECT")


@dataclass(frozen=True)
class TrustScope:
    """Explicit trust boundary attached to one canonical project path."""

    trusted: bool = False
    domains: tuple[str, ...] = ()
    remotes: tuple[str, ...] = ()
    scm_orgs: tuple[str, ...] = ()
    buckets: tuple[str, ...] = ()
    services: tuple[str, ...] = ()


def _load_raw() -> dict[str, object]:
    path = _trust_file()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _scope_from_raw(value: object) -> TrustScope:
    if isinstance(value, bool):
        return TrustScope(trusted=value)
    if not isinstance(value, dict):
        return TrustScope()

    def values(key: str) -> tuple[str, ...]:
        raw_values = value.get(key, ())
        if not isinstance(raw_values, (list, tuple, set)):
            return ()
        return tuple(
            sorted(
                {str(item).strip().lower() for item in raw_values if str(item).strip()}
            )
        )

    return TrustScope(
        trusted=bool(value.get("trusted", False)),
        domains=values("domains"),
        remotes=values("remotes"),
        scm_orgs=values("scm_orgs"),
        buckets=values("buckets"),
        services=values("services"),
    )


def _trust_file() -> Path:
    from code_puppy.config import CONFIG_DIR

    return Path(CONFIG_DIR) / "trust.json"


def _project_key(project_dir: Path | str | None = None) -> str:
    return str(Path(project_dir or Path.cwd()).expanduser().resolve())


def load_trust_decisions() -> dict[str, bool]:
    return {
        str(key): _scope_from_raw(value).trusted for key, value in _load_raw().items()
    }


def load_trust_scopes() -> dict[str, TrustScope]:
    return {str(key): _scope_from_raw(value) for key, value in _load_raw().items()}


def _write_raw(raw: dict[str, object]) -> None:
    path = _trust_file()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)


def set_project_trusted(
    project_dir: Path | str | None,
    trusted: bool,
) -> None:
    with _LOCK:
        raw = _load_raw()
        key = _project_key(project_dir)
        existing = raw.get(key)
        if isinstance(existing, dict):
            existing = dict(existing)
            existing["trusted"] = trusted
            raw[key] = existing
        else:
            # Preserve the compact legacy form until scoped values are added.
            raw[key] = trusted
        _write_raw(raw)


def get_trust_scope(project_dir: Path | str | None = None) -> TrustScope:
    key = _project_key(project_dir)
    scope = load_trust_scopes().get(key, TrustScope())
    if not scope.trusted:
        return scope
    remotes = tuple(sorted(set(scope.remotes) | set(_git_remotes(Path(key)))))
    domains = tuple(
        sorted(
            set(scope.domains)
            | {domain for remote in remotes if (domain := _remote_domain(remote))}
        )
    )
    scm_orgs = tuple(
        sorted(
            set(scope.scm_orgs)
            | {org for remote in remotes if (org := _remote_org(remote))}
        )
    )
    return TrustScope(
        trusted=True,
        domains=domains,
        remotes=remotes,
        scm_orgs=scm_orgs,
        buckets=scope.buckets,
        services=scope.services,
    )


def set_trust_scope(
    project_dir: Path | str | None,
    *,
    domains: tuple[str, ...] | list[str] | None = None,
    remotes: tuple[str, ...] | list[str] | None = None,
    scm_orgs: tuple[str, ...] | list[str] | None = None,
    buckets: tuple[str, ...] | list[str] | None = None,
    services: tuple[str, ...] | list[str] | None = None,
) -> TrustScope:
    """Merge named scopes into the existing project trust record."""
    with _LOCK:
        key = _project_key(project_dir)
        current = get_trust_scope(key)

        def merged(old: tuple[str, ...], new) -> tuple[str, ...]:
            return tuple(
                sorted(
                    set(old)
                    | {
                        str(item).strip().lower()
                        for item in (new or ())
                        if str(item).strip()
                    }
                )
            )

        updated = TrustScope(
            trusted=current.trusted,
            domains=merged(current.domains, domains),
            remotes=merged(current.remotes, remotes),
            scm_orgs=merged(current.scm_orgs, scm_orgs),
            buckets=merged(current.buckets, buckets),
            services=merged(current.services, services),
        )
        raw = _load_raw()
        raw[key] = asdict(updated)
        _write_raw(raw)
        return updated


def is_path_trusted(path: Path | str, project_dir: Path | str | None = None) -> bool:
    project = Path(project_dir or Path.cwd()).expanduser().resolve()
    target = Path(path).expanduser().resolve()
    return get_project_trust(project) is True and (
        target == project or project in target.parents
    )


def is_domain_trusted(domain: str, project_dir: Path | str | None = None) -> bool:
    normalized = domain.strip().lower().rstrip(".")
    return any(
        normalized == trusted or normalized.endswith(f".{trusted}")
        for trusted in get_trust_scope(project_dir).domains
    )


def is_url_trusted(url: str, project_dir: Path | str | None = None) -> bool:
    return is_domain_trusted(urlparse(url).hostname or "", project_dir)


def _git_remotes(project: Path) -> tuple[str, ...]:
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "remote", "-v"],
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()
    return tuple(
        sorted(
            {
                fields[1].strip().lower()
                for line in result.stdout.splitlines()
                if len(fields := line.split()) >= 2
            }
        )
    )


def _remote_domain(remote: str) -> str | None:
    parsed = urlparse(remote)
    if parsed.hostname:
        return parsed.hostname.lower()
    if "@" in remote and ":" in remote:
        return remote.split("@", 1)[1].split(":", 1)[0].lower()
    return None


def _remote_org(remote: str) -> str | None:
    parsed = urlparse(remote)
    if "://" not in remote and "@" in remote and ":" in remote:
        path = remote.split(":", 1)[1]
    else:
        path = parsed.path
    parts = [part for part in path.strip("/").split("/") if part]
    return parts[0].lower() if len(parts) >= 2 else None


def get_project_trust(project_dir: Path | str | None = None) -> bool | None:
    override = (
        next(
            (os.getenv(name, "") for name in _ENV_OVERRIDES if os.getenv(name)),
            "",
        )
        .strip()
        .lower()
    )
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False
    return load_trust_decisions().get(_project_key(project_dir))


def ensure_project_trusted(
    project_dir: Path | str | None = None,
    *,
    prompt: bool = True,
) -> bool:
    """Return whether project-local Python may be imported.

    Unknown projects fail closed when stdin is not interactive. Interactive
    decisions are persisted by canonical project path.
    """
    key = _project_key(project_dir)
    decision = get_project_trust(key)
    if decision is not None:
        return decision
    if not prompt or not getattr(sys.stdin, "isatty", lambda: False)():
        return False

    sys.stderr.write(
        "\nProject-local Mist plugins execute Python during startup.\n"
        f"Trust this project? {key}\nType 'yes' to trust: "
    )
    sys.stderr.flush()
    try:
        trusted = input().strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        trusted = False
    set_project_trusted(key, trusted)
    return trusted


def filter_untrusted_project_paths(paths: list[str | Path]) -> list[str]:
    """Drop paths inside the current project until that project is trusted."""
    project = Path.cwd().resolve()
    project_paths: list[tuple[str, bool]] = []
    requires_trust = False
    for raw in paths:
        resolved = Path(raw).expanduser().resolve()
        is_project_path = resolved == project or project in resolved.parents
        project_paths.append((str(raw), is_project_path))
        requires_trust = requires_trust or is_project_path
    if not requires_trust or ensure_project_trusted(project):
        return [raw for raw, _ in project_paths]
    return [raw for raw, is_project_path in project_paths if not is_project_path]
