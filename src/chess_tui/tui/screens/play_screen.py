"""Play mode & Chess.com puzzle / FEN launcher modal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

if TYPE_CHECKING:
    from chess_tui.tui.app import ChessTuiApp


class PlayScreen(ModalScreen[None]):
    """Choose Chess.com live play, Daily Puzzle, local 2-player, UCI bot, or custom FEN."""

    DEFAULT_CSS = """
    PlayScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.72);
    }
    PlayScreen #play_dialog {
        width: 74;
        height: auto;
        max-height: 34;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    PlayScreen .title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    PlayScreen .sec {
        color: $text-muted;
        margin-top: 1;
        margin-bottom: 0;
    }
    PlayScreen .row {
        height: auto;
        margin-top: 1;
    }
    PlayScreen Button {
        margin-right: 1;
    }
    PlayScreen Input {
        width: 1fr;
        margin-right: 1;
    }
    PlayScreen #play_status {
        margin-top: 1;
        color: $warning;
    }
    """

    BINDINGS = [("escape", "dismiss_modal", "Close")]

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        with Container(id="play_dialog"):
            yield Label("PLAY / PUZZLES / MODES", classes="title")
            with Vertical():
                yield Label("Chess.com Connected Browser", classes="sec")
                with Horizontal(classes="row"):
                    yield Button("Play Online", id="btn_cc_online", variant="success")
                    yield Button("vs Computer", id="btn_cc_bot")
                    yield Button("Web Puzzles", id="btn_cc_puzzles")

                yield Label("Official Chess.com PubAPI Puzzles (Play in TUI)", classes="sec")
                with Horizontal(classes="row"):
                    yield Button("Today's Daily Puzzle", id="btn_daily_puzzle", variant="primary")
                    yield Button("Random Puzzle", id="btn_random_puzzle")

                yield Label("Offline & Practice Modes", classes="sec")
                with Horizontal(classes="row"):
                    yield Button("Local 2-Player", id="btn_local_2p")
                    yield Button("vs Local UCI Engine", id="btn_local_uci")

                yield Label("Load Custom FEN Position", classes="sec")
                with Horizontal(classes="row"):
                    yield Input(id="fen_input", placeholder="Paste FEN string...")
                    yield Button("Load FEN", id="btn_load_fen")

                yield Static("", id="play_status")
                with Horizontal(classes="row"):
                    yield Button("Close [Esc]", id="btn_close")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        bid = event.button.id
        status = self.query_one("#play_status", Static)

        if bid == "btn_close":
            self.dismiss(None)
            return

        if bid == "btn_cc_online":
            ok = await tui.navigate_chesscom("https://www.chess.com/play/online")
            if ok:
                self.dismiss(None)
            else:
                status.update("Connect a Chess.com account first (Ctrl+A).")
            return

        if bid == "btn_cc_bot":
            ok = await tui.navigate_chesscom("https://www.chess.com/play/computer")
            if ok:
                self.dismiss(None)
            else:
                status.update("Connect a Chess.com account first (Ctrl+A).")
            return

        if bid == "btn_cc_puzzles":
            ok = await tui.navigate_chesscom("https://www.chess.com/puzzles")
            if ok:
                self.dismiss(None)
            else:
                status.update("Connect a Chess.com account first (Ctrl+A).")
            return

        if bid in ("btn_daily_puzzle", "btn_random_puzzle"):
            status.update("Fetching puzzle from Chess.com PubAPI...")
            ok, msg = await tui.start_daily_puzzle(random=(bid == "btn_random_puzzle"))
            if ok:
                self.dismiss(None)
            else:
                status.update(msg)
            return

        if bid == "btn_local_2p":
            tui.start_local_2p()
            self.dismiss(None)
            return

        if bid == "btn_local_uci":
            ok, msg = await tui.start_local_uci()
            if ok:
                self.dismiss(None)
            else:
                status.update(msg)
            return

        if bid == "btn_load_fen":
            fen = self.query_one("#fen_input", Input).value.strip()
            ok, msg = tui.load_fen(fen)
            if ok:
                self.dismiss(None)
            else:
                status.update(msg)
