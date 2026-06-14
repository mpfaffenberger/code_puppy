"""Textual modal for the ``ask_user_question`` tool.

Mirrors the classic split-panel prompt_toolkit UI:

    +----------------+--------------------------------------------+
    |  QUESTIONS     |  <current question text>                   |
    |  > Database  v |    (o) PostgreSQL  - Relational DB         |
    |    Caching     |    ( ) MongoDB     - Document store        |
    |    Auth        |    ( ) Other...                            |
    +----------------+--------------------------------------------+

Left panel  (fixed width): the question headers as tabs, with a check mark on
answered ones and a highlight on the current one.
Right panel (flex): the current question + its options (radio for single-select,
checkboxes for multi-select), an optional free-form "Other" entry, and the
description of the focused option.

CRITICAL INVARIANT (shared with ``screens/interactive.py``): the modal MUST
resolve on every exit path so the agent's awaited Future never hangs. Escape
maps to a cancelled result.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from code_puppy.messaging import QuestionRequest
from code_puppy.tools.ask_user_question.constants import (
    AUTO_ADD_OTHER_OPTION,
    OTHER_OPTION_LABEL,
)

# Result type: (answers, cancelled, timed_out)
QuestionResult = Tuple[List[Dict[str, Any]], bool, bool]

_CHECK = "\u2713"  #
_RADIO_ON = "\u25cf"  # ●
_RADIO_OFF = "\u25cb"  # ○
_BOX_ON = "[x]"
_BOX_OFF = "[ ]"


class QuestionModal(ModalScreen[QuestionResult]):
    """Split-panel multi-question picker. Returns (answers, cancelled, timed_out)."""

    CSS = """
    QuestionModal {
        align: center middle;
    }
    #qdialog {
        width: 90%;
        max-width: 120;
        height: 80%;
        max-height: 32;
        border: round $accent;
        background: $panel;
    }
    #qbody { height: 1fr; }
    #headers-panel {
        width: 30;
        border-right: solid $primary;
        background: $boost;
    }
    #headers { width: 1fr; height: 1fr; border: none; background: $boost; }
    #headers-title, #detail-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
        height: 1;
    }
    #detail { width: 1fr; padding: 0 1; }
    #question-text { text-style: bold; margin-bottom: 1; }
    #options { height: auto; max-height: 14; border: none; }
    #desc { color: $text-muted; margin-top: 1; height: auto; }
    #other-input { margin-top: 1; display: none; }
    #other-input.visible { display: block; }
    #qfooter {
        height: auto;
        align-horizontal: right;
        padding: 0 1;
        border-top: solid $primary;
    }
    #qhint { width: 1fr; color: $text-muted; padding-top: 1; }
    Button { margin-left: 1; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Submit"),
        Binding("left", "prev_question", "Prev", show=False),
        Binding("right", "next_question", "Next", show=False),
        Binding("space", "toggle", "Toggle", show=False),
    ]

    def __init__(self, request: QuestionRequest) -> None:
        super().__init__()
        self._questions: List[Dict[str, Any]] = list(request.questions)
        self._current = 0
        # Per-question selection state.
        self._multi_selected: List[Set[int]] = [set() for _ in self._questions]
        self._single_selected: List[Optional[int]] = [None] * len(self._questions)
        self._other_text: List[Optional[str]] = [None] * len(self._questions)

    # ------------------------------------------------------------------ helpers
    def _q(self, index: int) -> Dict[str, Any]:
        return self._questions[index]

    def _options(self, index: int) -> List[Dict[str, Any]]:
        return list(self._q(index).get("options", []))

    def _is_multi(self, index: int) -> bool:
        return bool(self._q(index).get("multi_select", False))

    def _other_index(self, index: int) -> Optional[int]:
        """Index of the synthetic 'Other' option, or None if disabled."""
        if not AUTO_ADD_OTHER_OPTION:
            return None
        return len(self._options(index))

    def _is_answered(self, index: int) -> bool:
        if self._is_multi(index):
            return bool(self._multi_selected[index]) or bool(self._other_text[index])
        return self._single_selected[index] is not None

    def _is_selected(self, qi: int, oi: int) -> bool:
        if self._is_multi(qi):
            return oi in self._multi_selected[qi]
        return self._single_selected[qi] == oi

    # ------------------------------------------------------------------ compose
    def compose(self) -> ComposeResult:
        with Vertical(id="qdialog"):
            with Horizontal(id="qbody"):
                with Vertical(id="headers-panel"):
                    yield Static("QUESTIONS", id="headers-title")
                    yield OptionList(id="headers")
                with VerticalScroll(id="detail"):
                    yield Static("", id="detail-title")
                    yield Static("", id="question-text")
                    yield OptionList(id="options")
                    yield Input(
                        placeholder="Type your custom answer...", id="other-input"
                    )
                    yield Static("", id="desc")
            with Horizontal(id="qfooter"):
                yield Static(
                    "\u2190/\u2192 switch question \u00b7 \u2191/\u2193 move \u00b7 "
                    "space/enter select \u00b7 Ctrl+S submit \u00b7 Esc cancel",
                    id="qhint",
                )
                yield Button("Cancel", id="cancel-btn")
                yield Button("Submit", id="submit-btn", variant="primary")

    def on_mount(self) -> None:
        self._refresh_headers()
        self._refresh_detail()
        self.query_one("#options", OptionList).focus()

    # ------------------------------------------------------------------ rendering
    def _refresh_headers(self) -> None:
        headers = self.query_one("#headers", OptionList)
        headers.clear_options()
        for i, q in enumerate(self._questions):
            mark = _CHECK if self._is_answered(i) else " "
            label = q.get("header", f"Q{i + 1}")
            headers.add_option(Option(Text(f"{mark} {label}"), id=str(i)))
        headers.highlighted = self._current

    def _option_prompt(self, qi: int, oi: int, label: str) -> Text:
        # Return a Text (not a markup str): option labels and our [x]/[ ]
        # markers would otherwise be parsed as Rich markup and eaten (e.g.
        # "[x]" renders as nothing). Text disables that parsing entirely.
        selected = self._is_selected(qi, oi)
        if self._is_multi(qi):
            marker = _BOX_ON if selected else _BOX_OFF
        else:
            marker = _RADIO_ON if selected else _RADIO_OFF
        return Text(f"{marker} {label}")

    def _refresh_detail(self) -> None:
        qi = self._current
        q = self._q(qi)
        total = len(self._questions)
        self.query_one("#detail-title", Static).update(
            f"Question {qi + 1}/{total}  \u00b7  {q.get('header', '')}"
            + ("  (multi-select)" if self._is_multi(qi) else "")
        )
        self.query_one("#question-text", Static).update(q.get("question", ""))

        options = self.query_one("#options", OptionList)
        options.clear_options()
        for oi, opt in enumerate(self._options(qi)):
            options.add_option(
                Option(self._option_prompt(qi, oi, opt.get("label", "")), id=str(oi))
            )
        other_idx = self._other_index(qi)
        if other_idx is not None:
            other_label = OTHER_OPTION_LABEL
            if self._other_text[qi]:
                other_label = f"{OTHER_OPTION_LABEL}: {self._other_text[qi]}"
            options.add_option(
                Option(
                    self._option_prompt(qi, other_idx, other_label), id=str(other_idx)
                )
            )
        options.highlighted = 0

        # Reset the Other input visibility for the new question.
        other_input = self.query_one("#other-input", Input)
        other_input.remove_class("visible")
        other_input.value = self._other_text[qi] or ""
        self._update_description()

    def _update_description(self) -> None:
        qi = self._current
        options = self.query_one("#options", OptionList)
        desc_widget = self.query_one("#desc", Static)
        hi = options.highlighted
        opts = self._options(qi)
        if hi is None:
            desc_widget.update("")
            return
        if hi < len(opts):
            desc_widget.update(opts[hi].get("description", ""))
        else:
            desc_widget.update("Pick this to enter a custom answer.")

    # ------------------------------------------------------------------ events
    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option_list.id == "options":
            self._update_description()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "headers":
            self._current = int(event.option.id)
            self._refresh_detail()
            self.query_one("#options", OptionList).focus()
            return
        # An option in the current question was activated (Enter / click).
        self._activate_option(int(event.option.id))

    def _activate_option(self, oi: int) -> None:
        qi = self._current
        other_idx = self._other_index(qi)

        if other_idx is not None and oi == other_idx:
            # Reveal the free-form input and focus it.
            other_input = self.query_one("#other-input", Input)
            other_input.add_class("visible")
            other_input.focus()
            return

        if self._is_multi(qi):
            self._toggle(qi, oi)
        else:
            self._single_selected[qi] = oi
        self._refresh_after_change()

    def _toggle(self, qi: int, oi: int) -> None:
        sel = self._multi_selected[qi]
        if oi in sel:
            sel.discard(oi)
        else:
            sel.add(oi)

    def action_toggle(self) -> None:
        options = self.query_one("#options", OptionList)
        if options.highlighted is None:
            return
        self._activate_option(options.highlighted)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        qi = self._current
        other_idx = self._other_index(qi)
        text = event.value.strip()
        if text:
            self._other_text[qi] = text
            if other_idx is not None:
                if self._is_multi(qi):
                    self._multi_selected[qi].add(other_idx)
                else:
                    self._single_selected[qi] = other_idx
        else:
            # Empty submit clears the Other selection.
            self._other_text[qi] = None
            if other_idx is not None:
                self._multi_selected[qi].discard(other_idx)
                if self._single_selected[qi] == other_idx:
                    self._single_selected[qi] = None
        self.query_one("#other-input", Input).remove_class("visible")
        self._refresh_after_change()
        self.query_one("#options", OptionList).focus()

    def _refresh_after_change(self) -> None:
        # Preserve the user's place in the option list across a rebuild.
        options = self.query_one("#options", OptionList)
        keep = options.highlighted
        self._refresh_detail()
        self._refresh_headers()
        if keep is not None and keep < options.option_count:
            options.highlighted = keep

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit-btn":
            self.action_submit()
        else:
            self.action_cancel()

    # ------------------------------------------------------------------ actions
    def action_prev_question(self) -> None:
        if self._current > 0:
            self._current -= 1
            self._refresh_detail()

    def action_next_question(self) -> None:
        if self._current < len(self._questions) - 1:
            self._current += 1
            self._refresh_detail()

    def action_cancel(self) -> None:
        self.dismiss(([], True, False))

    def action_submit(self) -> None:
        self.dismiss((self._build_answers(), False, False))

    # ------------------------------------------------------------------ result
    def _build_answers(self) -> List[Dict[str, Any]]:
        answers: List[Dict[str, Any]] = []
        for qi, q in enumerate(self._questions):
            opts = self._options(qi)
            other_idx = self._other_index(qi)
            labels: List[str] = []
            other_text: Optional[str] = None

            if self._is_multi(qi):
                indices = sorted(self._multi_selected[qi])
            else:
                sel = self._single_selected[qi]
                indices = [sel] if sel is not None else []

            for oi in indices:
                if other_idx is not None and oi == other_idx:
                    labels.append(OTHER_OPTION_LABEL)
                    other_text = self._other_text[qi]
                elif oi < len(opts):
                    labels.append(opts[oi].get("label", ""))

            answers.append(
                {
                    "question_header": q.get("header", ""),
                    "selected_options": labels,
                    "other_text": other_text,
                }
            )
        return answers
