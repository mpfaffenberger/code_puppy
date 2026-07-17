from pathlib import Path

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.project_trust import (
    get_project_trust,
    get_trust_scope,
    set_project_trusted,
    set_trust_scope,
)


def _help():
    return [
        (
            "/trust [status|project|revoke|domain DOMAIN|service NAME]",
            "Manage project and external trust scopes",
        )
    ]


def _command(command: str, name: str):
    if name != "trust":
        return None
    parts = command.split()
    action = parts[1].strip().lower() if len(parts) > 1 else "status"
    project = Path.cwd().resolve()
    if action in {"project", "yes", "allow"}:
        set_project_trusted(project, True)
        emit_success(f"Trusted project: {project}. Restart to load project plugins.")
    elif action in {"revoke", "deny", "no"}:
        set_project_trusted(project, False)
        emit_warning(f"Revoked project trust: {project}. Restart required.")
    elif action == "status":
        scope = get_trust_scope(project)
        emit_info(
            f"Project trust for {project}: {get_project_trust(project)}\n"
            f"Domains: {', '.join(scope.domains) or '(none)'}\n"
            f"Remotes: {', '.join(scope.remotes) or '(none)'}\n"
            f"Services: {', '.join(scope.services) or '(none)'}"
        )
    elif action in {"domain", "service", "bucket", "org", "remote"} and len(parts) >= 3:
        value = " ".join(parts[2:]).strip()
        field = {
            "domain": "domains",
            "service": "services",
            "bucket": "buckets",
            "org": "scm_orgs",
            "remote": "remotes",
        }[action]
        set_trust_scope(project, **{field: [value]})
        emit_success(f"Added trusted {action}: {value}")
    else:
        emit_warning(
            "Usage: /trust [status|project|revoke|domain DOMAIN|service NAME|"
            "bucket NAME|org NAME|remote URL]"
        )
    return True


register_callback("custom_command_help", _help)
register_callback("custom_command", _command)
