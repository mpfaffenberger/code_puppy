"""Local server authentication configuration."""

from __future__ import annotations

import json
import secrets
from pathlib import Path


def load_or_create_token(path: Path) -> str:
    try:
        token = json.loads(path.read_text(encoding="utf-8")).get("token")
        if isinstance(token, str) and token:
            return token
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"token": token}, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)
    return token
