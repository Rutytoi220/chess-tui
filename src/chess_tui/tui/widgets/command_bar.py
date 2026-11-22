"""Vim-like command & SAN input bar + live Vimium hint buffer indicator."""

from __future__ import annotations

from rich.style import Style
from rich.text import Text
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, Static

from chess_tui.config.themes import ThemePalette


class CommandBar(Horizontal):
    """Bottom bar displaying active Vimium buffer or accepting `:` / `/` commands."""

    DEFAULT_CSS = """
    CommandBar {
        height: 3;
        dock: bottom;
        padding: 0 1;
        align: left middle;
    }
    CommandBar #status_strip {
        width: 1fr;
        height: 1;
    }
    CommandBar #cmd_input {
        width: 1fr;
        display: none;
        height: 3;
        border: none;
    }
    """

    class CommandSubmitted(Message):
        def __init__(self, prefix: str, text: str) -> None:
            self.prefix = prefix
            self.text = text
            super().__init__()

    class CommandCancelled(Message):
        pass

    def __init__(self, theme: ThemePalette, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.theme = theme
        self._input_prefix: str = ":"
        self._input_active: bool = False
        self._hint_mode: str = "dynamic"
        self._hint_buffer: str = ""
        self._selected_label: str = ""
        self._status_message: str = "Ready"

    def compose(self):
        yield Static(id="status_strip")
        yield Input(id="cmd_input", placeholder="Enter command (e.g. theme dracula, set hints.alphabet ASDF)...")

    def on_mount(self) -> None:
        inp = self.query_one("#cmd_input", Input)
        inp.can_focus = False
        inp.disabled = True
        self._refresh_strip()

    @property
    def input_active(self) -> bool:
        return self._input_active

    def set_theme(self, theme: ThemePalette) -> None:
        self.theme = theme
        self.styles.background = theme.panel_bg
        self._refresh_strip()

    def update_status(
        self,
        *,
        hint_mode: str | None = None,
        hint_buffer: str | None = None,
        selected_label: str | None = None,
        message: str | None = None,
    ) -> None:
        if hint_mode is not None:
            self._hint_mode = hint_mode
        if hint_buffer is not None:
            self._hint_buffer = hint_buffer
        if selected_label is not None:
            self._selected_label = selected_label
        if message is not None:
            self._status_message = message
        self._refresh_strip()

    def _refresh_strip(self) -> None:
        if not self.is_mounted:
            return
        strip = self.query_one("#status_strip", Static)
        t = self.theme
        txt = Text()
        txt.append(f" {self._hint_mode.upper()} ", Style(color=t.hint_fg, bgcolor=t.accent_fg, bold=True))
        txt.append("  ", Style(bgcolor=t.panel_bg))

        if self._selected_label:
            txt.append(f" SELECTED: {self._selected_label} ", Style(color=t.hint_fg, bgcolor=t.selected_bg, bold=True))
            txt.append("  →  ", Style(color=t.muted_fg))

        if self._hint_buffer:
            txt.append("BUFFER: ", Style(color=t.muted_fg))
            txt.append(f" {self._hint_buffer}_ ", Style(color=t.hint_fg, bgcolor=t.hint_bg, bold=True))
            txt.append("  ", Style(bgcolor=t.panel_bg))

        txt.append(self._status_message, Style(color=t.text_fg))
        strip.update(txt)

    def open_input(self, prefix: str = ":") -> None:
        self._input_prefix = prefix
        self._input_active = True
        strip = self.query_one("#status_strip", Static)
        inp = self.query_one("#cmd_input", Input)
        strip.styles.display = "none"
        inp.disabled = False
        inp.can_focus = True
        inp.styles.display = "block"
        inp.value = prefix
        inp.placeholder = (
            ":theme <name> | :set <key> <val> | :account | :fen <fen>"
            if prefix == ":"
            else "/Nf3  /e2e4  /O-O"
        )
        inp.focus()
        inp.cursor_position = len(prefix)

    def close_input(self) -> None:
        self._input_active = False
        strip = self.query_one("#status_strip", Static)
        inp = self.query_one("#cmd_input", Input)
        inp.value = ""
        inp.styles.display = "none"
        inp.can_focus = False
        inp.disabled = True
        strip.styles.display = "block"
        self._refresh_strip()
        self.post_message(self.CommandCancelled())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        prefix = self._input_prefix
        if raw.startswith((":", "/")):
            prefix = raw[0]
            body = raw[1:].strip()
        else:
            body = raw
        self._input_active = False
        strip = self.query_one("#status_strip", Static)
        inp = self.query_one("#cmd_input", Input)
        inp.value = ""
        inp.styles.display = "none"
        inp.can_focus = False
        inp.disabled = True
        strip.styles.display = "block"
        self._refresh_strip()
        if body:
            self.post_message(self.CommandSubmitted(prefix, body))
        else:
            self.post_message(self.CommandCancelled())
