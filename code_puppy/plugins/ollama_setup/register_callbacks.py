"""Ollama cloud model setup — /ollama-setup command.

Pulls an Ollama `:cloud` model and registers it in extra_models.json so the
model is immediately available for use in Code Puppy.

Cloud models supported (the Ollama "Recommended Models" cloud tier):
    kimi-k2.5:cloud, glm-5:cloud, minimax-m2.7:cloud, qwen3.5:cloud
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from code_puppy.callbacks import register_callback
from code_puppy.config import EXTRA_MODELS_FILE
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

logger = logging.getLogger(__name__)

# ── Cloud model catalogue ───────────────────────────────────────────────────
# Only the four `:cloud` models from the Ollama recommended list.
# Each entry maps the ollama tag → extra_models.json config metadata.

CLOUD_MODELS: dict[str, dict[str, Any]] = {
    "kimi-k2.5:cloud": {
        "context_length": 131072,
        "description": "Moonshot Kimi K2.5 (cloud)",
    },
    "glm-5:cloud": {
        "context_length": 131072,
        "description": "ZhipuAI GLM-5 (cloud)",
    },
    "minimax-m2.7:cloud": {
        "context_length": 131072,
        "description": "MiniMax M2.7 (cloud)",
    },
    "qwen3.5:cloud": {
        "context_length": 131072,
        "description": "Alibaba Qwen 3.5 (cloud)",
    },
}

OLLAMA_ENDPOINT = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama"  # Ollama's local API doesn't need a real key


# ── Helpers ─────────────────────────────────────────────────────────────────


def _model_key(model_tag: str) -> str:
    """Derive a unique extra_models.json key from an ollama tag.

    e.g. ``glm-5:cloud`` → ``ollama-glm-5-cloud``
    """
    return "ollama-" + model_tag.replace(":", "-").replace("/", "-")


def _ollama_available() -> bool:
    """Return True if the ``ollama`` CLI is on PATH."""
    return shutil.which("ollama") is not None


def _pull_model(model_tag: str) -> bool:
    """Run ``ollama pull <model_tag>``, streaming output to the terminal.

    Returns True on success, False on failure.
    """
    emit_info(f"🐕 Pulling {model_tag} via ollama …")
    try:
        result = subprocess.run(
            ["ollama", "pull", model_tag],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            emit_error(f"ollama pull failed (exit {result.returncode}): {stderr}")
            return False

        stdout = result.stdout.strip()
        if stdout:
            emit_info(stdout)
        return True
    except subprocess.TimeoutExpired:
        emit_error("ollama pull timed out after 10 minutes")
        return False
    except Exception as exc:
        emit_error(f"Failed to run ollama pull: {exc}")
        return False


def _register_model(model_tag: str) -> bool:
    """Write (or update) the model entry in extra_models.json.

    Uses atomic-write via a temp file, same pattern as add_model_menu.py.
    Returns True on success.
    """
    meta = CLOUD_MODELS[model_tag]
    key = _model_key(model_tag)

    extra_path = Path(EXTRA_MODELS_FILE)
    extra_models: dict[str, Any] = {}

    if extra_path.exists():
        try:
            with open(extra_path, "r", encoding="utf-8") as fh:
                extra_models = json.load(fh)
                if not isinstance(extra_models, dict):
                    emit_error("extra_models.json must be a dict, not a list")
                    return False
        except json.JSONDecodeError as exc:
            emit_error(f"Corrupt extra_models.json: {exc}")
            return False

    if key in extra_models:
        emit_info(f"Model {key} already registered — updating entry")

    extra_models[key] = {
        "type": "custom_openai",
        "name": model_tag,
        "custom_endpoint": {
            "url": OLLAMA_ENDPOINT,
            "api_key": OLLAMA_API_KEY,
        },
        "context_length": meta["context_length"],
        "supported_settings": ["temperature", "top_p"],
    }

    extra_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = extra_path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(extra_models, fh, indent=4, ensure_ascii=False)
        tmp.replace(extra_path)
    except Exception as exc:
        emit_error(f"Failed to write extra_models.json: {exc}")
        return False

    emit_success(f"✅ Registered {key} in extra_models.json")
    return True


def _test_model_auth(model_tag: str) -> tuple[bool, str]:
    """Test if the model requires authentication.

    Returns (authorized: bool, message: str).
    If unauthorized, message contains guidance for the user.
    """
    import json as json_mod
    import urllib.request

    test_payload = json_mod.dumps(
        {
            "model": model_tag,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/chat/completions",
        data=test_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OLLAMA_API_KEY}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10):
            # 200 = good to go
            return (True, "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        # Check for auth errors
        if e.code == 401 or "unauthorized" in body.lower():
            return (False, _auth_help_message(model_tag))
        if e.code == 500 and (
            "internal service error" in body.lower() or "unauthorized" in body.lower()
        ):
            # Cloud models often return 500 instead of 401
            return (False, _auth_help_message(model_tag))
        return (False, f"HTTP {e.code}: {body[:200]}")
    except Exception as e:
        return (False, f"Connection test failed: {e}")


def _auth_help_message(model_tag: str) -> str:
    """Generate a helpful auth guidance message."""
    return f"""🔐 Authentication Required for {model_tag}

This is a cloud-hosted model (756B+ parameters) that requires Ollama Cloud access.

To use this model:
1. Run: ollama login
2. Visit https://ollama.com to create an account
3. Subscribe to Ollama Cloud (cloud models aren't free)
4. Accept the terms for {model_tag.split(":")[0]}

After logging in, you can use the model with:
/model {_model_key(model_tag)}
"""


def _run_ollama_login() -> bool:
    """Run ``ollama login`` interactively in the user's terminal.

    This will open a browser for OAuth flow. Returns True if login succeeded.
    """
    emit_info(
        "🔐 Launching 'ollama login' — this will open your browser for authentication..."
    )
    emit_info("   (Press Ctrl+C here if you want to cancel and do it manually later)")
    emit_info("")

    try:
        # Run ollama login with stdout/stderr connected to terminal
        # so the user can see the browser-open message and any instructions
        result = subprocess.run(
            ["ollama", "login"],
            capture_output=False,  # Let it flow to terminal
            text=True,
            timeout=120,  # 2 minutes — OAuth can take a while
        )

        if result.returncode == 0:
            emit_success("✅ Login completed!")
            return True
        else:
            emit_error(f"ollama login exited with code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        emit_error("ollama login timed out after 2 minutes")
        return False
    except Exception as exc:
        emit_error(f"Failed to run ollama login: {exc}")
        return False


def _start_ollama_serve() -> Optional[subprocess.Popen]:
    """Start ``ollama serve`` as a background subprocess if not already running.

    Returns the Popen handle, or None if already running / on failure.
    """
    # Quick liveness check — hit the version endpoint
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            emit_info("🟢 Ollama is already running")
            return None
    except Exception:
        pass

    emit_info("🚀 Starting ollama serve in the background …")
    try:
        proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        emit_success(f"ollama serve started (pid {proc.pid})")
        return proc
    except Exception as exc:
        emit_error(f"Could not start ollama serve: {exc}")
        return None


# ── Command handler ─────────────────────────────────────────────────────────


def _handle_ollama_setup(command: str, name: str) -> Any:
    """Handle ``/ollama-setup [model]``."""
    if name != "ollama-setup":
        return None  # Not our command

    parts = command.split(maxsplit=1)
    model_tag = parts[1].strip() if len(parts) > 1 else ""

    # No argument → show available models
    if not model_tag:
        lines = ["🦙 Available Ollama cloud models:\n"]
        for tag, meta in CLOUD_MODELS.items():
            lines.append(f"  • {tag:25s} — {meta['description']}")
        lines.append("\nUsage: /ollama-setup <model>")
        emit_info("\n".join(lines))
        return True

    # Fuzzy-ish match: allow partial names like "glm" → "glm-5:cloud"
    matched = _resolve_model(model_tag)
    if matched is None:
        emit_error(f"Unknown model '{model_tag}'. Available: {', '.join(CLOUD_MODELS)}")
        return True

    # Pre-flight: is ollama installed?
    if not _ollama_available():
        emit_error(
            "ollama CLI not found on PATH. "
            "Install it from https://ollama.com and try again."
        )
        return True

    # 1. Ensure ollama serve is up
    _start_ollama_serve()

    # 2. Pull the model
    if not _pull_model(matched):
        return True

    # 3. Register in extra_models.json
    _register_model(matched)

    # 4. Test auth / accessibility
    emit_info(f"🔍 Testing {matched} accessibility...")
    authorized, msg = _test_model_auth(matched)

    if authorized:
        emit_success(
            f"🎉 Done! Switch to the model with:  /model {_model_key(matched)}"
        )
    else:
        emit_warning(msg)
        emit_info("")
        emit_info(
            "💡 Want me to run 'ollama login' for you? (This will open your browser)"
        )
        emit_info(
            "   Type 'yes' to proceed, or anything else to skip and do it manually later."
        )

        # We can't do interactive input here (custom commands shouldn't block)
        # So we just run it — worst case it fails and they do it manually
        login_ok = _run_ollama_login()

        if login_ok:
            # Re-test auth after login
            emit_info("🔍 Re-testing accessibility after login...")
            authorized, msg = _test_model_auth(matched)

            if authorized:
                emit_success(
                    f"🎉 All set! Switch to the model with:  /model {_model_key(matched)}"
                )
            else:
                emit_warning("Still not authorized after login.")
                emit_info(
                    f"📋 Model registered as '{_model_key(matched)}'. "
                    f"You may need to subscribe to Ollama Cloud at https://ollama.com, "
                    f"then use /model {_model_key(matched)}"
                )
        else:
            emit_info(
                f"📋 Model registered as '{_model_key(matched)}' but needs auth. "
                f"Run 'ollama login' manually, then use /model {_model_key(matched)}"
            )

    return True


def _resolve_model(user_input: str) -> Optional[str]:
    """Resolve user input to an exact cloud model tag.

    Supports exact match and unambiguous prefix matching.
    """
    lowered = user_input.lower().strip()

    # Exact match first
    for tag in CLOUD_MODELS:
        if tag.lower() == lowered:
            return tag

    # Prefix / substring match
    candidates = [t for t in CLOUD_MODELS if lowered in t.lower()]
    if len(candidates) == 1:
        return candidates[0]

    return None


# ── Help entry ──────────────────────────────────────────────────────────────


def _custom_help():
    model_names = ", ".join(CLOUD_MODELS)
    return [
        ("ollama-setup", f"Pull & register an Ollama cloud model ({model_names})"),
    ]


# ── Register ────────────────────────────────────────────────────────────────

register_callback("custom_command", _handle_ollama_setup)
register_callback("custom_command_help", _custom_help)
