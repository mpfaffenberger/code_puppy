"""Phase 3 Wave C: /judges CRUD as Textual screens.

list -> add/edit (FormScreen) / delete (ConfirmModal). Reuses the kits;
persists through the wiggum judge_config helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .screens.base import FilterableListScreen, ListChoice
from .screens.form import FormField, FormScreen
from .screens.interactive import ConfirmModal

if TYPE_CHECKING:
    from .app import CooperApp

_ADD_ID = "__add_judge__"


def open_judges(app: "CooperApp") -> None:
    from code_puppy.plugins.wiggum.judge_config import load_judges

    registry = load_judges()
    choices = [ListChoice(id=_ADD_ID, label="+ Add a judge...", search="add new")]
    for judge in registry.judges:
        suffix = "" if judge.enabled else "   [disabled]"
        choices.append(
            ListChoice(
                id=judge.name,
                label=f"{judge.name}   ({judge.model}){suffix}",
                search=f"{judge.name} {judge.model}",
            )
        )

    def _on_pick(picked) -> None:
        if not picked:
            return
        if picked == _ADD_ID:
            _open_judge_form(app, None)
        else:
            _open_judge_actions(app, picked)

    app.push_screen(FilterableListScreen("Judges", choices), _on_pick)


def _open_judge_actions(app: "CooperApp", name: str) -> None:
    choices = [
        ListChoice(id="edit", label=f"Edit '{name}'"),
        ListChoice(id="delete", label=f"Delete '{name}'"),
    ]

    def _on_action(action) -> None:
        if action == "edit":
            _open_judge_form(app, name)
        elif action == "delete":
            _confirm_delete(app, name)

    app.push_screen(FilterableListScreen(f"Judge: {name}", choices), _on_action)


def _open_judge_form(app: "CooperApp", name: Optional[str]) -> None:
    from code_puppy.command_line.model_picker_completion import load_model_names
    from code_puppy.plugins.wiggum.judge_config import (
        DEFAULT_JUDGE_PROMPT,
        load_judges,
    )

    existing = load_judges().find(name) if name else None
    models = sorted(load_model_names())
    default_model = existing.model if existing else (models[0] if models else "")
    fields = [
        FormField(
            "name", "Name", default=(existing.name if existing else ""), required=True
        ),
        FormField(
            "model", "Model", kind="select", options=models, default=default_model
        ),
        FormField(
            "prompt",
            "Judge prompt",
            kind="textarea",
            default=(existing.prompt if existing else DEFAULT_JUDGE_PROMPT),
        ),
        FormField(
            "enabled",
            "Enabled",
            kind="bool",
            default=(existing.enabled if existing else True),
        ),
    ]

    def _on_submit(values) -> None:
        if values is None:
            return
        _save_judge(old_name=name, values=values)

    title = f"Edit judge '{name}'" if name else "Add a judge"
    app.push_screen(FormScreen(title, fields, submit_label="Save"), _on_submit)


def _save_judge(old_name: Optional[str], values: dict) -> None:
    from code_puppy.messaging import emit_error, emit_success
    from code_puppy.plugins.wiggum.judge_config import (
        DEFAULT_JUDGE_PROMPT,
        JudgeConfig,
        load_judges,
        save_judges,
        validate_name,
    )

    name = values["name"].strip()
    err = validate_name(name)
    if err:
        emit_error(err)
        return
    model = (values.get("model") or "").strip()
    if not model:
        emit_error("A model is required for a judge.")
        return

    new_judge = JudgeConfig(
        name=name,
        model=model,
        prompt=values.get("prompt") or DEFAULT_JUDGE_PROMPT,
        enabled=bool(values.get("enabled", True)),
    )

    registry = load_judges()
    # Drop the old entry (handles rename) then guard against name collisions.
    registry.judges = [j for j in registry.judges if j.name != old_name]
    if any(j.name == name for j in registry.judges):
        emit_error(f"A judge named '{name}' already exists.")
        return
    registry.judges.append(new_judge)
    save_judges(registry)
    emit_success(f"Saved judge '{name}'.")


def _confirm_delete(app: "CooperApp", name: str) -> None:
    from code_puppy.messaging import ConfirmationRequest, emit_success, emit_warning
    from code_puppy.plugins.wiggum.judge_config import delete_judge

    request = ConfirmationRequest(
        prompt_id="__judge_delete__",
        title=f"Delete judge '{name}'?",
        description="This cannot be undone.",
        options=["Delete", "Cancel"],
    )

    def _on_confirm(result) -> None:
        confirmed = result[0] if result else False
        if not confirmed:
            return
        if delete_judge(name):
            emit_success(f"Deleted judge '{name}'.")
        else:
            emit_warning(f"Judge '{name}' not found.")

    app.push_screen(ConfirmModal(request), _on_confirm)
