from pathlib import Path

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.project_trust import get_project_trust, set_project_trusted


def _help():
    return [("/trust [status|project|revoke]", "Manage project-local code trust")]


def _command(command: str, name: str):
    if name != "trust":
        return None
    action = (
        command.split(maxsplit=1)[1].strip().lower() if " " in command else "status"
    )
    project = Path.cwd().resolve()
    if action in {"project", "yes", "allow"}:
        set_project_trusted(project, True)
        emit_success(f"Trusted project: {project}. Restart to load project plugins.")
    elif action in {"revoke", "deny", "no"}:
        set_project_trusted(project, False)
        emit_warning(f"Revoked project trust: {project}. Restart required.")
    elif action == "status":
        emit_info(f"Project trust for {project}: {get_project_trust(project)}")
    else:
        emit_warning("Usage: /trust [status|project|revoke]")
    return True


register_callback("custom_command_help", _help)
register_callback("custom_command", _command)
