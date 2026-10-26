"""Termflow menus + sentinel constants for the add-model browser.

Split out of :mod:`code_puppy.command_line.add_model_menu` (which imports
these back) to keep that module under the 600-line cap. Owns the provider and
per-provider model lists, the Ctrl+E credentials chord, and the no-tool-call
confirmation, along with the sentinel item values they exchange with the
orchestrator.
"""

from typing import List

from code_puppy.command_line.add_model_details import (
    custom_model_details,
    model_details,
    provider_details,
)
from code_puppy.i18n import t
from code_puppy.models_dev_parser import ModelInfo, ProviderInfo

_CUSTOM_MODEL_VALUE = "__custom_model__"
_EDIT_CREDENTIALS = "__edit_credentials__"
# Sentinel for the vLLM entry appended to the provider list.
_VLLM_PROVIDER_VALUE = "__vllm_provider__"


def _edit_credentials_key(builder):
    """Bind Ctrl+E to exit the menu with an edit-credentials sentinel."""
    from termflow.tui import MenuItem
    from termflow.tui.menu import MenuResult

    def handler(_menu, item):
        return MenuResult(item=MenuItem("", value=(_EDIT_CREDENTIALS, item.value)))

    builder.on_key("ctrl-e", handler)
    return builder


def build_provider_menu(providers: List[ProviderInfo], **overrides):
    """Searchable provider list with a details preview pane."""
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    items = [
        MenuItem(f"{p.name} ({p.model_count})", value=p, description=p.id)
        for p in providers
    ]
    # Self-hosted / OpenAI-compatible server, addressed by URL, not a
    # models.dev provider. Last so it never shadows a real provider.
    items.append(
        MenuItem(t("model_menu.vllm.provider_entry"), _VLLM_PROVIDER_VALUE, "vllm")
    )
    builder = themed(
        MenuBuilder("Add Model - Providers")
        .items(items)
        .searchable()
        .list_width(36)
        .alt_screen(False)
        .preview(lambda item: provider_details(item.value))
        .footer_hint("type filter - Enter open - Ctrl+E credentials - Esc cancel")
    )
    _edit_credentials_key(builder)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def build_models_menu(provider: ProviderInfo, models: List[ModelInfo], **overrides):
    """Searchable model list for one provider, custom-model entry last."""
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    def preview(item):
        if item.value == _CUSTOM_MODEL_VALUE:
            return custom_model_details(provider)
        return model_details(item.value, provider)

    items = [MenuItem(m.name, value=m, description=m.model_id) for m in models]
    items.append(MenuItem("+ Custom model...", value=_CUSTOM_MODEL_VALUE))
    builder = themed(
        MenuBuilder(f"Add Model - {provider.name}")
        .items(items)
        .searchable()
        .list_width(36)
        .alt_screen(False)
        .preview(preview)
        .footer_hint("type filter - Enter add - Ctrl+E credentials - Esc back")
    )
    _edit_credentials_key(builder)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def confirm_no_tool_call(model: ModelInfo, **overrides) -> bool:
    """Explicit opt-in for models without tool calling."""
    from termflow.tui import MenuBuilder, MenuItem

    from code_puppy.command_line.tui_style import themed

    builder = themed(
        MenuBuilder(f"{model.name} has NO tool calling - add anyway?")
        .items(
            [
                MenuItem("No - pick something else", value=False),
                MenuItem("Yes - add it regardless", value=True),
            ]
        )
        .alt_screen(False)
        .footer_hint("Enter confirm - Esc cancel")
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    result = builder.build().run()
    return bool(result.item and result.item.value is True and not result.cancelled)
