from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_code_puppy_api_starts_without_dbos_installed(tmp_path):
    blocker_dir = tmp_path / "block_dbos"
    blocker_dir.mkdir()
    sitecustomize = blocker_dir / "sitecustomize.py"
    sitecustomize.write_text(
        """
import builtins

_original_import = builtins.__import__


def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == \"dbos\" or name.startswith(\"dbos.\"):
        raise ModuleNotFoundError(\"No module named 'dbos'\")
    return _original_import(name, globals, locals, fromlist, level)


builtins.__import__ = _blocked_import
""".strip()
    )

    db_path = tmp_path / "chat_messages.db"
    env = os.environ.copy()
    env["PUPPY_DESK_DB"] = str(db_path)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(blocker_dir), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    script = "\n".join(
        [
            "from contextlib import asynccontextmanager",
            "from starlette.routing import Router",
            "@asynccontextmanager",
            "async def _empty_lifespan(_app):",
            "    yield",
            "_original_router_init = Router.__init__",
            "def _compat_router_init(self, *args, **kwargs):",
            "    on_startup = kwargs.pop('on_startup', None)",
            "    on_shutdown = kwargs.pop('on_shutdown', None)",
            "    lifespan = kwargs.pop('lifespan', None)",
            "    result = _original_router_init(self, *args, **kwargs)",
            "    self.on_startup = list(on_startup or [])",
            "    self.on_shutdown = list(on_shutdown or [])",
            "    self.lifespan_context = lifespan or _empty_lifespan",
            "    return result",
            "Router.__init__ = _compat_router_init",
            "from fastapi.testclient import TestClient",
            "from code_puppy.api.app import create_app",
            "with TestClient(create_app()) as client:",
            "    response = client.get('/health')",
            "    assert response.status_code == 200",
            "    assert response.json()['status'] == 'healthy'",
            "print('ok')",
        ]
    )

    command = [sys.executable, "-c", script]

    result = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "ok" in result.stdout
