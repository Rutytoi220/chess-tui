"""Play mode & Chess.com puzzle / FEN launcher modal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static

from chess_tui.tui.screens.base import VimModalScreen

if TYPE_CHECKING:
    from chess_tui.tui.app import ChessTuiApp


class PlayScreen(VimModalScreen):
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
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        is_connected = bool(
            (tui.cdp_bridge and tui.cdp_bridge.connected) or tui.ws_bridge.client_count > 0
        )
        conn_msg = (
            f"Connected to Chess.com ({tui.active_username or tui.active_account_alias or 'Browser'})"
            if is_connected
            else "No Chess.com browser connected yet — click 'Login to Chess.com' or press Ctrl+A"
        )

        with Container(id="play_dialog"):
            yield Label("PLAY / PUZZLES / MODES", classes="title")
            with Vertical():
                yield Static(conn_msg, id="play_conn_banner")
                if not is_connected:
                    with Horizontal(classes="row"):
                        yield Button("Login / Connect Chess.com [Ctrl+A]", id="btn_open_accounts", variant="warning")

                yield Label("Chess.com Live Matchmaking (Connected Browser)", classes="sec")
                with Horizontal(classes="row"):
                    yield Button("1 min", id="tc_1min")
                    yield Button("3 min", id="tc_3min", variant="success")
                    yield Button("3 | 2", id="tc_3_2")
                    yield Button("5 min", id="tc_5min")
                    yield Button("10 min", id="tc_10min", variant="primary")
                    yield Button("15 | 10", id="tc_15_10")
                with Horizontal(classes="row"):
                    yield Button("Open /play/online", id="btn_cc_online")
                    yield Button("vs Computer", id="btn_cc_bot")
                    yield Button("Web Puzzles", id="btn_cc_puzzles")

                yield Label("Official Chess.com PubAPI Puzzles (Play in TUI)", classes="sec")
                with Horizontal(classes="row"):
                    yield Button("Today's Daily Puzzle", id="btn_daily_puzzle", variant="primary")
                    yield Button("Random Puzzle", id="btn_random_puzzle")

                yield Label("Local & Practice Modes", classes="sec")
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

        if bid == "btn_open_accounts":
            from chess_tui.tui.screens.accounts_screen import AccountsScreen

            self.dismiss(None)
            tui.push_screen(AccountsScreen())
            return

        tc_map = {
            "tc_1min": "1 min",
            "tc_3min": "3 min",
            "tc_3_2": "3 | 2",
            "tc_5min": "5 min",
            "tc_10min": "10 min",
            "tc_15_10": "15 | 10",
        }
        if bid in tc_map:
            status.update(f"Starting {tc_map[bid]} match on Chess.com...")
            ok, msg = await tui.start_chesscom_match(tc_map[bid])
            if ok:
                self.dismiss(None)
            else:
                status.update(msg)
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
