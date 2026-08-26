"""Detail-pane renderers for the add-model browser.

Plain ANSI strings over the active theme palette; consumed as termflow
Menu previews by :mod:`code_puppy.command_line.add_model_menu` (split
out of that module purely for the 600-line cap).
"""

from code_puppy.models_dev_parser import ModelInfo, ProviderInfo
from code_puppy.provider_credentials import (
    credential_display,
    credential_hint,
    is_credential_set,
)


def _unsupported() -> dict:
    # Lazy import: add_model_menu imports this module at load time.
    from code_puppy.command_line.add_model_menu import UNSUPPORTED_PROVIDERS

    return UNSUPPORTED_PROVIDERS


def _style():
    from termflow.render.style import RenderStyle

    from code_puppy.command_line.tui_style import menu_style

    return menu_style() or RenderStyle.default()


def _ansi(color: str, text: str) -> str:
    from termflow.ansi.codes import RESET
    from termflow.ansi.color import fg_color

    return f"{fg_color(color)}{text}{RESET}"


def provider_details(provider: ProviderInfo) -> str:
    s = _style()
    lines = [
        _ansi(s.bright, "MODEL DETAILS"),
        "",
        _ansi(s.head, f"{provider.name}"),
        f"ID: {provider.id}",
        f"Models: {provider.model_count}",
        f"API: {provider.api}",
    ]
    if provider.id in _unsupported():
        lines += [
            "",
            _ansi(s.error, "UNSUPPORTED PROVIDER"),
            _ansi(s.error, _unsupported()[provider.id]),
            _ansi(s.grey, "Models from this provider cannot be added."),
        ]
    if provider.env:
        lines += ["", _ansi(s.head, "Credentials:")]
        for env_var in provider.env:
            color = s.head if is_credential_set(env_var) else s.error
            lines.append(_ansi(color, f"  {env_var}: {credential_display(env_var)}"))
            hint = credential_hint(env_var)
            if hint:
                lines.append(_ansi(s.grey, f"    {hint}"))
    if provider.doc:
        lines += ["", _ansi(s.head, "Documentation:"), f"  {provider.doc}"]
    return "\n".join(lines)


def custom_model_details(provider: ProviderInfo) -> str:
    s = _style()
    lines = [
        _ansi(s.bright, "MODEL DETAILS"),
        "",
        _ansi(s.head, "Custom Model"),
        "Add a model not listed in models.dev",
        "",
        _ansi(s.grey, "1. Press Enter to select"),
        _ansi(s.grey, "2. Enter the model ID/name"),
        _ansi(s.grey, f"3. Uses {provider.name}'s API endpoint"),
    ]
    if provider.env:
        lines += ["", _ansi(s.head, "Required credentials:")]
        lines += [_ansi(s.grey, f"  {env_var}") for env_var in provider.env]
    return "\n".join(lines)


def model_details(model: ModelInfo, provider: ProviderInfo) -> str:
    s = _style()
    lines = [
        _ansi(s.bright, "MODEL DETAILS"),
        "",
        _ansi(s.head, f"{provider.name} - {model.name}"),
    ]
    if not model.tool_call:
        lines += [
            "",
            _ansi(s.error, "NO TOOL CALLING SUPPORT"),
            _ansi(s.error, "This model cannot use tools (file ops, shell"),
            _ansi(s.error, "commands, etc). Very limited for coding tasks!"),
        ]
    lines += ["", _ansi(s.head, "Capabilities:")]
    for cap_name, has_cap in (
        ("Vision", model.has_vision),
        ("Tool Calling", model.tool_call),
        ("Reasoning", model.reasoning),
        ("Temperature", model.temperature),
        ("Structured Output", model.structured_output),
        ("Attachments", model.attachment),
    ):
        mark = "+" if has_cap else "-"
        lines.append(_ansi(s.head if has_cap else s.grey, f"  {mark} {cap_name}"))
    lines += ["", _ansi(s.head, "Pricing:")]
    if model.cost_input is not None or model.cost_output is not None:
        if model.cost_input is not None:
            lines.append(_ansi(s.grey, f"  Input: ${model.cost_input:.6f}/token"))
        if model.cost_output is not None:
            lines.append(_ansi(s.grey, f"  Output: ${model.cost_output:.6f}/token"))
        if model.cost_cache_read is not None:
            lines.append(
                _ansi(s.grey, f"  Cache Read: ${model.cost_cache_read:.6f}/token")
            )
    else:
        lines.append(_ansi(s.grey, "  Pricing not available"))
    lines += ["", _ansi(s.head, "Limits:")]
    if model.context_length > 0:
        lines.append(_ansi(s.grey, f"  Context: {model.context_length:,} tokens"))
    if model.max_output > 0:
        lines.append(_ansi(s.grey, f"  Max Output: {model.max_output:,} tokens"))
    if model.input_modalities or model.output_modalities:
        lines += ["", _ansi(s.head, "Modalities:")]
        if model.input_modalities:
            lines.append(_ansi(s.grey, f"  Input: {', '.join(model.input_modalities)}"))
        if model.output_modalities:
            lines.append(
                _ansi(s.grey, f"  Output: {', '.join(model.output_modalities)}")
            )
    lines += ["", _ansi(s.head, "Metadata:")]
    lines.append(_ansi(s.grey, f"  Model ID: {model.model_id}"))
    lines.append(_ansi(s.grey, f"  Full ID: {model.full_id}"))
    if model.knowledge:
        lines.append(_ansi(s.grey, f"  Knowledge: {model.knowledge}"))
    if model.release_date:
        lines.append(_ansi(s.grey, f"  Released: {model.release_date}"))
    lines.append(_ansi(s.grey, f"  Open Weights: {model.open_weights}"))
    return "\n".join(lines)
