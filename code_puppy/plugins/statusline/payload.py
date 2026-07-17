"""Build the JSON session payload fed to the status line command on stdin.

Schema mirrors Claude Code's ``statusLine`` stdin contract where the data
exists in Mist, so scripts written for one are easy to port. Every field
is best-effort: a failure in one source must never break the payload.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any, Dict, Optional

from code_puppy.branding import DISTRIBUTION_NAME

logger = logging.getLogger(__name__)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _model_block() -> Dict[str, Any]:
    from code_puppy.command_line.model_picker_completion import get_active_model

    model_id = _safe(get_active_model) or "(default)"
    return {"id": model_id, "display_name": model_id}


def _agent_block() -> Optional[Dict[str, Any]]:
    from code_puppy.agents.agent_manager import get_current_agent

    agent = _safe(get_current_agent)
    if not agent:
        return None
    name = getattr(agent, "display_name", None) or getattr(agent, "name", None)
    return {"name": name} if name else None


def _git_branch(cwd: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        if out.returncode == 0:
            branch = out.stdout.strip()
            return branch or None
    except Exception:
        return None
    return None


def _context_block() -> Dict[str, Any]:
    block: Dict[str, Any] = {}
    try:
        from code_puppy.plugins.context_indicator.usage import get_current_usage

        usage = get_current_usage()
        if usage is not None:
            block["total_input_tokens"] = int(getattr(usage, "used_tokens", 0))
            block["context_window_size"] = int(getattr(usage, "capacity", 0))
            block["used_percentage"] = round(float(usage.percent), 1)
            block["remaining_percentage"] = round(100.0 - float(usage.percent), 1)
            block["indicator"] = usage.indicator
    except Exception:
        pass
    return block


def _tokens_per_second() -> float:
    try:
        from code_puppy.status_display import StatusDisplay

        return round(float(StatusDisplay.get_current_rate()), 1)
    except Exception:
        return 0.0


def build_payload() -> Dict[str, Any]:
    """Assemble the full session payload (all fields best-effort)."""
    from code_puppy.config import get_mist_name

    cwd = _safe(os.getcwd, "") or ""
    payload: Dict[str, Any] = {
        "cwd": cwd,
        "mist_name": _safe(get_mist_name) or "mist",
        "model": _model_block(),
        "workspace": {"current_dir": cwd},
        "context_window": _context_block(),
        "tokens_per_second": _tokens_per_second(),
    }

    try:
        from code_puppy.plugins.agent_modes.state import get_agent_mode

        payload["mode"] = get_agent_mode().value
    except Exception:
        pass

    agent = _agent_block()
    if agent:
        payload["agent"] = agent

    branch = _git_branch(cwd)
    if branch:
        payload["workspace"]["git_branch"] = branch

    try:
        from importlib.metadata import version

        payload["version"] = version(DISTRIBUTION_NAME)
    except Exception:
        pass

    return payload


def build_payload_json() -> str:
    return json.dumps(build_payload(), indent=2)
