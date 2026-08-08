"""Interactive split-panel model picker for /model (theme-style).

Left pane: paginated, filterable model list. Right pane: live preview of the
highlighted model (provider, context window, description, credential status,
pinned agents). Modeled after ``code_puppy/plugins/theme/picker.py`` so the
two commands share the same look and feel.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import textwrap
from typing import Optional

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.callbacks import on_prompt_toolkit_style
from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)
from code_puppy.list_filtering import query_matches_text
from code_puppy.model_descriptions import get_model_description
from code_puppy.provider_credentials import (
    credential_display,
    credential_hint,
    is_credential_set,
    required_env_var_for_model,
    save_credential,
)

logger = logging.getLogger(__name__)

MODEL_PAGE_SIZE = 10
_PREVIEW_WRAP_WIDTH = 68

# Friendly labels for common model ``type`` values (best-effort).
_PROVIDER_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "ollama": "Ollama",
    "openrouter": "OpenRouter",
    "azure_openai": "Azure OpenAI",
    "azure_anthropic": "Azure Anthropic",
    "custom_openai": "Custom OpenAI",
    "custom_openai_responses": "Custom OpenAI (Responses)",
    "custom_anthropic": "Custom Anthropic",
    "claude_code_oauth": "Claude Code OAuth",
    "chatgpt_oauth": "ChatGPT OAuth",
    "copilot": "GitHub Copilot",
    "round_robin": "Round-robin",
}


def _load_models() -> dict:
    """Load the merged model catalog (builtin + extra + OAuth sources)."""
    try:
        from code_puppy.model_factory import ModelFactory

        config = ModelFactory.load_config()
        if isinstance(config, dict):
            return config
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load model config: %s", exc)
    return {}


def _get_current_model() -> Optional[str]:
    try:
        from code_puppy.config import get_global_model_name

        return get_global_model_name()
    except Exception:  # pragma: no cover - defensive
        return None


def _provider_label(model_config: dict) -> str:
    provider = model_config.get("provider")
    if isinstance(provider, str) and provider:
        return provider
    type_ = model_config.get("type")
    if isinstance(type_, str) and type_:
        return _PROVIDER_LABELS.get(type_, type_)
    return "unknown"


def _context_label(model_config: dict) -> str:
    context = model_config.get("context_length")
    if isinstance(context, (int, float)) and context:
        if context >= 1_000_000:
            return f"{context / 1_000_000:.1f}M tokens"
        return f"{int(context):,} tokens"
    return ""


class ModelSwitcherMenu:
    """Paginated, filterable split-panel model picker."""

    def __init__(self, models_config: Optional[dict] = None):
        self.models_config = (
            models_config if models_config is not None else _load_models()
        )
        self.model_names = list(self.models_config.keys())
        self.current_model = _get_current_model()
        self.filter_text = ""
        self.selected_index = 0
        self.page = 0
        self.page_size = MODEL_PAGE_SIZE
        self.result: Optional[str] = None
        self.pending_credentials_edit: Optional[str] = None

        if self.current_model in self.visible_model_names:
            self.selected_index = self.visible_model_names.index(self.current_model)
            self.page = get_page_for_index(self.selected_index, self.page_size)

    # --- list state --------------------------------------------------------

    @property
    def total_pages(self) -> int:
        return get_total_pages(len(self.visible_model_names), self.page_size)

    @property
    def page_start(self) -> int:
        return get_page_bounds(
            self.page, len(self.visible_model_names), self.page_size
        )[0]

    @property
    def page_end(self) -> int:
        return get_page_bounds(
            self.page, len(self.visible_model_names), self.page_size
        )[1]

    @property
    def models_on_page(self) -> list[str]:
        return self.visible_model_names[self.page_start : self.page_end]

    @property
    def visible_model_names(self) -> list[str]:
        if not self.filter_text:
            return self.model_names
        return [
            name
            for name in self.model_names
            if query_matches_text(self.filter_text, name)
        ]

    def _get_selected_model_name(self) -> Optional[str]:
        if 0 <= self.selected_index < len(self.visible_model_names):
            return self.visible_model_names[self.selected_index]
        return None

    def _ensure_selection_visible(self) -> None:
        self.page = ensure_visible_page(
            self.selected_index,
            self.page,
            len(self.visible_model_names),
            self.page_size,
        )

    def _set_filter_text(self, value: str) -> None:
        selected = self._get_selected_model_name()
        self.filter_text = value
        visible = self.visible_model_names
        if not visible:
            self.selected_index = 0
            self.page = 0
            return
        if selected in visible:
            self.selected_index = visible.index(selected)
        elif self.current_model in visible:
            self.selected_index = visible.index(self.current_model)
        else:
            self.selected_index = 0
        self._ensure_selection_visible()

    def _append_filter_char(self, value: str) -> None:
        self._set_filter_text(self.filter_text + value)

    def _move_up(self) -> None:
        if self.selected_index > 0:
            self.selected_index -= 1
            self._ensure_selection_visible()

    def _move_down(self) -> None:
        if self.selected_index < len(self.visible_model_names) - 1:
            self.selected_index += 1
            self._ensure_selection_visible()

    def _page_up(self) -> None:
        if self.page > 0:
            self.page -= 1
            self.selected_index = self.page_start

    def _page_down(self) -> None:
        if self.page < self.total_pages - 1:
            self.page += 1
            self.selected_index = self.page_start

    def _accept_selection(self) -> bool:
        model = self._get_selected_model_name()
        if model is None:
            return False
        self.result = model
        return True

    # --- rendering ---------------------------------------------------------

    def _render_menu(self) -> FormattedText:
        lines: list[tuple[str, str]] = [
            ("class:tui.header", " Select Active Model"),
            ("class:tui.muted", f"  Page {self.page + 1}/{self.total_pages}"),
            ("", "\n\n"),
        ]
        if self.current_model:
            lines.append(("class:tui.muted", f"  current: {self.current_model}"))
            lines.append(("", "\n\n"))
        filter_label = self.filter_text or "type to filter"
        lines.append(("class:tui.muted", f"  filter: {filter_label}"))
        lines.append(("", "\n\n"))

        if not self.visible_model_names:
            lines.append(("class:tui.warning", "  No models match the filter."))
            lines.append(("", "\n"))
        else:
            for offset, model_name in enumerate(self.models_on_page):
                absolute_index = self.page_start + offset
                is_selected = absolute_index == self.selected_index
                is_current = model_name == self.current_model
                prefix = "› " if is_selected else "  "
                style = "class:tui.selected" if is_selected else "class:tui.body"
                marker = " ●" if is_current else ""
                lines.append((style, f"{prefix}{model_name}{marker}"))
                lines.append(("", "\n"))
                lines.append(
                    (
                        "class:tui.muted",
                        f"     {_provider_label(self.models_config.get(model_name, {}))}",
                    )
                )
                lines.append(("", "\n\n"))

        lines.append(("", "\n"))
        lines.append(("class:tui.help-key", "↑/↓"))
        lines.append(("class:tui.help", " Navigate  |  "))
        lines.append(("class:tui.help-key", "PgUp/PgDn"))
        lines.append(("class:tui.help", " Page\n"))
        lines.append(("class:tui.help-key", "Type"))
        lines.append(("class:tui.help", " Filter  |  "))
        lines.append(("class:tui.help-key", "Enter"))
        lines.append(("class:tui.help", " Apply  |  "))
        lines.append(("class:tui.help-key", "Esc"))
        lines.append(("class:tui.help", " Cancel"))
        return FormattedText(lines)

    def _render_preview(self) -> FormattedText:
        model_name = self._get_selected_model_name()
        lines: list[tuple[str, str]] = []
        if model_name is None:
            lines.append(("class:tui.warning", "  No model selected."))
            return FormattedText(lines)

        cfg = self.models_config.get(model_name, {})
        is_current = model_name == self.current_model

        title = f" {model_name}"
        if is_current:
            title += "  (active)"
        lines.append(("class:tui.title", title))
        lines.append(("", "\n"))

        lines.append(("class:tui.label", "  Provider"))
        lines.append(("", "\n"))
        lines.append(("class:tui.body", f"    {_provider_label(cfg)}"))
        lines.append(("", "\n\n"))

        context = _context_label(cfg)
        if context:
            lines.append(("class:tui.label", "  Context window"))
            lines.append(("", "\n"))
            lines.append(("class:tui.body", f"    {context}"))
            lines.append(("", "\n\n"))

        description = get_model_description(self.models_config, model_name)
        if description and description != "No description available.":
            lines.append(("class:tui.label", "  Description"))
            lines.append(("", "\n"))
            for wrapped in textwrap.wrap(description, width=_PREVIEW_WRAP_WIDTH):
                lines.append(("class:tui.body", f"    {wrapped}"))
                lines.append(("", "\n"))
            lines.append(("", "\n"))

        env_var = required_env_var_for_model(model_name)
        lines.append(("class:tui.label", "  Credentials"))
        lines.append(("", "\n"))
        if env_var:
            status = credential_display(env_var)
            hint = credential_hint(env_var)
            color = (
                "class:tui.success"
                if is_credential_set(env_var)
                else "class:tui.warning"
            )
            lines.append((color, f"    {env_var}: {status}"))
            lines.append(("", "\n"))
            if hint:
                lines.append(("class:tui.muted", f"    {hint}"))
                lines.append(("", "\n"))
            lines.append(("class:tui.help", "    (Ctrl+E to edit)"))
            lines.append(("", "\n\n"))
        else:
            lines.append(("class:tui.success", "    keyless / OAuth"))
            lines.append(("", "\n\n"))

        pinned = _pinned_agents_for(model_name)
        lines.append(("class:tui.label", "  Pinned to agents"))
        lines.append(("", "\n"))
        if pinned:
            lines.append(("class:tui.body", f"    {', '.join(pinned)}"))
        else:
            lines.append(("class:tui.muted", "    none"))
        lines.append(("", "\n\n"))

        lines.append(("", "\n"))
        lines.append(("class:tui.help-key", "Enter"))
        lines.append(("class:tui.help", " Apply  |  "))
        lines.append(("class:tui.help-key", "Ctrl+E"))
        lines.append(("class:tui.help", " Edit credentials  |  "))
        lines.append(("class:tui.help-key", "Esc"))
        lines.append(("class:tui.help", " Cancel"))
        return FormattedText(lines)

    # --- interactions ------------------------------------------------------

    def _edit_credentials_for_model(self, model_name: str) -> None:
        env_var = required_env_var_for_model(model_name)
        if not env_var:
            return
        status = credential_display(env_var)
        hint = credential_hint(env_var)
        print(f"\n🔑 {model_name} credential: {env_var} ({status})")
        if hint:
            print(f"   {hint}")
        try:
            from code_puppy.command_line.utils import safe_input

            value = safe_input("   New value (or Enter to skip): ")
            if value:
                save_credential(env_var, value)
                print(f"✅ Saved {env_var}")
        except (KeyboardInterrupt, EOFError):  # pragma: no cover - interactive
            print("\n⚠️ Credential editing cancelled")

    async def run_async(self) -> Optional[str]:
        from code_puppy.tools.command_runner import set_awaiting_user_input

        set_awaiting_user_input(True, notify=False)
        try:
            left = Window(
                content=FormattedTextControl(lambda: self._render_menu()),
                width=46,
            )
            right = Window(
                content=FormattedTextControl(lambda: self._render_preview()),
                wrap_lines=True,
            )
            kb = KeyBindings()

            @kb.add("up")
            @kb.add("c-p")
            def _(event):
                self._move_up()
                event.app.invalidate()

            @kb.add("down")
            @kb.add("c-n")
            def _(event):
                self._move_down()
                event.app.invalidate()

            @kb.add("pageup")
            @kb.add("left")
            def _(event):
                self._page_up()
                event.app.invalidate()

            @kb.add("pagedown")
            @kb.add("right")
            def _(event):
                self._page_down()
                event.app.invalidate()

            @kb.add("backspace")
            def _(event):
                if not self.filter_text:
                    return
                self._set_filter_text(self.filter_text[:-1])
                event.app.invalidate()

            @kb.add("c-u")
            def _(event):
                if not self.filter_text:
                    return
                self._set_filter_text("")
                event.app.invalidate()

            @kb.add("c-e")
            def _(event):
                selected = self._get_selected_model_name()
                if not selected or not required_env_var_for_model(selected):
                    return
                self.pending_credentials_edit = selected
                event.app.exit()

            @kb.add("<any>")
            def _(event):
                if not event.data or not event.data.isprintable():
                    return
                self._append_filter_char(event.data)
                event.app.invalidate()

            @kb.add("enter")
            def _(event):
                if self._accept_selection():
                    event.app.exit()

            @kb.add("escape")
            @kb.add("c-c")
            def _(event):
                self.result = None
                event.app.exit()

            # Build the Application ONCE and reuse it across the credential-edit
            # loop (mirrors theme/picker.py). A fresh prompt_toolkit Application
            # + Renderer re-runs the cursor-position-request (CPR) probe and
            # re-enters its own render loop every iteration; interleaving that
            # with the manual alt-screen writes right where the key listener
            # hands stdin back can eat the CPR reply on Terminal.app ->
            # "your terminal doesn't support CPR" + a flaky second invocation.
            layout = Layout(
                VSplit([Frame(left, title="Models"), Frame(right, title="Preview")])
            )
            app = Application(
                layout=layout,
                key_bindings=kb,
                full_screen=False,
                mouse_support=False,
                color_depth="DEPTH_24_BIT",
                style=on_prompt_toolkit_style(),
            )

            while True:
                sys.stdout.write("\033[?1049h\033[2J\033[H")
                sys.stdout.flush()
                # Settle before the Application's CPR probe, like the theme
                # picker (which repeats reliably) -- see picker.py:260.
                await asyncio.sleep(0.05)
                await app.run_async()
                sys.stdout.write("\033[?1049l")
                sys.stdout.flush()

                if self.pending_credentials_edit:
                    model_name = self.pending_credentials_edit
                    self.pending_credentials_edit = None
                    self._edit_credentials_for_model(model_name)
                    continue

                return self.result
        finally:
            set_awaiting_user_input(False, notify=False)


def _pinned_agents_for(model_name: str) -> list:
    try:
        from code_puppy.config import get_agents_pinned_to_model

        pinned = get_agents_pinned_to_model(model_name)
        return [str(agent) for agent in pinned]
    except Exception:  # pragma: no cover - defensive
        return []


async def interactive_model_picker(
    models_config: Optional[dict] = None,
) -> Optional[str]:
    """Run the theme-style split-panel model picker."""
    return await ModelSwitcherMenu(models_config).run_async()
