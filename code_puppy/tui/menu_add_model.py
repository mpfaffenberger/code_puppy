"""Phase 3 Wave C: /add_model as a Textual form.

The classic /add_model is a 54KB models.dev catalog wizard (prompt_toolkit).
This is a pragmatic manual port: a single form that writes a clean
extra_models.json entry, covering custom/self-hosted models the catalog can't.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .screens.form import FormField, FormScreen

if TYPE_CHECKING:
    from .app import CooperApp

_TYPES = [
    "custom_openai",
    "openai",
    "anthropic",
    "custom_anthropic",
    "gemini",
    "cerebras",
]
_CUSTOM_TYPES = ("custom_openai", "custom_anthropic")


def open_add_model(app: "CooperApp") -> None:
    fields = [
        FormField(
            "key",
            "Alias (shown in /model)",
            required=True,
            placeholder="openrouter-llama-3.3",
        ),
        FormField(
            "type", "Type", kind="select", options=_TYPES, default="custom_openai"
        ),
        FormField(
            "name",
            "Model id (sent to the API)",
            required=True,
            placeholder="meta-llama/llama-3.3-70b-instruct",
        ),
        FormField(
            "url",
            "Custom endpoint URL (custom_* only)",
            placeholder="https://openrouter.ai/api/v1",
        ),
        FormField(
            "api_key_env",
            "API key env var (custom_* only)",
            placeholder="OPENROUTER_API_KEY",
        ),
        FormField("context_length", "Context length (optional)", placeholder="128000"),
    ]

    def _on_submit(values) -> None:
        if values is None:
            return
        _save_extra_model(values)

    app.push_screen(
        FormScreen("Add a custom model", fields, submit_label="Add"), _on_submit
    )


def _save_extra_model(values: dict) -> None:
    from code_puppy.config import EXTRA_MODELS_FILE
    from code_puppy.messaging import emit_error, emit_success

    key = values["key"].strip()
    name = values["name"].strip()
    mtype = values.get("type") or "custom_openai"
    if not key or not name:
        emit_error("Alias and model id are required.")
        return

    config: dict = {"type": mtype, "name": name}

    url = (values.get("url") or "").strip()
    if mtype in _CUSTOM_TYPES and url:
        env = (values.get("api_key_env") or "").strip()
        config["custom_endpoint"] = {
            "url": url,
            "api_key": f"${env}" if env else "$API_KEY",
        }

    raw_cl = (values.get("context_length") or "").strip()
    if raw_cl:
        try:
            config["context_length"] = int(raw_cl)
        except ValueError:
            emit_error("Context length must be a whole number.")
            return

    path = Path(EXTRA_MODELS_FILE)
    extra: dict = {}
    if path.exists():
        try:
            extra = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            emit_error(f"Error parsing extra_models.json: {exc}")
            return
        if not isinstance(extra, dict):
            emit_error("extra_models.json must be a dictionary.")
            return

    if key in extra:
        emit_error(f"Model '{key}' already exists in extra_models.json.")
        return

    extra[key] = config
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(extra, indent=4, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    emit_success(f"Added model '{key}'. Use /model to select it (new terminals too).")
